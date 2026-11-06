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
- Python 3.13 or later
- A Phomemo M08F thermal printer (see [Printer models](models.md))

## Package managers

Two package formats today: RPMs from COPR for Fedora, and a snap for Ubuntu and every other distribution with snapd. More are welcome, see [Contributing](contributing.md).

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

### Snap (Ubuntu and every distribution with snapd)

```bash
sudo snap install phomemo-printer-app
sudo snap connect phomemo-printer-app:bluez
sudo snap connect phomemo-printer-app:avahi-control
```

The snap `phomemo-printer-app` contains both services with everything they need (PAPPL, Python, the library) and starts them on installation. It talks to the BlueZ and Avahi daemons of your system, so both must be running (they are on Ubuntu desktop). The two `snap connect` commands grant it that access; they are needed until the Snap Store grants the snap automatic connections.

The `phomemo-printer-app` command works as described everywhere in this documentation (`sudo phomemo-printer-app autoadd`, ...). The bridge command line is `phomemo-printer-app.bridge`:

```bash
phomemo-printer-app.bridge status
```

What differs from the other installations:

| What | In the snap |
|---|---|
| Services | `snap services phomemo-printer-app` lists `phomemo-bridge` and `phomemo-printer-app-server`; `sudo snap restart phomemo-printer-app` restarts both |
| Logs | `sudo snap logs -f phomemo-printer-app` |
| Configuration files | `/var/snap/phomemo-printer-app/common/bridge.toml` and `/var/snap/phomemo-printer-app/common/phomemo-printer-app.conf`, created from the packaged defaults at the services' first start and kept across upgrades |
| Bridge socket | `/var/snap/phomemo-printer-app/common/bridge.sock` |
| Printer app state and spool | `/var/snap/phomemo-printer-app/common/` |
| Web interface | [http://localhost:8000/](http://localhost:8000/), as everywhere |
| Service user | None: inside the snap both services run as root, confined by snapd |

Both services need the interfaces `bluez` (the bridge) and `avahi-control`, `network` and `network-bind` (the printer app); `snap connections phomemo-printer-app` shows which are connected. A snap can print files from your home directory through the `home` interface, which connects on its own.

```{tip}
`sudo snap install --channel=edge phomemo-printer-app` gives you the build of the latest `main`; `sudo snap refresh --channel=stable phomemo-printer-app` goes back to releases.
```

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
