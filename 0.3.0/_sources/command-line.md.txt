# Command line

Two commands come with the driver:

- `phomemo-bridge` runs the bridge and talks to it directly: scan, connect, check the sensors, print an image.
- `phomemo-printer-app` runs the printer app and manages its registered printers.

## phomemo-bridge

### First steps

```bash
phomemo-bridge devices      # scan for printers in range
phomemo-bridge connect      # bring the connection up
phomemo-bridge status       # sensors, battery, firmware, serial, auto-off
phomemo-bridge testpage     # print the test page
```

Every command except `server` talks to a running bridge over its socket (the system service, or one you started with `phomemo-bridge server`). When it cannot reach one, it prints `cannot reach the bridge at <socket>: ...` and exits with status 1.

### Global options

Put these before the command name.

| Option | Meaning |
|---|---|
| `--config FILE` | Read this TOML file instead of the default files. A missing file is an error (exit status 2). See [Configuration](configuration.md#bridge). |
| `-v`, `--verbose` | Debug logging. |
| `-V`, `--version` | Print the version and exit. |
| `-h`, `--help` | Show the help. `phomemo-bridge COMMAND -h` describes one command. |

```bash
phomemo-bridge -V
# phomemo-bridge 0.1.0
```

### Which printer a command uses

Commands that take `-a/--address` pick the printer like this:

1. the one given with `--address`,
2. else the printer connected or used last since the bridge started,
3. else the only printer of a known model a scan finds.

With several printers in range and none of these, the command refuses and lists them. Pick one with `--address`:

```bash
phomemo-bridge connect -a AA:BB:CC:DD:EE:FF
```

The model comes from the printer's advertised name.

:::{note}
`status` and `auto-off` never connect by themselves. Run `connect` first.
:::

### Commands

| Command | What it does |
|---|---|
| [`server`](#server) | Run the bridge in the foreground. |
| [`devices`](#devices) | Scan and list printers in range. |
| [`connect`](#connect) | Bring the connection up. |
| [`disconnect`](#disconnect) | Drop the connection now. |
| [`status`](#status) | Show the connection, sensors and device details. |
| [`auto-off`](#auto-off) | Show or set the auto-off timer. |
| [`print`](#print) | Print one image file as a page. |
| [`eject`](#eject) | Eject the sheet. |
| [`identify`](#identify) | Make the printer show itself. |
| [`testpage`](#testpage) | Print the test page. |

While a long command runs, the bridge's progress and `waiting` events are printed to stderr as JSON lines, for example `{"event": "waiting", "reason": "no-sheet"}`. Errors are printed as `error: ...` with exit status 1.

### server

```bash
phomemo-bridge server
```

Runs the bridge in the foreground: listens on the socket, owns the connection to the printer and serves the printer app and the command line. The packaged system service runs exactly this. No options.

:::{tip}
For development, run `phomemo-bridge -v server` as your user. The socket then lives in `$XDG_RUNTIME_DIR/phomemo-bridge.sock`, unless the system bridge's socket exists.
:::

### devices

```bash
phomemo-bridge devices
# AA:BB:CC:DD:EE:FF  m08f      M08F
```

Scans for printers of every known model. One line per printer: Bluetooth address, model, advertised name. A printer shows up only while it is switched on and not connected to another host. With none in range it prints `no printer in range` to stderr and exits with status 1.

| Option | Default | Meaning |
|---|---|---|
| `--timeout SECONDS` | `5` | How long to scan. |

### connect

```bash
phomemo-bridge connect
# connected to AA:BB:CC:DD:EE:FF
```

Brings the connection up. The bridge keeps it until the printer switches off or leaves range, or until `idle_disconnect_minutes` pass without a command, so later commands and jobs skip the reconnect. At each new connection the bridge sets the printer's auto-off timer to `auto_off_minutes` when that key is set.

| Option | Meaning |
|---|---|
| `-a`, `--address ADDRESS` | Printer to use (`AA:BB:CC:DD:EE:FF`). |

When the printer cannot be reached it prints `error: not reachable: <reason>`.

### disconnect

```bash
phomemo-bridge disconnect
# disconnected
```

Drops the connection right away instead of after the idle time, so another host (a phone, another computer) can reach the printer. No options.

### status

```bash
phomemo-bridge status
```

```json
{
  "connected": true,
  "address": "AA:BB:CC:DD:EE:FF",
  "model": "m08f",
  "lid": "closed",
  "paper": "absent",
  "battery": 80,
  "firmware": "...",
  "serial": "<serial>",
  "auto_off_minutes": 10
}
```

Prints a JSON object. With a connection it holds the printer's address, model, lid (`open`/`closed`), paper (`present`/`absent`), battery, firmware, serial number and auto-off timer. A value the printer did not answer is `null`.

Without a connection it shows what the bridge read last:

```json
{
  "connected": false,
  "address": "AA:BB:CC:DD:EE:FF",
  "last_seen": {
    "model": "m08f",
    "lid": "closed",
    "paper": "absent",
    "battery": 80,
    "at": "2026-11-04T10:15:00"
  }
}
```

| Field | When |
|---|---|
| `address` | The printer asked about, or the one connected last. |
| `connected_to` | The bridge holds a connection to a different printer than the one asked about. |
| `last_seen` | Values last read from that printer, with the time `at`. Absent until the bridge has read them once since it started. |

| Option | Meaning |
|---|---|
| `-a`, `--address ADDRESS` | Report on this printer. |

Does not connect by itself.

### auto-off

```bash
phomemo-bridge auto-off
# AA:BB:CC:DD:EE:FF: auto-off 10 min
phomemo-bridge auto-off 30
# AA:BB:CC:DD:EE:FF: auto-off 30 min
phomemo-bridge auto-off 0
# AA:BB:CC:DD:EE:FF: auto-off never
```

Shows the connected printer's auto-off timer, or sets it first when you give `MINUTES` (a multiple of 5 up to 1275, `0` = never switch off). The line shows the value the printer reports.

| Argument / option | Meaning |
|---|---|
| `minutes` | New timer in minutes, `0` = never. Optional. |
| `-a`, `--address ADDRESS` | Printer to use. |

Needs a connection: without one it prints `error: not connected; run "phomemo-bridge connect" first`.

:::{warning}
When `auto_off_minutes` is set in the [configuration](configuration.md#keys), the bridge writes that value again at the next connection. Change the key for a lasting setting.
:::

### print

```bash
phomemo-bridge print page.png --media a4 --quality high --tone diffusion
# printed 1 page(s)
```

Prints an image file (PNG, JPEG, anything Pillow reads) as one page, scaled to the media width, then ejects the sheet. The command waits for a sheet when none is loaded.

| Option | Default | Values |
|---|---|---|
| `file` | | Image file to print. |
| `-a`, `--address ADDRESS` | | Printer to use. |
| `--media` | `a4` | `a4`, `a5`, `roll` |
| `--tone` | `auto` (chosen from the content) | `auto`, `threshold`, `ordered`, `diffusion`: how gray becomes dots. |
| `--quality` | `normal` | `draft`, `normal`, `high`: print density. |
| `--content` | `auto` | `auto`, `text`, `graphic`, `photo`: content hint for `--tone auto`. |
| `--abort-after SECONDS` | | Cancel the page this many seconds into the transfer (for testing). |

:::{note}
An A5 sheet is fed long edge first; the page is rotated so its right edge leads out of the printer.
:::

### eject

```bash
phomemo-bridge eject
# ejected
```

Ejects the loaded sheet. Prints `sheet still present` when the sheet is still sensed afterwards.

| Option | Meaning |
|---|---|
| `-a`, `--address ADDRESS` | Printer to use. |

### identify

```bash
phomemo-bridge identify
# identified
```

Ejects a loaded sheet, then pulses the paper feed three times so you can tell which printer this is.

| Option | Meaning |
|---|---|
| `-a`, `--address ADDRESS` | Printer to use. |

### testpage

```bash
phomemo-bridge testpage
# printed 1 page(s)
```

Prints the test page: device details, millimetre scales, a gray ramp, line widths and text samples.

| Option | Default | Meaning |
|---|---|---|
| `-a`, `--address ADDRESS` | | Printer to use. |
| `--quality` | `normal` | `draft`, `normal`, `high`: print density. |

## phomemo-printer-app

`phomemo-printer-app` is a [PAPPL](https://www.msweet.org/pappl/) printer application, so it has PAPPL's standard sub-commands. Except `server`, each one talks to a running server, and which server depends on who runs it: as root the system service, as your own user a private printer app that the sub-command starts if none runs. So use `sudo` for every sub-command meant for the installed service, listing included.

### First steps

```bash
sudo phomemo-printer-app devices            # scan: what is in range
sudo phomemo-printer-app autoadd            # register every M08F in range
sudo phomemo-printer-app printers           # confirm what is registered
```

:::{note}
Without `sudo`, `devices`, `printers` and the other sub-commands reach a private printer app of your user, not the system service; that is useful only for development.
:::

### Sub-commands

| Sub-command | What it does |
|---|---|
| `server` | Run a server. |
| `devices` | List devices (scan). |
| `autoadd` | Register every supported printer found. |
| `add PRINTER` | Register a printer. |
| `printers` | List registered printers. |
| `drivers` | List drivers. |
| `delete` | Delete a printer. |
| `modify` | Modify a printer. |
| `default` | Set the default printer. |
| `options` | List printer options. |
| `status` | Show server, printer or job status. |
| `jobs` | List jobs. |
| `submit` | Submit a file for printing. |
| `cancel` | Cancel one or more jobs. |
| `pause`, `resume` | Pause or resume printing for a printer. |
| `shutdown` | Shut down a running server. |

Common options: `-d PRINTER` (printer), `-m DRIVER-NAME` (driver, for `add`/`modify`), `-v DEVICE-URI` (device, for `add`/`modify`), `-o NAME=VALUE` (option, for `add`, `modify`, `server`, `submit`), `-u URI` (server or printer to talk to), `-j JOB-ID` and `-a` (for `cancel`), `-n COPIES` (for `submit`). `phomemo-printer-app --help` lists them all.

:::{warning}
`-h` is not help here: PAPPL uses it for a host name. Use `--help`.
:::

### server

```bash
phomemo-printer-app server -o log-file=- -o log-level=debug
```

Runs the printer app in the foreground. The system service runs `phomemo-printer-app server -o log-file=-`, so the log goes to the journal. Any [option](configuration.md#options) works as `-o name=value` and wins over the configuration files.

At its very first start (no saved state yet) the server registers each M08F in range.

### devices

```bash
sudo phomemo-printer-app devices
```

Scans and lists what is in range, without registering anything.

:::{note}
When it finds no server to talk to, `devices` starts a private one for you, and that server keeps running afterwards (`pgrep -af 'phomemo-printer-app server'`).
:::

### autoadd

```bash
sudo phomemo-printer-app autoadd
```

Scans and registers every M08F in range (printer on, lid closed). Each printer is named after its model and the last three bytes of its Bluetooth address, for example **Phomemo M08F (DDEEFF)**.

### add

```bash
sudo phomemo-printer-app add -d "Phomemo M08F (DDEEFF)" -m m08f \
  -v "phomemo://AA-BB-CC-DD-EE-FF?model=m08f"
```

Registers a printer you know the address of.

| Option | Meaning |
|---|---|
| `-d NAME` | Printer name, as DNS-SD advertises it and print dialogs show it. |
| `-m m08f` | Driver: the model identifier (see `drivers`). |
| `-v URI` | Device URI: `phomemo://` plus the Bluetooth address with dashes instead of colons, and the model as `?model=`. |

:::{tip}
A URI host cannot hold colons, which is why the address uses dashes. A URI without `?model=` still works: the bridge reads the model from the printer's advertised name.
:::

### printers

```bash
sudo phomemo-printer-app printers
```

Lists the registered printers.

### drivers

```bash
sudo phomemo-printer-app drivers
```

Lists the drivers, one per model manifest. The driver name is the model identifier (`m08f`) you pass to `add -m`.
