# Python library

`phomemo` lets you drive a Phomemo thermal printer from any asyncio program: scan, connect, print images, read the sensors. It is built on [bleak](https://github.com/hbldh/bleak) and [Pillow](https://python-pillow.github.io/), and the bridge and printer app run on top of it (see [Driver stack](driver-stack.md)).

Every class and function is listed in the [API reference](api.md). This page walks you through the parts you need first.

## Install

```bash
pip install phomemo
```

Or with uv, or on Fedora from the COPR repository `passionatebytes/phomemo-driver`:

```bash
uv add phomemo
sudo dnf install python3-phomemo
```

You need Python 3.13 or later and a Bluetooth adapter. Linux with BlueZ is tested; bleak also runs on macOS and Windows.

## Quick start

```python
import asyncio
from phomemo import Printer, Density, ImageFit, discover

async def main():
    devices = await discover(name_pattern=r"^M08F")
    if not devices:
        print("No printers found")
        return

    async with Printer("m08f", devices[0]) as printer:
        await printer.connect()
        await printer.wait_for_ready(timeout=60)
        await printer.print_image("photo.png", density=Density.MEDIUM, fit=ImageFit.FIT_PAGE)
        await printer.eject_paper()

asyncio.run(main())
```

Here is what happens:

1. `discover()` scans for printers that advertise a name starting with `M08F`.
2. `Printer("m08f", ...)` picks the `m08f` profile; `connect()` brings up the connection.
3. `wait_for_ready()` blocks until the lid is closed and a sheet is seated.
4. `print_image()` scales the image to the sheet, dithers it and prints it.
5. `eject_paper()` feeds the sheet out.

```{tip}
Switch the printer on before you scan. While another host holds a connection, the printer does not advertise and your scan will not find it.
```

## Scan for printers

```python
from phomemo import discover

devices = await discover()                         # every BLE device in range
devices = await discover(name_pattern=r"^M08F")    # M08F printers only
```

`discover()` scans for `timeout` seconds (default 5) and returns `BLEDevice` objects sorted by name. `name_pattern` is a regular expression searched in the advertised name.

```{note}
The M08F uses no pairing: any host in range can connect.
```

## Connect

```python
from phomemo import Printer

async with Printer("m08f", "AA:BB:CC:DD:EE:FF") as printer:
    await printer.connect()
    ...
# disconnected here
```

`Printer` takes a profile name (`"m08f"` is the default) or a `PrinterProfile`, plus the device:

- a `BLEDevice` from `discover()`,
- an address string,
- or nothing, to find a printer by its advertised name on `connect()`.

An address string is resolved through a short targeted scan first, because BlueZ only connects to a device it has seen advertising recently. `connect(discovery_timeout=...)` bounds that scan.

```{warning}
A connection the printer drops on its own surfaces as `ConnectionError`. Call `reconnect()` to bring it up again.
```

## Print an image

```python
from phomemo import Density, DitherMode, ImageFit

await printer.print_image(
    "photo.png",
    density=Density.HIGH,
    fit=ImageFit.FIT_PAGE,
    dither=DitherMode.FLOYD_STEINBERG,
)
```

`print_image()` accepts a file path or a PIL `Image` and handles the rest: resize, dither, raster encoding, transfer and waiting for the motor to stop.

### Fit

| `ImageFit` | Effect |
|---|---|
| `FIT_WIDTH` (default) | Scale to the head width |
| `FIT_PAGE` | Scale to the head width, bounded in height by the profile's `max_rows` |
| `FIT_HEIGHT`, `STRETCH`, `ORIGINAL` | See the [API reference](api.md) |

```{tip}
Use `FIT_PAGE` for anything taller than a sheet. It guarantees the image cannot run the sheet out mid-print.
```

### Density and dithering

| `Density` | M08F `ESC N 04` value |
|---|---|
| `LOW` | 1 |
| `MEDIUM` (default) | 5 |
| `HIGH` | 6 |

The values come from the model manifest; a model without them has no density control.

`DitherMode.FLOYD_STEINBERG` (default) suits photos; `DitherMode.THRESHOLD` splits at 128 without dithering.

## Print a bitmap

Want full control over the pixels? Prepare the bitmap and send it yourself:

```python
from phomemo import prepare_image, image_to_bitmap
from PIL import Image

img = Image.open("photo.png")
processed = prepare_image(img, target_width=printer.profile.print_width_px)
bitmap = image_to_bitmap(processed)
await printer.print_bitmap(bitmap, height=processed.size[1])
```

`print_bitmap()` logs a warning when the raster is taller than `max_rows`. For other sheet lengths, `profile.rows_for(length_mm)` gives the printable rows. `printer.rows_sent` reports progress while the transfer runs.

### When a print stops early

| Situation | You get |
|---|---|
| The `abort` event passed to `print_bitmap(abort=event)` is set | `PrintAborted("cancelled")` |
| The sheet runs out with more than a quarter of the page unsent, or the printer stops answering after the motor stop | `SheetRanOut` |
| The lid is open at the motor stop | `PrintAborted("lid opened")` |
| A BLE failure, including a dropped connection | `ConnectionError` |

On abort, the band in progress is padded with white rows so the printer's parser stays in sync.

```{note}
Raster data goes out with ATT write-with-response as one continuous stream, so the printer paces the transfer itself (roughly 6.5 to 7.4 KiB/s). You never need to add delays. The [Protocol reference](m08f-protocol-reference.md) explains why.
```

### Page rasters and tone modes

```python
from PIL import Image
from phomemo.imaging import ToneMode, prepare_page

page = Image.open("page.png")   # e.g. a rendered 8-bit gray page
sheet = prepare_page(page, printer.profile, length_mm=297.0, tone=ToneMode.DIFFUSION)
```

`prepare_page()` maps a page raster from a print system (mode `L` with 0 = black, or mode `1`) onto the sheet: an optional quarter turn with `rotate=True` (A5 is fed long edge first), centring on the head width, dropping the rows in the unprintable top lead, and clipping to the sheet. Gray input is converted with a tone mode; 1-bit input keeps its pixels.

| `ToneMode` | Result |
|---|---|
| `THRESHOLD` | Split at mid gray: true black and white, crisp text |
| `ORDERED` | 8x8 Bayer pattern: even tone |
| `DIFFUSION` | Floyd-Steinberg error diffusion: photos |

## Move the paper

```python
await printer.feed(20)                              # 20 dot rows, about 2.5 mm
await printer.wait_for_ready(timeout=300, settle=3.0)
ejected = await printer.eject_paper()
```

- `wait_for_ready()` blocks until the lid is closed and a sheet is loaded and seated, else raises `TimeoutError`. `settle` caps the wait for the feed motor after the sensor sees the sheet. A printer that stops answering queries is reconnected once.
- `eject_paper()` keeps two 15 mm feeds queued until the paper-absent event arrives, then a 20 mm feed clears the rollers. It returns `False` if the sheet is still there after `max_feeds` (64, about 1 m).

## Listen to events

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

Your callback receives typed events as the printer sends them. The other types are `BatteryEvent`, `FirmwareEvent`, `SerialEvent` and `TimerEvent`.

## Read device information

```python
battery = await printer.query_battery()       # int 0-100, or None
firmware = await printer.query_firmware()     # str such as "1.1.3", or None
lid = await printer.query_lid()               # LidState.CLOSED / .OPEN
paper = await printer.query_paper()           # PaperState.PRESENT / .ABSENT
minutes = await printer.query_auto_off()      # auto-off timer in minutes

info = await printer.query_device_info()      # everything at once
print(info.battery, info.lid, info.paper, info.firmware, info.serial)

await printer.set_auto_off_timer(15)          # 5-minute steps, 0 = never
```

A query that gets no answer returns `None`.

```{warning}
Paper state is unreliable while the lid is open. `query_device_info()` takes care of this and queries paper only when the lid is closed.
```

## Profiles and model manifests

A profile (`PrinterProfile`) holds everything model-specific. The built-in profiles are built at import from the [model manifests](models.md), the same files the printer app embeds.

```{tip}
Adding a printer model? Write a model manifest instead of code; every part of the stack picks it up. See [Printer models](models.md).
```

You can also load or register profiles in your own program:

```python
from pathlib import Path
from phomemo import Printer, register_profile
from phomemo.registry import PrinterProfile, load_manifest, profile_for_name

register_profile(load_manifest(Path("my-models/m02s")))   # directory with model.json

register_profile(PrinterProfile(
    name="m02s",
    ble_name_pattern=r"^M02S",
    print_width_px=576,
    sheet_length_mm=None,   # continuous roll
))

profile_for_name("M08F")    # profile whose ble_name_pattern matches, or None

async with Printer("m02s") as printer:
    ...
```

| Function | Does |
|---|---|
| `load_manifest(path)` | Builds a profile from a model manifest directory; a missing or mistyped field raises `ValueError` naming file and field |
| `register_profile(profile)` | Adds a profile, replacing one of the same name |
| `get_profile(name)` | Looks a profile up; `KeyError` lists the known names |
| `list_profiles()` | Sorted profile names |
| `profile_for_name(ble_name)` | The profile whose `ble_name_pattern` matches an advertised name, or `None` |

### Profile fields

| Field | Default | Meaning |
|---|---|---|
| `name` | required | Lower-case model identifier (`m08f`), also the manifest's directory name |
| `ble_name_pattern` | required | Regular expression matched against the advertised name |
| `print_width_px` | required | Head width in dots, a multiple of 8 |
| `dpi` | `203` | Resolution |
| `write_with_response` | `True` | ATT Write Request; the printer paces the stream. `False` only for models that need Write Command, then with `chunk_delay_s` |
| `chunk_delay_s` | `0.0` | Delay between writes; only meaningful without responses |
| `max_chunk_bytes` | `244` | Write size when the MTU cannot be read |
| `negotiate_mtu` | `True` | Derive the write size from the negotiated MTU |
| `band_height` | `256` | Rows per `GS v 0` command |
| `sheet_length_mm` | `None` | Sheet length in the feed direction (`None` for roll media) |
| `top_margin_mm` | `0.0` | Unprintable lead at the top of a sheet (sensor-to-head distance) |
| `bottom_margin_mm` | `0.0` | Kept free at the sheet end (M08F: 5 mm) |
| `density_levels` | `None` | `ESC N 04` values for `LOW`, `MEDIUM`, `HIGH`; `None` means no density control |
| `supports_escpos_queries` | `False` | Standard ESC/POS queries answer |
| `service_uuid`, `write_uuid`, `notify_uuid`, `status_uuid` | `ff00`, `ff02`, `ff01`, `ff03` | GATT service and characteristics |
| `make`, `model_name` | `"Phomemo"`, `""` | Names as users see them |
| `media`, `default_media` | `()`, `None` | PWG names of the sheet sizes, and the default |
| `max_rows` (property) | derived | Rows between the margins of the default sheet; A4: 2253 |

## Next steps

- The full API: [API reference](api.md).
- How the printer behaves on the wire: [Protocol reference](m08f-protocol-reference.md).
- Found a gap or have a new printer model? See [Contributing](contributing.md).
