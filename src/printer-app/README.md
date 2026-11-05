# phomemo-printer-app

The printer app of [phomemo-driver](https://github.com/PassionateBytes/phomemo-driver): a [PAPPL](https://www.msweet.org/pappl/) printer application in C that presents each registered Phomemo printer as an IPP Everywhere printer, so CUPS, desktops and phones print to it like to any other printer. It handles IPP, DNS-SD, the job queue and the web interface; the Bluetooth side lives in `phomemo-bridge`.

```
client ──IPP──▶ phomemo-printer-app ──unix socket──▶ phomemo-bridge ──Bluetooth──▶ printer
                (PAPPL, C)                            (Python)
```

**Using it:** see the documentation: [Installation](https://passionatebytes.github.io/phomemo-driver/installation.html), [First steps](https://passionatebytes.github.io/phomemo-driver/first-steps.html), [Configuration](https://passionatebytes.github.io/phomemo-driver/configuration.html), [Command line](https://passionatebytes.github.io/phomemo-driver/command-line.html).

## Build and test

Dependencies on Fedora: `pappl-devel`, `cjson-devel`, `cups-devel`, `gcc`, `make`, `pkgconf-pkg-config`; the end-to-end tests also use `ipptool` (package `cups-ipptool`) and Ghostscript.

```bash
make -C src/printer-app            # builds src/printer-app/phomemo-printer-app
make -C src/printer-app test       # C unit tests
uv run pytest src/phomemo/tests/test_printer_app.py   # end-to-end against a fake bridge
```

The model manifests in [`../models/`](../models/) are built into the binary at build time; `PHOMEMO_MODELS_DIR` set at start replaces them with a directory of manifests.

## Sources

| File | Role |
|------|------|
| `main.c` | Driver table built from the model manifests, auto-add rule, `papplMainloop` entry point. |
| `models.c` | The model table: the built-in manifests, or the directories under `PHOMEMO_MODELS_DIR` when set. |
| `embed-models.sh` | Builds `../models/*` (manifest and icons) into `models_data.c` at build time. |
| `device.c` | The `phomemo://` device scheme over the bridge socket, status mapping. |
| `driver.c` | Printer capabilities from the model (media, resolution, margins, icons) plus `phomemo-tone`, and option mapping helpers. |
| `job.c` | Raster callbacks: wait for a sheet, stream rows, finish the page, surface errors. |
| `bridge.c` | Line-oriented JSON client for the bridge protocol. |

How the parts fit together: [Driver stack](https://passionatebytes.github.io/phomemo-driver/driver-stack.html).

## License

Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions.

GNU General Public License, version 3 or later: see [COPYING](COPYING). This README is documentation and licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
