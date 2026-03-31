"""Device event parsing for Phomemo printer notifications.

All events arrive on the ``ff01`` BLE characteristic as ``1a <sub-type>
<data>`` messages. Events can be spontaneous (triggered by physical
state changes) or solicited (responses to ``1f 11 XX`` queries). Both
use the same ``1a``-prefixed format.

Multiple 3-byte events can arrive concatenated in a single BLE
notification. The parser consumes 3 bytes at a time.
"""

import logging
from dataclasses import dataclass
from enum import IntEnum, StrEnum

logger = logging.getLogger(__name__)


class EventKind(IntEnum):
    """Event sub-type byte in ``1a <sub-type> <data>`` messages.

    Maps the second byte of each event to its semantic meaning.
    """

    SERIAL_SHORT = 0x03
    BATTERY = 0x04
    LID = 0x05
    PAPER = 0x06
    FIRMWARE = 0x07
    SERIAL_ASCII = 0x08
    DEVICE_TIMER = 0x09
    MOTOR_STOP = 0x0F


class LidState(StrEnum):
    """Physical lid position."""

    CLOSED = "closed"
    OPEN = "open"


class PaperState(StrEnum):
    """Paper presence as reported by the rear optical sensor."""

    PRESENT = "present"
    ABSENT = "absent"


# ---------------------------------------------------------------------------
# Parsed event types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeviceEvent:
    """Base class for all device events.

    Used directly as a fallback for unrecognised event sub-types.

    Attributes:
        kind: The event sub-type byte.
        raw: The original raw bytes from the notification.
    """

    kind: int
    raw: bytes = b""


@dataclass(frozen=True, slots=True)
class LidEvent(DeviceEvent):
    """Lid state change event.

    Attributes:
        lid: Current lid state.
    """

    lid: LidState = LidState.CLOSED


@dataclass(frozen=True, slots=True)
class PaperEvent(DeviceEvent):
    """Paper presence change event.

    Attributes:
        paper: Current paper state.
    """

    paper: PaperState = PaperState.ABSENT


@dataclass(frozen=True, slots=True)
class BatteryEvent(DeviceEvent):
    """Battery level report.

    Attributes:
        percent: Battery charge percentage (0-100).
    """

    percent: int = 0

    def __post_init__(self) -> None:
        """Clamp percent to 0-100 to handle corrupt BLE data."""
        object.__setattr__(self, "percent", max(0, min(100, self.percent)))


@dataclass(frozen=True, slots=True)
class FirmwareEvent(DeviceEvent):
    """Firmware version report.

    The version bytes map to ``major.minor.patch``. Example:
    ``1a 07 01 01 03`` → v1.1.3.

    Attributes:
        major: Major version number.
        minor: Minor version number.
        patch: Patch version number.
    """

    major: int = 0
    minor: int = 0
    patch: int = 0


@dataclass(frozen=True, slots=True)
class SerialEvent(DeviceEvent):
    """Serial number report (ASCII or short form).

    Attributes:
        value: The serial string or hex representation.
    """

    value: str = ""


@dataclass(frozen=True, slots=True)
class TimerEvent(DeviceEvent):
    """Auto-off timer setting report.

    Attributes:
        value: Raw timer byte. 0 = disabled, non-zero = timeout in
            5-minute increments.
        minutes: Computed timeout in minutes (0 = disabled). Derived
            from ``value * 5``; cannot be set independently.
    """

    value: int = 0
    minutes: int = 0

    def __post_init__(self) -> None:
        """Derive minutes from value to enforce the invariant."""
        object.__setattr__(self, "minutes", self.value * 5)


@dataclass(frozen=True, slots=True)
class MotorStopEvent(DeviceEvent):
    """Motor stop / print complete signal.

    Fires when the motor stops after a print job. The third byte
    (``0x0c``) is invariant across all tested conditions.
    """


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_one(data: bytes) -> DeviceEvent:
    """Parse a single 3-byte event from raw notification data.

    Args:
        data: Exactly 3 bytes starting with ``0x1a``.

    Returns:
        A typed event dataclass.
    """
    sub_type = data[1]
    value = data[2]

    match sub_type:
        case EventKind.LID:
            lid = LidState.OPEN if (value & 0x01) else LidState.CLOSED
            return LidEvent(kind=EventKind.LID, lid=lid, raw=data)

        case EventKind.PAPER:
            paper = PaperState.PRESENT if (value & 0x01) else PaperState.ABSENT
            return PaperEvent(kind=EventKind.PAPER, paper=paper, raw=data)

        case EventKind.BATTERY:
            return BatteryEvent(kind=EventKind.BATTERY, percent=value, raw=data)

        case EventKind.SERIAL_SHORT:
            return SerialEvent(
                kind=EventKind.SERIAL_SHORT,
                value=f"0x{value:02x}",
                raw=data,
            )

        case EventKind.DEVICE_TIMER:
            return TimerEvent(
                kind=EventKind.DEVICE_TIMER,
                value=value,
                raw=data,
            )

        case EventKind.MOTOR_STOP:
            return MotorStopEvent(kind=EventKind.MOTOR_STOP, raw=data)

        case _:
            return DeviceEvent(kind=sub_type, raw=data)


def parse_notification(data: bytes) -> list[DeviceEvent]:
    """Parse a BLE notification payload into typed events.

    Notifications from ``ff01`` can contain one or more concatenated
    3-byte events. This function splits the payload and parses each
    event individually.

    Args:
        data: Raw bytes from a BLE notification on ``ff01``.

    Returns:
        List of parsed ``DeviceEvent`` instances. Empty list if the
        data doesn't start with ``0x1a`` or has invalid length.
    """
    events: list[DeviceEvent] = []

    # Handle variable-length responses (firmware, serial ASCII)
    if len(data) >= 5 and data[0] == 0x1A and data[1] == EventKind.FIRMWARE:
        return [
            FirmwareEvent(
                kind=EventKind.FIRMWARE,
                major=data[2],
                minor=data[3],
                patch=data[4],
                raw=bytes(data),
            )
        ]

    if len(data) > 3 and data[0] == 0x1A and data[1] == EventKind.SERIAL_ASCII:
        return [
            SerialEvent(
                kind=EventKind.SERIAL_ASCII,
                value=data[2:].decode("ascii", errors="replace"),
                raw=bytes(data),
            )
        ]

    # Standard 3-byte event parsing (may be batched)
    offset = 0
    while offset + 3 <= len(data):
        if data[offset] != 0x1A:
            logger.debug(
                "Unexpected byte 0x%02x at offset %d, stopping parse",
                data[offset],
                offset,
            )
            break
        chunk = bytes(data[offset : offset + 3])
        events.append(_parse_one(chunk))
        offset += 3

    if not events and len(data) > 0:
        logger.debug("No events parsed from %d bytes: %s", len(data), data.hex())

    return events
