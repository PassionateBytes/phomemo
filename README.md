# Phomemo

Open-source Python toolkit for Phomemo portable thermal printers over Bluetooth Low Energy.

This project provides everything needed to control Phomemo printers from Python, from low-level BLE communication to a system printer that CUPS and other IPP clients print to. It is built from a [reverse-engineered protocol specification](docs/m08f-protocol-reference.md) for the **Phomemo M08F A4 portable thermal printer**, but should be adaptable for other devices of the Phomemo family.

## Packages

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) for the Python packages plus a C printer application:

| Package | Description |
|---------|-------------|
| [**phomemo**](packages/phomemo/) | Async driver library. Modular, profile-based API for BLE communication, raster printing, device queries, and event handling. Ships `phomemo-bridge`, the daemon that owns the printer for the printer application. |
| [**printer-app**](printer-app/) | [PAPPL](https://www.msweet.org/pappl/) printer application in C: presents the M08F as an IPP Everywhere printer to CUPS and other clients, driving `phomemo-bridge`. |

## Protocol Reference

The [`docs/m08f-protocol-reference.md`](docs/m08f-protocol-reference.md) contains the complete reverse-engineered protocol specification for the Phomemo M08F, covering BLE services, raster format, the Phomemo query/event system, device configuration, and physical sensor behaviour.

## Getting Started

```bash
git clone <repo-url>
cd phomemo-printer
uv sync
```

See the [phomemo README](packages/phomemo/README.md) for library usage. To use the M08F as a system printer, build and install the printer application and the bridge daemon as described in the [printer-app README](printer-app/README.md).

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
