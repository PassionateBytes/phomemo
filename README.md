# Phomemo

Open-source Python toolkit for Phomemo portable thermal printers over Bluetooth Low Energy.

This project provides everything needed to control Phomemo printers from Python, from low-level BLE communication to a system printer that CUPS and other IPP clients print to. It is built from a [reverse-engineered protocol specification](docs/m08f-protocol-reference.md) for the **Phomemo M08F A4 portable thermal printer**, but should be adaptable for other devices of the Phomemo family.

## Packages

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) for the Python packages plus a C printer application:

| Package | Description |
|---------|-------------|
| [**phomemo**](packages/phomemo/) | Async driver library. Modular, profile-based API for BLE communication, raster printing, device queries, and event handling. Ships `phomemo-bridge`, the daemon that owns the printer for the printer application. |
| [**printer-app**](printer-app/) | [PAPPL](https://www.msweet.org/pappl/) printer application in C: presents the M08F as an IPP Everywhere printer to CUPS and other clients, driving `phomemo-bridge`. |

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

Then switch the printer on and restart the service once (`sudo systemctl restart phomemo-printer-app`), or run `sudo phomemo-printer-app autoadd`; details and the package route in the [printer-app README](printer-app/README.md). For development or library use:

```bash
uv sync
uv run pytest
```

See the [phomemo README](packages/phomemo/README.md) for library usage.

## Supported Printers

| Model | Profile | Print Width | Status |
|-------|---------|-------------|--------|
| M08F (A4) | `M08F-A4` | 1680 px | Tested |

The profile system is extensible; see the [driver README](packages/phomemo/README.md#custom-profiles) for adding support for other models.

## Requirements

- Python 3.13+
- Linux with BlueZ (tested), macOS, or Windows
- A Phomemo M08F printer (or compatible model)

## License

- **phomemo** (driver library): [LGPL-3.0-or-later](packages/phomemo/LICENSE)
- **Protocol reference**: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
