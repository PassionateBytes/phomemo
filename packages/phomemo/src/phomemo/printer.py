"""High-level async printer client.

The ``Printer`` class is the primary developer-facing API. It composes
the transport, protocol, event, and imaging modules into a single
coherent interface for controlling Phomemo thermal printers.

Typical usage::

    from phomemo import Printer, Density

    async with Printer("M08F-A4") as printer:
        await printer.connect("60:6E:41:23:0B:D6")

        # Check device state before printing
        info = await printer.query_device_info()
        print(f"Battery: {info.battery}%, Lid: {info.lid}, Paper: {info.paper}")

        # Print an image
        await printer.print_image("photo.png", density=Density.MEDIUM)

        # Eject the page
        await printer.eject_paper()
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from PIL import Image

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from phomemo.discovery import discover
from phomemo.events import (
    BatteryEvent,
    DeviceEvent,
    FirmwareEvent,
    LidEvent,
    LidState,
    MotorStopEvent,
    PaperEvent,
    PaperState,
    SerialEvent,
    TimerEvent,
    parse_notification,
)
from phomemo.imaging import (
    DitherMode,
    ImageFit,
    image_to_bitmap,
    prepare_image,
)
from phomemo.protocol import (
    Density,
    QueryCommand,
    ScaleMode,
    encode_auto_off_timer,
    encode_density,
    encode_feed_lines,
    encode_init,
    encode_paper_eject,
    encode_raster_header,
)
from phomemo.registry import PrinterProfile, get_profile
from phomemo.transport import BleTransport

logger = logging.getLogger(__name__)

EventCallback = Callable[[DeviceEvent], None]
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Snapshot of device state collected from query responses.

    Attributes:
        battery: Battery percentage (0-100), or None if not queried.
        lid: Lid state, or None if not queried.
        paper: Paper state, or None if not queried.
        firmware: Firmware version string, or None if not queried.
        serial: Serial number string, or None if not queried.
        auto_off_minutes: Auto-off timer in minutes (0 = disabled),
            or None if not queried.
    """

    battery: int | None = None
    lid: LidState | None = None
    paper: PaperState | None = None
    firmware: str | None = None
    serial: str | None = None
    auto_off_minutes: int | None = None


class Printer:
    """Async BLE client for Phomemo thermal printers.

    Manages the full lifecycle: BLE connection, device queries, image
    preparation, raster printing, and paper transport. Designed to be
    used as an async context manager.

    Args:
        profile: Either a profile name string (e.g. ``"M08F-A4"``) or
            a ``PrinterProfile`` instance.
        address: BLE MAC address (e.g. ``"60:6E:41:23:0B:D6"``). If
            omitted, ``connect()`` will auto-discover a nearby device
            matching the profile's ``ble_name_pattern``.
    """

    def __init__(
        self,
        profile: str | PrinterProfile = "M08F-A4",
        address: str | BLEDevice | None = None,
    ) -> None:
        if isinstance(profile, str):
            self._profile = get_profile(profile)
        else:
            self._profile = profile

        self._address = address
        self._transport = BleTransport(self._profile)
        self._event_callbacks: list[EventCallback] = []
        self._waiters: list[tuple[type[DeviceEvent], asyncio.Future[DeviceEvent]]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def profile(self) -> PrinterProfile:
        """The active printer hardware profile."""
        return self._profile

    @property
    def is_connected(self) -> bool:
        """Whether the BLE connection is active."""
        return self._transport.is_connected

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def on_event(self, callback: EventCallback) -> None:
        """Register a listener for parsed device events.

        Callbacks receive typed event dataclasses (``LidEvent``,
        ``PaperEvent``, ``BatteryEvent``, ``MotorStopEvent``, etc.) as
        they arrive from the printer.

        Args:
            callback: Called with each parsed ``DeviceEvent``.
        """
        self._event_callbacks.append(callback)

    def _dispatch_event(self, event: DeviceEvent) -> None:
        """Route a parsed event to callbacks and any active typed waiters.

        Events are delivered to the first waiter whose registered type
        matches the event. Unmatched events are still delivered to
        callbacks but do not consume any waiter.

        Args:
            event: The parsed device event.
        """
        for cb in self._event_callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Event callback %r failed for %r", cb, event)

        for event_type, future in self._waiters:
            if not future.done() and isinstance(event, event_type):
                future.set_result(event)
                break

    def _on_notification(self, data: bytes) -> None:
        """Handle raw BLE notification data from ff01.

        Args:
            data: Raw bytes from the notification.
        """
        for event in parse_notification(data):
            self._dispatch_event(event)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self, discovery_timeout: float = 5.0) -> None:
        """Connect to the printer.

        The transport always receives a ``BLEDevice`` from a live scan:
        BlueZ can only connect to a device it has seen advertising recently,
        so a bare MAC address is resolved through a targeted scan first.
        Without an ``address``, scans for a nearby device whose advertised
        name matches the profile's ``ble_name_pattern`` and connects to the
        first match.

        Args:
            discovery_timeout: Scan duration in seconds, for both name-based
                discovery and MAC resolution. Ignored if a ``BLEDevice`` was
                provided at instantiation.

        Raises:
            ConnectionError: If the connection fails, if no matching device
                is discovered, or if the given MAC address is not seen within
                ``discovery_timeout``.
            RuntimeError: If already connected.
        """
        device = self._address
        if device is None:
            pattern = self._profile.ble_name_pattern
            devices = await discover(name_pattern=pattern, timeout=discovery_timeout)
            if not devices:
                raise ConnectionError(
                    f"No device found matching profile {self._profile.name!r} "
                    f"(pattern {pattern!r}) within {discovery_timeout}s"
                )
            device = devices[0]
            logger.info("Discovered %s at %s", device.name, device.address)
        elif isinstance(device, str):
            found = await BleakScanner.find_device_by_address(
                device, timeout=discovery_timeout
            )
            if found is None:
                raise ConnectionError(
                    f"Device {device} not found within {discovery_timeout}s"
                )
            device = found

        await self._transport.connect(
            device,
            on_event=self._on_notification,
        )

    async def disconnect(self) -> None:
        """Disconnect from the printer.

        Safe to call even if not connected.
        """
        await self._transport.disconnect()

    # ------------------------------------------------------------------
    # Low-level commands
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Send ``ESC @`` to reset the printer to its default state.

        Should precede standalone ESC-prefix commands to prevent the
        BLE bridge chip from intercepting them.
        """
        logger.debug("Sending ESC @")
        await self._transport.write(encode_init())

    async def set_density(self, level: Density) -> None:
        """Set print concentration via ``ESC N 04``.

        Persists until the next ``ESC @`` reset.

        Args:
            level: Desired concentration level.
        """
        logger.debug("Setting density: %s", level)
        await self._transport.write(encode_density(level))

    async def feed(self, lines: int = 20) -> None:
        """Feed paper by the given number of lines via ``ESC d``.

        Each line is approximately one dot row (0.125mm at 203 DPI).

        Args:
            lines: Number of lines to feed (1-255).
        """
        logger.debug("Feeding %d lines", lines)
        await self._transport.write(encode_feed_lines(lines))

    async def eject_paper(self, repetitions: int = 12) -> None:
        """Eject the current sheet with repeated maximum-length feeds.

        Chains ``ESC d 255`` commands. 12 repetitions produce ~384mm,
        sufficient for A4 paper with margin.

        Args:
            repetitions: Number of ``ESC d 255`` commands.
        """
        logger.debug("Ejecting paper (%d repetitions)", repetitions)
        payload = encode_paper_eject(repetitions)
        await self._transport.write_chunked(payload)

    async def set_auto_off_timer(self, minutes: int) -> None:
        """Set the auto-off timer.

        Args:
            minutes: Timeout in minutes. Must be a multiple of 5.
                0 disables the timer.

        Raises:
            ValueError: If minutes is not a non-negative multiple of 5.
        """
        if minutes < 0 or minutes % 5 != 0:
            raise ValueError(
                f"Timer must be a non-negative multiple of 5, got {minutes}"
            )
        logger.debug("Setting auto-off timer: %d minutes", minutes)
        value = minutes // 5
        await self.initialize()
        await self._transport.write(encode_auto_off_timer(value))

    # ------------------------------------------------------------------
    # Device queries
    # ------------------------------------------------------------------

    async def _wait_for(
        self,
        event_type: type[DeviceEvent],
        timeout: float,
    ) -> DeviceEvent | None:
        """Wait for the next event of a specific type.

        Spontaneous events of other types are ignored by this waiter
        (they still reach registered callbacks).

        Args:
            event_type: The event class to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            The matched event, or None on timeout.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[DeviceEvent] = loop.create_future()
        entry = (event_type, future)
        self._waiters.append(entry)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return None
        finally:
            self._waiters.remove(entry)

    async def _query(
        self,
        command: QueryCommand,
        event_type: type[DeviceEvent],
        timeout: float = 1.0,
    ) -> DeviceEvent | None:
        """Send a query and wait for the matching response event.

        Returns as soon as the expected event type arrives, rather than
        waiting for the full timeout. Spontaneous events of other types
        do not interfere.

        Args:
            command: The query command bytes.
            event_type: Expected response event class.
            timeout: Maximum seconds to wait for a response.

        Returns:
            The matched event, or None on timeout.
        """
        logger.debug("Query %s (timeout=%.1fs)", command.hex(), timeout)
        await self._transport.write(command)
        return await self._wait_for(event_type, timeout)

    async def query_battery(self, timeout: float = 1.0) -> int | None:
        """Query the current battery level.

        Args:
            timeout: Seconds to wait for a response.

        Returns:
            Battery percentage (0-100), or None if no response.
        """
        event = await self._query(QueryCommand.BATTERY, BatteryEvent, timeout)
        return event.percent if event else None

    async def query_firmware(self, timeout: float = 1.0) -> str | None:
        """Query the firmware version.

        Args:
            timeout: Seconds to wait for a response.

        Returns:
            Version string (e.g. ``"1.1.3"``), or None if no response.
        """
        event = await self._query(QueryCommand.FIRMWARE, FirmwareEvent, timeout)
        if not event:
            return None
        assert isinstance(event, FirmwareEvent)
        return f"{event.major}.{event.minor}.{event.patch}"

    async def query_serial(self, timeout: float = 1.0) -> str | None:
        """Query the device serial number (ASCII form).

        Args:
            timeout: Seconds to wait for a response.

        Returns:
            Serial number string, or None if no response.
        """
        event = await self._query(QueryCommand.SERIAL_ASCII, SerialEvent, timeout)
        return event.value if event else None

    async def query_lid(self, timeout: float = 1.0) -> LidState | None:
        """Query the lid state.

        Args:
            timeout: Seconds to wait for a response.

        Returns:
            ``LidState.CLOSED`` or ``LidState.OPEN``, or None.
        """
        event = await self._query(QueryCommand.LID_STATE, LidEvent, timeout)
        return event.lid if event else None

    async def query_paper(self, timeout: float = 1.0) -> PaperState | None:
        """Query the paper sensor state.

        **Important:** Paper state is unreliable when the lid is open.
        Always query lid state first.

        Args:
            timeout: Seconds to wait for a response.

        Returns:
            ``PaperState.PRESENT`` or ``PaperState.ABSENT``, or None.
        """
        event = await self._query(QueryCommand.PAPER_STATE, PaperEvent, timeout)
        return event.paper if event else None

    async def query_device_info(self, timeout: float = 1.0) -> DeviceInfo:
        """Query all available device information.

        Sends battery, firmware, serial, lid, paper, and timer queries
        sequentially. Each query returns as soon as the device responds
        (typically ~70ms), so the full round-trip is well under 1s.

        Paper state is discarded if the lid is open (sensor unreliable).

        Args:
            timeout: Per-query timeout in seconds.

        Returns:
            A ``DeviceInfo`` with all available fields populated.
        """
        battery = await self.query_battery(timeout)
        firmware = await self.query_firmware(timeout)
        serial = await self.query_serial(timeout)
        lid = await self.query_lid(timeout)

        # Paper sensor is unreliable with lid open — only query if closed
        paper = None
        if lid == LidState.CLOSED:
            paper = await self.query_paper(timeout)

        timer_ev = await self._query(QueryCommand.DEVICE_TIMER, TimerEvent, timeout)
        auto_off_minutes = (
            timer_ev.minutes if isinstance(timer_ev, TimerEvent) else None
        )

        return DeviceInfo(
            battery=battery,
            lid=lid,
            paper=paper,
            firmware=firmware,
            serial=serial,
            auto_off_minutes=auto_off_minutes,
        )

    # ------------------------------------------------------------------
    # Pre-print readiness check
    # ------------------------------------------------------------------

    async def check_ready(self, timeout: float = 1.0) -> tuple[bool, str]:
        """Check whether the printer is ready to print.

        Queries lid and paper state. Returns a tuple of ``(ready, reason)``
        where ``ready`` is ``True`` if the printer can accept a print job.

        Args:
            timeout: Per-query timeout in seconds.

        Returns:
            ``(True, "ready")`` or ``(False, reason_string)``.
        """
        lid = await self.query_lid(timeout)
        if lid is None:
            logger.debug("check_ready: lid query timed out")
            return False, "Could not query lid state"
        if lid == LidState.OPEN:
            logger.debug("check_ready: lid is open")
            return False, "Lid is open"

        paper = await self.query_paper(timeout)
        if paper is None:
            logger.debug("check_ready: paper query timed out")
            return False, "Could not query paper state"
        if paper == PaperState.ABSENT:
            logger.debug("check_ready: no paper loaded")
            return False, "No paper loaded"

        logger.debug("check_ready: ready")
        return True, "ready"

    # ------------------------------------------------------------------
    # Raster printing
    # ------------------------------------------------------------------

    def _build_raster_payload(
        self,
        bitmap: bytes,
        height: int,
        density: Density | None = None,
        mode: ScaleMode = ScaleMode.NORMAL,
        feed_lines: int = 20,
    ) -> bytes:
        """Assemble the complete print job payload.

        Constructs the full byte stream: ``ESC @`` init, optional density,
        banded ``GS v 0`` raster data, and trailing paper feed.

        Args:
            bitmap: Packed 1-bit bitmap bytes (row-major).
            height: Total number of rows in the bitmap.
            density: Print concentration, or None to skip.
            mode: GS v 0 scaling mode.
            feed_lines: Paper feed lines after the raster data.

        Returns:
            The complete payload bytes ready for chunked transmission.
        """
        width_bytes = self._profile.width_bytes
        band_height = self._profile.band_height
        parts: list[bytes] = []

        # Initialise and optionally set density
        parts.append(encode_init())
        if density is not None and self._profile.supports_density:
            parts.append(encode_density(density))

        # Split into bands — each needs its own GS v 0 header
        row = 0
        while row < height:
            band_rows = min(band_height, height - row)
            band_start = row * width_bytes
            band_end = band_start + band_rows * width_bytes
            parts.append(encode_raster_header(width_bytes, band_rows, mode))
            parts.append(bitmap[band_start:band_end])
            row += band_rows

        # Trailing feed
        if feed_lines > 0:
            parts.append(encode_feed_lines(min(feed_lines, 255)))

        return b"".join(parts)

    async def print_bitmap(
        self,
        bitmap: bytes,
        height: int,
        density: Density | None = Density.MEDIUM,
        mode: ScaleMode = ScaleMode.NORMAL,
        feed_lines: int = 20,
        on_progress: ProgressCallback | None = None,
        wait_for_completion: bool = True,
        completion_timeout: float = 30.0,
    ) -> None:
        """Send pre-rendered bitmap data to the printer.

        Args:
            bitmap: Packed 1-bit bitmap (``width_bytes * height`` bytes).
            height: Number of rows in the bitmap.
            density: Print concentration (None to skip).
            mode: GS v 0 scaling mode.
            feed_lines: Paper feed lines after printing.
            on_progress: Progress callback ``(chunks_sent, total_chunks)``.
            wait_for_completion: If True, block until the ``1a 0f 0c``
                motor-stop signal is received.
            completion_timeout: Maximum seconds to wait for completion.

        Raises:
            RuntimeError: If not connected.
            TimeoutError: If completion signal not received within timeout.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        logger.debug(
            "print_bitmap: %d rows, %d bitmap bytes, density=%s",
            height,
            len(bitmap),
            density,
        )
        payload = self._build_raster_payload(bitmap, height, density, mode, feed_lines)
        logger.debug("print_bitmap: payload %d bytes", len(payload))
        await self._transport.write_chunked(payload, on_chunk=on_progress)

        if wait_for_completion:
            logger.debug("print_bitmap: waiting for motor stop")
            await self._wait_for_motor_stop(completion_timeout)
            logger.debug("print_bitmap: complete")

    async def _wait_for_motor_stop(self, timeout: float) -> None:
        """Wait for the print-complete (motor stop) signal.

        The printer fires ``1a 0f 0c`` on ``ff01`` when the motor stops.
        Uses a typed waiter so spontaneous sensor events don't interfere.

        Args:
            timeout: Maximum seconds to wait.

        Raises:
            TimeoutError: If the signal is not received in time.
        """
        event = await self._wait_for(MotorStopEvent, timeout)
        if event is None:
            raise TimeoutError("Timed out waiting for print completion signal")

    # ------------------------------------------------------------------
    # Image pipeline
    # ------------------------------------------------------------------

    async def print_image(
        self,
        source: str | Path | Image.Image,
        density: Density | None = Density.MEDIUM,
        fit: ImageFit = ImageFit.FIT_WIDTH,
        dither: DitherMode = DitherMode.FLOYD_STEINBERG,
        feed_lines: int = 20,
        on_progress: ProgressCallback | None = None,
        wait_for_completion: bool = True,
        completion_timeout: float = 30.0,
    ) -> None:
        """Full print pipeline: load image, process, print, feed.

        Accepts a file path or an already-opened PIL Image. Handles the
        complete pipeline from image to paper.

        Args:
            source: Path to an image file, or a PIL ``Image`` instance.
            density: Print concentration (None to skip).
            fit: How to fit the image to the print width.
            dither: Dithering algorithm for 1-bit conversion.
            feed_lines: Paper feed lines after printing.
            on_progress: Progress callback ``(chunks_sent, total_chunks)``.
            wait_for_completion: If True, block until print-complete signal.
            completion_timeout: Maximum seconds to wait for completion.

        Raises:
            RuntimeError: If not connected.
            FileNotFoundError: If the source path doesn't exist.
        """

        logger.debug("print_image: source=%r fit=%s dither=%s", source, fit, dither)

        def _process_image() -> tuple[bytes, int]:
            """Load, resize, dither, and pack the image (CPU-bound)."""
            img = Image.open(source) if isinstance(source, (str, Path)) else source
            processed = prepare_image(
                img,
                target_width=self._profile.print_width_px,
                fit=fit,
                dither=dither,
            )
            return image_to_bitmap(processed), processed.size[1]

        bitmap, height = await asyncio.to_thread(_process_image)
        logger.debug("print_image: processed to %d rows", height)

        await self.print_bitmap(
            bitmap,
            height,
            density=density,
            feed_lines=feed_lines,
            on_progress=on_progress,
            wait_for_completion=wait_for_completion,
            completion_timeout=completion_timeout,
        )

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        Returns:
            This ``Printer`` instance. Call ``connect()`` to establish
            the BLE connection.
        """
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Exit the async context manager and disconnect."""
        await self.disconnect()
