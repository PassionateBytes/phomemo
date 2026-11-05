# This file is part of phomemo.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with phomemo.  If not, see <https://www.gnu.org/licenses/>.

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

    profile = get_profile("m08f")
    assert profile.sheet_length_mm == 297.0
    assert profile.top_margin_mm == 10.0
    assert profile.bottom_margin_mm == 5.0
    assert profile.max_rows == 2253


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

    profile = get_profile("m08f")
    assert profile.rows_for(297.0) == 2253 == profile.max_rows


def test_rows_for_a5_turned() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    assert get_profile("m08f").rows_for(148.0) == 1062


def test_rows_for_none_is_roll() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    assert get_profile("m08f").rows_for(None) is None


def test_lead_rows_a4() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    assert get_profile("m08f").lead_rows == 80


def test_rows_for_rejects_length_inside_margins() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    with pytest.raises(ValueError, match="margin"):
        get_profile("m08f").rows_for(10.0)


def test_media_size_from_pwg_name_in_millimetres() -> None:
    from phomemo.registry import MediaSize

    size = MediaSize.from_pwg("iso_a4_210x297mm")
    assert size == MediaSize("iso_a4_210x297mm", 210.0, 297.0)
    assert size.tested


def test_media_size_from_pwg_name_in_inches() -> None:
    from phomemo.registry import MediaSize

    size = MediaSize.from_pwg("na_letter_8.5x11in", tested=False)
    assert size.pwg == "na_letter_8.5x11in"
    assert (size.width_mm, size.length_mm) == (
        pytest.approx(215.9),
        pytest.approx(279.4),
    )
    assert not size.tested


@pytest.mark.parametrize("name", ["letter", "iso_a4_210x297", "na_letter_8.5x11cm"])
def test_media_size_rejects_names_without_dimensions(name: str) -> None:
    from phomemo.registry import MediaSize

    with pytest.raises(ValueError, match="PWG"):
        MediaSize.from_pwg(name)


def test_sheet_length_is_the_dimension_along_the_feed() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    profile = get_profile("m08f")
    a4, a5, letter = (
        profile.medium(name)
        for name in ("iso_a4_210x297mm", "iso_a5_148x210mm", "na_letter_8.5x11in")
    )
    assert profile.sheet_length_for(a4) == 297.0
    assert profile.sheet_length_for(a5) == 148.0
    assert profile.sheet_length_for(letter) == pytest.approx(279.4)
    assert not profile.rotates(a4)
    assert profile.rotates(a5)
    assert not profile.rotates(letter)


def test_medium_rejects_a_size_the_model_does_not_take() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    with pytest.raises(KeyError, match="iso_b5"):
        get_profile("m08f").medium("iso_b5_176x250mm")


def test_rows_for_letter() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    assert get_profile("m08f").rows_for(279.4) == 2113


def test_lead_rows_do_not_depend_on_the_sheet() -> None:
    import phomemo.profiles  # noqa: F401, registers built-in profiles
    from phomemo.registry import get_profile

    profile = get_profile("m08f")
    assert profile.lead_rows == 80
    assert profile.rows_for(297.0) == 2253
    assert profile.rows_for(148.0) == 1062
