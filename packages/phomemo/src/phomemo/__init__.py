"""Async BLE driver library for Phomemo thermal printers.

Provides a modular, profile-based API for communicating with Phomemo
thermal printers over Bluetooth Low Energy.

Basic usage::

    from phomemo import Printer

    async with Printer("M08F-A4") as printer:
        # connect() must be called after entering the context
        await printer.connect("60:6E:41:23:0B:D6")
        await printer.print_image("photo.png")
"""

from phomemo.discovery import discover
from phomemo.events import (
    BatteryEvent,
    DeviceEvent,
    EventKind,
    FirmwareEvent,
    LidEvent,
    LidState,
    MotorStopEvent,
    PaperEvent,
    PaperState,
    SerialEvent,
    TimerEvent,
)
from phomemo.imaging import DitherMode, ImageFit, image_to_bitmap, prepare_image
from phomemo.printer import Printer
from phomemo.protocol import Density
from phomemo.registry import (
    PrinterProfile,
    get_profile,
    list_profiles,
    register_profile,
)

__all__ = [
    "BatteryEvent",
    "Density",
    "DeviceEvent",
    "DitherMode",
    "EventKind",
    "FirmwareEvent",
    "ImageFit",
    "LidEvent",
    "LidState",
    "MotorStopEvent",
    "PaperEvent",
    "PaperState",
    "Printer",
    "PrinterProfile",
    "SerialEvent",
    "TimerEvent",
    "discover",
    "get_profile",
    "image_to_bitmap",
    "list_profiles",
    "prepare_image",
    "register_profile",
]
