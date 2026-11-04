# Troubleshooting

Something does not work? Start with the logs, then find your symptom below.

## Read the logs

```bash
journalctl -f -u phomemo-printer-app -u phomemo-bridge
```

This follows both services. The printer app's unit runs the server with `-o log-file=-`, so its log goes to the journal too.

```{tip}
The bridge also logs unusable settings in `/etc/phomemo/bridge.toml` there: `journalctl -u phomemo-bridge`. For more detail from the printer app, set `log-level=debug` in `/etc/phomemo-printer-app.conf` and restart it.
```

Running both by hand, for development:

```bash
phomemo-bridge server -v
phomemo-printer-app server -o log-file=- -o log-level=debug
```

## No devices listed, or jobs pause

The printer app cannot reach the bridge.

```bash
systemctl status phomemo-bridge
phomemo-bridge status
```

The first shows whether the bridge service runs; the second talks to the bridge directly.

When the bridge is not running, the printer app pauses the queue and names the socket path in its log. It resumes on its own once the bridge answers.

Both programs must use the same socket:

| Setup | Socket |
|---|---|
| System services | `/run/phomemo/bridge.sock` |
| Run by hand | `PHOMEMO_BRIDGE_SOCKET` when set, else `$XDG_RUNTIME_DIR/phomemo-bridge.sock` |

```{note}
During a restart of the bridge service the socket is briefly missing. A bridge restarted while jobs are queued fails the job in progress; the queued jobs reconnect and print.
```

## Printer not found although it is on

Work through these in order.

**The bridge still holds the connection.** The printer does not show up in a scan while it is connected. Release it:

```bash
phomemo-bridge disconnect
```

**BlueZ holds a stale connection.** After a bridge that was killed (for example with `SIGKILL`), BlueZ may keep the connection up:

```bash
bluetoothctl disconnect AA:BB:CC:DD:EE:FF
```

**Another device is connected.** The printer accepts one connection at a time. Disconnect your phone or the other computer.

**The printer is out of range.** Bluetooth range is short; bring the printer within about 2 m.

**The printer switched itself off.** Its auto-off timer ran out. Switch it on again, and see [Everyday use](everyday-use.md#auto-off) to change the timer.

```{tip}
`phomemo-bridge devices` scans and lists every printer in range with its address. A printer shows up only while it is switched on and not connected to another host.
```

## A job waits and does not print

The job is waiting for something. Check the printer's page in the web interface (http://localhost:8000/) for the reason:

| Reason | Message | What to do |
|---|---|---|
| `cover-open` | "Close the lid." | Close the lid, then insert a sheet. |
| `media-empty` | "Insert a sheet." | Insert a sheet with the lid closed. |
| `offline` | | The printer is off, out of range or connected elsewhere: switch it on, bring it closer or disconnect the other device. |
| `other` | "Turn on Bluetooth." | Bluetooth on this computer is off. |

```{note}
CUPS shows "Printing." throughout; only the printer app shows the reason.
```

## The printer does not show up in GNOME Settings

GNOME Settings lists only permanent CUPS queues. Add one as described in [First steps](first-steps.md#step-6-add-a-permanent-cups-queue-optional).

## The printer app does not start: "no model manifests"

The model manifests are built into the printer app, so it normally needs no files. This error appears only when `PHOMEMO_MODELS_DIR` is set: the printer app then loads the manifests from that directory instead and refuses to start when it holds none it can use.

Unset `PHOMEMO_MODELS_DIR`, or point it at a directory with one subdirectory per model, each with a valid `model.json`. See [Printer models](models.md).

## Still stuck?

Open an issue on [GitHub](https://github.com/PassionateBytes/phomemo-driver/issues) with the output of `journalctl -u phomemo-printer-app -u phomemo-bridge` around the time of the problem.
