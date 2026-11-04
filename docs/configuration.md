# Configuration

Two programs read configuration: the bridge (`phomemo-bridge`) and the printer app (`phomemo-printer-app`). Both work without any change; every setting is optional. This page lists what you can change and where.

## Bridge

### Quick start

```toml
# /etc/phomemo/bridge.toml
auto_off_minutes = 30
idle_disconnect_minutes = 10
```

```bash
sudo systemctl restart phomemo-bridge
```

That sets the printer's auto-off to 30 minutes at each new connection and drops an idle connection after 10 minutes. The bridge reads the file only at start, so restart it after every change.

### Where the bridge looks

| Order | File | Used by |
|---|---|---|
| 1 | `/etc/phomemo/bridge.toml` | the system service and every user |
| 2 | `$XDG_CONFIG_HOME/phomemo/bridge.toml` (default `~/.config/phomemo/bridge.toml`) | a bridge run by that user |

Both are read in this order, and a key in the later file wins. A file that does not exist is skipped.

`phomemo-bridge --config FILE` reads only `FILE` instead of both. Here a missing file is an error: the command prints `configuration error: ...` and exits with status 2.

The format is TOML: one `name = value` per line, `#` starts a comment. The packaged file has every key commented out, so you can see the defaults.

### Keys

| Key | Default | Valid values | Meaning |
|---|---|---|---|
| `auto_off_minutes` | unset | `0` to `1275` in 5-minute steps, `0` = never | Auto-off timer the bridge sets on the printer at each new connection. Unset: the printer keeps its own setting. |
| `idle_disconnect_minutes` | `30` | number, `0` or more | Minutes without a command before the bridge drops the connection. `0` keeps it until the printer switches off or leaves range. |
| `settle_seconds` | `3` | number, `0` or more | Longest wait for an inserted sheet to settle at the print head. |
| `completion_timeout` | `300` | number, `0` or more | Longest wait in seconds for the motor to stop after a page. |
| `drain_seconds` | `1` | number, `0` or more | Pause after a cancelled page, so the printer finishes the data it already took, before the sheet is ejected. |
| `socket_path` | see below | string | Unix socket the bridge listens on and the command line connects to. |

:::{note}
While the bridge holds the connection, the printer does not advertise itself, so a phone or another computer cannot reach it. Lower `idle_disconnect_minutes`, or run `phomemo-bridge disconnect`, if you share the printer.
:::

:::{tip}
`auto_off_minutes` is written again at every new connection, but only when the printer reports a different value. Setting the timer with `phomemo-bridge auto-off` lasts only until the next connection while this key is set, so change the key for a lasting setting.
:::

### Invalid values

The bridge never refuses to start over a bad setting. It logs a warning (see `journalctl -u phomemo-bridge`) and keeps the default for that key. This covers:

- unknown keys,
- values of the wrong type (a string where a number belongs, `true`/`false` for a number),
- negative numbers,
- a file that does not parse as TOML (the whole file is ignored).

`auto_off_minutes` is adjusted instead of dropped when it is a number:

| You write | Bridge uses | Rule |
|---|---|---|
| `0` | `0` | never switch off |
| `12` | `10` | nearest 5-minute step |
| `13` | `15` | nearest 5-minute step (halves round up) |
| `1` | `5` | at least 5 |
| `5000` | `1275` | at most 1275 |
| `"ten"`, `-5`, `true` | not set | not a usable number: logged, the printer keeps its own setting |

Each adjustment is logged with the value used.

### Socket path

Without `socket_path` and without `PHOMEMO_BRIDGE_SOCKET`, the bridge and its command line pick the socket like this:

1. `/run/phomemo/bridge.sock` when it exists (the system service),
2. else `$XDG_RUNTIME_DIR/phomemo-bridge.sock`,
3. else `/run/phomemo/bridge.sock`.

`PHOMEMO_BRIDGE_SOCKET` overrides `socket_path` from any file. The system unit sets it to `/run/phomemo/bridge.sock`.

## Printer app

### Quick start

```ini
# /etc/phomemo-printer-app.conf
log-level=debug
server-port=8631
```

```bash
sudo systemctl restart phomemo-printer-app
```

The file uses PAPPL's `name=value` format, one setting per line, `#` for comments. The packaged file sets `log-level=info` and shows the rest commented out.

### Where the printer app looks

Each option comes from the first of these that sets it:

| Order | Source |
|---|---|
| 1 | `-o name=value` on the command line |
| 2 | `~/.config/phomemo-printer-app.conf` |
| 3 | `/usr/local/etc/phomemo-printer-app.conf` |
| 4 | `/etc/phomemo-printer-app.conf` |

The system service runs as root and is started with `-o log-file=-`, so its log goes to the journal. For your own settings, edit `/etc/phomemo-printer-app.conf`.

:::{warning}
Unknown options are ignored without a message. Check the spelling if a setting seems to have no effect.
:::

### Options

| Option | Default | Meaning |
|---|---|---|
| `log-level` | `info` (packaged file) | Log detail: `fatal`, `error`, `warn`, `info` or `debug`. |
| `server-port` | automatic, see below | Port for IPP and the web interface. |
| `listen-hostname` | all interfaces | Address to listen on. `localhost` refuses connections from other machines. |
| `server-hostname` | the system host name | Host name advertised in URIs and DNS-SD records. |
| `server-options` | none | Comma-separated feature changes: `none`, `dnssd-host`, `no-multi-queue`, `no-web-interface`, `no-tls`, `raw-socket`, `web-log`, `web-network`, `web-remote`, `web-security`. |
| `auth-service` | unset | PAM service that lets users change settings from other machines. |
| `admin-group` | unset | Group allowed to change settings once `auth-service` is set. |
| `spool-directory` | chosen by the server | Directory for spooled jobs. |

:::{note}
Changing settings through the web interface is limited to this machine unless you set `auth-service` (and `admin-group`).
:::

### Which port the printer app uses

Without `server-port`, the printer app tries port `8000 + (UID % 1000)` and counts up past ports in use. For the system service (root, UID 0) that is 8000; for a server you run as UID 1000 it is 8000 as well, for UID 1001 it is 8001.

Find the port it actually got:

```bash
journalctl -u phomemo-printer-app | grep "Listening for connections"
avahi-browse -rt _ipp._tcp
```

:::{tip}
Clients find the printer through DNS-SD, so they follow a port change on their own. A permanent CUPS queue created with the DNS-SD URI keeps working too. Pin `server-port` only when something needs a fixed number.
:::

## Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `PHOMEMO_BRIDGE_SOCKET` | bridge, its command line, printer app | Bridge socket path. Overrides `socket_path` in the bridge's files. Both system units set it to `/run/phomemo/bridge.sock`. |
| `XDG_RUNTIME_DIR` | bridge, printer app | Fallback socket directory: `$XDG_RUNTIME_DIR/phomemo-bridge.sock`. The bridge also writes its test page PNG there. |
| `XDG_CONFIG_HOME` | bridge | Location of the user's `phomemo/bridge.toml` (default `~/.config`). |
| `PHOMEMO_MODELS_DIR` | library, printer app | Directory of model manifests to use instead of the built-in ones, for trying out a model without a rebuild. |

The printer app resolves the socket slightly differently from the bridge:

1. `PHOMEMO_BRIDGE_SOCKET`,
2. else `$XDG_RUNTIME_DIR/phomemo-bridge.sock`,
3. else `/run/phomemo/bridge.sock`.

:::{warning}
When you run the printer app by hand against the system bridge, set `PHOMEMO_BRIDGE_SOCKET=/run/phomemo/bridge.sock`. Otherwise it looks in your `$XDG_RUNTIME_DIR` and finds no bridge there.
:::

`PHOMEMO_MODELS_DIR` works the same for both: the library reads it at import, the printer app at start. Each subdirectory holds one model's manifest (`model.json`) and icons; see [`src/models/`](https://github.com/PassionateBytes/phomemo-driver/tree/main/src/models).
