# Printer models

Every printer model the driver supports is described once, in a model manifest, for the whole stack. The library builds its profile from the manifest, the bridge uses that profile for each printer it connects to, and the printer app builds its PAPPL driver (media, resolution, margins, names, icons) from the same files.

| Model | Identifier | Head width | Status |
|---|---|---|---|
| Phomemo M08F (A4) | `m08f` | 1680 dots at 203 dpi | Tested |

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
  "serial_codes": [],
  "print_width_px": 1680,
  "dpi": 203,
  "band_height": 256,
  "sheet_length_mm": 297.0,
  "top_margin_mm": 10.0,
  "bottom_margin_mm": 5.0,
  "density": {"low": 1, "medium": 5, "high": 6},
  "media": [
    {"pwg": "iso_a4_210x297mm", "default": true},
    {"pwg": "iso_a5_148x210mm"}
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
| `ble_name_pattern` | Regular expression matched against the name the printer advertises over Bluetooth; it decides which model a printer is at scan time |
| `serial_codes` | Optional: substrings of the printer serial that mark a hardware variant. A model with codes takes only printers whose serial contains one of them; a model without codes takes every printer its name pattern matches that no code claims. See [How a printer is matched](#how-a-printer-is-matched) |
| `print_width_px`, `dpi` | Print head width in dots and resolution |
| `band_height` | Rows per `GS v 0` raster command |
| `sheet_length_mm` | Default sheet length in the feed direction |
| `top_margin_mm`, `bottom_margin_mm` | Unprintable lead at the top of a sheet, and the space kept free at its end |
| `density` | Optional: the `ESC N 04` concentration values for `low`, `medium` and `high`; without it the model has no density control |
| `media` | Sheet sizes as PWG names; exactly one has `"default": true` |
| `ble` | Connection parameters: `max_chunk_bytes`, `negotiate_mtu`, `write_with_response`, `chunk_delay_s` and the four characteristic UUIDs |
| `features` | Optional: `escpos_queries` when standard ESC/POS queries answer |

```{note}
A manifest with a missing or mistyped field is rejected, with the file and the field named in the error.
```

## How a printer is matched

A printer is matched to a model in two steps:

1. **At scan time, by name.** The name the printer advertises over Bluetooth is matched against every manifest's `ble_name_pattern`. Devices of no known model are left out.
2. **After connecting, by serial.** When the name matches several manifests, the bridge reads the printer's serial and picks the manifest whose `serial_codes` entry occurs in it (a substring match, case-sensitive). Without a matching code the manifest without codes wins; when every candidate carries codes, the first in identifier order. A printer that does not answer the serial query keeps the name match.

Phomemo sells some models in hardware variants under the same name, with a code in the serial to tell them apart. The variant's manifest shares the generic model's `ble_name_pattern` and lists its codes:

```json
{
  "id": "m08f-letter",
  "ble_name_pattern": "^M08F",
  "serial_codes": ["Q123"]
}
```

With this, `phomemo-bridge devices` connects briefly to each printer whose name matches both manifests, reads the serial and reports the resolved model; a printer it cannot reach is listed as the generic model and marked unconfirmed. An `open` without an explicit model (`phomemo-bridge connect`, printers registered by older versions of the printer app) switches to the resolved model after connecting; the printer app's `open` always names the model from the device URI, and that choice stands: the bridge only logs a warning when the serial points to another model.

```{note}
Variants that share an advertised name must share the `ble` block too: the serial can only be read over a connection, which is set up with the generic model's parameters.
```

No shipped manifest carries serial codes yet. The M08F's Letter variant (216 mm paper) is known to exist, but its code is not: if you own one, `phomemo-bridge status` shows your serial once connected, and a manifest with its `Qnnn` code is a welcome contribution.

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

Got a Phomemo printer that speaks the same protocol? [Open a new-model issue](https://github.com/PassionateBytes/phomemo-driver/issues/new?template=new-model.yml) if you would rather have someone else write the manifest; you answer a few questions and run the test prints. To add it yourself:

1. Create `src/models/<id>/` with a `model.json`, starting from the M08F's.
2. Find the name it advertises and write `ble_name_pattern` for it. `phomemo-bridge devices` lists only known models; `bluetoothctl scan on` shows all devices.
   A hardware variant of a listed model, sold under the same name, gets the same pattern plus `serial_codes` with the code from its serial (see [How a printer is matched](#how-a-printer-is-matched)).
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
