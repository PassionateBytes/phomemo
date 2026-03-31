"""Textual message types for service-to-UI and UI-to-service communication."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from phomemo.events import LidState, PaperState
from textual.message import Message

# ---------------------------------------------------------------------------
# Service → UI
# ---------------------------------------------------------------------------


class DeviceScanStarted(Message):
    """PrinterService has begun scanning for BLE devices."""


class DeviceConnected(Message):
    """PrinterService successfully connected to a printer.

    Attributes:
        address: BLE MAC address.
        name: Advertised device name.
        profile_name: Active printer profile name.
    """

    def __init__(self, address: str, name: str, profile_name: str) -> None:
        super().__init__()
        self.address = address
        self.name = name
        self.profile_name = profile_name


class DeviceDisconnected(Message):
    """PrinterService lost or closed the BLE connection."""


class DeviceStateUpdated(Message):
    """Device sensor state snapshot received from polling or spontaneous event.

    Attributes:
        battery: Battery percentage, or None if unknown.
        lid: Lid state, or None if unknown.
        paper: Paper presence, or None if unknown.
    """

    def __init__(
        self,
        battery: int | None,
        lid: LidState | None,
        paper: PaperState | None,
    ) -> None:
        super().__init__()
        self.battery = battery
        self.lid = lid
        self.paper = paper


class PrintWaitingForReady(Message):
    """Printer is not ready to print; waiting for the user to fix it.

    Attributes:
        reason: Which condition is blocking: 'lid', 'paper', or 'both'.
    """

    def __init__(self, reason: Literal["lid", "paper", "both"]) -> None:
        super().__init__()
        self.reason = reason


class PrintProgress(Message):
    """Print chunk progress update.

    Attributes:
        chunks_sent: Chunks transmitted so far.
        total_chunks: Total chunks in this page.
    """

    def __init__(self, chunks_sent: int, total_chunks: int) -> None:
        super().__init__()
        self.chunks_sent = chunks_sent
        self.total_chunks = total_chunks


class PrintPageComplete(Message):
    """One page of a multi-page job finished printing.

    Attributes:
        page: 1-based page number just printed.
        total_pages: Total pages in the job.
    """

    def __init__(self, page: int, total_pages: int) -> None:
        super().__init__()
        self.page = page
        self.total_pages = total_pages


class PrintWaitingForPaper(Message):
    """Auto-sequence mode is waiting for the user to feed the next sheet.

    Attributes:
        next_page: 1-based page number that will print next.
        total_pages: Total pages in the job.
    """

    def __init__(self, next_page: int, total_pages: int) -> None:
        super().__init__()
        self.next_page = next_page
        self.total_pages = total_pages


class PrintComplete(Message):
    """All pages of the print job finished successfully."""


class PrintError(Message):
    """Print job failed with an error.

    Attributes:
        message: Human-readable error description.
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message


class PrintCancelled(Message):
    """Print job was cancelled by the user."""


# ---------------------------------------------------------------------------
# UI → Service (routed via PhomemoApp)
# ---------------------------------------------------------------------------


class PrintRequested(Message):
    """User pressed the Print button.

    Attributes:
        source: Path to the image or PDF file.
        start_page: 1-based page to start from, or None for default (page 1).
    """

    def __init__(self, source: Path, start_page: int | None) -> None:
        super().__init__()
        self.source = source
        self.start_page = start_page


class CancelPrintRequested(Message):
    """User pressed the Cancel button during a print job."""


class FileSelected(Message):
    """User picked a file in the file picker.

    Attributes:
        path: Absolute path of the selected file.
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
