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

"""Built-in printer profiles for the Phomemo M08F.

Registers the M08F-A4 profile on import. Profile data is
derived from the M08F Protocol Reference document.

Third-party code can follow the same pattern: define ``PrinterProfile``
instances and pass them to ``register_profile``.
"""

from phomemo.registry import PrinterProfile

_M08F_WRITE = "00000000-0000-0000-0000-00000000ff02"
_M08F_NOTIFY = "00000000-0000-0000-0000-00000000ff01"
_M08F_STATUS = "00000000-0000-0000-0000-00000000ff03"

# The sensor sits 10mm ahead of the head, so the first 10mm of a sheet cannot be
# printed. The bottom margin keeps the raster off the sheet end; a page longer
# than that is clipped.
_TOP_MARGIN_MM = 10.0
_BOTTOM_MARGIN_MM = 5.0

M08F_A4 = PrinterProfile(
    name="M08F-A4",
    ble_name_pattern=r"^M08F",
    print_width_px=1680,
    sheet_length_mm=297.0,
    top_margin_mm=_TOP_MARGIN_MM,
    bottom_margin_mm=_BOTTOM_MARGIN_MM,
    write_uuid=_M08F_WRITE,
    notify_uuid=_M08F_NOTIFY,
    status_uuid=_M08F_STATUS,
)
