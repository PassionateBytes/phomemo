# Print flow

How the parts of the [driver stack](driver-stack.md) work together: what happens during a job, how the bridge picks a printer, and the protocol the printer app and the bridge speak.

## A job, step by step

1. CUPS, or any IPP client, sends the document to the printer app. PAPPL renders it to an `sgray_8` raster.
2. Opening the device sends `open` with the printer's address and model.
3. Each page starts with `wait_ready`. The bridge connects if needed and pushes `waiting` events (`no-sheet`, `lid-open`, `printer-off`, ...), which the printer app shows as `printer-state-reasons` and job messages.
4. `page_begin` describes the page; `lines` messages carry its 8-bit gray rows.
5. `page_end` makes the bridge fit the page to the sheet, stream it to the printer, wait for the motor stop and eject the sheet.
6. After the job the printer app sends `close`. The bridge keeps the connection until `idle_disconnect_minutes` pass without a command.

```{note}
Cancelling a job sends `abort`. It is the only command the bridge accepts while another one is pending.
```

## Interrupted pages

Opening the lid or running out of sheet during a page does not lose the page. The bridge keeps the prepared page, reconnects, ejects a sheet it senses right after the lid closes (its position is unknown), waits for a sheet and prints the page again. The job carries on as if nothing happened.

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

A scanned printer's model is the one whose `ble_name_pattern` matches its advertised name. Devices of no known model are left out of every scan. When the name matches several models (hardware variants with the same name), the printer's serial decides: `discover` connects briefly to read it, and an `open` without a model reads it right after connecting and switches to the model it names. A model named in the `open` stays; the bridge only warns when the serial points elsewhere. Details in [How a printer is matched](models.md#how-a-printer-is-matched).

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
| `discover` | `timeout` | `printers: [{name, address, model}]`: printers of every known model in range, with the model their advertised name matches. A printer whose name matches several models also carries `serial` and `resolved`: `true` with the model its serial names, `false` (serial `null`) with the generic model when the printer could not be reached |
| `open` | `address`, `model` (both optional) | Connects (or reuses the held connection) with the profile of `model`, or of the model the advertised name matches, refined by the serial; replies `model`; another address retargets the bridge; `connected: false` with a `reason` when the printer is unreachable or the choice is ambiguous, `wait_ready` keeps retrying |
| `close` | | Ends the session's use of the connection and starts the idle timer (`idle_disconnect_minutes`) |
| `disconnect` | | Drops the connection now |
| `status` | `address` (optional) | Connected: `connected: true`, `address`, `model`, live `lid`, `paper`, `battery`. Otherwise `connected: false`, the `address` asked about (or the last connected printer), `connected_to` when the bridge holds another printer, and `last_seen` with the values last read and their time `at` (absent until read once since the bridge started). Never connects. |
| `info` | | `address`, `model`, `firmware`, `serial`, `battery`, `auto_off_minutes`, `lid`, `paper`; error `not connected` without a connection |
| `auto_off` | `minutes` (optional) | Sets the timer when `minutes` is given, then `auto_off_minutes` as the printer reports it; error `not connected` without a connection |
| `wait_ready` | `settle` | Returns once a sheet is seated; waits as long as it takes, pushes `waiting` events |
| `page_begin` | `width`, `length_rows`, `bits` (1/8), `tone` (`auto` or a tone mode), `content` (`auto`/`text`/`graphic`/`photo`), `density` (`low`/`medium`/`high`), `media_length_mm` (number or null), `rotate` | |
| `lines` | `count` + payload of `count` rows (`width * bits / 8` bytes each; 8-bit gray 0 = black, 1-bit 1 = black) | `rows` received so far |
| `page_end` | | Prints and ejects; `impressions: 1`. An opened lid or a sheet that runs out does not end the page (see [Interrupted pages](#interrupted-pages)). `error`: `cancelled`, `connection lost: ...` |
| `identify` | | Connects if needed, ejects a loaded sheet, then pulses the feed three times |
| `test_page` | `printer_name`, `versions` (name to version) | Connects if needed, queries the device and writes a test page PNG to `$XDG_RUNTIME_DIR/phomemo-testpage.png` (else the temp dir); `path` |
| `eject` | | `ejected` |
| `abort` | | Stops a pending `wait_ready` or transfer (the band in progress is padded white, then drain and eject); ok even when idle |

```{tip}
Writing your own client? The framing lives in `phomemo.bridge.protocol`, the commands in `phomemo.bridge.session`, and `phomemo.bridge.client` is the Python client the command line uses. The printer app's C client is `src/printer-app/bridge.c`.
```
