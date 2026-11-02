import asyncio

import phomemo.printer as printer_module
import phomemo.profiles  # noqa: F401, registers built-in profiles
import pytest
from bleak.backends.device import BLEDevice
from phomemo.events import (
    BatteryEvent,
    DeviceEvent,
    EventKind,
    LidEvent,
    LidState,
    MotorStopEvent,
    PaperState,
)
from phomemo.printer import Printer
from phomemo.protocol import QueryCommand


class FakeTransport:
    """Minimal transport stub for testing event routing."""

    def __init__(self) -> None:
        self.is_connected = True
        self.written: list[bytes] = []

    async def write(self, data: bytes) -> None:
        self.written.append(data)

    async def write_chunked(self, data: bytes, on_chunk: object = None) -> None:
        self.written.append(data)

    async def connect(self, address: object, **kwargs: object) -> None:
        self.connect_address = address

    async def disconnect(self) -> None:
        pass


def _make_printer() -> Printer:
    """Create a Printer with a fake transport for testing."""
    printer = Printer("M08F-A4")
    printer._transport = FakeTransport()  # type: ignore[assignment]
    return printer


@pytest.mark.asyncio
async def test_query_does_not_eat_unrelated_events():
    """Events not matching the query type should still reach callbacks."""
    printer = _make_printer()
    received: list[DeviceEvent] = []
    printer.on_event(received.append)

    async def inject_events():
        await asyncio.sleep(0.01)
        printer._dispatch_event(LidEvent(kind=EventKind.LID, lid=LidState.OPEN))
        await asyncio.sleep(0.01)
        printer._dispatch_event(BatteryEvent(kind=EventKind.BATTERY, percent=75))

    asyncio.create_task(inject_events())
    result = await printer._query(QueryCommand.BATTERY, BatteryEvent, timeout=0.5)

    assert isinstance(result, BatteryEvent)
    assert result.percent == 75

    # The lid event should have reached the callback
    lid_events = [e for e in received if isinstance(e, LidEvent)]
    assert len(lid_events) == 1


@pytest.mark.asyncio
async def test_wait_for_motor_stop_does_not_eat_other_events():
    """Non-MotorStop events during wait should still reach callbacks."""
    printer = _make_printer()
    received: list[DeviceEvent] = []
    printer.on_event(received.append)

    async def inject_events():
        await asyncio.sleep(0.01)
        printer._dispatch_event(LidEvent(kind=EventKind.LID, lid=LidState.CLOSED))
        await asyncio.sleep(0.01)
        printer._dispatch_event(MotorStopEvent(kind=EventKind.MOTOR_STOP))

    asyncio.create_task(inject_events())
    await printer._wait_for_motor_stop(timeout=1.0)

    # Both events should have reached the callback
    assert len(received) == 2


_MAC = "60:6E:41:23:0B:D6"


def _fake_device() -> BLEDevice:
    return BLEDevice(address=_MAC, name="M08F", details=None)


@pytest.mark.asyncio
async def test_connect_passes_discovered_bledevice_to_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = _fake_device()

    async def fake_discover(name_pattern: str, timeout: float) -> list[BLEDevice]:
        return [device]

    monkeypatch.setattr(printer_module, "discover", fake_discover)
    printer = _make_printer()
    await printer.connect()
    assert printer._transport.connect_address is device  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_connect_resolves_mac_string_via_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = _fake_device()
    seen: list[tuple[str, float]] = []

    async def fake_find(address: str, timeout: float) -> BLEDevice | None:
        seen.append((address, timeout))
        return device

    monkeypatch.setattr(
        printer_module.BleakScanner, "find_device_by_address", fake_find
    )
    printer = Printer("M08F-A4", _MAC)
    printer._transport = FakeTransport()  # type: ignore[assignment]
    await printer.connect(discovery_timeout=3.0)
    assert seen == [(_MAC, 3.0)]
    assert printer._transport.connect_address is device  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_connect_unresolvable_mac_raises_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_find(address: str, timeout: float) -> BLEDevice | None:
        return None

    monkeypatch.setattr(
        printer_module.BleakScanner, "find_device_by_address", fake_find
    )
    printer = Printer("M08F-A4", _MAC)
    printer._transport = FakeTransport()  # type: ignore[assignment]
    with pytest.raises(ConnectionError, match=_MAC):
        await printer.connect()


@pytest.mark.asyncio
async def test_connect_bledevice_instance_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_find(address: str, timeout: float) -> BLEDevice | None:
        raise AssertionError("scanner must not be used for a BLEDevice")

    monkeypatch.setattr(
        printer_module.BleakScanner, "find_device_by_address", fail_find
    )
    device = _fake_device()
    printer = Printer("M08F-A4", device)
    printer._transport = FakeTransport()  # type: ignore[assignment]
    await printer.connect()
    assert printer._transport.connect_address is device  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_print_bitmap_warns_above_max_rows(
    caplog: pytest.LogCaptureFixture,
) -> None:
    printer = _make_printer()
    width_bytes = printer.profile.width_bytes
    with caplog.at_level("WARNING", logger="phomemo.printer"):
        await printer.print_bitmap(
            bytes(width_bytes * 2290), height=2290, wait_for_completion=False
        )
        assert not caplog.records
        await printer.print_bitmap(
            bytes(width_bytes * 2291), height=2291, wait_for_completion=False
        )
    assert len(caplog.records) == 1
    assert "2291" in caplog.records[0].getMessage()
    assert "2290" in caplog.records[0].getMessage()


_FEED_255 = b"\x1b\x64\xff"


def _scripted(values: list[object]) -> object:
    """Async stub returning scripted values in order, repeating the last one."""

    async def stub(*_args: object, **_kwargs: object) -> object:
        return values.pop(0) if len(values) > 1 else values[0]

    return stub


def _eject_printer(monkeypatch: pytest.MonkeyPatch, paper: list[object]) -> Printer:
    printer = _make_printer()
    monkeypatch.setattr(printer, "query_paper", _scripted(paper))

    async def no_sleep(_delay: float) -> None:
        pass

    monkeypatch.setattr(printer_module.asyncio, "sleep", no_sleep)
    return printer


def _feeds(printer: Printer) -> int:
    return printer._transport.written.count(_FEED_255)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_eject_stops_after_sensor_reports_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _eject_printer(
        monkeypatch, [PaperState.PRESENT, PaperState.PRESENT, PaperState.ABSENT]
    )
    assert await printer.eject_paper() is True
    assert _feeds(printer) == 4


@pytest.mark.asyncio
async def test_eject_gives_the_sensor_two_seconds_after_a_feed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _eject_printer(monkeypatch, [PaperState.ABSENT])
    timeouts: list[float] = []

    async def record(timeout: float) -> PaperState:
        timeouts.append(timeout)
        return PaperState.ABSENT

    monkeypatch.setattr(printer, "query_paper", record)
    await printer.eject_paper()
    assert timeouts == [2.0]


@pytest.mark.asyncio
async def test_eject_treats_query_timeout_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _eject_printer(monkeypatch, [None])
    assert await printer.eject_paper() is True
    assert _feeds(printer) == 2


@pytest.mark.asyncio
async def test_eject_gives_up_at_max_feeds(monkeypatch: pytest.MonkeyPatch) -> None:
    printer = _eject_printer(monkeypatch, [PaperState.PRESENT])
    assert await printer.eject_paper(max_feeds=3) is False
    assert _feeds(printer) == 3


@pytest.mark.asyncio
async def test_eject_already_absent_returns_after_one_clearing_feed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _eject_printer(monkeypatch, [PaperState.ABSENT])
    assert await printer.eject_paper() is True
    assert _feeds(printer) == 2


@pytest.mark.asyncio
async def test_wait_for_ready_returns_when_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _make_printer()
    monkeypatch.setattr(
        printer, "check_ready", _scripted([(False, "Lid is open"), (True, "ready")])
    )

    async def no_sleep(_delay: float) -> None:
        pass

    monkeypatch.setattr(printer_module.asyncio, "sleep", no_sleep)
    assert await printer.wait_for_ready(timeout=1.0, poll=0.01) is None


@pytest.mark.asyncio
async def test_wait_for_ready_times_out_with_last_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _make_printer()
    monkeypatch.setattr(printer, "check_ready", _scripted([(False, "No paper loaded")]))
    with pytest.raises(TimeoutError, match="No paper loaded"):
        await printer.wait_for_ready(timeout=0.05, poll=0.01)


@pytest.mark.asyncio
async def test_print_bitmap_never_warns_without_max_rows(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from dataclasses import replace

    printer = Printer(replace(printer_module.get_profile("M08F-A4"), max_rows=None))
    printer._transport = FakeTransport()  # type: ignore[assignment]
    width_bytes = printer.profile.width_bytes
    with caplog.at_level("WARNING", logger="phomemo.printer"):
        await printer.print_bitmap(
            bytes(width_bytes * 5000), height=5000, wait_for_completion=False
        )
    assert not caplog.records
