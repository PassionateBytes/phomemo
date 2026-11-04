# Everyday use

Once the printer is registered (see [First steps](first-steps.md)), you print to it like to any other printer. This page covers the options and what to expect from the printer day to day.

## Printing options

```bash
lp -d Phomemo_M08F_DDEEFF -o media=iso_a5_148x210mm -o print-quality=5 -o phomemo-tone=ordered photo.png
```

Every option also appears in the print dialog of your application and in the printer app's web interface.

| Option | Values | Effect |
|---|---|---|
| `media` | `iso_a4_210x297mm` (default), `iso_a5_148x210mm` | Sheet size. |
| `print-quality` | `3` draft, `4` normal (default), `5` high | Printer density: low, medium, high. |
| `phomemo-tone` | see below | How gray becomes dots. |
| `print-content-optimize` | `auto`, `text`, `graphic`, `photo` | Guides `phomemo-tone=auto`. |

### A5 sheets

A5 sheets go in long edge first. A portrait A5 page is rotated so its right edge leads out of the printer; you do not need to rotate anything yourself.

### Rendering (`phomemo-tone`)

| Value | Label in the web interface | Use it for |
|---|---|---|
| `auto` (default) | Automatic | Black and white for text and graphics, diffusion dither for photos, following `print-content-optimize`. |
| `threshold` | Black and white | Text and line art. |
| `ordered` | Ordered dither | Gray areas as a regular pattern. |
| `diffusion` | Diffusion dither | Photos. |

```{note}
The printer prints grayscale only, one page per sheet, no duplex. The only media type is thermal paper. Margins are 10 mm at the top and bottom of the sheet and 0 mm at the sides.
```

## Loading sheets

```{important}
Close the lid first, then insert the sheet. A sheet inserted while the lid is still open is ejected again.
```

A job waits until a sheet is seated, then prints and ejects it. A job with several pages waits for each sheet in turn. While the job waits, the printer app tells you what to do: "Insert a sheet.", "Close the lid." or "Turn on Bluetooth.".

```{note}
CUPS shows the queue as "Printing." the whole time. The reasons (`media-empty`, `cover-open`, `offline`) are visible in the printer app's web interface and through IPP.
```

### When something interrupts a page

Nothing is lost. The page is printed again:

| What happens | What the driver does |
|---|---|
| The lid opens mid-page | Reports `cover-open`. When the lid closes, a sheet still inside is ejected. Insert a new sheet and the page prints again. |
| The sheet runs out before the page ends | Reports `media-empty`. Insert a longer sheet and the page prints again. |
| The printer switches off or the connection drops mid-page | Picks the printer up again when it comes back on and prints the page again. |

### Cancelling

Cancel a job while it waits for a sheet and it simply stops. Cancel it once printing has started and the transfer stops and the sheet is ejected.

## Battery

The printer app shows the battery charge as the printer's supply level, in its web interface and through IPP. It keeps the last reading while the printer is off or out of range.

```{tip}
GNOME Settings shows the battery as an ink level, but only for a permanent CUPS queue and only after a job. See [First steps](first-steps.md#step-6-add-a-permanent-cups-queue-optional).
```

## Several printers

Each printer gets its own name with the end of its Bluetooth address, for example "Phomemo M08F (DDEEFF)", and its own CUPS queue. Print to the one you want.

The bridge holds one connection at a time. A job for another printer switches the connection to that printer.

```{tip}
With several printers in range, `phomemo-bridge` commands refuse to guess and list the printers. Pick one with `-a AA:BB:CC:DD:EE:FF`. See [Command line](command-line.md).
```

## Using the printer from a phone or another computer

The printer accepts one connection. While the bridge holds it, the printer does not show up for other devices.

```bash
phomemo-bridge disconnect
```

This drops the connection right away, so your phone or the other computer can reach the printer.

Without that, the bridge drops the connection on its own after `idle_disconnect_minutes` without a command (default 30), or earlier when the printer switches off or leaves range. Set it in `/etc/phomemo/bridge.toml`:

```toml
idle_disconnect_minutes = 10
```

Then restart the bridge: `sudo systemctl restart phomemo-bridge`. `0` keeps the connection until the printer switches off. See [Configuration](configuration.md).

## Auto-off

The printer switches itself off after a period without activity. Check or change the timer with the bridge:

```bash
phomemo-bridge connect
phomemo-bridge auto-off        # show the timer
phomemo-bridge auto-off 15     # set it to 15 minutes
```

Values are multiples of 5 up to 1275; `0` means never switch off. The printer keeps the setting when it is switched off and on again.

For a lasting setting, set `auto_off_minutes` in `/etc/phomemo/bridge.toml`. The bridge writes it to the printer at each new connection, so it also wins over a value set with `phomemo-bridge auto-off`. Leave it unset and the printer keeps its own setting.

```{note}
An open connection without traffic does not keep the printer on. Queries do count as activity: a client that keeps polling the printer keeps it on for as long as it polls.
```
