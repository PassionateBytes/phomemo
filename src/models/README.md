# Printer models

Every printer model the driver supports is described here, once, for all
parts of the stack: the Python library builds its profile from the
description, `phomemo-bridge` uses that profile for each printer it links
to, and the printer application builds its PAPPL driver (media, resolution,
margins, names, icons) from the same files.

A model is a directory named after its identifier (lower case, also the
PAPPL driver name):

```
m08f/
  model.json      the description
  icon-48.png     printer icons in the three sizes PAPPL uses
  icon-128.png
  icon-512.png
```

## model.json

| Field | Meaning |
|---|---|
| `id` | The identifier; must equal the directory name. |
| `make`, `name` | Manufacturer and model as users see them: make-and-model "Phomemo M08F", device ID `MFG:Phomemo;MDL:M08F;CMD:PHOMEMO;`. |
| `ble_name_pattern` | Regular expression matched against the name the printer advertises over Bluetooth; it decides which model a printer is. |
| `print_width_px`, `dpi` | Print head width in dots and resolution. |
| `band_height` | Rows per `GS v 0` raster command. |
| `sheet_length_mm` | Default sheet length in the feed direction. |
| `top_margin_mm`, `bottom_margin_mm` | Unprintable lead at the top of a sheet and the space kept free at its end. |
| `density` | Optional: the `ESC N 04` concentration values for `low`, `medium` and `high`. Without it the model has no density control. |
| `media` | Sheet sizes as PWG names; exactly one has `"default": true`. |
| `ble` | Link parameters: `max_chunk_bytes`, `negotiate_mtu`, `write_with_response`, `chunk_delay_s` and the four characteristic UUIDs. |
| `features` | Optional: `escpos_queries` when standard ESC/POS queries answer. |

A description with a missing or mistyped field is rejected with the file and
the field named.

## How the parts get them

- Library: a hatch build hook copies this directory into the wheel and the
  sdist as package data. At import it reads `PHOMEMO_MODELS_DIR` when set,
  else that package copy, else this directory in a source checkout.
- Printer application: `embed-models.sh` builds every description and its
  icons into the binary (`models_data.c`, generated at build time).
  `PHOMEMO_MODELS_DIR` set at start replaces the built-in descriptions with
  the directories found there, for trying out a model without a rebuild.

## Adding a model

A Phomemo model that speaks the same protocol needs only a new directory:
measure the head width and margins, find the name it advertises
(`phomemo-bridge devices` lists only known models; `bluetoothctl scan on`
shows all), pick the density values, add icons, and print the test page
(`phomemo-bridge testpage -a <address>`). Contributions of new models are
very welcome: open a pull request with the directory and a note on how you
tested it. Models with real protocol differences also need code in the
library; open an issue first.

Like the library that ships them, the descriptions are licensed under the
GNU LGPL, version 3 or later.
