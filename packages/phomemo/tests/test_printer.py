import asyncio

import pytest
from phomemo.events import (
    BatteryEvent,
    DeviceEvent,
    EventKind,
    LidEvent,
    LidState,
    MotorStopEvent,
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

    async def connect(self, *args: object, **kwargs: object) -> None:
        pass

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
    result = await printer._query(QueryCommand.BATTERY, timeout=0.5)

    # The battery event should be in the query result
    battery_events = [e for e in result if isinstance(e, BatteryEvent)]
    assert len(battery_events) == 1
    assert battery_events[0].percent == 75

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
