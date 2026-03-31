"""Device event parsing for Phomemo printer notifications.

All events arrive on the ``ff01`` BLE characteristic as ``1a <sub-type>
<data>`` messages. Events can be spontaneous (triggered by physical
state changes) or solicited (responses to ``1f 11 XX`` queries). Both
use the same ``1a``-prefixed format.

Multiple 3-byte events can arrive concatenated in a single BLE
notification. The parser consumes 3 bytes at a time.

Event sub-types and their semantics are documented in the M08F Protocol
Reference under "Device Events".
"""

from dataclasses import dataclass
from enum import IntEnum, StrEnum


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
class SensorEvent:
    """Lid or paper state change event.

    Attributes:
        kind: Whether this is a lid or paper event.
        lid: Lid state (only set for lid events).
        paper: Paper state (only set for paper events).
        raw: The original 3-byte event.
    """

    kind: EventKind
    lid: LidState | None = None
    paper: PaperState | None = None
    raw: bytes = b""


@dataclass(frozen=True, slots=True)
class BatteryEvent:
    """Battery level report.

    Attributes:
        percent: Battery charge percentage (0–100).
        raw: The original 3-byte event.
    """

    percent: int
    raw: bytes = b""


@dataclass(frozen=True, slots=True)
class FirmwareEvent:
    """Firmware version report.

    The version bytes map to ``major.minor.patch``. Example:
    ``1a 07 01 01 03`` → v1.1.3.

    Note: Firmware responses are variable-length (5 bytes total),
    but the 3-byte parser captures the major version byte. For full
    version parsing, use the ``parse_firmware_response`` helper.

    Attributes:
        major: Major version number.
        minor: Minor version number.
        patch: Patch version number.
        raw: The original response bytes.
    """

    major: int
    minor: int = 0
    patch: int = 0
    raw: bytes = b""


@dataclass(frozen=True, slots=True)
class SerialEvent:
    """Serial number report (ASCII or short form).

    Attributes:
        kind: ``SERIAL_ASCII`` for the full string, ``SERIAL_SHORT``
            for the single-byte hardware revision.
        value: The serial string or hex representation.
        raw: The original response bytes.
    """

    kind: EventKind
    value: str
    raw: bytes = b""


@dataclass(frozen=True, slots=True)
class TimerEvent:
    """Auto-off timer setting report.

    Attributes:
        value: Raw timer byte. 0 = disabled, non-zero = timeout in
            5-minute increments.
        minutes: Computed timeout in minutes (0 = disabled).
        raw: The original 3-byte event.
    """

    value: int
    minutes: int
    raw: bytes = b""


@dataclass(frozen=True, slots=True)
class MotorStopEvent:
    """Motor stop / print complete signal.

    Fires when the motor stops after a print job. The third byte
    (``0x0c``) is invariant across all tested conditions.

    Attributes:
        raw: The original 3-byte event.
    """

    raw: bytes = b""


# Union of all parsed event types
DeviceEvent = (
    SensorEvent
    | BatteryEvent
    | FirmwareEvent
    | SerialEvent
    | TimerEvent
    | MotorStopEvent
)


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
            state = LidState.OPEN if (value & 0x01) else LidState.CLOSED
            return SensorEvent(kind=EventKind.LID, lid=state, raw=data)

        case EventKind.PAPER:
            state = PaperState.PRESENT if (value & 0x01) else PaperState.ABSENT
            return SensorEvent(kind=EventKind.PAPER, paper=state, raw=data)

        case EventKind.BATTERY:
            return BatteryEvent(percent=value, raw=data)

        case EventKind.SERIAL_SHORT:
            return SerialEvent(
                kind=EventKind.SERIAL_SHORT,
                value=f"0x{value:02x}",
                raw=data,
            )

        case EventKind.DEVICE_TIMER:
            return TimerEvent(
                value=value,
                minutes=value * 5,
                raw=data,
            )

        case EventKind.MOTOR_STOP:
            return MotorStopEvent(raw=data)

        case _:
            # Unknown sub-type — return as a generic sensor event
            return SensorEvent(kind=EventKind(sub_type), raw=data)


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
            break
        chunk = bytes(data[offset : offset + 3])
        events.append(_parse_one(chunk))
        offset += 3

    return events
