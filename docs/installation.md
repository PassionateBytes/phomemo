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

Every route delivers the same two packages:

| Package | Contents |
|---|---|
| `phomemo-driver` | The printer app, both system units, the service user and the configuration files. Pulls in `python3-phomemo`, Avahi, BlueZ and CUPS; recommends `cups-browsed`. |
| `python3-phomemo` | The Python library and the `phomemo-bridge` command. Install it alone if you only need the library. |

The packages enable both services and start them on first installation. Upgrades restart them and keep your changes to the configuration files.

### DNF (Fedora, COPR)

```bash
sudo dnf copr enable passionatebytes/phomemo-driver
sudo dnf install phomemo-driver
```

The first command adds the COPR repository [passionatebytes/phomemo-driver](https://copr.fedorainfracloud.org/coprs/passionatebytes/phomemo-driver/), the second installs the complete driver package. COPR is the primary route for Fedora.

### APT (Debian, Ubuntu)

The Debian packages are built on the [Open Build Service](https://build.opensuse.org/project/show/home:passionatebytes:phomemo-driver) for Debian 13 (trixie) and unstable, Ubuntu 24.04 LTS and the current Ubuntu releases. Pick the directory that matches your release (`Debian_13`, `Debian_Unstable`, `xUbuntu_24.04`, `xUbuntu_25.10`, `xUbuntu_26.04`, ...):

```bash
distro=Debian_13
repo="https://download.opensuse.org/repositories/home:/passionatebytes:/phomemo-driver/$distro"
curl -fsSL "$repo/Release.key" | gpg --dearmor | sudo tee /etc/apt/keyrings/phomemo-driver.gpg >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/phomemo-driver.gpg] $repo/ /" | sudo tee /etc/apt/sources.list.d/phomemo-driver.list
sudo apt update
sudo apt install phomemo-driver
```

Debian 12 and Ubuntu releases before 24.04 are not supported: their Python, bleak and Pillow are older than the library's floors.

### DNF (Fedora, Open Build Service)

The same OBS project also builds the RPM packages, as an alternative to COPR (same spec, different build service and signing key; use one of the two repositories, not both):

```bash
release=$(rpm -E %fedora)
sudo dnf config-manager addrepo --from-repofile="https://download.opensuse.org/repositories/home:/passionatebytes:/phomemo-driver/Fedora_$release/home:passionatebytes:phomemo-driver.repo"
sudo dnf install phomemo-driver
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
