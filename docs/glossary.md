# Glossary

These terms are used the same way throughout the documentation, the command
help, the code and its comments.

| Term | Meaning | Not |
|---|---|---|
| **scan** | Search for printers in range over Bluetooth and list them: `phomemo-bridge devices`, `phomemo-printer-app devices`, the web interface's device list, the search `autoadd` runs. | search, discover (the socket command and the library function keep the name `discover`) |
| **register** | Add a printer to the printer app, which turns it into an IPP printer: at the first start, with `autoadd`, with `add`, or with the web interface's *Add Printer*. | pair, add, set up |
| **pairing** | Bluetooth bonding. The M08F does not use it: any host in range can connect without pairing. | — |
| **connection** | The Bluetooth connection between the bridge and one printer. `connect` brings it up, `disconnect` drops it, `idle_disconnect_minutes` limits how long it stays idle. | link |
| **printer app** | `phomemo-printer-app`, the PAPPL printer application that presents registered printers to CUPS and other IPP clients. | printer application (except when naming PAPPL's concept) |
| **bridge** | `phomemo-bridge`, the service that owns the connection and prints; also its command line. | daemon (except when the background process itself is meant) |
| **CUPS queue** | The printer entry CUPS keeps for a registered printer: temporary (created on use from DNS-SD) or permanent. | printer (for the queue) |
| **model** | A printer model, by its identifier (`m08f`). | — |
| **model manifest** | A model's directory in `src/models/`: `model.json` and the icons. | model description, profile (for the files) |
| **profile** | The library's `PrinterProfile`, built from a model manifest. | — |
| **sheet** | One sheet of paper in the printer. *Paper* only in general ("load paper"). | page (for the sheet) |
| **page** | The printed content of one sheet in a job. | — |
| **eject** | Feed the sheet out of the printer. | — |
| **auto-off** | The printer's own timer that switches it off after a period without activity. | sleep, standby |
