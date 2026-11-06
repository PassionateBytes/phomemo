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
    profiles_for_name,
)

logger = logging.getLogger(__name__)

PrinterFactory = Callable[[PrinterProfile, "str | BLEDevice | None"], Printer]

__all__ = ["BridgeConfig", "Bridge", "Found", "serve", "start_server"]

_SERIAL_TIMEOUT = 1.0


@dataclass(frozen=True, slots=True)
class Found:
    """A printer a scan turned up, with the model it was taken for.

    Attributes:
        device: The device as the scan saw it.
        profile: The model: resolved from the serial when the advertised
            name matched several models and the printer answered, else the
            model the name alone gives.
        serial: The serial read to resolve the model, if any.
        resolved: ``None`` when the name alone settled the model; otherwise
            whether the serial could be read.
    """

    device: BLEDevice
    profile: PrinterProfile
    serial: str | None = None
    resolved: bool | None = None


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
        # The printer connected or used last, with its model's profile; kept in
        # memory until the bridge stops.
        self.printer: Printer | None = None
        # Whether that printer's model was named by the client (kept as is)
        # rather than read from the advertised name (refined by the serial).
        self._model_explicit = False
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

    async def scan(self, timeout: float) -> list[BLEDevice]:
        """Scan for printers of every known model, without connecting.

        Args:
            timeout: Scan duration in seconds.

        Returns:
            The devices whose advertised name matches a known model.
        """
        pattern = "|".join(
            f"(?:{get_profile(name).ble_name_pattern})" for name in list_profiles()
        )
        devices = await discover(name_pattern=pattern, timeout=timeout)
        return [device for device in devices if profiles_for_name(device.name)]

    async def discover(self, timeout: float) -> list[Found]:
        """Scan for printers of every known model and tell their models apart.

        A printer whose advertised name matches one model is reported as
        that model without connecting. When several models share the name,
        the bridge reads the printer's serial (over the held connection
        when it is that printer, else over a brief one) and resolves the
        model from it.

        Args:
            timeout: Scan duration in seconds.

        Returns:
            Each printer found with its model.
        """
        found: list[Found] = []
        for device in await self.scan(timeout):
            candidates = profiles_for_name(device.name)
            if len(candidates) == 1:
                found.append(Found(device, candidates[0]))
                continue
            serial = await self._read_serial(device, timeout)
            profile = profile_for_name(device.name, serial)
            assert profile is not None
            self.remember(device.address, serial=serial, model=profile.name)
            found.append(Found(device, profile, serial, serial is not None))
        return found

    async def _read_serial(self, device: BLEDevice, timeout: float) -> str | None:
        """The serial of a scanned printer, read over a connection to it.

        Returns:
            The serial, or ``None`` when the printer cannot be reached or
            does not answer.
        """
        held = self.printer
        if (
            held is not None
            and held.is_connected
            and (held.address or "").upper() == device.address.upper()
        ):
            return await self._query_serial(held)
        probe = self._factory(profile_for_name(device.name), device)
        try:
            await probe.connect(discovery_timeout=timeout)
        except ConnectionError as exc:
            logger.info("Cannot read the serial of %s: %s", device.address, exc)
            return None
        try:
            return await self._query_serial(probe)
        finally:
            with contextlib.suppress(Exception):
                await probe.disconnect()

    @staticmethod
    async def _query_serial(printer: Printer) -> str | None:
        try:
            return await printer.query_serial(timeout=_SERIAL_TIMEOUT)
        except Exception as exc:  # noqa: BLE001, the model falls back to the name
            logger.warning("Could not read the printer serial: %s", exc)
            return None

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
            model: Model of that printer, kept as given; without it a scan
                reads the model from the printer's advertised name and the
                serial settles it when several models share that name.

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
            self._model_explicit = model is not None
        await self.printer.connect(discovery_timeout=discovery_timeout)
        await self._refine_model(discovery_timeout)
        logger.info("Printer connected (%s)", self.printer.profile.name)
        await self._apply_auto_off(self.printer)

    async def _new_printer(
        self, address: str | None, model: str | None, timeout: float
    ) -> Printer:
        if model is not None:
            return self._factory(get_profile(model), address)
        found = await self.scan(timeout)
        if address is not None:
            matches = [
                device for device in found if device.address.upper() == address.upper()
            ]
            if not matches:
                raise ConnectionError(f"no printer of a known model at {address}")
            device = matches[0]
        elif not found:
            raise ConnectionError("no printer of a known model in range")
        elif len(found) > 1:
            addresses = ", ".join(sorted(device.address for device in found))
            raise ConnectionError(
                f"several printers in range ({addresses}); choose one by address"
            )
        else:
            device = found[0]
        return self._factory(profile_for_name(device.name), device)

    async def _refine_model(self, discovery_timeout: float) -> None:
        """Settle the connected printer's model by its serial.

        The advertised name may match several models; the serial tells
        them apart. A model named by the client stays, with a warning when
        the serial points elsewhere. A serial the printer does not give
        leaves the name match in place.
        """
        printer = self.printer
        assert printer is not None
        name = printer.advertised_name
        if not name or len(profiles_for_name(name)) < 2:
            return
        serial = await self._query_serial(printer)
        if serial is None:
            return
        self.remember(printer.address, serial=serial)
        resolved = profile_for_name(name, serial)
        if resolved is None or resolved == printer.profile:
            return
        if self._model_explicit:
            logger.warning(
                "Printer %s opened as model %s, but its serial points to %s",
                printer.address,
                printer.profile.name,
                resolved.name,
            )
            return
        logger.info(
            "Printer %s is model %s by its serial (name match: %s)",
            printer.address,
            resolved.name,
            printer.profile.name,
        )
        if resolved.ble_settings() == printer.profile.ble_settings():
            printer.use_profile(resolved)
            return
        await printer.disconnect()
        self.printer = self._factory(resolved, printer.address)
        await self.printer.connect(discovery_timeout=discovery_timeout)

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
