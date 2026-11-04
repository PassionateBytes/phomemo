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
> uv pip install -e src/phomemo
> ```

## Requirements

- Python 3.13+
- A Phomemo thermal printer (M08F tested; others through a model description or a custom profile)
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

    async with Printer("m08f", devices[0]) as printer:
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

async with Printer("m08f", "AA:BB:CC:DD:EE:FF") as printer:
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

# Keeps two 15mm feeds queued so the motor runs without pauses, adding one
# every 0.7 s until the printer's paper-absent event arrives, then a 20mm
# feed clears the rollers. Returns False if the sheet is still present after
# max_feeds (64, about 1 m).
ejected = await printer.eject_paper()
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

### Profiles and Model Descriptions

A profile holds everything model-specific. The built-in profiles come from the model descriptions in [`src/models/`](../models/README.md), which the printer application reads as well; a new model belongs there. A program can also register a profile in code:

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
| `bottom_margin_mm` | `0.0` | Kept free at the sheet end (M08F profiles: 5 mm). |
| `density_levels` | `None` | `ESC N 04` values for `Density.LOW`, `MEDIUM`, `HIGH`; `None` means no density control. M08F: 1, 5, 6. |
| `make`, `model_name` | `"Phomemo"`, `""` | Names as users see them. |
| `media`, `default_media` | `()`, `None` | PWG names of the sheet sizes, and the default. |
| `max_rows` (property) | derived | Rows between the margins; used by `FIT_PAGE` and the oversize warning. A4: 2253. |

`load_description(path)` builds a profile from a model directory; `profile_for_name(name)` returns the profile whose `ble_name_pattern` matches an advertised Bluetooth name.

## Bridge Daemon

`phomemo-bridge` runs the device side of a printer application: it owns the BLE link, waits for sheets, converts pages and prints them, and takes commands over a unix socket. The [printer application](../printer-app/README.md) (PAPPL based) or the bundled CLI drives it. Each printer brings its own profile: the printer application names the model in every `open`, otherwise the bridge reads it from the printer's advertised name.

```bash
phomemo-bridge server                     # daemon; socket in $XDG_RUNTIME_DIR/phomemo-bridge.sock
phomemo-bridge -V                         # version
phomemo-bridge devices                    # list printers in range
phomemo-bridge connect                    # bring the link up (dropped after idle_disconnect_minutes)
phomemo-bridge status                     # link, sensors, battery, firmware, serial, auto-off
phomemo-bridge auto-off                   # show the auto-off timer
phomemo-bridge auto-off 15                # set it (5-minute steps, 0 = never)
phomemo-bridge disconnect                 # drop the link now
phomemo-bridge identify                   # eject a loaded sheet, pulse the feed three times
phomemo-bridge testpage                   # print the test page
phomemo-bridge print page.png --media a4 --quality high --tone diffusion
phomemo-bridge print page.png --media a5  # sheet fed long edge first; the page's right edge leads
phomemo-bridge eject
phomemo-bridge connect -a AA:BB:CC:DD:EE:FF   # pick a printer when several are in range
```

`phomemo-bridge COMMAND -h` describes each command. Commands use the printer given with `-a/--address`, else the one linked or used last since the bridge started, else the only printer of a known model a scan finds; with several printers in range they refuse and list them. `status` and `auto-off` never connect by themselves; run `connect` first.

`packaging/systemd/phomemo-bridge.service` is its system unit (service user `phomemo` from `packaging/systemd/phomemo.sysusers.conf`, socket `/run/phomemo/bridge.sock`, enabled by `packaging/systemd/90-phomemo-bridge.preset`); `packaging/rpm/phomemo-driver.spec` builds it as the `python3-phomemo` RPM, a subpackage of `phomemo-driver`.

Configuration is TOML, `/etc/phomemo/bridge.toml` overridden by `$XDG_CONFIG_HOME/phomemo/bridge.toml`; every key is optional. `PHOMEMO_BRIDGE_SOCKET` overrides the socket path. Unknown keys, values of the wrong type or range and files that do not parse are logged as warnings; the affected setting keeps its default.

| Key | Default | Meaning |
|-----|---------|---------|
| `socket_path` | `/run/phomemo/bridge.sock` when that exists (the system service), else `$XDG_RUNTIME_DIR/phomemo-bridge.sock` | Listening socket; the command line finds the system bridge the same way. |
| `idle_disconnect_minutes` | `30` | Minutes without a command after which the bridge drops the BLE link; it ends earlier when the printer switches off or leaves range, and `0` keeps it until then. While the link is held the printer does not advertise, so other devices cannot connect to it. |
| `settle_seconds` | `3` | Cap on the wait for an inserted sheet to seat at the head. |
| `completion_timeout` | `300` | Seconds to wait for the motor stop after a page. |
| `drain_seconds` | `1` | Pause after a cancelled transfer before ejecting. |
| `auto_off_minutes` | unset (also in the packaged file) | Auto-off timer the bridge sets on the printer at each new link, written only when the printer reports another value: a multiple of 5 up to 1275, `0` = never switch off; another number is rounded to the nearest step (at least 5). Unset, or a value that is no number, leaves the printer's own setting alone. |

The bridge has no fixed printer: the printer application names one in every `open`. Commands without an address use the printer linked or used last (kept in memory until the bridge restarts), else the only printer of a known model a scan finds; with several in range they refuse and list them.

Wire format: one JSON object per line; a message with `"bytes": N` is followed by N raw bytes. Replies carry `ok` and `cmd`; while a long command is pending the bridge pushes `{"event": "progress", "percent": P}` and `{"event": "waiting", "reason": R}` lines with `R` one of `connecting` (link being brought up), `printer-off` (printer off, out of range or in use elsewhere), `adapter-off` (Bluetooth unavailable), `lid-open`, `no-sheet`, `short-sheet` (the last sheet ran out, a longer one is needed). One client at a time; `abort` is the only command accepted while another is pending.

| Command | Arguments | Reply |
|---------|-----------|-------|
| `discover` | `timeout` | `printers: [{name, address, model}]`: printers of every known model in range, with the model their advertised name matches |
| `open` | `address`, `model` (both optional) | connects (or reuses the held link) with the profile of `model`, or of the model the printer's advertised name matches; a different address than the current one retargets the bridge; `connected: false` with a `reason` when the printer is unreachable or the choice is ambiguous, `wait_ready` keeps retrying |
| `close` | | ends the session's use of the link; the bridge drops it after `idle_disconnect_minutes` without a command |
| `disconnect` | | drops the link now instead of after `idle_disconnect_minutes` |
| `status` | `address` (optional) | linked: `connected: true`, `address`, `model`, live `lid`, `paper`, `battery`. Otherwise `connected: false`, the `address` asked about (or the last linked printer), `linked_to` when the bridge holds another printer, and `last_seen` with the values last read from that printer and their time `at` (absent until it was read once since the bridge started). Never connects. |
| `info` | | linked printer's `address`, `model`, `firmware`, `serial`, `battery`, `auto_off_minutes`, `lid`, `paper`; error `not connected` without a link |
| `auto_off` | `minutes` (optional) | sets the timer when `minutes` is given, then `auto_off_minutes` as the printer reports it; error `not connected` without a link |
| `wait_ready` | `settle` | returns once a sheet is seated; waits as long as it takes, pushes `waiting` events |
| `page_begin` | `width`, `length_rows`, `bits` (1/8), `tone` (`auto` or a tone mode), `content` (`auto`/`text`/`graphic`/`photo`), `density` (`low`/`medium`/`high`), `media_length_mm` (number or null), `rotate` | |
| `lines` | `count` + payload of `count` rows (`width * bits / 8` bytes each; 8-bit gray 0 = black, 1-bit 1 = black) | `rows` received so far |
| `page_end` | | prints and ejects; `impressions: 1`. A lid opened mid-page or a sheet that runs out does not end the page: the bridge reconnects, ejects a sheet it senses right after the lid closes (its position is unknown), waits for a sheet (`waiting` events) and prints the page again. `error`: `cancelled`, `connection lost: ...` |
| `identify` | | connects if needed, ejects a loaded sheet, then pulses the feed three times (the printer's way of saying "here") |
| `test_page` | `printer_name`, `versions` (name to version) | connects if needed, queries the device and writes a test page PNG to `$XDG_RUNTIME_DIR/phomemo-testpage.png` (else the temp dir); `path` |
| `eject` | | `ejected` |
| `abort` | | stops a pending `wait_ready` or transfer (the band in progress is padded white, then drain and eject); ok even when idle |
| `close` | | starts the idle timer (`idle_disconnect_minutes`) |

## Supported Printers

| Model | Profile | Print Width | Status |
|-------|---------|-------------|--------|
| M08F (A4) | `m08f` | 1680 px (210 bytes/row) | Tested |

New models are welcome; see [`src/models/`](../models/README.md).

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

Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions.

GNU Lesser General Public License, version 3 or later: see [COPYING.LESSER](COPYING.LESSER) and the GNU General Public License it builds on in [COPYING](COPYING). This README is documentation and licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
