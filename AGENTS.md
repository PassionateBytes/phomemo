# Working in this repository

Guidance for contributors and coding agents. Keep it current: when a change makes a line here untrue, fix the line in the same change.

## What this is

A driver stack for the Phomemo M08F A4 thermal printer over Bluetooth Low Energy:

- `packages/phomemo/`: the Python library (BLE transport, printing protocol, image preparation, printer profiles) and the `phomemo-bridge` daemon that owns the printer for other programs over a unix socket.
- `printer-app/`: a PAPPL printer application in C that presents the printer as an IPP Everywhere printer and drives the bridge.
- `packaging/`: systemd user units.
- `docs/m08f-protocol-reference.md`: the reverse-engineered protocol; the source of truth for printer behaviour.

## Setup and commands

```bash
uv sync                                   # Python workspace with test tooling
uv run pytest                             # Python tests (root pyproject sets the paths)
uv run ruff check . && uv run ruff format .
make -C printer-app                       # needs pappl-devel and cups-devel
make -C printer-app test                  # C unit tests
uv run pytest packages/phomemo/tests/test_printer_app.py   # end-to-end, needs the built binary, ipptool, ghostscript
```

The printer-app pytest module starts the built binary as a private server under the test's temporary directory. Never run `phomemo-printer-app devices` or `server` from a test or script outside that harness: it starts a long-lived server and writes state under the user's config directory.

Tests touching the real printer are not automated. Hardware checks are done by hand with the printer on and in range.

## Conventions

- Commits follow Conventional Commits (`feat(phomemo): ...`, `fix(printer-app): ...`, `docs: ...`); the body says why.
- Documentation changes with the code in the same commit: README, docstrings, the protocol reference and comments must stay true.
- Comments describe what the code does or which invariant it keeps, not the history of how it got there.
- Python: modern typing (`X | None`, built-in generics), Google-style docstrings without types, ruff clean. C: `-Wall -Wextra -Werror`, C99.
- No device identifiers (printer MAC, serial), personal paths or host names in tracked files. Placeholders: `AA:BB:CC:DD:EE:FF`, `<serial>`.
- No em-dashes in text.
- Tests first for behaviour changes; the fake printer in `packages/phomemo/tests/test_bridge_server.py` scripts the device side.

## Where the knowledge is

Protocol facts and measured behaviour go into `docs/m08f-protocol-reference.md`. User-facing behaviour of the library and daemon into `packages/phomemo/README.md`, of the printer application into `printer-app/README.md`. Planning documents, specs and review reports are not tracked here.
