# First steps

You have the driver installed (see [Installation](installation.md)) and both services are running. Now you register the printer with the printer app and print a first page.

## Step 1: switch the printer on

Switch the printer on, close the lid and keep it close to your computer.

```{note}
The printer accepts one connection at a time and does not show up in a scan while another device (a phone, another computer) is connected to it. Bluetooth range is short: keep the printer within about 2 m.
```

## Step 2: register the printer

```bash
sudo phomemo-printer-app autoadd
```

This scans for printers in range and registers every M08F it finds. Registering needs `sudo` because it changes the system service.

```{tip}
At its very first start (no saved state yet) the printer app registers every printer in range on its own. If the printer was on during installation, it may already be registered: check with step 3 first.
```

Each printer is named after its model and the last three bytes of its Bluetooth address, for example **Phomemo M08F (DDEEFF)**. That way several printers never clash.

### Other ways to register

| How | What it does |
|---|---|
| Web interface at http://localhost:8000/, *Add Printer* | Scans the same way as `autoadd`; you pick the printer. |
| `phomemo-printer-app devices` | Only scans and lists what is in range; registers nothing. |
| `phomemo-printer-app add` | Registers a printer whose address you know (see below). |

For `add`, give the name, the model and the device URI:

```bash
sudo phomemo-printer-app add -d "Phomemo M08F (DDEEFF)" -m m08f \
  -v "phomemo://AA-BB-CC-DD-EE-FF?model=m08f"
```

```{note}
The device URI writes the Bluetooth address with dashes instead of colons, because a URI host cannot hold colons.
```

`phomemo-printer-app --help` lists all subcommands.

## Step 3: check the registration

```bash
phomemo-printer-app printers
```

You should see your printer, for example `Phomemo M08F (DDEEFF)`. Listing needs no `sudo`.

## Step 4: print a first page

```bash
lpstat -e
lp -d Phomemo_M08F_DDEEFF document.pdf
```

CUPS discovers the printer through DNS-SD, so there is nothing to set up: `lpstat -e` lists it, and `lp` prints to it. CUPS creates the CUPS queue on first use.

The queue name comes from the printer name: CUPS replaces each run of characters other than letters and digits with one underscore, so "Phomemo M08F (DDEEFF)" becomes `Phomemo_M08F_DDEEFF`.

```{important}
Close the lid first, then insert a sheet. The job waits until a sheet is seated, prints and ejects it.
```

## Step 5: print the test page

Open the printer's page in the web interface (http://localhost:8000/, then your printer) and click *Print test page*.

The test page shows the printer's address, firmware, serial number, battery, connection and version details, millimetre rulers, a gray ramp, and line and text samples. It goes through the normal job pipeline, so it also tests the whole setup.

```{tip}
"Identify printer" in the web interface ejects a loaded sheet and pulses the feed three times, so you can tell which printer is which.
```

## Step 6: add a permanent CUPS queue (optional)

The queue CUPS creates on first use is temporary: CUPS removes it when idle. GNOME Settings lists only permanent queues, so add one if you want the printer to show up there.

**In GNOME:** Settings → Printers → Add Printer, then pick the printer.

**On the command line:**

```bash
sudo lpadmin -p Phomemo_M08F_DDEEFF -E -m everywhere \
  -v 'ipps://Phomemo%20M08F%20(DDEEFF)._ipps._tcp.local/'
```

This queue uses the DNS-SD URI, so it keeps working when the printer app's port changes. `lpinfo --include-schemes dnssd -v` lists the exact URI for your printer.

```{note}
The battery shows up in GNOME Settings only after the first job through the permanent queue: CUPS reads supply levels only while it runs a job. It then shows the reading from the last job.
```

## Next

- [Everyday use](everyday-use.md): printing options, sheets, battery, several printers.
- [Troubleshooting](troubleshooting.md): when something does not work.
