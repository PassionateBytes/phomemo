# Installation

The driver package delivers two parts, both runnning as system services:

- the **printer app** (`phomemo-printer-app`) presents the printer to CUPS and other IPP clients, and
- the **bridge** (`phomemo-bridge`) owns the Bluetooth connection to the printer.

You can install both from source or directly from a package. If you only want the Python library, install it from PyPI (see below).

```{important}
After installing the driver package you need to follow the [First steps](first-steps.md) for the one-time setup of your printer. This step is required to register your printer with the driver, and is required for your printer to be discovered by your system.
```

## Requirements

- Linux with BlueZ (tested on Fedora)
- CUPS and Avahi (DNS-SD), so applications can discover the printer
- Python 3.12 or later
- A Phomemo M08F thermal printer (see [Printer models](models.md))

## Package managers

More package formats are planned.

### DNF (Fedora, COPR)

```bash
sudo dnf copr enable passionatebytes/phomemo-driver
sudo dnf install phomemo-driver
```

The first command adds the COPR repository [passionatebytes/phomemo-driver](https://copr.fedorainfracloud.org/coprs/passionatebytes/phomemo-driver/), the second installs the complete driver package.

| Package | Contents |
|---|---|
| `phomemo-driver` | The printer app, both system units, the service user, presets and configuration files. Pulls in `python3-phomemo`, `avahi`, `bluez` and `cups`; recommends `cups-browsed`. |
| `python3-phomemo` | The Python library and the `phomemo-bridge` command. Install it alone if you only need the library. |

The package enables both services and starts them on first installation. Upgrades restart them and keep your changes to the configuration files.

## From source

### Step 1: install the dependencies

```bash
sudo dnf install gcc make pkgconf-pkg-config pappl-devel cjson-devel cups-devel python3 cups avahi bluez
```

These are the Fedora package names for everything the build and the services need.

### Step 2: clone and install

```bash
git clone https://github.com/PassionateBytes/phomemo-driver.git
cd phomemo-driver
sudo make
```

`sudo make` builds the application and installs everything under `/usr/local`. It then creates the service user, then enables and starts the printer driver services.

Installed components:

| What | Where |
|---|---|
| Printer app | `/usr/local/bin/phomemo-printer-app` |
| Python library and bridge, in a virtual environment | `/usr/local/lib/phomemo`, linked as `/usr/local/bin/phomemo-bridge` |
| System units | `/etc/systemd/system/phomemo-bridge.service`, `/etc/systemd/system/phomemo-printer-app.service` |
| Presets that enable the units | `/usr/lib/systemd/system-preset/` |
| Service user `phomemo` for the bridge | `/etc/sysusers.d/phomemo.conf` |
| Configuration files | `/etc/phomemo/bridge.toml`, `/etc/phomemo-printer-app.conf` |

```{note}
pip fetches the library's Python dependencies during the install, so you need a network connection.
```

```{tip}
`sudo make uninstall` reverses the installation. It keeps the configuration files and the printer app's state in `/var/lib`.
```

## PyPI (library only)

```bash
pip install phomemo
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add phomemo
```

This gives you the library and the `phomemo-bridge` command line tool, without the printer app and without system units.

```{tip}
You can still run the bridge by hand: `phomemo-bridge server`. Its socket then lives in `$XDG_RUNTIME_DIR`.
```

## Next

- [First steps](first-steps.md): register the printer and print a first page.
- [Configuration](configuration.md): the configuration files and their settings.
