# Driver stack

A print job passes through three programs on its way to the printer. Each one has a single job and knows only what that job needs:

```
application
    │  IPP (lp, a print dialog, ...)
    ▼
CUPS queue                 temporary (from DNS-SD) or permanent
    │  IPP
    ▼
phomemo-printer-app        PAPPL: job queue, raster callbacks
    │  unix socket: JSON lines + raw rows
    ▼
phomemo-bridge             one session per client
    │  Bluetooth LE (through the phomemo library)
    ▼
printer (M08F)
```

The model manifests sit beside the chain: every part reads its printer models from them.

How the parts work together on a job is in [Print flow](print-flow.md).

## Printer app

`phomemo-printer-app`, in `src/printer-app/`: C, built on [PAPPL](https://www.msweet.org/pappl/).

**Place in the chain.** It receives print jobs over IPP, from CUPS or any other IPP client, and announces its printers on the network with DNS-SD. It sends each page on to the bridge over the bridge's unix socket, as commands and raw raster rows. Events coming back from the bridge (waiting for a sheet, lid open, progress) end up as `printer-state-reasons` and job messages, which the IPP clients show.

**What it does.** It presents each registered printer as an IPP Everywhere printer: job queue, rendering of the documents to an 8-bit gray raster, a web interface for adding printers and printing a test page, and a command line for the same.

**What it knows.**

- The registered printers, each with its device URI:

  ```
  phomemo://AA-BB-CC-DD-EE-FF?model=m08f
  ```

  Dashes replace the colons, because a URI host cannot hold colons.
- The model manifests built into its binary: media, resolution, margins, names, icons.
- Where the bridge listens: `PHOMEMO_BRIDGE_SOCKET`, else `$XDG_RUNTIME_DIR/phomemo-bridge.sock`, else `/run/phomemo/bridge.sock` (the system services).

It knows nothing about Bluetooth.

## Bridge

`phomemo-bridge`, in `src/phomemo/src/phomemo/bridge/`: Python.

**Place in the chain.** It takes commands on a unix socket, one client at a time: the printer app, or the `phomemo-bridge` [command line](command-line.md). It talks to the printer over Bluetooth LE through the library, and answers its client with replies and pushed events.

**What it does.** It owns the Bluetooth connection, to one printer at a time. For each page it connects if needed, waits until a sheet is loaded, fits the page to the sheet, streams it to the printer and ejects the sheet. An interrupted page is printed again (see [Print flow](print-flow.md#interrupted-pages)). It also scans for printers, reports their sensors and prints the test page.

The bridge drops the connection after `idle_disconnect_minutes` without a command (default 30; `0` keeps it until the printer switches off or leaves range). When `auto_off_minutes` is set, the bridge writes that auto-off timer to the printer on each new connection, and only when the printer reports another value.

**What it knows.**

- The printer it is connected to, if any.
- The printer connected or used last, kept in memory until the bridge stops.
- The values last read from each printer (battery, lid, paper, auto-off) with the time they were read; `status` reports them as `last_seen`.
- Its own settings: `idle_disconnect_minutes`, `auto_off_minutes` and a few timeouts (see [Configuration](configuration.md)).

It has no fixed printer and does not know which printers are registered: each client names the printer it wants, or the bridge picks one (see [Print flow](print-flow.md#how-the-printer-is-chosen)).

```{warning}
While the bridge holds the connection, the printer does not advertise, so no other host can connect to it. `phomemo-bridge disconnect` releases it.
```

## Library

`phomemo`, in `src/phomemo/src/phomemo/`: Python, on [bleak](https://github.com/hbldh/bleak) and [Pillow](https://python-pillow.github.io/).

**Place in the chain.** The bridge runs on top of it; your own Python programs can use it directly (see the [library guide](library.md)). It takes images or prepared bitmaps and turns them into Bluetooth writes to the printer; notifications from the printer come back as events.

**What it does.** BLE transport (MTU, chunking, write-with-response), encoding of the printing protocol, image preparation, scanning, and parsing of the printer's notifications into events.

**What it knows.**

- The profiles built from the model manifests.

It knows nothing about sockets, jobs or CUPS.

```{note}
Raster data goes out as one continuous stream of ATT writes with response. The printer delays its response while its buffer is full, so the print head paces the stream. Writes without response overflow the buffer on full A4 pages, and sending the page in bursts makes the printer feed blank paper between them. The measurements are in the [Protocol reference](m08f-protocol-reference.md).
```

## Model manifests

`src/models/`: JSON and PNG, one directory per printer model.

Each manifest describes one model for the whole stack: geometry, media, Bluetooth parameters, icons. The manifests are built into the Python package and the printer app's binary, so nothing extra is installed or looked up at run time. The format, how each part reads them and how to add a model are in [Printer models](models.md).
