---
html_theme.sidebar_secondary.remove: true
---

```{raw} html
<div class="hero">
  <img class="hero-logo" src="_static/m08f.png" alt="Phomemo M08F">
</div>
```

# phomemo-driver

**Print to a Phomemo thermal printer like to any other printer.** This package
turns the Phomemo M08F, an A4 thermal printer that only speaks Bluetooth LE,
into an ordinary IPP printer, ready to be used via your desktop, phones and every
other IPP client.  
The underlying python library can also be used directly to control your Phomemo printer
directly.

## Where to start

- **You want to print from your computer.** Follow [Installation](installation.md),
  then [First steps](first-steps.md): install, register the printer, print a
  page. That's it.
- **You want to print from Python.** The [library](library.md) scans for
  printers, prints images and bitmaps and reports the printer's sensors as
  events.
- **You want to know how it works, or contribute.** [Architecture](architecture.md)
  explains the parts, the [protocol reference](m08f-protocol-reference.md)
  documents what is known about the M08F, and [Contributing](contributing.md)
  shows how to get started. New [printer models](models.md) are especially
  welcome.

## The parts

| Part | What it does |
|---|---|
| **printer app** (`phomemo-printer-app`) | A [PAPPL](https://www.msweet.org/pappl/) printer app: presents each registered printer as an IPP Everywhere printer, with a web interface. |
| **bridge** (`phomemo-bridge`) | Owns the Bluetooth connection to the printer and prints the pages; also a command line for scanning, status and test pages. |
| **library** (`phomemo`) | The Python library both are built on: Bluetooth transport, raster printing, events. |
| **model manifests** | One description per printer model, shared by all of the above. |

```{toctree}
:caption: Get started
:hidden:

installation
first-steps
```

```{toctree}
:caption: Using it
:hidden:

everyday-use
configuration
command-line
troubleshooting
```

```{toctree}
:caption: Python library
:hidden:

library
api
```

```{toctree}
:caption: Under the hood
:hidden:

architecture
models
m08f-protocol-reference
glossary
```

```{toctree}
:caption: Project
:hidden:

contributing
```
