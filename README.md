<p align="center">
  <img src="src/models/m08f/icon-128.png" alt="Phomemo M08F" width="128">
</p>

<h1 align="center">phomemo-driver</h1>

<p align="center">
  <b>Print to a Phomemo thermal printer like to any other printer.</b><br>
  <a href="https://passionatebytes.github.io/phomemo-driver/">Documentation</a> ·
  <a href="https://passionatebytes.github.io/phomemo-driver/installation.html">Installation</a> ·
  <a href="https://passionatebytes.github.io/phomemo-driver/first-steps.html">First steps</a> ·
  <a href="https://passionatebytes.github.io/phomemo-driver/contributing.html">Contributing</a>
</p>

<p align="center">
  <a href="https://github.com/PassionateBytes/phomemo-driver/actions/workflows/ci.yml"><img src="https://github.com/PassionateBytes/phomemo-driver/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://copr.fedorainfracloud.org/coprs/passionatebytes/phomemo-driver/"><img src="https://copr.fedorainfracloud.org/coprs/passionatebytes/phomemo-driver/package/phomemo-driver/status_image/last_build.png" alt="COPR build"></a>
  <a href="https://passionatebytes.github.io/phomemo-driver/"><img src="https://github.com/PassionateBytes/phomemo-driver/actions/workflows/docs.yml/badge.svg" alt="Docs"></a>
  <a href="https://pypi.org/project/phomemo/"><img src="https://img.shields.io/pypi/v/phomemo" alt="PyPI"></a>
  <a href="COPYING"><img src="https://img.shields.io/badge/license-GPL--3.0%20%2F%20LGPL--3.0-blue" alt="License"></a>
</p>

The Phomemo M08F is an A4 thermal printer that only speaks Bluetooth LE with a custom protocol. The printer normally only works through the manufacturer's phone app.  
This project provides a **fully featured printer driver stack** for this printer. Once installed, your Phomemo M08F shows up as a regular printer on your system. No vendor app, no phone required.

> **Own another Phomemo model?** Only the M08F has been tested so far. Phomemo's other printers, especially the Bluetooth ones, most likely speak the same protocol and need an owner to try them. [Open an issue](https://github.com/PassionateBytes/phomemo-driver/issues/new?template=new-model.yml) with the model name and the name it advertises over Bluetooth; no coding needed.

## Features

- **A real system printer:** an IPP Everywhere printer app (PAPPL) that CUPS finds by DNS-SD, with its own web interface. Print from any application, `lp`, or any IPP client.
- **Grayscale done right:** documents and photos rendered with ordered or diffusion dithering; print density chosen per job.
- **Printer state reporting:** battery level as a supply gauge, lid open, out of paper and printer off reported as printer state with messages that say what to do.
- **Recovers on its own:** a lid opened mid-page, a sheet that runs out or a dropped Bluetooth connection pauses the job; close the lid or insert a sheet and the page prints again automatically.
- **Starts with the system:** the printer app and the bridge run as system services, enabled on install.
- **Several printers** at once, each with its own queue. Identify and test page features available from the web interface.

## Install

From the COPR repository (Fedora):

```bash
sudo dnf copr enable passionatebytes/phomemo-driver
sudo dnf install phomemo-driver
```

On Debian 13 and Ubuntu 24.04 or newer, from the [Open Build Service](https://build.opensuse.org/project/show/home:passionatebytes:phomemo-driver) repository (pick your release's directory, see [Installation](https://passionatebytes.github.io/phomemo-driver/installation.html)):

```bash
repo="https://download.opensuse.org/repositories/home:/passionatebytes:/phomemo-driver/Debian_13"
curl -fsSL "$repo/Release.key" | gpg --dearmor | sudo tee /etc/apt/keyrings/phomemo-driver.gpg >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/phomemo-driver.gpg] $repo/ /" | sudo tee /etc/apt/sources.list.d/phomemo-driver.list
sudo apt update && sudo apt install phomemo-driver
```

Or from source:

```bash
sudo dnf install gcc make pkgconf-pkg-config pappl-devel cjson-devel cups-devel python3 cups avahi bluez
git clone https://github.com/PassionateBytes/phomemo-driver.git
cd phomemo-driver
sudo make
```

> [!IMPORTANT]
> After installing, **register the printer** with the printer app! Turn the printer on, enable Bluetooth on your computer, and run `sudo phomemo-printer-app autoadd`.  
> See [First steps](https://passionatebytes.github.io/phomemo-driver/first-steps.html) and [Everyday use](https://passionatebytes.github.io/phomemo-driver/everyday-use.html) for more details.

## Supported printers

| Model | ID | Status |
|-------|----|--------|
| Phomemo M08F (A4) | `m08f` | Tested |

Each model is described once in [`src/models/`](src/models/), shared by the whole stack. A Phomemo model that speaks the same protocol needs only a new model manifest there.   
**Contributions of new models are very welcome**, see [Printer models](https://passionatebytes.github.io/phomemo-driver/models.html) for more details and feel free to file an Issue or PR.

## Python library

At the core of this project sits `phomemo`, an asyncio python library that drives the printer directly via Bluetooth.
This library handles connectivity, printing images and bitmaps, sensors and events.

```bash
pip install phomemo
```

```python
import asyncio
from phomemo import Printer, discover

async def main():
    devices = await discover(name_pattern=r"^M08F")
    async with Printer("m08f", devices[0]) as printer:
        await printer.connect()
        await printer.wait_for_ready(timeout=60)
        await printer.print_image("photo.png")

asyncio.run(main())
```

See the [library guide](https://passionatebytes.github.io/phomemo-driver/library.html) and the [M08F protocol reference](https://passionatebytes.github.io/phomemo-driver/m08f-protocol-reference.html).

## Acknowledgements

Built on [PAPPL](https://www.msweet.org/pappl/) and [CUPS](https://openprinting.github.io/cups/) from OpenPrinting and on [bleak](https://github.com/hbldh/bleak). The device protocol reverse engineering was informed by [vivier/phomemo-tools](https://github.com/vivier/phomemo-tools), [theacodes/phomemo_m02s](https://github.com/theacodes/phomemo_m02s) and [gbl/phomemo](https://github.com/gbl/phomemo).

## License

GPL-3.0-or-later; the Python library and the model manifests are LGPL-3.0-or-later, the documentation CC BY-SA 4.0. Each file states its licence in its header; see [COPYING](COPYING).

Not affiliated with or endorsed by Phomemo. Product names are trademarks of their owners.
