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

```bash
make -C printer-app install    # PREFIX defaults to ~/.local
```

With a `PREFIX` under `$HOME` the systemd user unit `packaging/phomemo-printer-app.service` is installed to `~/.config/systemd/user/` as well. Install `phomemo` (with its `phomemo-bridge` unit) the same way, then:

```bash
systemctl --user enable --now phomemo-bridge phomemo-printer-app
```

Both units point at the same bridge socket, `$XDG_RUNTIME_DIR/phomemo-bridge.sock`. Without the unit, run the server by hand:

```bash
phomemo-printer-app server -o log-level=info
```

The server listens on port 8000 for the first user on a machine (the log names the port, `-o server-port=N` pins it) and serves a web interface at `http://localhost:8000/`.

## Add the printer

When the server starts without a saved state it looks for printers through the bridge and adds the first M08F in range as **Phomemo M08F**. To add one by hand:

```bash
phomemo-printer-app devices                          # lists phomemo://... URIs (printer on, bridge running)
phomemo-printer-app add -d phomemo -m m08f -v phomemo://AA-BB-CC-DD-EE-FF
```

The device URI carries the printer's BLE address with dashes instead of colons, because a URI host cannot hold colons.

### CUPS queue

CUPS discovers the printer through DNS-SD (`lpstat -e`, cups-browsed, or the printer dialogs of desktop environments). To create a queue explicitly:

```bash
lpadmin -p phomemo -E -v ipp://localhost:8000/ipp/print/phomemo -m everywhere
lp -d phomemo document.pdf
```

## Options

| Option | Values | Effect |
|--------|--------|--------|
| `media` | `iso_a4_210x297mm` (default), `iso_a5_148x210mm` | A5 is fed long edge first; a portrait A5 page is rotated so its right edge leads out of the printer. |
| `print-quality` | `3` draft, `4` normal (default), `5` high | Printer density low, medium, high. |
| `phomemo-tone` | `auto` (default), `threshold`, `ordered`, `diffusion` | Dithering. `auto` thresholds text and graphics and diffuses photos, following `print-content-optimize`. |
| `print-content-optimize` | `auto`, `text`, `graphic`, `photo` | Guides `phomemo-tone=auto`. |

For example `lp -d phomemo -o print-quality=5 -o phomemo-tone=ordered photo.png`.

Margins are 10 mm at the top and bottom of the sheet (the head cannot reach the first 10 mm; the bridge keeps the last 6 mm clear regardless) and 0 mm at the sides. One page per sheet, no duplex, grayscale only (`sgray_8` raster).

## Behaviour

- A job waits for a sheet; the printer reports `media-empty`, `cover-open` or `other` (printer off) until the sheet is seated, then prints and ejects. A multi-page job waits for each sheet in turn.
- A printer that is switched off while a job waits is picked up again when it comes back on.
- Cancelling a job while it waits, or during the transfer, stops it and ejects the sheet.
- A sheet shorter than the page aborts the job with `paper ran out`; a lid opened mid-page aborts it with `lid opened`.
- When the bridge is not running the queue pauses (`printer-state` stopped, the device error names the socket path in the log) and resumes on its own once the bridge answers.
- While idle, lid and paper state show up in `printer-state-reasons` as long as the bridge still holds the link (two minutes after a job by default).

## Troubleshooting

- **No devices listed / jobs pause**: the bridge is not reachable. Check `systemctl --user status phomemo-bridge` and that `PHOMEMO_BRIDGE_SOCKET` (or `$XDG_RUNTIME_DIR/phomemo-bridge.sock`) is the same for both programs; `phomemo-bridge status` talks to the daemon directly.
- **Printer not found although it is on**: BlueZ may still hold a stale link after a killed daemon; `bluetoothctl disconnect <address>` frees it. The printer does not advertise while connected, and switches off after ten minutes idle.
- **Logs**: `phomemo-printer-app server -o log-file=/path -o log-level=debug`; the bridge logs with `phomemo-bridge serve -v`.

## Sources

| File | Role |
|------|------|
| `main.c` | Driver table, auto-add rule, `papplMainloop` entry point. |
| `device.c` | The `phomemo://` device scheme over the bridge socket, status mapping. |
| `driver.c` | Printer capabilities (media, resolution, raster type, `phomemo-tone`) and option mapping helpers. |
| `job.c` | Raster callbacks: wait for a sheet, stream rows, finish the page, surface errors. |
| `bridge.c` | Line-oriented JSON client for the bridge protocol. |
| `third_party/cJSON.*` | [cJSON](https://github.com/DaveGamble/cJSON) 1.7.18, MIT. |
