"""BLE device discovery for Phomemo printers.

Wraps ``bleak.BleakScanner`` to find nearby BLE devices, with optional
regex filtering on advertised names.
"""

import logging
import re

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

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
    """
    logger.debug("Starting BLE scan (timeout=%.1fs, pattern=%s)", timeout, name_pattern)
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    devices = [dev for dev, _ in discovered.values()]

    if name_pattern is not None:
        compiled = re.compile(name_pattern)
        devices = [d for d in devices if d.name and compiled.search(d.name)]

    logger.debug("Scan complete: %d device(s) found", len(devices))
    return sorted(devices, key=lambda d: d.name or "")
