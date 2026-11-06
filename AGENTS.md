# Working in this repository

Guidance for contributors and coding agents. Keep it current: when a change makes a line here untrue, fix the line in the same change.

## What this is

A driver stack for the Phomemo M08F A4 thermal printer over Bluetooth Low Energy:

- `src/phomemo/`: the Python library (BLE transport, printing protocol, image preparation, printer profiles) and `phomemo-bridge`, the bridge that owns the printer for other programs over a unix socket.
- `src/printer-app/`: a PAPPL printer application in C that presents the printer as an IPP Everywhere printer and drives the bridge.
- `src/models/`: one description per printer model (`model.json` plus icons), read by the library, the bridge and the printer application; a new model with the same protocol is a new directory there. A hardware variant sold under the same advertised name is a directory with the same `ble_name_pattern` and the variant's `serial_codes`.
- `packaging/`: system units and presets (`systemd/`), default configuration (`config/`), RPM spec files (`rpm/`); one directory per package format, see `packaging/README.md`.
- `docs/`: the documentation site (Sphinx, its own uv project `phomemo-docs`), published per version (`latest/` from main, one directory per tag, `stable/`) on the `gh-pages` branch by `docs/publish.py`; `docs/m08f-protocol-reference.md` is the reverse-engineered protocol and the source of truth for printer behaviour.
- Root: the uv workspace (`pyproject.toml` with the members and the ruff settings, `uv.lock`, `.python-version`), the `Makefile` for builds, installs and releases.

## Setup and commands

```bash
uv sync --all-packages                    # workspace: library with test tooling, docs site
uv run pytest src/phomemo/tests           # Python tests
uv run ruff check . && uv run ruff format .
make -C src/printer-app                   # needs pappl-devel, cjson-devel, cups-devel
make -C src/printer-app test              # C unit tests
uv run pytest src/phomemo/tests/test_printer_app.py   # end-to-end, needs the built binary, ipptool, ghostscript
uv run --package phomemo-docs sphinx-build -W -b html docs docs/_build/html   # documentation site
make check                                # all of the above, as CI runs it
make help                                 # list the Makefile targets
make dist | tarball | srpm | deb          # release artefacts into dist/ (deb needs dpkg-dev, debhelper and the build dependencies)
make release VERSION=minor                # release: version everywhere (or major, patch, x.y.z), commit, tag; then push
```

CI (`.github/workflows/ci.yml`) runs the checks, the docs build and the RPM builds (`python-bleak`, then `phomemo-driver` against it) in a container per supported Fedora release (Bodhi's current releases from `MIN_FEDORA` on, plus Rawhide as informational), the Debian packages (`make deb`, lintian, install) on Debian 13 and Ubuntu 24.04, and the Python tests once more on Ubuntu 24.04 with its distribution packages (Python 3.12, bleak 0.21, Pillow 10.1: the library's declared floors); Renovate (`.github/renovate.json5`) updates `uv.lock` within the declared ranges (runtime dependencies capped below their next major, a new major comes as a cap-raising PR for review; dev and docs tools uncapped), the `Version:` of `packaging/rpm/python-bleak.spec` from PyPI, and the Actions weekly, automerging in-range updates; a `v*` tag runs `release.yml` (PyPI via trusted publishing, the source RPM, a GitHub release, the COPR build of `phomemo-driver` and the OBS service run, both of which build the newest `v*` tag; `bleak.yml` triggers the COPR and OBS `python-bleak` builds when a push to main changes the spec's version). COPR goes through its custom webhook (secret `COPR_WEBHOOK`), OBS through a service-run token (secret `OBS_TOKEN`, project name in the repository variable `OBS_PROJECT`). Spec files, Debian packaging, OBS service files and systemd units live in `packaging/`. Fedora has no bleak, so COPR and OBS also build `packaging/rpm/python-bleak.spec` at the version it names (Renovate bumps it; the requirement in `src/phomemo/pyproject.toml` caps it below 4; Debian and Ubuntu use their own `python3-bleak`).

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
