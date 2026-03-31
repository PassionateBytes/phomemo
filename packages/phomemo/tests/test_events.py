"""Tests for device event parsing and invariants."""

from phomemo.events import BatteryEvent, EventKind


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
