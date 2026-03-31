"""BLE connection lifecycle and print job state machine.

PrinterService manages auto-connect, polling, and print jobs. It posts
Textual messages via the ``post_message`` callback for UI updates.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from phomemo import Printer, discover, get_profile, list_profiles
from phomemo.events import (
    BatteryEvent,
    DeviceEvent,
    LidEvent,
    LidState,
    PaperEvent,
    PaperState,
)
from phomemo.imaging import DitherMode, ImageFit
from phomemo.protocol import Density
from textual.message import Message

from phomemo_tui.config import AppConfig
from phomemo_tui.file_utils import get_page_count, load_page_as_pil
from phomemo_tui.messages import (
    DeviceConnected,
    DeviceDisconnected,
    DeviceScanStarted,
    DeviceStateUpdated,
    PrintCancelled,
    PrintComplete,
    PrintError,
    PrintPageComplete,
    PrintProgress,
    PrintWaitingForPaper,
    PrintWaitingForReady,
)

logger = logging.getLogger(__name__)

PostMessageCallback = Callable[[Message], bool]


class ServiceState(Enum):
    """Connection and print state of the printer service."""

    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    WAITING_FOR_READY = "waiting_for_ready"
    PRINTING = "printing"
    WAITING_FOR_PAPER = "waiting_for_paper"


@dataclass
class _DeviceSnapshot:
    """Latest known device sensor state."""

    battery: int | None = None
    lid: LidState | None = None
    paper: PaperState | None = None


class PrinterService:
    """Manages BLE connection lifecycle and print jobs.

    Runs two concurrent asyncio tasks: a connection loop (via ``start()``)
    and optionally a print job (via ``print_job()``). Posts Textual Message
    instances via ``post_message`` for all state transitions.

    Args:
        post_message: Callback to deliver messages to the Textual app.
        config: Shared application configuration.
    """

    def __init__(
        self,
        post_message: PostMessageCallback,
        config: AppConfig,
    ) -> None:
        self._post = post_message
        self._config = config
        self._printer: Printer | None = None
        self._state = ServiceState.DISCONNECTED
        self._snapshot = _DeviceSnapshot()
        self._print_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def state(self) -> ServiceState:
        """Current service state."""
        return self._state

    # ------------------------------------------------------------------
    # Connection loop (runs as a Textual worker)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Auto-connect loop. Retries every 5 s until connected, then polls."""
        while True:
            await self._run_until_connected()
            await self._run_while_connected()

    async def _run_until_connected(self) -> None:
        """Keep trying to connect until one attempt succeeds."""
        while True:
            try:
                self._set_state(ServiceState.SCANNING)
                self._post(DeviceScanStarted())
                await self._try_connect()
                return
            except Exception as exc:
                logger.debug("Connection attempt failed: %s", exc)
                self._set_state(ServiceState.DISCONNECTED)
                self._post(DeviceDisconnected())
                await asyncio.sleep(5.0)

    async def _try_connect(self) -> None:
        """One scan + connect attempt. Raises on failure."""
        cfg = self._config
        devices = await discover(timeout=5.0)

        address: str | None = None
        device_name: str | None = None
        profile_name: str | None = None

        # Priority 1: last known device
        if cfg.last_device_address:
            match = next(
                (d for d in devices if d.address == cfg.last_device_address), None
            )
            if match:
                address = match.address
                device_name = match.name
                profile_name = cfg.profile_override or match_profile(match.name)

        # Priority 2: first device matching any profile pattern
        if address is None:
            for device in devices:
                matched = match_profile(device.name)
                if matched:
                    address = device.address
                    device_name = device.name
                    profile_name = cfg.profile_override or matched
                    break

        if address is None:
            raise ConnectionError("No suitable device found")

        await self.connect_to(
            address,
            device_name or address,
            profile_name or "M08F-A4",
        )

    async def connect_to(self, address: str, name: str, profile_name: str) -> None:
        """Connect to a specific device by address.

        Args:
            address: BLE MAC address.
            name: Human-readable device name (for display and config).
            profile_name: Printer profile to use.
        """
        self._set_state(ServiceState.CONNECTING)
        printer = Printer(profile=profile_name, address=address)
        printer.on_event(self._on_device_event)
        await printer.connect()
        self._printer = printer
        self._config.last_device_address = address
        self._config.last_device_name = name
        self._set_state(ServiceState.CONNECTED)
        self._post(
            DeviceConnected(address=address, name=name, profile_name=profile_name)
        )

    async def _run_while_connected(self) -> None:
        """Poll device state every 10 s while connected."""
        assert self._printer is not None
        while self._printer.is_connected:
            if self._state == ServiceState.CONNECTED:
                try:
                    info = await self._printer.query_device_info(timeout=2.0)
                    self._snapshot.battery = info.battery
                    self._snapshot.lid = info.lid
                    self._snapshot.paper = info.paper
                    self._post(
                        DeviceStateUpdated(
                            battery=info.battery,
                            lid=info.lid,
                            paper=info.paper,
                        )
                    )
                except Exception as exc:
                    logger.debug("Poll failed: %s", exc)
            await asyncio.sleep(10.0)

        # BLE connection dropped
        self._printer = None
        self._snapshot = _DeviceSnapshot()
        self._set_state(ServiceState.DISCONNECTED)
        self._post(DeviceDisconnected())
        await asyncio.sleep(2.0)

    async def disconnect(self) -> None:
        """Disconnect the printer and reset state.

        Safe to call when not connected.
        """
        if self._printer is not None:
            await self._printer.disconnect()
            self._printer = None
        self._snapshot = _DeviceSnapshot()
        self._set_state(ServiceState.DISCONNECTED)
        self._post(DeviceDisconnected())

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_device_event(self, event: DeviceEvent) -> None:
        """Handle incoming BLE notification events.

        Args:
            event: Parsed device event from the printer.
        """
        if isinstance(event, BatteryEvent):
            self._snapshot.battery = event.percent
        elif isinstance(event, LidEvent):
            self._snapshot.lid = event.lid
        elif isinstance(event, PaperEvent):
            self._snapshot.paper = event.paper
        else:
            return  # MotorStopEvent etc. handled in print job

        self._post(
            DeviceStateUpdated(
                battery=self._snapshot.battery,
                lid=self._snapshot.lid,
                paper=self._snapshot.paper,
            )
        )

    # ------------------------------------------------------------------
    # Print job (runs as a separate Textual worker)
    # ------------------------------------------------------------------

    async def print_job(self, source: Path, start_page: int | None) -> None:
        """Execute a full print job (single file or multi-page PDF).

        Designed to run as a Textual worker. CancelledError is caught and
        results in paper ejection and a PrintCancelled message.

        Args:
            source: Path to image or PDF.
            start_page: 1-based starting page (None = page 1).
        """
        self._print_task = asyncio.current_task()
        try:
            await self._do_print(source, start_page)
        except asyncio.CancelledError:
            await self._eject_and_cancel()
        except Exception as exc:
            logger.exception("Print job error")
            self._post(PrintError(message=str(exc)))
        finally:
            self._print_task = None
            if self._state not in (
                ServiceState.DISCONNECTED,
                ServiceState.SCANNING,
                ServiceState.CONNECTING,
            ):
                self._set_state(ServiceState.CONNECTED)

    async def _do_print(self, source: Path, start_page: int | None) -> None:
        """Inner print loop. Raises on error or CancelledError on cancel."""
        assert self._printer is not None
        cfg = self._config

        total_pages = get_page_count(source)
        first = start_page if start_page is not None else 1

        if (
            total_pages == 1
            or start_page is not None
            or cfg.multi_page_mode == "manual"
        ):
            pages = [first]
        else:
            # auto: print from first page to end
            pages = list(range(first, total_pages + 1))

        for i, page_num in enumerate(pages):
            # Wait until printer is ready (lid closed, paper present)
            await self._wait_for_ready()

            # Load image for this page
            img = await asyncio.to_thread(load_page_as_pil, source, page_num)

            self._set_state(ServiceState.PRINTING)

            def _on_progress(sent: int, total: int) -> None:
                self._post(PrintProgress(chunks_sent=sent, total_chunks=total))

            await self._printer.print_image(
                source=img,
                density=Density[cfg.density.upper()],
                fit=ImageFit(cfg.fit),
                dither=DitherMode(cfg.dither),
                feed_lines=cfg.feed_lines,
                on_progress=_on_progress,
            )

            self._post(PrintPageComplete(page=page_num, total_pages=total_pages))
            self._set_state(ServiceState.CONNECTED)

            # Auto-mode: wait for next sheet before continuing
            if i < len(pages) - 1:
                next_page = pages[i + 1]
                self._set_state(ServiceState.WAITING_FOR_PAPER)
                self._post(
                    PrintWaitingForPaper(next_page=next_page, total_pages=total_pages)
                )
                await self._wait_for_paper()
                self._set_state(ServiceState.CONNECTED)

        self._post(PrintComplete())

    async def _wait_for_ready(self) -> None:
        """Block until lid is closed and paper is present.

        Posts PrintWaitingForReady if not immediately ready. Raises
        CancelledError if the print task is cancelled while waiting.
        """
        assert self._printer is not None
        self._set_state(ServiceState.WAITING_FOR_READY)

        try:
            info = await self._printer.query_device_info(timeout=2.0)
            self._snapshot.lid = info.lid
            self._snapshot.paper = info.paper
        except Exception:
            pass

        lid_ok = self._snapshot.lid != LidState.OPEN
        paper_ok = self._snapshot.paper != PaperState.ABSENT

        if lid_ok and paper_ok:
            return

        reason: Literal["lid", "paper", "both"]
        if not lid_ok and not paper_ok:
            reason = "both"
        elif not lid_ok:
            reason = "lid"
        else:
            reason = "paper"
        self._post(PrintWaitingForReady(reason=reason))

        while True:
            await asyncio.sleep(1.0)
            try:
                info = await self._printer.query_device_info(timeout=2.0)
                self._snapshot.lid = info.lid
                self._snapshot.paper = info.paper
            except Exception:
                pass
            lid_ok = self._snapshot.lid != LidState.OPEN
            paper_ok = self._snapshot.paper != PaperState.ABSENT
            if lid_ok and paper_ok:
                return

    async def _wait_for_paper(self) -> None:
        """Block until paper is detected.

        Used in auto multi-page mode between pages.
        """
        while True:
            await asyncio.sleep(1.5)
            assert self._printer is not None
            try:
                info = await self._printer.query_device_info(timeout=2.0)
                self._snapshot.paper = info.paper
            except Exception:
                pass
            if self._snapshot.paper == PaperState.PRESENT:
                return

    async def _eject_and_cancel(self) -> None:
        """Eject paper and post PrintCancelled."""
        if self._printer and self._printer.is_connected:
            with contextlib.suppress(Exception):
                await self._printer.eject_paper()
        self._post(PrintCancelled())

    def request_cancel(self) -> None:
        """Cancel the running print task, if any."""
        if self._print_task is not None and not self._print_task.done():
            self._print_task.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_state(self, state: ServiceState) -> None:
        self._state = state


def match_profile(name: str | None) -> str | None:
    """Return the first profile name whose ble_name_pattern matches name.

    Args:
        name: BLE advertised device name, or None.

    Returns:
        Profile name string, or None if no match.
    """
    if not name:
        return None
    for profile_name in list_profiles():
        profile = get_profile(profile_name)
        if re.search(profile.ble_name_pattern, name):
            return profile_name
    return None
