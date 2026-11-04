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

"""Async BLE driver library for Phomemo thermal printers.

Provides a modular, profile-based API for communicating with Phomemo
thermal printers over Bluetooth Low Energy.

Basic usage::

    from phomemo import Printer

    async with Printer("M08F-A4", "AA:BB:CC:DD:EE:FF") as printer:
        # connect() must be called after entering the context
        await printer.connect()
        await printer.wait_for_ready()
        await printer.print_image("photo.png")
        await printer.eject_paper()
"""

from phomemo import profiles  # noqa F401  # auto-load profiles at import time
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
