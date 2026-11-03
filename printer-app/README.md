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
make -C printer-app            # builds printer-app/phomemo-printer-app
make -C printer-app test       # C unit tests (bridge client, option mapping)
uv run pytest packages/phomemo/tests/test_printer_app.py   # end-to-end against a fake bridge
```

The pytest harness starts the built binary as a private server under the test's temporary directory and is skipped when the binary is missing.

## Install

Fedora, from the COPR repository (both parts, services enabled and started by the package presets):

```bash
sudo dnf copr enable <account>/phomemo-driver
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

The server listens on port 8000 for the first user on a machine (the log names the port, `-o server-port=N` pins it) and serves a web interface at `http://localhost:8000/`. It binds all interfaces so other machines can print; `-o listen-hostname=localhost` keeps it local. Queue management through the web interface is limited to localhost by default.

## Register the printer

At every start the server looks for printers through the bridge and registers each M08F in range (printer on, lid closed) as **Phomemo M08F**; a printer registered earlier stays. So: install, switch the printer on, start or restart the service. Later, or for a printer that was off at the time:

```bash
sudo phomemo-printer-app autoadd                     # scan and add every M08F in range
phomemo-printer-app printers                         # confirm what is configured
```

(`sudo` because adding a printer to the system service is an administrative change; listing is not.)

or open the web interface at http://localhost:8000/ and use "Add Printer", which scans the same way. `phomemo-printer-app devices` shows what is in range without adding anything; `add -d "Phomemo M08F" -m m08f -v phomemo://AA-BB-CC-DD-EE-FF` adds a known address. `phomemo-printer-app --help` (or `-h` on its own) lists all subcommands.

The device URI carries the printer's BLE address with dashes instead of colons, because a URI host cannot hold colons. The printer name is what DNS-SD advertises and what printer dialogs show; the web interface lives at `http://localhost:8000/Phomemo_M08F/`.

### CUPS queue

CUPS discovers the printer through DNS-SD and creates its queue on first use; no `lpadmin` needed. CUPS derives the queue name from the advertised name by replacing everything but letters and digits with underscores, so "Phomemo M08F" prints as:

```bash
lpstat -e                       # lists Phomemo_M08F
lp -d Phomemo_M08F document.pdf
```

A queue with a name of your choosing: `lpadmin -p <name> -E -v ipp://localhost:8000/ipp/print/Phomemo_M08F -m everywhere`.

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
- While idle, lid and paper state show up in `printer-state-reasons` as long as the bridge still holds the link (two minutes after a job by default). The battery charge is shown as the printer's supply level and keeps its last reading while the printer is off or out of range.
- "Identify printer" (web interface button, IPP Identify-Printer) ejects a loaded sheet and pulses the feed three times.
- "Print test page" (web interface) prints a page with the printer's address, firmware, serial, battery, link and version details, millimetre rulers, a gray ramp and line and text samples. The bridge renders it; the page goes through the normal job pipeline.

## Troubleshooting

- **No devices listed / jobs pause**: the bridge is not reachable. Check `systemctl --user status phomemo-bridge` and that `PHOMEMO_BRIDGE_SOCKET` (or `$XDG_RUNTIME_DIR/phomemo-bridge.sock`) is the same for both programs; `phomemo-bridge status` talks to the daemon directly.
- **Printer not found although it is on**: BlueZ may still hold a stale link after a killed daemon; `bluetoothctl disconnect <address>` frees it. The printer does not advertise while connected, and switches off after ten minutes idle.
- **Logs**: with the units, `journalctl -f -u phomemo-printer-app -u phomemo-bridge` follows both (the unit runs the server with `-o log-file=-`, so its log goes to the journal). By hand: `phomemo-printer-app server -o log-file=- -o log-level=debug`; the bridge logs with `phomemo-bridge server -v`.

## Sources

| File | Role |
|------|------|
| `main.c` | Driver table, auto-add rule, `papplMainloop` entry point. |
| `device.c` | The `phomemo://` device scheme over the bridge socket, status mapping. |
| `driver.c` | Printer capabilities (media, resolution, raster type, `phomemo-tone`) and option mapping helpers. |
| `job.c` | Raster callbacks: wait for a sheet, stream rows, finish the page, surface errors. |
| `bridge.c` | Line-oriented JSON client for the bridge protocol. |
| `icons/` | Printer icons (48, 128, 512 px PNG), embedded into the binary at build time by `icons/embed.sh`. |
| `third_party/cJSON.*` | [cJSON](https://github.com/DaveGamble/cJSON) 1.7.18, MIT. |
