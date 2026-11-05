# First steps

You have the driver installed (see [Installation](installation.md)) and both services are running. Now you register the printer with the printer app and print a first page.

## Step 1: Power and Bluetooth on

Power the printer on and keep it close to your computer. Ensure Bluetooth is enabled on your computer.

```{note}
The printer accepts one connection at a time and does not show up in a scan while another device (a phone or another computer) is connected to it. Bluetooth range is short: keep the printer near your computer.
```

## Step 2: Register the printer

```bash
sudo phomemo-printer-app autoadd
sudo phomemo-printer-app printers
```

The `autoadd` command automatically scans for printers within range and registers every compatible printer it finds. The `printers` command then lists all registered printers.

```{tip}
At its very first start (no saved state yet) the printer app registers every printer in range automatically. This means you may be able to skip the `autoadd` command, if you have the printer turned on and in range during the first installation of the driver package.
```

### Alternative: Register through the web interface

In addition to the CLI commands you can register a printer through the printer app web interface:

1. Open [http://localhost:8000/](http://localhost:8000/) in your browser
1. Use the the *Add Printer* button. The printer app then scans for printers in range.
1. Select the printer and continue the registration through the web interface.

## Step 3: Print the test page

Ensure the printer is powered on and in range, and load a sheet.  
Then open the printer app web interface at [http://localhost:8000/](http://localhost:8000/), select your printer in the menu, then use the button *Print test page*.

The test page shows the printer's address, serial number, battery state, firmware and driver versions, and more.

## Step 4: Add a permanent CUPS queue (optional)

The queue CUPS creates on first use is temporary: CUPS removes it once the printer idles. GNOME Settings lists only permanent queues, so add one if you want the printer to show up in your system printer GUI.

**In GNOME:**  
Settings → Printers → Add Printer, then pick the printer.

**On the command line:**

```bash
sudo lpadmin -p Phomemo_M08F_DDEEFF -E -m everywhere \
  -v 'ipps://Phomemo%20M08F%20(DDEEFF)._ipps._tcp.local/'
```

`driverless` (from cups-filters) lists the exact URI for your printer. CUPS' own `lpinfo --include-schemes dnssd -v` may leave the printer out.

## Next

- [Everyday use](everyday-use.md): printing options, sheets, battery, several printers.
- [Troubleshooting](troubleshooting.md): when something does not work.
