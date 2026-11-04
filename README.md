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

phomemo-driver turns the Phomemo M08F, an A4 thermal printer that only speaks Bluetooth Low Energy, into an ordinary IPP printer for CUPS, your desktop, phones and every other IPP client. The Python library underneath drives the printer directly, if you prefer code.

```
your application ──IPP──▶ CUPS ──IPP──▶ printer app ──socket──▶ bridge ──Bluetooth──▶ M08F
```

## Install

From source, on Fedora:

```bash
sudo dnf install gcc make pkgconf-pkg-config pappl-devel cups-devel python3 cups avahi bluez
git clone https://github.com/PassionateBytes/phomemo-driver.git
cd phomemo-driver
sudo make
```

Or from the COPR repository:

```bash
sudo dnf copr enable passionatebytes/phomemo-driver
sudo dnf install phomemo-driver
```

Just the Python library: `pip install phomemo`.

> [!IMPORTANT]
> After installing, **register the printer** with the printer app: switch it on and run `sudo phomemo-printer-app autoadd`. See [First steps](https://passionatebytes.github.io/phomemo-driver/first-steps.html).

## Supported printers

| Model | ID | Status |
|-------|----|--------|
| Phomemo M08F (A4) | `m08f` | Tested |

Each model is described once in [`src/models/`](src/models/), shared by the library, the bridge and the printer app. A Phomemo model that speaks the same protocol needs only a new model manifest there: **contributions of new models are very welcome**, see [Printer models](https://passionatebytes.github.io/phomemo-driver/models.html).

## Repository

| Path | What |
|------|------|
| [`src/phomemo/`](src/phomemo/) | Python library and the bridge (`phomemo-bridge`) |
| [`src/printer-app/`](src/printer-app/) | PAPPL printer app in C (`phomemo-printer-app`) |
| [`src/models/`](src/models/) | Model manifests: one per printer model |
| [`docs/`](docs/) | Documentation site, including the [M08F protocol reference](docs/m08f-protocol-reference.md) |
| [`packaging/`](packaging/) | System units, configuration, RPM specs |

## License

Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions.

| Part | Licence | Text |
|------|---------|------|
| Python library and bridge (`src/phomemo/`), model manifests (`src/models/`) | GNU LGPL, version 3 or later | [COPYING.LESSER](src/phomemo/COPYING.LESSER), with the GNU GPL it builds on in [COPYING](src/phomemo/COPYING) |
| Printer app (`src/printer-app/`) | GNU GPL, version 3 or later | [COPYING](src/printer-app/COPYING) |
| Packaging, build files and everything else not listed here | GNU GPL, version 3 or later | [COPYING](COPYING) |
| Documentation (`docs/`, the READMEs) | CC BY-SA 4.0 | [docs/LICENSE](docs/LICENSE) |

Each source file states its licence in its header. Bundled third-party code keeps its own licence: [cJSON](src/printer-app/third_party/cJSON.LICENSE) (MIT) in the printer app, and the documentation's fonts (SIL Open Font License 1.1, see `docs/_static/fonts/`).

## Contact

Paul Bütof, Passionate Bytes Solutions, [www.passionate-bytes.com](https://www.passionate-bytes.com). Bug reports and questions: [GitHub issues](https://github.com/PassionateBytes/phomemo-driver/issues).
