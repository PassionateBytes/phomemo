# phomemo-printer-app

A [PAPPL](https://www.msweet.org/pappl/) printer application for the Phomemo M08F. It presents the printer to the network as an IPP Everywhere printer, so CUPS, macOS, Windows and mobile clients print to it like to any other printer. The application handles IPP, DNS-SD, the job queue and the web interface; the BLE side lives in `phomemo-bridge`, the daemon shipped with the `phomemo` Python package.

```
client ──IPP──▶ phomemo-printer-app ──unix socket──▶ phomemo-bridge ──BLE──▶ M08F
                (PAPPL, C)                           (Python)
```

The application sends each page to the bridge as 8-bit grayscale rows; the bridge waits for a sheet, dithers, prints and ejects.

## Build

Dependencies on Fedora: `pappl-devel`, `cups-devel`, `gcc`, `make`, `pkg-config`. The tests additionally use `ipptool` (package `cups-ipptool`) and Ghostscript.

```bash
make -C src/printer-app            # builds printer-app/phomemo-printer-app
make -C src/printer-app test       # C unit tests (bridge client, option mapping)
uv run pytest src/phomemo/tests/test_printer_app.py   # end-to-end against a fake bridge
```

The pytest harness starts the built binary as a private server under the test's temporary directory and is skipped when the binary is missing.

## Install

Fedora, from the COPR repository. The package enables both services and starts them on installation, so the printer works right away:

```bash
sudo dnf copr enable passionatebytes/phomemo-driver
sudo dnf install phomemo-driver
```

From source, from the repository root: builds the application, installs the Python package into a virtual environment under `/usr/local/lib/phomemo`, installs both system units with their presets, creates the service user, enables and starts the services.

```bash
sudo dnf install gcc make pkgconf-pkg-config pappl-devel cups-devel python3 cups avahi bluez   # build and runtime dependencies
sudo make                                        # PREFIX=/usr/local; `sudo make uninstall` reverses it
```

Both services are system services: the bridge runs as the `phomemo` user and listens on `/run/phomemo/bridge.sock` (open to local users), the application runs as root like other PAPPL printer applications, with its state in `/var/lib` and the web interface on port 8000. Without the units, for development, run both by hand as your user (the bridge socket then lives in `$XDG_RUNTIME_DIR`):

```bash
phomemo-bridge server
phomemo-printer-app server -o log-level=info
```

The server tries port 8000 + (user ID % 1000), so 8000 for the root service, and counts up past ports in use; the log names the port it got. It serves a web interface at `http://localhost:8000/` and binds all interfaces so other machines can print. Changing settings through the web interface is limited to this machine by default.

### Configuration

The service reads `/etc/phomemo-printer-app.conf` (PAPPL's `name=value` format, commented; the packaged file sets `log-level=info`): `server-port` pins the port, `listen-hostname=localhost` keeps the server local, `server-options` switches web interface pages and TLS, `auth-service` and `admin-group` allow changes from other machines. Each option can also be given as `-o name=value` on the command line, which wins over the file; `~/.config/phomemo-printer-app.conf` serves a server run by hand. Restart the service after a change. The bridge reads `/etc/phomemo/bridge.toml` (see the [library README](../phomemo/README.md#bridge-daemon)).

## Register the printer

At its very first start (no saved state yet) the server registers each M08F in range (printer on, lid closed), as PAPPL does for every printer application. Each printer is named after its model and the last three bytes of its Bluetooth address, for example **Phomemo M08F (DDEEFF)**, so several printers never clash. Printers switched on later, or after the first start, are added with:

```bash
sudo phomemo-printer-app autoadd                     # scan and add every M08F in range
phomemo-printer-app printers                         # confirm what is configured
```

(`sudo` because adding a printer to the system service is an administrative change; listing is not.)

or open the web interface at http://localhost:8000/ and use "Add Printer", which scans the same way. `phomemo-printer-app devices` shows what is in range without adding anything; `add -d "Phomemo M08F (DDEEFF)" -m m08f -v "phomemo://AA-BB-CC-DD-EE-FF?model=m08f"` adds a known address. `phomemo-printer-app --help` lists all subcommands.

The device URI carries the printer's BLE address with dashes instead of colons, because a URI host cannot hold colons, and its model (`?model=m08f`); the driver of the same name comes from the model description in [`src/models/`](../models/README.md). A URI without the model (printers registered by older versions) still works: the bridge reads the model from the printer's advertised name. The printer name is what DNS-SD advertises and what printer dialogs show; the web interface lives at `http://localhost:8000/Phomemo_M08F_(DDEEFF)/` (PAPPL replaces only the spaces in the name).

### CUPS queue

CUPS discovers the printer through DNS-SD and creates its queue on first use; no `lpadmin` needed. CUPS derives the queue name from the advertised name by replacing each run of characters other than letters and digits with one underscore, so "Phomemo M08F (DDEEFF)" prints as:

```bash
lpstat -e                       # lists Phomemo_M08F_DDEEFF
lp -d Phomemo_M08F_DDEEFF document.pdf
```

That queue is temporary: CUPS removes it when idle, and GNOME Settings lists only permanent queues. A permanent queue comes from GNOME Settings → Printers → Add Printer, or from `lpadmin` with the DNS-SD URI (it keeps working when the app's port changes):

```bash
sudo lpadmin -p Phomemo_M08F_DDEEFF -E -m everywhere \
  -v 'ipps://Phomemo%20M08F%20(DDEEFF)._ipps._tcp.local/'
```

`lpinfo --include-schemes dnssd -v` lists the exact URI. CUPS reads supply levels only while it runs a job, so the battery (reported as an ink level, the only kind GNOME draws) appears in GNOME Settings after the first job through the permanent queue and shows the reading from the last job.

## Options

| Option | Values | Effect |
|--------|--------|--------|
| `media` | `iso_a4_210x297mm` (default), `iso_a5_148x210mm` | A5 is fed long edge first; a portrait A5 page is rotated so its right edge leads out of the printer. |
| `print-quality` | `3` draft, `4` normal (default), `5` high | Printer density low, medium, high. |
| `phomemo-tone` | `auto` (default), `threshold`, `ordered`, `diffusion` | Rendering ("Rendering" in the web interface): black and white, ordered dither, diffusion dither; `auto` picks black and white for text and graphics and diffusion for photos, following `print-content-optimize`. |
| `print-content-optimize` | `auto`, `text`, `graphic`, `photo` | Guides `phomemo-tone=auto`. |

For example `lp -d phomemo -o print-quality=5 -o phomemo-tone=ordered photo.png`.

The only media type is `thermal` (the printer takes nothing else). Margins are 10 mm at the top and bottom of the sheet (the head cannot reach the first 10 mm, and PAPPL only models symmetric margins) and 0 mm at the sides. A raster that ignores the bottom margin is printed to 5 mm before the sheet end, where the bridge clips. One page per sheet, no duplex, grayscale only (`sgray_8` raster).

## Behaviour

- A job waits for a sheet; the printer reports `media-empty`, `cover-open` or `offline` (printer off, out of range or in use elsewhere; `other` when Bluetooth itself is off) until the sheet is seated, then prints and ejects. The job message says what to do ("Insert a sheet.", "Close the lid.", "Turn on Bluetooth."). A multi-page job waits for each sheet in turn. CUPS shows the queue as "Printing." throughout; the reasons are visible in the application's web interface and through IPP.
- A printer that is switched off while a job waits, or that drops the link mid-page, is picked up again when it comes back on; an interrupted page is printed again.
- Cancelling a job while it waits for a sheet stops it; cancelling once printing has started stops the transfer and ejects the sheet. A job cancelled while its page is still being spooled leaves the seated sheet in the printer for the next job.
- A lid opened mid-page or a sheet shorter than the page does not end the job: the printer reports `cover-open` or `media-empty`, a sheet still inside when the lid closes is ejected, and the page is printed again on the next sheet. Close the lid first, then insert the sheet; a sheet inserted before the lid closes is ejected as well.
- When the bridge is not running the queue pauses (`printer-state` stopped, the device error in the log names the socket path) and resumes on its own once the bridge answers. A bridge restarted while jobs are queued fails the job in progress; the queued jobs reconnect and print.
- While idle, lid and paper state show up in `printer-state-reasons` as long as the bridge still holds the link (five minutes after a job by default). The battery charge is shown as the printer's supply level and keeps its last reading while the printer is off or out of range.
- "Identify printer" (web interface button, IPP Identify-Printer) ejects a loaded sheet and pulses the feed three times.
- "Print test page" (web interface) prints a page with the printer's address, firmware, serial, battery, link and version details, millimetre rulers, a gray ramp and line and text samples. The bridge renders it; the page goes through the normal job pipeline.

## Troubleshooting

- **No devices listed / jobs pause**: the bridge is not reachable. Check `systemctl status phomemo-bridge` and that both programs use the same socket (`/run/phomemo/bridge.sock` for the system services, else `PHOMEMO_BRIDGE_SOCKET` or `$XDG_RUNTIME_DIR/phomemo-bridge.sock`); `phomemo-bridge status` talks to the daemon directly.
- **Printer not found although it is on**: BlueZ may still hold a stale link after a killed daemon; `bluetoothctl disconnect <address>` frees it. The printer does not advertise while connected (`phomemo-bridge disconnect` releases it), and switches itself off after its auto-off time (`phomemo-bridge auto-off`; the bridge sets `auto_off_minutes` from its configuration).
- **Logs**: with the units, `journalctl -f -u phomemo-printer-app -u phomemo-bridge` follows both (the unit runs the server with `-o log-file=-`, so its log goes to the journal). By hand: `phomemo-printer-app server -o log-file=- -o log-level=debug`; the bridge logs with `phomemo-bridge server -v`.

## Sources

| File | Role |
|------|------|
| `main.c` | Driver table built from the model descriptions, auto-add rule, `papplMainloop` entry point. |
| `models.c` | Reads the model descriptions (`PHOMEMO_MODELS_DIR`, else `$(DATADIR)/phomemo/models` as built). |
| `device.c` | The `phomemo://` device scheme over the bridge socket, status mapping. |
| `driver.c` | Printer capabilities from the model (media, resolution, margins, icons) plus `phomemo-tone`, and option mapping helpers. |
| `job.c` | Raster callbacks: wait for a sheet, stream rows, finish the page, surface errors. |
| `bridge.c` | Line-oriented JSON client for the bridge protocol. |
| `third_party/cJSON.*` | [cJSON](https://github.com/DaveGamble/cJSON) 1.7.18, MIT. |

## License

Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions.

GNU General Public License, version 3 or later: see [COPYING](COPYING). The bundled [cJSON](third_party/cJSON.LICENSE) is MIT-licensed. This README is documentation and licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
