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

"""Bridge service: socket server, shared printer connection, idle timer."""

import asyncio
import contextlib
import logging
import signal
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bleak.backends.device import BLEDevice

from phomemo.discovery import discover
from phomemo.printer import Printer
from phomemo.registry import (
    PrinterProfile,
    get_profile,
    list_profiles,
    profile_for_name,
)

logger = logging.getLogger(__name__)

PrinterFactory = Callable[[PrinterProfile, "str | BLEDevice | None"], Printer]

__all__ = ["BridgeConfig", "Bridge", "serve", "start_server"]


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    """Operational settings of the bridge.

    The printer model, and with it everything about the printer's geometry,
    comes from each printer's model manifest, not from here.

    Attributes:
        socket_path: Unix socket the bridge listens on.
        idle_disconnect_minutes: Minutes without a command after which the
            bridge drops the Bluetooth connection (it ends earlier when the printer
            switches off or leaves range); 0 keeps it until then.
        auto_off_minutes: Auto-off timer the bridge sets on the printer at
            each new connection (multiple of 5, 0 = never switch off); ``None``
            leaves the printer's setting alone.
        settle_seconds: Cap on the wait for the sheet to seat after insertion.
        completion_timeout: Seconds to wait for the motor stop after a page.
        drain_seconds: Pause after a cancelled transfer so the printer
            finishes the data it already accepted before the eject.
    """

    socket_path: Path
    idle_disconnect_minutes: float = 30.0
    auto_off_minutes: int | None = None
    settle_seconds: float = 3.0
    completion_timeout: float = 300.0
    drain_seconds: float = 1.0


class Bridge:
    """State shared by all sessions: the printer connection and its idle timer."""

    def __init__(self, config: BridgeConfig, printer_factory: PrinterFactory) -> None:
        self.config = config
        self._factory = printer_factory
        # The printer connectioned or used last, with its model's profile; kept in
        # memory until the bridge stops.
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
        """Address of the printer the bridge is or was last connected to."""
        return self.printer.address if self.printer is not None else None

    @property
    def connected(self) -> bool:
        """Whether a live Bluetooth connection exists."""
        return self.printer is not None and self.printer.is_connected

    async def discover(self, timeout: float) -> list[tuple[BLEDevice, PrinterProfile]]:
        """Scan for printers of every known model.

        Args:
            timeout: Scan duration in seconds.

        Returns:
            Each device found with the profile its advertised name matches;
            devices of no known model are left out.
        """
        pattern = "|".join(
            f"(?:{get_profile(name).ble_name_pattern})" for name in list_profiles()
        )
        devices = await discover(name_pattern=pattern, timeout=timeout)
        found = [(device, profile_for_name(device.name)) for device in devices]
        return [(device, profile) for device, profile in found if profile is not None]

    async def connect(
        self,
        discovery_timeout: float = 5.0,
        address: str | None = None,
        model: str | None = None,
    ) -> None:
        """Establish the Bluetooth connection, reusing a held one.

        Args:
            discovery_timeout: Scan budget when the printer must be found.
            address: Printer to connect to; another address than the current
                printer's drops that connection. ``None`` keeps the printer used
                last, or takes the only known printer a scan finds.
            model: Model of that printer; without it a scan reads the model
                from the printer's advertised name.

        Raises:
            ConnectionError: If the model is unknown, the printer is not
                found, several printers qualify, or the printer refuses.
        """
        self.cancel_hold()
        if model is not None and model not in list_profiles():
            raise ConnectionError(f"unknown printer model {model!r}")
        current = self.printer
        if current is not None and (
            (address is not None and address != current.address)
            or (model is not None and model != current.profile.name)
        ):
            await self.disconnect()
            self.printer = None
        if self.connected:
            return
        if self.printer is None:
            self.printer = await self._new_printer(address, model, discovery_timeout)
        await self.printer.connect(discovery_timeout=discovery_timeout)
        logger.info("Printer connected (%s)", self.printer.profile.name)
        await self._apply_auto_off(self.printer)

    async def _new_printer(
        self, address: str | None, model: str | None, timeout: float
    ) -> Printer:
        if model is not None:
            return self._factory(get_profile(model), address)
        found = await self.discover(timeout)
        if address is not None:
            matches = [
                (device, profile)
                for device, profile in found
                if device.address.upper() == address.upper()
            ]
            if not matches:
                raise ConnectionError(f"no printer of a known model at {address}")
            device, profile = matches[0]
            return self._factory(profile, device)
        if not found:
            raise ConnectionError("no printer of a known model in range")
        if len(found) > 1:
            addresses = ", ".join(sorted(device.address for device, _ in found))
            raise ConnectionError(
                f"several printers in range ({addresses}); choose one by address"
            )
        device, profile = found[0]
        return self._factory(profile, device)

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
        except Exception as exc:  # noqa: BLE001, a connection problem surfaces at the next command
            logger.warning("Could not set the printer auto-off: %s", exc)

    async def disconnect(self) -> None:
        """Drop the Bluetooth connection."""
        self.cancel_hold()
        if self.printer is not None and self.printer.is_connected:
            await self.printer.disconnect()
            logger.info("Printer disconnected")

    def start_hold(self) -> None:
        """Keep the connection for ``idle_disconnect_minutes``, then drop it."""
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

    SIGTERM and SIGINT stop the server. On the way out the printer connection is
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
