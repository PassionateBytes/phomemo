# phomemo

Async Python driver library for Phomemo portable thermal printers over Bluetooth Low Energy.

Built from a [reverse-engineered protocol specification](../../docs/m08f-protocol-reference.md) for the Phomemo M08F. Designed to be modular, extensible to other Phomemo models, and usable as a standalone dependency in any async Python application.

## Features

- Async-native BLE communication via [bleak](https://github.com/hbldh/bleak)
- Full raster printing (GS v 0) with automatic banding for large images
- Image preparation pipeline — resize, dither, 1-bit bitmap conversion via [Pillow](https://python-pillow.github.io/)
- Device queries — battery, firmware version, serial number, lid/paper state, auto-off timer
- Real-time event stream — typed parsing of lid, paper, and print-complete notifications
- Print density control (ESC N 04 concentration)
- Flow control via ATT write responses, so full-page jobs never overflow the printer
- Paper feed, sensor-driven sheet eject, wait-for-sheet helper
- Print completion detection via motor-stop signal
- Extensible profile system for multi-model support

## Installation

```bash
pip install phomemo
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add phomemo
```

> **Note:** If the package is not yet published to PyPI, install from source:
>
> ```bash
> git clone <repo-url> && cd phonemo-printer
> uv pip install -e packages/phomemo
> ```

## Requirements

- Python 3.13+
- A Phomemo thermal printer (M08F tested, others via custom profiles)
- Platform with BLE support — Linux/BlueZ (tested), macOS, Windows

## Quick Start

```python
import asyncio
from phomemo import Printer, Density, ImageFit, discover

async def main():
    # Find nearby printers
    devices = await discover(name_pattern=r"^M08F")
    if not devices:
        print("No printers found")
        return

    async with Printer("M08F-A4", devices[0]) as printer:
        await printer.connect()

        # Block until lid closed and a sheet is loaded
        await printer.wait_for_ready(timeout=60)

        # Print an image file, scaled to fit the sheet
        await printer.print_image("photo.png", density=Density.MEDIUM, fit=ImageFit.FIT_PAGE)

        # Feed until the sheet has left the paper sensor
        await printer.eject_paper()

asyncio.run(main())
```

## Usage

### Device Discovery

`discover()` scans for BLE devices and optionally filters by a regex pattern on the advertised name:

```python
from phomemo import discover

# All nearby BLE devices
devices = await discover()

# Only Phomemo M08F printers
devices = await discover(name_pattern=r"^M08F")
```

### Connecting

The `Printer` class manages the BLE connection lifecycle. Pass a profile name or a `PrinterProfile` instance, and optionally the device: a `BLEDevice` from `discover()`, a MAC address string, or nothing to discover by name on `connect()`:

```python
from phomemo import Printer

async with Printer("M08F-A4", "60:6E:41:23:0B:D6") as printer:
    await printer.connect()
    # ... use the printer ...
# automatically disconnects on exit
```

A MAC string is resolved through a short targeted scan first, because BlueZ can only connect to a device it has recently seen advertising. The `discovery_timeout` argument of `connect()` bounds both that scan and name-based discovery.

### Querying Device State

```python
# Individual queries
battery = await printer.query_battery()       # int (0–100) or None
firmware = await printer.query_firmware()     # str like "1.1.3" or None
lid = await printer.query_lid()               # LidState.CLOSED / .OPEN
paper = await printer.query_paper()           # PaperState.PRESENT / .ABSENT

# All-in-one snapshot
info = await printer.query_device_info()
print(info.battery, info.lid, info.paper, info.firmware, info.serial)
```

Note: paper state is unreliable when the lid is open. `query_device_info()` handles this automatically — it only queries paper if the lid is closed.

### Printing

The high-level `print_image()` accepts a file path or a PIL `Image` and handles the full pipeline — resize, dither, raster encoding, chunked BLE transmission, and completion detection:

```python
from phomemo import Density, DitherMode, ImageFit

await printer.print_image(
    "photo.png",
    density=Density.HIGH,
    fit=ImageFit.FIT_PAGE,
    dither=DitherMode.FLOYD_STEINBERG,
)
```

`ImageFit.FIT_WIDTH` scales to the head width only; `FIT_PAGE` also bounds the height by the profile's `max_rows`, so a tall image cannot run the sheet out. `print_bitmap()` logs a warning when a raster is taller than `max_rows`.

Raster data is written with ATT write responses. The printer holds each response while its buffer is full, so transfer speed follows the print head (roughly 7 KiB/s on sparse pages, 6 KiB/s on dense ones) and no inter-chunk delay is needed.

For lower-level control, prepare and send bitmap data directly:

```python
from phomemo import prepare_image, image_to_bitmap
from PIL import Image

img = Image.open("photo.png")
processed = prepare_image(img, target_width=printer.profile.print_width_px)
bitmap = image_to_bitmap(processed)
await printer.print_bitmap(bitmap, height=processed.size[1])
```

### Paper Transport

```python
# Feed a small amount (20 dot rows ~ 2.5mm)
await printer.feed(20)

# Block until lid closed and a sheet is loaded (TimeoutError otherwise)
await printer.wait_for_ready(timeout=60)

# Feed 32mm at a time until the paper sensor reports the sheet gone,
# then one more feed to clear the rollers. Returns False if the sheet
# is still present after max_feeds.
ejected = await printer.eject_paper(max_feeds=16)
```

### Event Listening

Register a callback to receive typed events as they arrive from the printer:

```python
from phomemo import DeviceEvent, LidEvent, PaperEvent, MotorStopEvent

def on_event(event: DeviceEvent):
    match event:
        case LidEvent(lid=lid):
            print(f"Lid: {lid.value}")
        case PaperEvent(paper=paper):
            print(f"Paper: {paper.value}")
        case MotorStopEvent():
            print("Print complete")

printer.on_event(on_event)
```

### Custom Profiles

Add support for other Phomemo models by registering a profile:

```python
from phomemo.profiles import PrinterProfile, register_profile

register_profile(PrinterProfile(
    name="M02S",
    ble_name_pattern=r"^M02S",
    print_width_px=576,
    max_chunk_bytes=244,
    max_rows=None,          # continuous roll
))

async with Printer("M02S") as printer:
    ...
```

Profile fields beyond the BLE UUIDs:

| Field | Default | Meaning |
|-------|---------|---------|
| `write_with_response` | `True` | ATT Write Request; the printer paces the stream. Set `False` only for models that need Write Command, and then set `chunk_delay_s`. |
| `chunk_delay_s` | `0.0` | Delay between writes; only meaningful without responses. |
| `max_chunk_bytes` | `244` | Fallback write size when the MTU cannot be read. |
| `band_height` | `256` | Rows per `GS v 0` command. |
| `max_rows` | `None` | Rows that fit on one sheet (`None` for roll media). Used by `FIT_PAGE` and the oversize warning. |
| `top_margin_mm` | `0.0` | Unprintable lead at the top of a sheet. |

## Supported Printers

| Model | Profile | Print Width | Status |
|-------|---------|-------------|--------|
| M08F (A4) | `M08F-A4` | 1680 px (210 bytes/row) | Tested |
| M08F (Letter) | `M08F-Letter` | 1728 px (216 bytes/row) | Untested |

## Architecture

```
phomemo/
├── discovery.py   # BLE device discovery
├── events.py      # Notification parsing (1a XX event stream)
├── imaging.py     # Image → 1-bit bitmap pipeline
├── printer.py     # High-level async Printer client
├── profiles.py    # Printer hardware profiles (extensible)
├── protocol.py    # ESC/POS + Phomemo command encoding
└── transport.py   # BLE transport layer (chunking, writes)
```

## License

[LGPL-3.0-or-later](LICENSE)
