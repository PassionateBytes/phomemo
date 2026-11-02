"""Bridge daemon: socket server, shared printer link, hold timer."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from pathlib import Path

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
        address: BLE address of the printer, or ``None`` to discover by name.
        profile: Printer profile name.
        hold_seconds: Seconds the BLE link stays up after ``close``.
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
    address: str | None = None
    profile: str = "M08F-A4"
    hold_seconds: float = 120.0
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
    """State shared by all client sessions: the printer link and its hold timer."""

    def __init__(self, config: BridgeConfig, printer_factory: PrinterFactory) -> None:
        self.config = config
        self.profile = config.resolved_profile()
        self._factory = printer_factory
        self._address: str | None = config.address
        self.printer: Printer | None = None
        self.session_active = False
        self._hold_handle: asyncio.TimerHandle | None = None

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

    async def disconnect(self) -> None:
        """Drop the BLE link."""
        self.cancel_hold()
        if self.printer is not None and self.printer.is_connected:
            await self.printer.disconnect()
            logger.info("Printer link down")

    def start_hold(self) -> None:
        """Keep the link for ``hold_seconds``, then drop it."""
        self.cancel_hold()
        if not self.connected:
            return
        loop = asyncio.get_running_loop()
        self._hold_handle = loop.call_later(
            self.config.hold_seconds,
            lambda: asyncio.ensure_future(self.disconnect()),
        )

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
    logger.info("Listening on %s", config.socket_path)
    return server


async def serve(
    config: BridgeConfig, printer_factory: PrinterFactory = Printer
) -> None:
    """Run the bridge until cancelled.

    Args:
        config: Bridge settings.
        printer_factory: Builds the printer object; replaced in tests.
    """
    server = await start_server(config, printer_factory)
    async with server:
        await server.serve_forever()
