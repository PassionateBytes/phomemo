# phomemo-driver

A driver stack for the Phomemo M08F A4 thermal printer over Bluetooth Low Energy: a Python library, the `phomemo-bridge` daemon that owns the printer, and a PAPPL printer application that presents it to CUPS and every other IPP client as an ordinary printer.

```
application ──IPP──▶ CUPS ──IPP──▶ phomemo-printer-app ──unix socket──▶ phomemo-bridge ──BLE──▶ M08F
```

- **Printing from the desktop**: install the two packages, switch the printer on, print. See [Printer application](printer-app.md).
- **From Python**: the [library](library.md) drives the printer directly, from discovery to raster printing and sensor events.
- **How the printer works**: the [protocol reference](m08f-protocol-reference.md) documents everything learned about the M08F.

```{toctree}
:maxdepth: 2
:hidden:

printer-app
library
m08f-protocol-reference
api
```

Source and issues: [github.com/PassionateBytes/phomemo-driver](https://github.com/PassionateBytes/phomemo-driver).
