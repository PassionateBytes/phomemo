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

"""BLE device discovery for Phomemo printers.

Wraps ``bleak.BleakScanner`` to find nearby BLE devices, with optional
regex filtering on advertised names.
"""

import logging
import re

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

logger = logging.getLogger(__name__)


async def discover(
    name_pattern: str | None = None,
    timeout: float = 5.0,
) -> list[BLEDevice]:
    """Discover nearby BLE devices, optionally filtered by name pattern.

    Args:
        name_pattern: If provided, only return devices whose advertised
            name matches this regex pattern (searched, not full-match).
        timeout: Scan duration in seconds.

    Returns:
        List of discovered ``BLEDevice`` objects, sorted by name.

    Raises:
        ConnectionError: If the Bluetooth adapter is unavailable or the
            scan fails at the OS/adapter level.
    """
    logger.debug("Starting BLE scan (timeout=%.1fs, pattern=%s)", timeout, name_pattern)
    try:
        discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    except BleakError as exc:
        raise ConnectionError(
            f"Bluetooth scan failed, is the adapter powered on? {exc}"
        ) from exc
    devices = [dev for dev, _ in discovered.values()]

    if name_pattern is not None:
        compiled = re.compile(name_pattern)
        all_devices = devices
        devices = [d for d in all_devices if d.name and compiled.search(d.name)]
        logger.debug(
            "Pattern %r matched %d of %d device(s)",
            name_pattern,
            len(devices),
            len(all_devices),
        )

    logger.debug("Scan complete: %d device(s) found", len(devices))
    return sorted(devices, key=lambda d: d.name or "")
