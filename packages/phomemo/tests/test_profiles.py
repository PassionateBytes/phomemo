"""Tests for PrinterProfile validation."""

import pytest
from phomemo.registry import PrinterProfile

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


def test_a4_profile_printable_area() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    profile = get_profile("M08F-A4")
    assert profile.sheet_length_mm == 297.0
    assert profile.top_margin_mm == 10.0
    assert profile.bottom_margin_mm == 5.0
    assert profile.max_rows == 2253


def test_letter_profile_uses_the_same_margins() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    profile = get_profile("M08F-Letter")
    assert profile.sheet_length_mm == 279.4
    assert profile.max_rows == 2113


def test_profile_rejects_margins_that_consume_the_sheet() -> None:
    with pytest.raises(ValueError, match="margin"):
        _make_profile(sheet_length_mm=20.0, top_margin_mm=10.0, bottom_margin_mm=10.0)


def test_profile_rejects_non_positive_sheet_length() -> None:
    with pytest.raises(ValueError, match="sheet_length_mm"):
        _make_profile(sheet_length_mm=0.0)


def test_roll_profile_has_no_max_rows() -> None:
    profile = _make_profile(sheet_length_mm=None)
    assert profile.max_rows is None


def test_rows_for_a4_matches_max_rows() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    profile = get_profile("M08F-A4")
    assert profile.rows_for(297.0) == 2253 == profile.max_rows


def test_rows_for_a5_turned() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    assert get_profile("M08F-A4").rows_for(148.0) == 1062


def test_rows_for_none_is_roll() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    assert get_profile("M08F-A4").rows_for(None) is None


def test_lead_rows_a4() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    assert get_profile("M08F-A4").lead_rows == 80


def test_rows_for_rejects_length_inside_margins() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    with pytest.raises(ValueError, match="margin"):
        get_profile("M08F-A4").rows_for(10.0)
