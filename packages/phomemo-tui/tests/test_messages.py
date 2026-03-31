"""Smoke tests – messages instantiate without error."""

from pathlib import Path

from phomemo.events import LidState, PaperState
from phomemo_tui.messages import (
    CancelPrintRequested,
    DeviceConnected,
    DeviceDisconnected,
    DeviceScanStarted,
    DeviceStateUpdated,
    FileSelected,
    PrintCancelled,
    PrintComplete,
    PrintError,
    PrintPageComplete,
    PrintProgress,
    PrintRequested,
    PrintWaitingForPaper,
    PrintWaitingForReady,
)


def test_device_connected() -> None:
    m = DeviceConnected(address="AA:BB", name="M08F-001", profile_name="M08F-A4")
    assert m.address == "AA:BB"


def test_device_state_updated() -> None:
    m = DeviceStateUpdated(battery=80, lid=LidState.CLOSED, paper=PaperState.PRESENT)
    assert m.battery == 80


def test_print_waiting_for_ready() -> None:
    m = PrintWaitingForReady(reason="lid")
    assert m.reason == "lid"


def test_print_progress() -> None:
    m = PrintProgress(chunks_sent=5, total_chunks=20)
    assert m.chunks_sent == 5


def test_print_page_complete() -> None:
    m = PrintPageComplete(page=1, total_pages=3)
    assert m.total_pages == 3


def test_print_waiting_for_paper() -> None:
    m = PrintWaitingForPaper(next_page=2, total_pages=3)
    assert m.next_page == 2


def test_print_requested() -> None:
    m = PrintRequested(source=Path("/tmp/a.png"), start_page=None)
    assert m.source == Path("/tmp/a.png")


def test_file_selected() -> None:
    m = FileSelected(path=Path("/tmp/x.pdf"))
    assert m.path.suffix == ".pdf"
