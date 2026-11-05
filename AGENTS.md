# Working in this repository

Guidance for contributors and coding agents. Keep it current: when a change makes a line here untrue, fix the line in the same change.

## What this is

A driver stack for the Phomemo M08F A4 thermal printer over Bluetooth Low Energy:

- `src/phomemo/`: the Python library (BLE transport, printing protocol, image preparation, printer profiles) and `phomemo-bridge`, the bridge that owns the printer for other programs over a unix socket.
- `src/printer-app/`: a PAPPL printer application in C that presents the printer as an IPP Everywhere printer and drives the bridge.
- `src/models/`: one description per printer model (`model.json` plus icons), read by the library, the bridge and the printer application; a new model with the same protocol is a new directory there.
- `packaging/`: system units and presets (`systemd/`), default configuration (`config/`), RPM spec files (`rpm/`); one directory per package format, see `packaging/README.md`.
- `docs/`: the documentation site (Sphinx, its own uv project `phomemo-docs`); `docs/m08f-protocol-reference.md` is the reverse-engineered protocol and the source of truth for printer behaviour.
- Root: the uv workspace (`pyproject.toml` with the members and the ruff settings, `uv.lock`, `.python-version`), the `Makefile` for builds, installs and releases.

## Setup and commands

```bash
uv sync --all-packages                    # workspace: library with test tooling, docs site
uv run pytest src/phomemo/tests           # Python tests
uv run ruff check . && uv run ruff format .
make -C src/printer-app                   # needs pappl-devel and cups-devel
make -C src/printer-app test              # C unit tests
uv run pytest src/phomemo/tests/test_printer_app.py   # end-to-end, needs the built binary, ipptool, ghostscript
uv run --package phomemo-docs sphinx-build -W -b html docs docs/_build/html   # documentation site
make check                                # all of the above, as CI runs it
make dist | tarball | srpm                # release artefacts into dist/
make bump VERSION=x.y.z && make tag       # release: version everywhere, commit, tag
```

CI (`.github/workflows/ci.yml`) runs the checks and the RPM build in a Fedora container; a `v*` tag runs `release.yml` (PyPI via trusted publishing, the source RPM and a GitHub release; COPR builds through its webhook from every push to main and from the tag). Spec files and systemd units live in `packaging/`. Fedora has no bleak, so the COPR project also builds `packaging/rpm/python-bleak.spec`, at the bleak version locked in `uv.lock`; update it with `uv lock --upgrade-package bleak` (the requirement in `src/phomemo/pyproject.toml` caps it below 4).

The printer-app pytest module starts the built binary as a private server under the test's temporary directory. Never run `phomemo-printer-app devices` or `server` from a test or script outside that harness: it starts a long-lived server and writes state under the user's config directory.

Tests touching the real printer are not automated. Hardware checks are done by hand with the printer on and in range.

## Conventions

- Commits follow Conventional Commits (`feat(phomemo): ...`, `fix(printer-app): ...`, `docs: ...`); the body says why.
- Documentation changes with the code in the same commit: the pages in `docs/`, the READMEs, docstrings, help texts and comments must stay true.
- Terminology follows `docs/glossary.md` everywhere (docs, help texts, log messages, docstrings, comments): *scan*, *register* (never "pair"), *connection* (never "link"), *printer app*, *bridge*, *model manifest*, *sheet* and *page*.
- Comments describe what the code does or which invariant it keeps, not the history of how it got there.
- Python: modern typing (`X | None`, built-in generics), Google-style docstrings without types, ruff clean. C: `-Wall -Wextra -Werror`, C99.
- No device identifiers (printer MAC, serial), personal paths or host names in tracked files. Placeholders: `AA:BB:CC:DD:EE:FF`, `<serial>`.
- No em-dashes in text.
- Licences: the library (`src/phomemo/`) and the model manifests (`src/models/`) are LGPL-3.0-or-later, the printer app and everything else GPL-3.0-or-later, documentation CC BY-SA 4.0 (see the README). Every new source file starts with the copyright notice and licence statement used in its neighbours.
- Tests first for behaviour changes; the fake printer in `src/phomemo/tests/test_bridge_server.py` scripts the device side.

## Where the knowledge is

Protocol facts and measured behaviour go into `docs/m08f-protocol-reference.md`. User-facing behaviour goes into the documentation site in `docs/` (Sphinx, MyST, Shibuya theme; build with `uv run --package phomemo-docs sphinx-build -W -b html docs docs/_build/html`): installation, first steps, everyday use, configuration, command line, troubleshooting, driver stack, print flow, library, printer models, contributing. The READMEs stay short entry points that link there. The docs' tone is friendly and direct in the style of FastAPI's documentation: second person, example first, short sections, admonitions for side remarks. Planning documents, specs and review reports are not tracked here.
