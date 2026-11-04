# This file is part of phomemo.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with phomemo.  If not, see <https://www.gnu.org/licenses/>.

"""Bridge daemon: socket server, shared printer link, idle timer."""

import asyncio
import contextlib
import logging
import signal
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from bleak.backends.device import BLEDevice

from phomemo.discovery import discover
from phomemo.printer import Printer
from phomemo.registry import PrinterProfile, get_profile

logger = logging.getLogger(__name__)

PrinterFactory = Callable[[PrinterProfile, "str | BLEDevice | None"], Printer]

__all__ = ["BridgeConfig", "Bridge", "serve", "start_server"]


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    """Operational settings of the bridge.

    Geometry overrides default to the profile's values when ``None``.

    Attributes:
        socket_path: Unix socket the bridge listens on.
        profile: Printer profile name.
        idle_disconnect_minutes: Minutes without a command after which the
            bridge drops the BLE link (it ends earlier when the printer
            switches off or leaves range); 0 keeps it until then.
        auto_off_minutes: Auto-off timer the bridge sets on the printer at
            each new link (multiple of 5, 0 = never switch off); ``None``
            leaves the printer's setting alone.
        settle_seconds: Cap on the wait for the sheet to seat after insertion.
        completion_timeout: Seconds to wait for the motor stop after a page.
        drain_seconds: Pause after a cancelled transfer so the printer
            finishes the data it already accepted before the eject.
        band_height: Rows per ``GS v 0`` band.
        top_margin_mm: Unprintable lead of the sheet.
        bottom_margin_mm: Rows kept free at the sheet end.
        dpi: Print resolution.
        print_width_px: Head width in dots.
    """

    socket_path: Path
    profile: str = "m08f"
    idle_disconnect_minutes: float = 30.0
    auto_off_minutes: int | None = None
    settle_seconds: float = 3.0
    completion_timeout: float = 300.0
    drain_seconds: float = 1.0
    band_height: int | None = None
    top_margin_mm: float | None = None
    bottom_margin_mm: float | None = None
    dpi: int | None = None
    print_width_px: int | None = None

    def resolved_profile(self) -> PrinterProfile:
        """The printer profile with the config's geometry overrides applied."""
        base = get_profile(self.profile)
        overrides = {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name in _PROFILE_FIELDS and getattr(self, f.name) is not None
        }
        return replace(base, **overrides) if overrides else base


_PROFILE_FIELDS = frozenset(
    {"band_height", "top_margin_mm", "bottom_margin_mm", "dpi", "print_width_px"}
)


class Bridge:
    """State shared by all client sessions: the printer link and its idle timer."""

    def __init__(self, config: BridgeConfig, printer_factory: PrinterFactory) -> None:
        self.config = config
        self.profile = config.resolved_profile()
        self._factory = printer_factory
        self._address: str | None = None  # last printer used, kept in memory
        self.printer: Printer | None = None
        self.session_active = False
        self._seen: dict[str, dict[str, Any]] = {}
        self._hold_handle: asyncio.TimerHandle | None = None
        self._hold_task: asyncio.Task[None] | None = None

    def remember(self, address: str | None, **values: Any) -> None:
        """Record values read from the printer at ``address``, with the time.

        ``None`` values (a query that got no answer) keep what was known.
        """
        if address is None:
            return
        entry = self._seen.setdefault(address, {})
        entry.update({k: v for k, v in values.items() if v is not None})
        entry["at"] = datetime.now().isoformat(timespec="seconds")

    def last_seen(self, address: str | None) -> dict[str, Any] | None:
        """The values last read from the printer at ``address``, if any."""
        entry = self._seen.get(address) if address is not None else None
        return dict(entry) if entry else None

    @property
    def linked_address(self) -> str | None:
        """Address of the printer the bridge holds or last held a link to."""
        return self.printer.address if self.printer is not None else None

    @property
    def connected(self) -> bool:
        """Whether a live BLE link exists."""
        return self.printer is not None and self.printer.is_connected

    async def discover(self, timeout: float) -> list[BLEDevice]:
        """Scan for printers matching the profile's advertised name.

        Args:
            timeout: Scan duration in seconds.

        Returns:
            Matching devices, possibly empty.
        """
        return await discover(
            name_pattern=self.profile.ble_name_pattern, timeout=timeout
        )

    async def connect(
        self, discovery_timeout: float = 5.0, address: str | None = None
    ) -> None:
        """Establish the BLE link, reusing a held one.

        Args:
            discovery_timeout: Scan budget when the printer must be found.
            address: Printer to use instead of the configured one; a change
                of address drops the current link and targets the new one.

        Raises:
            ConnectionError: If the printer is not found or refuses.
        """
        self.cancel_hold()
        if address is not None and address != self._address:
            await self.disconnect()
            self.printer = None
            self._address = address
        if self.connected:
            return
        if self.printer is None:
            self.printer = self._factory(self.profile, self._address)
        await self.printer.connect(discovery_timeout=discovery_timeout)
        logger.info("Printer link up")
        await self._apply_auto_off(self.printer)

    async def _apply_auto_off(self, printer: Printer) -> None:
        """Set the configured auto-off timer unless the printer already has it."""
        wanted = self.config.auto_off_minutes
        if wanted is None:
            return
        try:
            current = await printer.query_auto_off()
            if current != wanted:
                await printer.set_auto_off_timer(wanted)
                logger.info("Printer auto-off set from %s to %d min", current, wanted)
            self.remember(printer.address, auto_off_minutes=wanted)
        except Exception as exc:  # noqa: BLE001, a link problem surfaces at the next command
            logger.warning("Could not set the printer auto-off: %s", exc)

    async def disconnect(self) -> None:
        """Drop the BLE link."""
        self.cancel_hold()
        if self.printer is not None and self.printer.is_connected:
            await self.printer.disconnect()
            logger.info("Printer link down")

    def start_hold(self) -> None:
        """Keep the link for ``idle_disconnect_minutes``, then drop it."""
        self.cancel_hold()
        if not self.connected:
            return
        loop = asyncio.get_running_loop()
        minutes = self.config.idle_disconnect_minutes
        if minutes > 0:
            self._hold_handle = loop.call_later(minutes * 60, self._expire_hold)

    def _expire_hold(self) -> None:
        self._hold_task = asyncio.ensure_future(self.disconnect())

    def cancel_hold(self) -> None:
        """Cancel a pending hold expiry."""
        if self._hold_handle is not None:
            self._hold_handle.cancel()
            self._hold_handle = None


async def start_server(
    config: BridgeConfig, printer_factory: PrinterFactory = Printer
) -> asyncio.AbstractServer:
    """Bind the unix socket and start accepting sessions.

    Args:
        config: Bridge settings.
        printer_factory: Builds the printer object; replaced in tests.

    Returns:
        The listening server; close it to stop.
    """
    server, _bridge = await _start(config, printer_factory)
    return server


async def _start(
    config: BridgeConfig, printer_factory: PrinterFactory
) -> tuple[asyncio.AbstractServer, Bridge]:
    from phomemo.bridge.session import Session

    bridge = Bridge(config, printer_factory)

    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await Session(bridge, reader, writer).run()

    config.socket_path.parent.mkdir(parents=True, exist_ok=True)
    if config.socket_path.exists():
        config.socket_path.unlink()
    server = await asyncio.start_unix_server(handle, path=str(config.socket_path))
    # Any local user may drive the printer, as with CUPS's own socket.
    config.socket_path.chmod(0o666)
    logger.info("Listening on %s", config.socket_path)
    return server, bridge


async def serve(
    config: BridgeConfig, printer_factory: PrinterFactory = Printer
) -> None:
    """Run the bridge until cancelled or signalled.

    SIGTERM and SIGINT stop the server. On the way out the printer link is
    dropped (BlueZ would otherwise keep it and the printer would stop
    advertising) and the socket file is removed.

    Args:
        config: Bridge settings.
        printer_factory: Builds the printer object; replaced in tests.
    """
    server, bridge = await _start(config, printer_factory)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop.set)
    try:
        async with server:
            await stop.wait()
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(sig)
        server.close()
        with contextlib.suppress(Exception):
            await asyncio.shield(bridge.disconnect())
        with contextlib.suppress(OSError):
            config.socket_path.unlink()
        logger.info("Bridge stopped")
