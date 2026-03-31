"""ESC/POS and Phomemo command encoding.

Implements command construction for the Phomemo printer protocol. All
byte sequences are derived from the M08F Protocol Reference document.

The M08F uses a subset of ESC/POS plus Phomemo-specific extensions:
- ``GS v 0`` for raster printing (the only print command)
- ``ESC N 04`` for density/concentration control
- ``ESC d`` for paper feed
- ``1f 11 XX`` for device information queries
- ``ESC @`` for printer state initialization

Commands are encoded as plain ``bytes`` objects — the transport layer
handles chunking and BLE writes.
"""

from enum import IntEnum


class Density(IntEnum):
    """Print density (concentration) levels for ESC N 04.

    Values map directly to the ESC N 04 concentration byte. The M08F
    saturates at level 6 — higher values produce no further darkening.

    From the reference doc:
        0–4 = light (default), 5 = medium, 6+ = dark (saturated).
    Tested mappings: low=1, medium=5, high=6.
    """

    LOW = 1
    MEDIUM = 5
    HIGH = 6


class ScaleMode(IntEnum):
    """GS v 0 raster scaling modes.

    Controls how the printer scales raster data. The data format sent
    must match the mode — double-width mode expects half-width data.
    """

    NORMAL = 0x00
    DOUBLE_WIDTH = 0x01
    DOUBLE_HEIGHT = 0x02
    QUADRUPLE = 0x03


# ---------------------------------------------------------------------------
# Printer initialisation
# ---------------------------------------------------------------------------


def encode_init() -> bytes:
    """Encode ``ESC @`` — initialize printer state.

    Resets the printer to its default configuration. Must precede
    standalone ESC-prefix commands to prevent bridge chip interception.

    Returns:
        The 2-byte ESC @ command.
    """
    return b"\x1b\x40"


# ---------------------------------------------------------------------------
# Density / concentration
# ---------------------------------------------------------------------------


def encode_density(level: Density) -> bytes:
    """Encode ``ESC N 04 <n>`` — set print concentration.

    This is the **only working density command** on the M08F. Persists
    until the next ``ESC @`` reset or another ``ESC N 04`` call.

    Must be preceded by ``ESC @`` or embedded in a larger write to
    avoid bridge chip interception.

    Args:
        level: Concentration value (see ``Density`` enum).

    Returns:
        The 4-byte ESC N 04 command.
    """
    return b"\x1b\x4e\x04" + bytes([int(level)])


# ---------------------------------------------------------------------------
# Raster printing (GS v 0)
# ---------------------------------------------------------------------------


def encode_raster_header(
    width_bytes: int,
    height: int,
    mode: ScaleMode = ScaleMode.NORMAL,
) -> bytes:
    """Encode ``GS v 0`` raster bit image header.

    The header is followed by ``width_bytes * height`` bytes of raw
    1-bit bitmap data (MSB-first, 1=black, 0=white).

    Args:
        width_bytes: Image width in bytes (pixels / 8).
        height: Number of rows in this raster band.
        mode: Scaling mode (default: normal 1:1).

    Returns:
        The 8-byte GS v 0 header.
    """
    return (
        b"\x1d\x76\x30"
        + bytes([int(mode)])
        + width_bytes.to_bytes(2, "little")
        + height.to_bytes(2, "little")
    )


# ---------------------------------------------------------------------------
# Paper feed and transport
# ---------------------------------------------------------------------------


def encode_feed_lines(lines: int) -> bytes:
    """Encode ``ESC d <n>`` — feed n lines.

    Each line is approximately one dot row (0.125mm at 203 DPI).
    Maximum 255 per call. ``ESC d 255`` feeds approximately 32mm.

    Args:
        lines: Number of lines to feed (1–255).

    Returns:
        The 3-byte ESC d command.

    Raises:
        ValueError: If lines is outside the 1–255 range.
    """
    if not 1 <= lines <= 255:
        raise ValueError(f"Feed lines must be 1–255, got {lines}")
    return b"\x1b\x64" + bytes([lines])


def encode_paper_eject(repetitions: int = 12) -> bytes:
    """Encode a paper eject sequence (repeated ``ESC d 255``).

    Ejects the current sheet by chaining multiple maximum-length feed
    commands. 12 repetitions produce ~384mm of feed, sufficient for A4
    paper (297mm) with margin.

    Args:
        repetitions: Number of ``ESC d 255`` commands to chain.

    Returns:
        The concatenated feed commands.
    """
    return b"\x1b\x64\xff" * repetitions


# ---------------------------------------------------------------------------
# Device information queries (Phomemo 1f 11 XX family)
# ---------------------------------------------------------------------------


class QueryCommand:
    """Phomemo-specific device queries (``1f 11 XX``).

    Write these to ``ff02``; responses arrive on ``ff01`` as
    ``1a <sub-type> <data>`` messages. The response sub-type does NOT
    always match the query parameter.

    Each class attribute holds the raw 3-byte command.
    """

    BATTERY = b"\x1f\x11\x08"
    FIRMWARE = b"\x1f\x11\x07"
    SERIAL_ASCII = b"\x1f\x11\x09"
    SERIAL_SHORT = b"\x1f\x11\x13"
    PAPER_STATE = b"\x1f\x11\x11"
    LID_STATE = b"\x1f\x11\x12"
    DEVICE_TIMER = b"\x1f\x11\x0e"
    OTA_REBOOT = b"\x1f\x11\x0f"


# ---------------------------------------------------------------------------
# Device configuration
# ---------------------------------------------------------------------------


def encode_auto_off_timer(value: int) -> bytes:
    """Encode ``ESC N 07 <value>`` — set auto-off timer.

    Must be preceded by ``ESC @`` to avoid bridge chip interception.

    Args:
        value: Timer value. 0 = disabled, non-zero = timeout in
            5-minute increments (1 = 5min, 2 = 10min, etc.).

    Returns:
        The 4-byte ESC N 07 command.

    Raises:
        ValueError: If value is outside 0–255.
    """
    if not 0 <= value <= 255:
        raise ValueError(f"Timer value must be 0–255, got {value}")
    return b"\x1b\x4e\x07" + bytes([value])
