# Architecture

phomemo-driver is four parts, and each does one job. Once you know which part knows what, the rest of the stack is easy to follow.

| Part | Where | Language | Job |
|---|---|---|---|
| Library `phomemo` | `src/phomemo/src/phomemo/` | Python | BLE transport, printing protocol, image preparation, events, profiles |
| Bridge `phomemo-bridge` | `src/phomemo/src/phomemo/bridge/` | Python | Owns the connection to one printer at a time, waits for sheets, prints pages, answers commands on a unix socket |
| Printer app `phomemo-printer-app` | `src/printer-app/` | C (PAPPL) | Presents registered printers as IPP Everywhere printers: IPP, DNS-SD, job queue, web interface |
| Model manifests | `src/models/` | JSON and PNG | One directory per model: geometry, media, Bluetooth parameters, icons; read by all of the above |

## How a job flows

```
application
    │  IPP (lp, a print dialog, ...)
    ▼
CUPS queue                 temporary (from DNS-SD) or permanent
    │  IPP
    ▼
phomemo-printer-app        PAPPL: job queue, raster callbacks (job.c)
    │  unix socket: JSON lines + raw rows
    │  /run/phomemo/bridge.sock for the system services
    ▼
phomemo-bridge             one session per client (session.py)
    │  Bluetooth LE, ATT write-with-response
    ▼
printer (M08F)
```

Step by step:

1. CUPS, or any IPP client, sends the document to the printer app. PAPPL renders it to an `sgray_8` raster.
2. Opening the device sends `open` with the printer's address and model.
3. Each page starts with `wait_ready`. The bridge connects if needed and pushes `waiting` events (`no-sheet`, `lid-open`, `printer-off`, ...), which the printer app shows as `printer-state-reasons` and job messages.
4. `page_begin` describes the page; `lines` messages carry its 8-bit gray rows.
5. `page_end` makes the bridge fit the page to the sheet, stream it to the printer, wait for the motor stop and eject the sheet.
6. After the job the printer app sends `close`. The bridge keeps the connection until `idle_disconnect_minutes` pass without a command.

```{note}
Cancelling a job sends `abort`. It is the only command the bridge accepts while another one is pending.
```

## Who knows what

### Printer app

- The registered printers, each with its device URI:

  ```
  phomemo://AA-BB-CC-DD-EE-FF?model=m08f
  ```

  Dashes replace the colons, because a URI host cannot hold colons.
- The model manifests built into its binary: media, resolution, margins, names, icons.
- Where the bridge listens: `PHOMEMO_BRIDGE_SOCKET`, else `$XDG_RUNTIME_DIR/phomemo-bridge.sock`, else `/run/phomemo/bridge.sock`.

It knows nothing about Bluetooth.

### Bridge

- One connection at a time.
- The printer connected or used last, kept in memory until the bridge stops.
- The values last read from each printer (battery, lid, paper, auto-off) with the time they were read; `status` reports them as `last_seen`.
- Its own settings: `idle_disconnect_minutes`, `auto_off_minutes` and a few timeouts (see [Configuration](configuration.md)).

It has no fixed printer and does not know which printers are registered.

The bridge drops the connection after `idle_disconnect_minutes` without a command (default 30; `0` keeps it until the printer switches off or leaves range). When `auto_off_minutes` is set, the bridge writes that auto-off timer to the printer on each new connection, and only when the printer reports another value.

```{warning}
While the bridge holds the connection, the printer does not advertise, so no other host can connect to it. `phomemo-bridge disconnect` releases it.
```

### Library

- The profiles built from the model manifests.
- The BLE transport: MTU, chunking, write-with-response.
- Protocol encoding and event parsing.

It knows nothing about sockets, jobs or CUPS.

## How the printer is chosen

The printer app always names the printer: its `open` carries the address and model from the device URI.

```{note}
A URI without `?model=` (printers registered by older versions) still works. The bridge then reads the model from the printer's advertised name.
```

Commands without an address, such as the [command line](command-line.md) ones, resolve the printer in this order:

1. the address given with `-a/--address`;
2. else the printer connected or used last since the bridge started;
3. else the only printer of a known model a scan finds.

With several printers in range and nothing else to go on, the command refuses and lists their addresses. An `open` with another address than the current printer's drops the current connection and retargets the bridge.

A scanned printer's model is the one whose `ble_name_pattern` matches its advertised name. Devices of no known model are left out of every scan.

## Socket protocol

```
client → {"cmd": "lines", "count": 32, "bytes": 53760}\n<53760 raw bytes>
bridge → {"ok": true, "cmd": "lines", "rows": 32}\n
```

- Every message is one JSON object on its own line.
- A message with `"bytes": N` is followed by exactly N raw bytes (raster rows).
- Replies and pushed events use the same framing in the other direction.
- Lines are limited to 64 KiB, payloads to 16 MiB.
- One client at a time.

Replies carry `ok` and `cmd`.

### Events

While a long command is pending, the bridge pushes events:

| Event | Fields | Meaning |
|---|---|---|
| `progress` | `percent` | Transfer progress of the page |
| `waiting` | `reason` | Why the bridge is waiting |

| `reason` | Meaning |
|---|---|
| `connecting` | The connection is being brought up |
| `printer-off` | Printer off, out of range or in use elsewhere |
| `adapter-off` | Bluetooth unavailable |
| `lid-open` | Lid open |
| `no-sheet` | No sheet loaded |
| `short-sheet` | The last sheet ran out; a longer one is needed |

### Commands

| Command | Arguments | Reply |
|---|---|---|
| `discover` | `timeout` | `printers: [{name, address, model}]`: printers of every known model in range, with the model their advertised name matches |
| `open` | `address`, `model` (both optional) | Connects (or reuses the held connection) with the profile of `model`, or of the model the advertised name matches; another address retargets the bridge; `connected: false` with a `reason` when the printer is unreachable or the choice is ambiguous, `wait_ready` keeps retrying |
| `close` | | Ends the session's use of the connection and starts the idle timer (`idle_disconnect_minutes`) |
| `disconnect` | | Drops the connection now |
| `status` | `address` (optional) | Connected: `connected: true`, `address`, `model`, live `lid`, `paper`, `battery`. Otherwise `connected: false`, the `address` asked about (or the last connected printer), `connected_to` when the bridge holds another printer, and `last_seen` with the values last read and their time `at` (absent until read once since the bridge started). Never connects. |
| `info` | | `address`, `model`, `firmware`, `serial`, `battery`, `auto_off_minutes`, `lid`, `paper`; error `not connected` without a connection |
| `auto_off` | `minutes` (optional) | Sets the timer when `minutes` is given, then `auto_off_minutes` as the printer reports it; error `not connected` without a connection |
| `wait_ready` | `settle` | Returns once a sheet is seated; waits as long as it takes, pushes `waiting` events |
| `page_begin` | `width`, `length_rows`, `bits` (1/8), `tone` (`auto` or a tone mode), `content` (`auto`/`text`/`graphic`/`photo`), `density` (`low`/`medium`/`high`), `media_length_mm` (number or null), `rotate` | |
| `lines` | `count` + payload of `count` rows (`width * bits / 8` bytes each; 8-bit gray 0 = black, 1-bit 1 = black) | `rows` received so far |
| `page_end` | | Prints and ejects; `impressions: 1`. An opened lid or a sheet that runs out does not end the page (see the design decisions below). `error`: `cancelled`, `connection lost: ...` |
| `identify` | | Connects if needed, ejects a loaded sheet, then pulses the feed three times |
| `test_page` | `printer_name`, `versions` (name to version) | Connects if needed, queries the device and writes a test page PNG to `$XDG_RUNTIME_DIR/phomemo-testpage.png` (else the temp dir); `path` |
| `eject` | | `ejected` |
| `abort` | | Stops a pending `wait_ready` or transfer (the band in progress is padded white, then drain and eject); ok even when idle |

```{tip}
Writing your own client? The framing lives in `phomemo.bridge.protocol`, the commands in `phomemo.bridge.session`, and `phomemo.bridge.client` is the Python client the command line uses. The printer app's C client is `src/printer-app/bridge.c`.
```

## How model manifests reach each part

```
src/models/<id>/model.json + icons
    │
    ├── hatch build hook (src/phomemo/hatch_build.py)
    │       wheel: phomemo/models     sdist: src/phomemo/models
    │       → library and bridge load them at import
    │
    └── embed-models.sh, at build time
            → models_data.c, compiled into phomemo-printer-app
```

| Reader | Where it looks, in order |
|---|---|
| Library and bridge | `PHOMEMO_MODELS_DIR` when set; else the copy installed with the package (`phomemo/models`); else `src/models/` of a source checkout |
| Printer app | `PHOMEMO_MODELS_DIR` set at start, which replaces the built-in manifests with the directories found there; else the manifests embedded in the binary |

```{tip}
Trying out a new model? Point `PHOMEMO_MODELS_DIR` at your directory and you need no rebuild. The format is in [Printer models](models.md).
```

## Design decisions

| Decision | Why |
|---|---|
| Raster data goes out with ATT write-with-response, as one continuous stream | The printer delays its response while its buffer is full, so the print head paces the stream; unacknowledged writes overflow the buffer on full A4 pages, and a burst per band makes the printer feed blank paper at each band end |
| An interrupted page is printed again | The bridge keeps the prepared page; after an opened lid or a sheet that ran out it reconnects, ejects a sheet it senses right after the lid closes (its position is unknown), waits for a sheet and reprints, so the job survives |
| One connection at a time, owned by the bridge | While connected the printer does not advertise, so no other host can reach it; a single owner serialises jobs, status queries and commands |
| Model manifests embedded in the wheel and the binary | Nothing extra to install or find at run time; `PHOMEMO_MODELS_DIR` remains for development |

The measured behaviour behind these decisions is in the [Protocol reference](m08f-protocol-reference.md). The Python side is in the [API reference](api.md).
