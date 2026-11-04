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

"""Shared fixtures: no test scans for real Bluetooth devices."""

import phomemo.bridge.server as server_module
import pytest
from bleak.backends.device import BLEDevice

IN_RANGE_ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture(autouse=True)
def one_m08f_in_range(monkeypatch: pytest.MonkeyPatch) -> list[BLEDevice]:
    """Make the bridge's scans find one M08F; tests may change the list."""
    in_range = [BLEDevice(address=IN_RANGE_ADDRESS, name="M08F", details=None)]

    async def fake_discover(name_pattern: str, timeout: float) -> list[BLEDevice]:
        return list(in_range)

    monkeypatch.setattr(server_module, "discover", fake_discover)
    return in_range
