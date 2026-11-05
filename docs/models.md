# Printer models

Every printer model the driver supports is described once, in a model manifest, for the whole stack. The library builds its profile from the manifest, the bridge uses that profile for each printer it connects to, and the printer app builds its PAPPL driver (media, resolution, margins, names, icons) from the same files.

| Model | Identifier | Head width | Sheet sizes | Status |
|---|---|---|---|---|
| Phomemo M08F (A4) | `m08f` | 1680 dots at 203 dpi | A4, A5, US Letter (untested) | Tested |

```{tip}
Your printer is not listed? A model that speaks the same protocol needs only a new directory, no code. See [Add a model](#add-a-model) below; contributions are very welcome.
```

## Layout

```
src/models/
  m08f/
    model.json      the manifest
    icon-48.png     printer icons in the three sizes PAPPL uses
    icon-128.png
    icon-512.png
```

The directory name is the model identifier: lower case, also the PAPPL driver name and the `?model=` value in the device URI.

## model.json

Here is the M08F's manifest:

```json
{
  "id": "m08f",
  "make": "Phomemo",
  "name": "M08F",
  "ble_name_pattern": "^M08F",
  "print_width_px": 1680,
  "dpi": 203,
  "band_height": 256,
  "sheet_length_mm": 297.0,
  "top_margin_mm": 10.0,
  "bottom_margin_mm": 5.0,
  "density": {"low": 1, "medium": 5, "high": 6},
  "media": [
    {"pwg": "iso_a4_210x297mm", "default": true},
    {"pwg": "iso_a5_148x210mm"},
    {"pwg": "na_letter_8.5x11in", "tested": false}
  ],
  "ble": {
    "max_chunk_bytes": 244,
    "negotiate_mtu": true,
    "write_with_response": true,
    "chunk_delay_s": 0.0,
    "service_uuid": "0000ff00-0000-1000-8000-00805f9b34fb",
    "write_uuid": "00000000-0000-0000-0000-00000000ff02",
    "notify_uuid": "00000000-0000-0000-0000-00000000ff01",
    "status_uuid": "00000000-0000-0000-0000-00000000ff03"
  },
  "features": {
    "escpos_queries": false
  }
}
```

And what each field means:

| Field | Meaning |
|---|---|
| `id` | The identifier; must equal the directory name |
| `make`, `name` | Manufacturer and model as users see them: make-and-model "Phomemo M08F", device ID `MFG:Phomemo;MDL:M08F;CMD:PHOMEMO;` |
| `ble_name_pattern` | Regular expression matched against the name the printer advertises over Bluetooth; it decides which model a printer is |
| `print_width_px`, `dpi` | Print head width in dots and resolution |
| `band_height` | Rows per `GS v 0` raster command |
| `sheet_length_mm` | Length of the default sheet in the feed direction; the library's `max_rows` and the test page use it |
| `top_margin_mm`, `bottom_margin_mm` | Unprintable lead at the top of a sheet, and the space kept free at its end |
| `density` | Optional: the `ESC N 04` concentration values for `low`, `medium` and `high`; without it the model has no density control |
| `media` | Sheet sizes as [PWG self-describing names](https://ftp.pwg.org/pub/pwg/candidates/cs-pwgmsn20-20130328-5101.1.pdf); exactly one has `"default": true`; `"tested": false` marks a size nobody has printed on yet (see [Sheet sizes](#sheet-sizes)) |
| `ble` | Connection parameters: `max_chunk_bytes`, `negotiate_mtu`, `write_with_response`, `chunk_delay_s` and the four characteristic UUIDs |
| `features` | Optional: `escpos_queries` when standard ESC/POS queries answer |

```{note}
A manifest with a missing or mistyped field is rejected, with the file and the field named in the error.
```

## Sheet sizes

The `media` list names the sheets a model takes. Each size's geometry comes from its PWG name (`iso_a4_210x297mm` is 210 x 297 mm, `na_letter_8.5x11in` is 8.5 x 11 in), so an entry needs no numbers of its own:

- The dimension closer to the head width lies across the head, the other one runs along the feed and sets the sheet length: 297 mm for A4, 148 mm for A5 (fed long edge first, portrait pages rotated), 279.4 mm for Letter.
- A sheet narrower than the head is centred on it; a sheet wider than the head (Letter, 215.9 mm on a 210 mm head) is printed on its centre band, about 3 mm stay blank at each side.
- The top and bottom margins are the model's, whatever the sheet.

The M08F's sizes:

| Size | PWG name | Fed | Status |
|---|---|---|---|
| A4 | `iso_a4_210x297mm` (default) | Short edge first | Tested |
| A5 | `iso_a5_148x210mm` | Long edge first, page rotated | Tested |
| US Letter | `na_letter_8.5x11in` | Short edge first | Untested |

`"tested": false` says that the entry comes from documentation (here: the vendor's Linux driver, which lists Letter for the M08F) and nobody has printed on that sheet with this driver yet. The geometry is the same as for a tested sheet; only the bottom margin has not been checked against a real sheet. Have you printed on an untested size? Open an issue or a pull request that flips the flag, with a note on how it went.

## How the stack reads them

The manifests are built into the Python package and the printer app's binary, so nothing extra is installed or looked up at run time:

```
src/models/<id>/model.json + icons
    │
    ├── hatch build hook (src/phomemo/hatch_build.py)
    │       wheel: phomemo/models     sdist: src/phomemo/models
    │       → library and bridge load them at import
    │
    └── embed-models.sh, at build time
            → models_data.c, compiled into phomemo-printer-app
```

| Reader | Where it looks, in order |
|---|---|
| Library and bridge | `PHOMEMO_MODELS_DIR` when set; else the copy installed with the package (`phomemo/models`); else `src/models/` of a source checkout |
| Printer app | `PHOMEMO_MODELS_DIR` set at start, which replaces the built-in manifests with the directories found there; else the manifests embedded in the binary |

```{tip}
Use `PHOMEMO_MODELS_DIR` to try out a new manifest without rebuilding anything.
```

From Python you can load a manifest directly:

```python
from pathlib import Path
from phomemo.registry import load_manifest, register_profile

register_profile(load_manifest(Path("src/models/m08f")))
```

More on profiles in the [library guide](library.md#profiles-and-model-manifests). How the pieces fit together is in [Driver stack](driver-stack.md).

## Add a model

Got a Phomemo printer that speaks the same protocol? Here is how to add it:

1. Create `src/models/<id>/` with a `model.json`, starting from the M08F's.
2. Find the name it advertises and write `ble_name_pattern` for it. `phomemo-bridge devices` lists only known models; `bluetoothctl scan on` shows all devices.
3. Measure the head width and the margins.
4. Pick the density values.
5. Add the three icons.
6. Print the test page:

   ```bash
   phomemo-bridge testpage -a AA:BB:CC:DD:EE:FF
   ```

Then open a pull request with the directory and a note on how you tested it. New models are among the contributions we most hope for; see [Contributing](contributing.md).

```{warning}
A model with real protocol differences also needs code in the library. Open an issue first so we can work out the approach together.
```

## Licence

Like the library that ships them, the model manifests are licensed under the GNU LGPL, version 3 or later.
