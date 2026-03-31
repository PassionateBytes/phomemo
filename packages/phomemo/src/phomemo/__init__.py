"""Async BLE driver library for Phomemo thermal printers.

Provides a modular, profile-based API for communicating with Phomemo
thermal printers over Bluetooth Low Energy.

Basic usage::

    from phomemo import Printer

    async with Printer("M08F-A4") as printer:
        await printer.connect("60:6E:41:23:0B:D6")
        await printer.print_image("photo.png")
"""

from phomemo.discovery import discover
from phomemo.events import (
    BatteryEvent,
    DeviceEvent,
    EventKind,
    LidState,
    MotorStopEvent,
    PaperState,
    SensorEvent,
)
from phomemo.imaging import DitherMode, ImageFit, image_to_bitmap, prepare_image
from phomemo.printer import Printer
from phomemo.profiles import PrinterProfile, get_profile, list_profiles
from phomemo.protocol import Density

__all__ = [
    "BatteryEvent",
    "Density",
    "DeviceEvent",
    "DitherMode",
    "EventKind",
    "ImageFit",
    "LidState",
    "MotorStopEvent",
    "PaperState",
    "Printer",
    "PrinterProfile",
    "SensorEvent",
    "get_profile",
    "image_to_bitmap",
    "list_profiles",
    "prepare_image",
    "discover",
]
