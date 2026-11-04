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

"""Tests for the test page renderer."""

from pathlib import Path

import phomemo.profiles  # noqa: F401, registers built-in profiles
from phomemo.bridge.testpage import (
    PageInfo,
    page_lines,
    render_test_page,
    save_test_page,
)
from phomemo.registry import get_profile
from PIL import Image

A4 = get_profile("M08F-A4")


def _info() -> PageInfo:
    return PageInfo(
        printer_name="Phomemo M08F",
        address="AA:BB:CC:DD:EE:FF",
        firmware="1.1.3",
        serial="<serial>",
        battery=77,
        auto_off_minutes=10,
        chunk_bytes=244,
        versions={
            "phomemo-printer-app": "0.1.0",
            "pappl": "1.4.12",
            "phomemo": "0.1.0",
        },
        socket_path="/run/user/1000/phomemo-bridge.sock",
    )


def test_render_fills_the_imageable_a4_area_at_printer_resolution() -> None:
    img = render_test_page(_info(), A4, 297.0)
    assert img.mode == "L"
    # 210 mm wide, 297 mm minus a 10 mm margin at each end, at 203 dpi.
    assert img.size == (1678, 2213)
    # Border, ruler and text leave ink; the gray ramp leaves mid tones.
    histogram = img.histogram()
    assert histogram[0] > 10_000
    assert sum(histogram[64:192]) > 10_000


def test_page_lines_carry_the_device_and_software_details() -> None:
    text = "\n".join(page_lines(_info(), A4, 297.0))
    for expected in ("AA:BB:CC:DD:EE:FF", "1.1.3", "77 %", "pappl 1.4.12", "244 bytes"):
        assert expected in text
    assert f"{A4.rows_for(297.0)} printable rows" in text


def test_save_writes_a_png_tagged_with_the_printer_resolution(tmp_path: Path) -> None:
    path = save_test_page(render_test_page(_info(), A4, 297.0), tmp_path / "t.png")
    with Image.open(path) as saved:
        assert saved.format == "PNG"
        # PNG stores pixels per metre, so the value comes back a hair off.
        assert tuple(round(v) for v in saved.info["dpi"]) == (203, 203)
