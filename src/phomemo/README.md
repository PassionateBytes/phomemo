# phomemo

**Async Python library for Phomemo thermal printers over Bluetooth Low Energy.**

Scan for printers, print images and bitmaps, read the battery and the lid and paper sensors, and react to the printer's events, all from asyncio. Built from a [reverse-engineered protocol reference](https://passionatebytes.github.io/phomemo-driver/m08f-protocol-reference.html) for the Phomemo M08F, with one profile per printer model.

The package also ships `phomemo-bridge`, the service the [phomemo-driver](https://github.com/PassionateBytes/phomemo-driver) printer app prints through.

**Documentation:** [passionatebytes.github.io/phomemo-driver/library](https://passionatebytes.github.io/phomemo-driver/library.html)

## Install

```bash
pip install phomemo
```

Python 3.12 or later, and a platform with Bluetooth Low Energy (Linux with BlueZ is tested).

## Print a page

```python
import asyncio

from phomemo import Density, ImageFit, Printer


async def main() -> None:
    async with Printer("m08f") as printer:
        await printer.connect()  # scans for the M08F in range and connects
        await printer.wait_for_ready(timeout=60)  # lid closed, sheet loaded
        await printer.print_image("photo.png", density=Density.MEDIUM, fit=ImageFit.FIT_PAGE)
        await printer.eject_paper()


asyncio.run(main())
```

Where to go next:

- [Library guide](https://passionatebytes.github.io/phomemo-driver/library.html): scanning, printing, events, device queries, profiles.
- [API reference](https://passionatebytes.github.io/phomemo-driver/api.html).
- [The bridge](https://passionatebytes.github.io/phomemo-driver/command-line.html): `phomemo-bridge` on the command line.

## Supported printers

| Model | Profile | Status |
|-------|---------|--------|
| Phomemo M08F (A4) | `m08f` | Tested |

New models are very welcome: see [Printer models](https://passionatebytes.github.io/phomemo-driver/models.html).

## License

Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions.

GNU Lesser General Public License, version 3 or later: see [COPYING.LESSER](https://github.com/PassionateBytes/phomemo-driver/blob/main/src/phomemo/COPYING.LESSER) and the GNU General Public License it builds on in [COPYING](https://github.com/PassionateBytes/phomemo-driver/blob/main/src/phomemo/COPYING). This README is documentation and licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
