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

from phomemo.protocol import QueryCommand


def test_query_command_is_bytes():
    assert isinstance(QueryCommand.BATTERY, bytes)
    assert QueryCommand.BATTERY == b"\x1f\x11\x08"


def test_query_command_members():
    names = [m.name for m in QueryCommand]
    assert "BATTERY" in names
    assert "FIRMWARE" in names
    assert "OTA_REBOOT" not in names
