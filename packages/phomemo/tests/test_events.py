"""Tests for device event parsing and invariants."""

from phomemo.events import (
    BatteryEvent,
    EventKind,
    LidEvent,
    LidState,
    PaperEvent,
    PaperState,
    parse_notification,
)


def test_battery_event_clamps_high_value() -> None:
    """BatteryEvent should clamp percent values above 100 to 100."""
    event = BatteryEvent(kind=EventKind.BATTERY, percent=150)
    assert event.percent == 100


def test_battery_event_clamps_negative_value() -> None:
    """BatteryEvent should clamp negative percent values to 0."""
    event = BatteryEvent(kind=EventKind.BATTERY, percent=-5)
    assert event.percent == 0


def test_battery_event_preserves_valid_value() -> None:
    """BatteryEvent should preserve percent values within 0-100."""
    event = BatteryEvent(kind=EventKind.BATTERY, percent=64)
    assert event.percent == 64


def test_lid_event_from_notification() -> None:
    """parse_notification should return a LidEvent for lid sub-type."""
    events = parse_notification(bytes([0x1A, 0x05, 0x99]))
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, LidEvent)
    assert event.lid == LidState.OPEN


def test_paper_event_from_notification() -> None:
    """parse_notification should return a PaperEvent for paper sub-type."""
    events = parse_notification(bytes([0x1A, 0x06, 0x89]))
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, PaperEvent)
    assert event.paper == PaperState.PRESENT


def test_lid_event_closed() -> None:
    """LidEvent should reflect CLOSED state when LSB is 0."""
    events = parse_notification(bytes([0x1A, 0x05, 0x98]))
    event = events[0]
    assert isinstance(event, LidEvent)
    assert event.lid == LidState.CLOSED


def test_paper_event_absent() -> None:
    """PaperEvent should reflect ABSENT state when LSB is 0."""
    events = parse_notification(bytes([0x1A, 0x06, 0x88]))
    event = events[0]
    assert isinstance(event, PaperEvent)
    assert event.paper == PaperState.ABSENT
