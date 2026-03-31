# phomemo-tui

Terminal UI for Phomemo portable thermal printers, built on [Textual](https://textual.textualize.io/) and the [phomemo](../phomemo/) driver library.

Provides an interactive interface for discovering printers, monitoring device state, and controlling paper transport — all from the terminal.

## Features

- BLE device scanning and selection
- Live device status display (battery, firmware, serial, lid, paper, auto-off timer)
- Real-time event log (lid opens/closes, paper insertion, print completion)
- Paper feed and full-sheet eject controls
- Keyboard-driven navigation

## Installation

```bash
pip install phomemo-tui
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add phomemo-tui
```

This installs the `phomemo` driver library as a dependency.

## Requirements

- Python 3.13+
- A Phomemo thermal printer (M08F tested)
- Platform with BLE support — Linux/BlueZ (tested), macOS, Windows

## Usage

Launch the TUI:

```bash
phomemo-tui
```

### Screens

**Scan screen** — discovers nearby BLE devices. Select a device from the list to connect. Press `r` to re-scan.

**Main screen** — shows once connected. Displays device information and a live event log. Available controls:

| Key | Action |
|-----|--------|
| `i` | Refresh device info |
| `f` | Feed paper |
| `e` | Eject paper |
| `d` | Disconnect |
| `q` | Quit |

## License

[GPL-3.0-or-later](LICENSE)
