"""BLE transport layer for Phomemo printers.

Handles the low-level BLE connection, chunked writes, and notification
subscription. All communication with the printer passes through this
layer.

Key protocol constraints for the Phomemo M08F device:
- Maximum write size: 244 bytes per ``write_gatt_char`` call.
- Write method: Write Without Response (``response=False``).
- Inter-chunk delay: 20ms is reliable for full-page jobs.
- No per-chunk acknowledgement — fire-and-forget protocol.
- ``0x0A`` outside raster data triggers a line feed (~5mm paper advance).
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Self

from bleak import BleakClient
from bleak.exc import BleakError

from phomemo.profiles import PrinterProfile

logger = logging.getLogger(__name__)

NotifyCallback = Callable[[bytes], None]


class BleTransport:
    """Manages a BLE connection to a Phomemo printer.

    Handles connection lifecycle, notification subscriptions, and chunked
    writes respecting the printer's MTU and timing constraints.

    Args:
        profile: Printer hardware profile with BLE UUIDs and timing.
    """

    def __init__(self, profile: PrinterProfile) -> None:
        self._profile = profile
        self._client: BleakClient | None = None
        self._connected = False
        self._effective_chunk_bytes: int = profile.max_chunk_bytes

    @property
    def is_connected(self) -> bool:
        """Whether the BLE connection is active."""
        return self._connected and self._client is not None

    async def connect(
        self,
        address: str,
        on_event: NotifyCallback | None = None,
        on_status: NotifyCallback | None = None,
    ) -> None:
        """Establish a BLE connection to the printer.

        Connects to the device, then subscribes to the event notification
        channel (``ff01``) and optionally the status echo channel (``ff03``).

        Args:
            address: BLE MAC address (e.g. ``"60:6E:41:23:0B:D6"``).
            on_event: Callback for event notifications on ``ff01``.
            on_status: Callback for status echo on ``ff03``.

        Raises:
            ConnectionError: If the connection fails.
            RuntimeError: If already connected.
        """
        if self.is_connected:
            raise RuntimeError("Already connected")

        logger.debug("Connecting to %s...", address)
        try:
            self._client = BleakClient(address)
            await self._client.connect()
            self._connected = True
            logger.info("Connected to %s", address)
        except BleakError as exc:
            self._client = None
            raise ConnectionError(f"Failed to connect to {address}: {exc}") from exc

        if self._profile.negotiate_mtu:
            logger.debug("Negotiating effective max chunk size...")
            try:
                negotiated_chunk_bytes = self._client.mtu_size - 3
                if negotiated_chunk_bytes > 0:
                    self._effective_chunk_bytes = negotiated_chunk_bytes
            finally:
                logging.debug("Using max chunk size of %s bytes", self._effective_chunk_bytes)


        try:
            if on_event is not None:
                await self._client.start_notify(
                    self._profile.notify_uuid,
                    lambda _handle, data: on_event(bytes(data)),
                )

            if on_status is not None:
                await self._client.start_notify(
                    self._profile.status_uuid,
                    lambda _handle, data: on_status(bytes(data)),
                )
            logger.debug("Connected")
        except BleakError as exc:
            await self.disconnect()
            raise ConnectionError(
                f"Connected to {address} but failed to subscribe "
                f"to notifications: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        """Disconnect from the printer.

        Safe to call even if not connected.
        """
        if self._client is not None:
            logger.debug("Disconnecting...")
            try:
                await self._client.disconnect()
            finally:
                self._client = None
                self._connected = False
                self._effective_chunk_bytes = self._profile.max_chunk_bytes
                logger.info("Disconnected")

    async def write(self, data: bytes) -> None:
        """Write raw bytes to the printer's command channel.

        Uses Write Without Response as required by the protocol.

        Args:
            data: Bytes to send. Must be ≤ ``max_chunk_bytes``.

        Raises:
            RuntimeError: If not connected.
            ValueError: If data exceeds the maximum chunk size.
        """
        if self._client is None:
            raise RuntimeError("Not connected")
        max_size = self._effective_chunk_bytes
        if len(data) > max_size:
            raise ValueError(f"Write size {len(data)} exceeds max {max_size} bytes")
        await self._client.write_gatt_char(
            self._profile.write_uuid, data, response=False
        )

    async def write_chunked(
        self,
        data: bytes,
        on_chunk: Callable[[int, int], None] | None = None,
    ) -> None:
        """Write data in chunks respecting the BLE MTU limit.

        Splits ``data`` into segments of at most ``max_chunk_bytes`` and
        writes them sequentially with the configured inter-chunk delay.

        Args:
            data: The full payload to send.
            on_chunk: Optional progress callback invoked after each chunk
                write with ``(chunks_sent, total_chunks)``.

        Raises:
            RuntimeError: If not connected.
        """
        max_size = self._effective_chunk_bytes
        delay = self._profile.chunk_delay_s
        total = (len(data) + max_size - 1) // max_size
        logger.debug("Writing %d bytes in %d chunks", len(data), total)

        for i in range(total):
            start = i * max_size
            chunk = data[start : start + max_size]
            await self.write(chunk)
            if delay > 0 and i < total - 1:
                await asyncio.sleep(delay)
            if on_chunk is not None:
                try:
                    on_chunk(i + 1, total)
                except Exception:
                    logger.exception(
                        "Progress callback failed on chunk %d/%d", i + 1, total
                    )

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        Returns:
            This transport instance (call ``connect()`` separately).
        """
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Exit the async context manager and disconnect."""
        await self.disconnect()
