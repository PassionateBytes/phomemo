<p align="center">
  <img src="src/models/m08f/icon-128.png" alt="Phomemo M08F" width="96">
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

phomemo-driver is a complete Linux printer driver stack for the Phomemo M08F, an A4 thermal printer that only speaks Bluetooth Low Energy. Once installed, the printer shows up in CUPS and in the print dialog of every application: pick it, press Print, done. No vendor app, no phone.

```
your application ──IPP──▶ CUPS ──IPP──▶ printer app ──socket──▶ bridge ──Bluetooth──▶ M08F
```

> [!NOTE]
> Beta: version 0.x. Linux only (CUPS, BlueZ); packaged for Fedora, other distributions install from source.

## Features

- **A real system printer:** an IPP Everywhere printer app (PAPPL) that CUPS finds by DNS-SD, with its own web interface. Print from any application, `lp`, or any IPP client.
- **A4 and A5,** A5 rotated automatically to the printer's paper path.
- **Grayscale done right:** documents and photos rendered with ordered or diffusion dithering; print density chosen per job.
- **Printer state where you expect it:** battery level as a supply gauge, lid open, out of paper and printer off reported as printer state with messages that say what to do.
- **Recovers on its own:** a lid opened mid-page, a sheet that runs out or a dropped Bluetooth connection pauses the job; close the lid or insert a sheet and the page prints again.
- **Starts with the system:** the printer app and the bridge run as system services, enabled on install.
- **Several printers** at once, each with its own queue. Identify and test page from the web interface.

## Install

From the COPR repository (Fedora):

```bash
sudo dnf copr enable passionatebytes/phomemo-driver
sudo dnf install phomemo-driver
```

Or from source:

```bash
sudo dnf install gcc make pkgconf-pkg-config pappl-devel cups-devel python3 cups avahi bluez
git clone https://github.com/PassionateBytes/phomemo-driver.git
cd phomemo-driver
sudo make
```

> [!IMPORTANT]
> After installing, **register the printer** with the printer app: switch it on and run `sudo phomemo-printer-app autoadd`. See [First steps](https://passionatebytes.github.io/phomemo-driver/first-steps.html).

## Print

From any application's print dialog, or from the command line:

```bash
lp -d Phomemo_M08F_DDEEFF document.pdf
lp -d Phomemo_M08F_DDEEFF -o media=iso_a5_148x210mm -o phomemo-tone=ordered photo.png
```

More in [Everyday use](https://passionatebytes.github.io/phomemo-driver/everyday-use.html).

## Supported printers

| Model | ID | Status |
|-------|----|--------|
| Phomemo M08F (A4) | `m08f` | Tested |

Each model is described once in [`src/models/`](src/models/), shared by the whole stack. A Phomemo model that speaks the same protocol needs only a new model manifest there: **contributions of new models are very welcome**, see [Printer models](https://passionatebytes.github.io/phomemo-driver/models.html).

## Python library

The stack is built on `phomemo`, an asyncio library that drives the printer directly over Bluetooth: scanning, printing images and bitmaps, sensors and events.

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

Built on [PAPPL](https://www.msweet.org/pappl/) and [CUPS](https://openprinting.github.io/cups/) from OpenPrinting and on [bleak](https://github.com/hbldh/bleak). The protocol work was informed by [vivier/phomemo-tools](https://github.com/vivier/phomemo-tools), [theacodes/phomemo_m02s](https://github.com/theacodes/phomemo_m02s) and [gbl/phomemo](https://github.com/gbl/phomemo).

## License

GPL-3.0-or-later; the Python library and the model manifests are LGPL-3.0-or-later, the documentation CC BY-SA 4.0. Each file states its licence in its header; see [COPYING](COPYING).

Not affiliated with or endorsed by Phomemo. Product names are trademarks of their owners.
