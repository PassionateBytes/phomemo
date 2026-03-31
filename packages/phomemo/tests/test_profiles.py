"""Tests for PrinterProfile validation."""

import pytest
from phomemo.profiles import PrinterProfile

_VALID_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
_VALID_WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
_VALID_NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
_VALID_STATUS_UUID = "0000ff03-0000-1000-8000-00805f9b34fb"


def _make_profile(**overrides: object) -> PrinterProfile:
    """Create a valid PrinterProfile with optional field overrides."""
    defaults: dict[str, object] = {
        "name": "TestPrinter",
        "ble_name_pattern": r"^Test",
        "print_width_px": 576,
        "service_uuid": _VALID_UUID,
        "write_uuid": _VALID_WRITE_UUID,
        "notify_uuid": _VALID_NOTIFY_UUID,
        "status_uuid": _VALID_STATUS_UUID,
    }
    defaults.update(overrides)
    return PrinterProfile(**defaults)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_profile_rejects_non_multiple_of_8_width() -> None:
    """PrinterProfile raises ValueError when print_width_px is not a multiple of 8."""
    with pytest.raises(ValueError, match="print_width_px"):
        _make_profile(print_width_px=577)


def test_profile_accepts_valid_width() -> None:
    """PrinterProfile should accept print_width_px values that are multiples of 8."""
    profile = _make_profile(print_width_px=576)
    assert profile.print_width_px == 576


def test_profile_rejects_invalid_uuid_format() -> None:
    """PrinterProfile raises ValueError for a UUID field with an invalid format."""
    with pytest.raises(ValueError, match="service_uuid"):
        _make_profile(service_uuid="not-a-uuid")


def test_profile_accepts_valid_uuids() -> None:
    """PrinterProfile should accept correctly formatted UUID strings."""
    profile = _make_profile()
    assert profile.service_uuid == _VALID_UUID
