# Phomemo

Open-source Python toolkit for Phomemo portable thermal printers over Bluetooth Low Energy.

This project provides everything needed to control Phomemo printers from Python — from low-level BLE communication to a ready-to-use terminal interface. It is built from a [reverse-engineered protocol specification](docs/m08f-protocol-reference.md) for the Phomemo M08F A4 portable thermal printer.

## Packages

The repository is structured as a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) with two independent packages:

| Package | Description |
|---------|-------------|
| [**phomemo**](packages/phomemo/) | Async driver library. Modular, profile-based API for BLE communication, raster printing, device queries, and event handling. Extensible to other Phomemo models. |
| [**phomemo-tui**](packages/phomemo-tui/) | Terminal UI built on [Textual](https://textual.textualize.io/). Interactive device scanning, status monitoring, and paper transport controls. |

## Protocol Reference

The [`docs/m08f-protocol-reference.md`](docs/m08f-protocol-reference.md) contains the complete reverse-engineered protocol specification for the Phomemo M08F, covering BLE services, raster format, the Phomemo query/event system, device configuration, and physical sensor behaviour.

## Getting Started

```bash
git clone <repo-url>
cd phomemo-printer
uv sync
```

See the [phomemo README](packages/phomemo/README.md) for library usage, or launch the TUI directly:

```bash
uv run phomemo-tui
```

## Supported Printers

| Model | Profile | Print Width | Status |
|-------|---------|-------------|--------|
| M08F (A4) | `M08F-A4` | 1680 px | Tested |
| M08F (Letter) | `M08F-Letter` | 1728 px | Untested |

The profile system is extensible — see the [driver README](packages/phomemo/README.md#custom-profiles) for adding support for other models.

## Requirements

- Python 3.13+
- Linux with BlueZ (tested), macOS, or Windows
- A Phomemo M08F printer (or compatible model)

## License

- **phomemo** (driver library) — [LGPL-3.0-or-later](packages/phomemo/LICENSE)
- **phomemo-tui** (terminal UI) — [GPL-3.0-or-later](packages/phomemo-tui/LICENSE)
- **Protocol reference** — [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
