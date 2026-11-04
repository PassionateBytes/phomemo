# Phomemo

Open-source Python toolkit for Phomemo portable thermal printers over Bluetooth Low Energy.

This project provides everything needed to control Phomemo printers from Python, from low-level BLE communication to a system printer that CUPS and other IPP clients print to. It is built from a [reverse-engineered protocol specification](docs/m08f-protocol-reference.md) for the **Phomemo M08F A4 portable thermal printer**, but should be adaptable for other devices of the Phomemo family.

## Packages

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) for the Python packages plus a C printer application:

| Package | Description |
|---------|-------------|
| [**phomemo**](src/phomemo/) | Async driver library. Modular, profile-based API for BLE communication, raster printing, device queries, and event handling. Ships `phomemo-bridge`, the daemon that owns the printer for the printer application. |
| [**printer-app**](src/printer-app/) | [PAPPL](https://www.msweet.org/pappl/) printer application in C: presents the M08F as an IPP Everywhere printer to CUPS and other clients, driving `phomemo-bridge`. |

Documentation site: [passionatebytes.github.io/phomemo-driver](https://passionatebytes.github.io/phomemo-driver/) (built from this repository's READMEs, the protocol reference and the library's docstrings).

## Protocol Reference

The [`docs/m08f-protocol-reference.md`](docs/m08f-protocol-reference.md) contains the complete reverse-engineered protocol specification for the Phomemo M08F, covering BLE services, raster format, the Phomemo query/event system, device configuration, and physical sensor behaviour.

## Getting Started

Use the M08F as a system printer. On Fedora, from the COPR repository:

```bash
sudo dnf copr enable passionatebytes/phomemo-driver
sudo dnf install phomemo-driver      # the whole driver; python3-phomemo alone for just the library
```

From source (Fedora; `pappl-devel` and `cups-devel` needed to build):

```bash
git clone https://github.com/PassionateBytes/phomemo-driver.git
cd phomemo-driver
sudo make              # builds, installs under /usr/local, enables and starts both services
```

Then switch the printer on and restart the service once (`sudo systemctl restart phomemo-printer-app`), or run `sudo phomemo-printer-app autoadd`; details and the package route in the [printer-app README](src/printer-app/README.md). For development or library use:

```bash
uv sync --all-packages
uv run pytest src/phomemo/tests
```

See the [phomemo README](src/phomemo/README.md) for library usage.

## Supported Printers

| Model | ID | Print Width | Status |
|-------|----|-------------|--------|
| M08F (A4) | `m08f` | 1680 px | Tested |

Each model is described once in [`src/models/`](src/models/README.md), shared by the library, the bridge and the printer application. A Phomemo model that speaks the same protocol needs only a new description there; contributions of new models are very welcome.

## Requirements

- Python 3.13+
- Linux with BlueZ (tested), macOS, or Windows
- A Phomemo M08F printer (or compatible model)

## License

Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions.

| Part | Licence | Text |
|------|---------|------|
| Python library and bridge daemon (`src/phomemo/`), printer model descriptions (`src/models/`) | GNU LGPL, version 3 or later | [COPYING.LESSER](src/phomemo/COPYING.LESSER), with the GNU GPL it builds on in [COPYING](src/phomemo/COPYING) |
| Printer application (`src/printer-app/`) | GNU GPL, version 3 or later | [COPYING](src/printer-app/COPYING) |
| Packaging, build files and everything else not listed here | GNU GPL, version 3 or later | [COPYING](COPYING) |
| Documentation (`docs/`, the READMEs) | CC BY-SA 4.0 | [docs/LICENSE](docs/LICENSE) |

Each source file states its licence in its header. Bundled third-party code keeps its own licence: [cJSON](src/printer-app/third_party/cJSON.LICENSE) (MIT) in the printer application.

## Contact

Paul Bütof, Passionate Bytes Solutions, [www.passionate-bytes.com](https://www.passionate-bytes.com). Bug reports and questions: [GitHub issues](https://github.com/PassionateBytes/phomemo-driver/issues).
