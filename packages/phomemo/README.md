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

async with Printer("M08F-A4", "AA:BB:CC:DD:EE:FF") as printer:
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

`ImageFit.FIT_WIDTH` scales to the head width only; `FIT_PAGE` also bounds the height by the profile's `max_rows` (the printable rows of its default sheet; `profile.rows_for(length_mm)` gives the same for any sheet length), so a tall image cannot run the sheet out. `print_bitmap()` logs a warning when a raster is taller than `max_rows`.

Raster data is written with ATT write responses as one continuous stream of link-sized chunks (the printer advances blank paper whenever it runs dry at a `GS v 0` band end, so bands are never sent as separate bursts). The ATT round trip caps the stream at roughly 6.5–7.4 KiB/s, which the printer keeps up with on every content tested, so no inter-chunk delay is needed. `print_bitmap(abort=event)` stops when the event is set: the band in progress is completed with white rows so the printer's parser stays in sync, then `PrintAborted("cancelled")` is raised. A paper-absent event while more than a quarter of the page is unsent, or a printer that stops answering after the motor stop, raises `SheetRanOut`; a lid found open at the motor stop raises `PrintAborted("lid opened")`. `Printer.rows_sent` reports transfer progress. BLE failures surface as `ConnectionError`, including a link the printer drops on its own.

For a page raster coming from a print system (8-bit gray or 1-bit), `prepare_page(img, profile, length_mm, tone, rotate)` maps it onto the sheet: optional quarter-turn rotation (A5 fed long edge first), centring on the head width, dropping the rows in the unprintable top lead, clipping to the sheet, and converting gray with a `ToneMode` (`THRESHOLD`, `ORDERED`, `DIFFUSION`).

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

# Block until lid closed and a sheet is loaded and seated (TimeoutError otherwise).
# After the sensor sees the sheet the feed motor runs ~2 s more; `settle` waits
# for that (3 s cap). Three consecutive query timeouts mean the printer is in
# the overrun error state; the link is reconnected once to clear it.
await printer.wait_for_ready(timeout=300, settle=3.0)

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
    sheet_length_mm=None,   # continuous roll
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
| `sheet_length_mm` | `None` | Sheet length in the feed direction (`None` for roll media). |
| `top_margin_mm` | `0.0` | Unprintable lead at the top of a sheet (sensor-to-head distance). |
| `bottom_margin_mm` | `0.0` | Kept free at the sheet end so raster plus trailing feed never overrun the sheet. |
| `max_rows` (property) | derived | Rows between the margins; used by `FIT_PAGE` and the oversize warning. A4: 2245. |

## Bridge Daemon

`phomemo-bridge` runs the device side of a printer application: it owns the BLE link, waits for sheets, converts pages and prints them, and takes commands over a unix socket. A printer application (PAPPL based, separate project stage) or the bundled CLI drives it.

```bash
phomemo-bridge serve                      # daemon; socket in $XDG_RUNTIME_DIR/phomemo-bridge.sock
phomemo-bridge discover                   # list printers in range
phomemo-bridge status                     # link and sensor state
phomemo-bridge print page.png --media a4 --quality high --tone diffusion
phomemo-bridge print page.png --media a5  # sheet fed long edge first; the page's right edge leads
phomemo-bridge eject
```

`packaging/phomemo-bridge.service` is a systemd user unit for it.

Configuration is TOML, `/etc/phomemo/bridge.toml` overridden by `$XDG_CONFIG_HOME/phomemo/bridge.toml`; every key is optional. `PHOMEMO_BRIDGE_SOCKET` overrides the socket path.

| Key | Default | Meaning |
|-----|---------|---------|
| `socket_path` | `$XDG_RUNTIME_DIR/phomemo-bridge.sock`, else `/run/phomemo/bridge.sock` | Listening socket. |
| `hold_seconds` | `120` | Keep the BLE link after a job so the next one skips the reconnect. |
| `settle_seconds` | `3` | Cap on the wait for an inserted sheet to seat at the head. |
| `completion_timeout` | `300` | Seconds to wait for the motor stop after a page. |
| `drain_seconds` | `1` | Pause after a cancelled transfer before ejecting. |
| `band_height` | profile (256) | Rows per `GS v 0` band; on cancel the band in progress is finished with white rows (up to this many). |
| `top_margin_mm`, `bottom_margin_mm`, `dpi`, `print_width_px` | profile | Geometry overrides. |
| `[printer] address` | discover by name | BLE address of the printer. |
| `[printer] profile` | `M08F-A4` | Profile name. |

Wire format: one JSON object per line; a message with `"bytes": N` is followed by N raw bytes. Replies carry `ok` and `cmd`; while a long command is pending the bridge pushes `{"event": "progress", "percent": P}` and `{"event": "waiting", "reason": "no-sheet" | "printer-off" | "lid-open"}` lines. One client at a time; `abort` is the only command accepted while another is pending.

| Command | Arguments | Reply |
|---------|-----------|-------|
| `discover` | `timeout` | `printers: [{name, address}]` |
| `open` | `address` (optional) | connects (or reuses the held link); a different address than the current one retargets the bridge; `connected: false` when the printer is unreachable, `wait_ready` keeps retrying |
| `status` | | `connected`, and when connected `lid`, `paper`, `battery` |
| `wait_ready` | `settle` | returns once a sheet is seated; waits as long as it takes, pushes `waiting` events |
| `page_begin` | `width`, `length_rows`, `bits` (1/8), `tone` (`auto` or a tone mode), `content` (`auto`/`text`/`graphic`/`photo`), `density` (`low`/`medium`/`high`), `media_length_mm` (number or null), `rotate` | |
| `lines` | `count` + payload of `count` rows (`width * bits / 8` bytes each; 8-bit gray 0 = black, 1-bit 1 = black) | `rows` received so far |
| `page_end` | | prints and ejects; `impressions: 1`, or `error`: `paper ran out`, `cancelled`, `lid opened`, `connection lost: ...` |
| `eject` | | `ejected` |
| `abort` | | stops a pending `wait_ready` or transfer (the band in progress is padded white, then drain and eject); ok even when idle |
| `close` | | starts the hold timer |

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
