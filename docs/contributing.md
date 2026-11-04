# Contributing

Thanks for wanting to help! Bug reports, fixes, documentation and new features are all welcome. Two kinds of contribution we especially hope for:

- **New printer models.** A Phomemo model with the same protocol needs only a model manifest; see [Printer models](models.md).
- **New package formats.** Today there are RPMs (COPR) and PyPI. Debian packages (apt), a snap or anything else that brings the driver to more systems would be great; see [Add a package format](#add-a-package-format).

Questions and bug reports go to [GitHub issues](https://github.com/PassionateBytes/phomemo-driver/issues).

## Set up

```bash
git clone https://github.com/PassionateBytes/phomemo-driver.git
cd phomemo-driver
uv sync --all-packages
```

That gives you one environment with the library, its test tooling (pytest, pytest-asyncio, ruff, ty) and the documentation tools.

To build the printer app you also need its C dependencies. On Fedora:

```bash
sudo dnf install gcc make pkgconf-pkg-config pappl-devel cups-devel
sudo dnf install cups-ipptool ghostscript    # for the end-to-end tests
```

## Repository layout

```
pyproject.toml      uv workspace root (members, ruff settings); no project of its own
uv.lock             one lock file for the workspace
Makefile            build, install, checks, release
src/phomemo/        Python library and bridge (uv project "phomemo")
src/printer-app/    PAPPL printer app in C
src/models/         model manifests, one directory per model
docs/               this site (Sphinx, uv project "phomemo-docs")
packaging/          systemd units, default configuration, spec files
```

`docs/m08f-protocol-reference.md` is the source of truth for how the printer behaves.

## Run the checks

```bash
make check
```

This runs what CI runs: ruff lint and format check, the Python tests and the C unit tests. The individual commands:

```bash
uv run ruff check . && uv run ruff format .
uv run pytest src/phomemo/tests
make -C src/printer-app
make -C src/printer-app test
uv run --package phomemo-docs sphinx-build -W -b html docs docs/_build/html
```

```{tip}
Build the docs with `-W` before you push: CI treats every Sphinx warning as an error.
```

CI (`.github/workflows/ci.yml`) runs everything in a Fedora 44 container as an ordinary user, and lints and builds the RPM packages in a second job.

## Tests

### The fake printer

```python
from tests.test_bridge_server import FakePrinter
```

`FakePrinter` in `src/phomemo/tests/test_bridge_server.py` is a scripted stand-in for `phomemo.Printer`. Use it to script the device side (lid, paper, a sheet running out, a dropped connection) in bridge tests, without a printer.

### The printer app end to end

```bash
make -C src/printer-app
uv run pytest src/phomemo/tests/test_printer_app.py
```

`test_printer_app.py` starts the built `phomemo-printer-app` as a private server, with its state, spool and control socket under the test's temporary directory, and serves it a bridge whose printer is the `FakePrinter`. It needs `ipptool` and Ghostscript, and it is skipped when the binary has not been built.

```{warning}
Never run `phomemo-printer-app devices` or `server` from a test or script outside that harness. It starts a long-lived server and writes state under your config directory.
```

### Hardware

Tests against a real printer are not automated. If your change affects printing, check it by hand with the printer on and in range, and say in the pull request what you tried.

## Conventions

| Topic | Rule |
|---|---|
| Commits | [Conventional Commits](https://www.conventionalcommits.org/): `feat(phomemo): ...`, `fix(printer-app): ...`, `docs: ...`; the body says why |
| Tests | Tests first for behaviour changes |
| Documentation | Changes with the code, in the same commit: READMEs, docstrings, comments, the protocol reference and these pages stay true |
| Comments | Describe what the code does or which invariant it keeps, not how it got there |
| Python | Modern typing (`X \| None`, built-in generics), Google-style docstrings without types, ruff clean |
| C | C99, `-Wall -Wextra -Werror` |
| Terms | As defined in the [glossary](glossary.md): register (not pair), connection (not link), sheet and page, model manifest |
| Privacy | No device identifiers, personal paths or host names in tracked files; use `AA:BB:CC:DD:EE:FF` and `<serial>` |
| Text | No em-dashes |

### Licences

Every new source file starts with the copyright notice and licence statement (FSF style) used in its neighbours.

| Part | Licence |
|---|---|
| Library and bridge (`src/phomemo/`), model manifests (`src/models/`) | GNU LGPL, version 3 or later |
| Printer app (`src/printer-app/`) | GNU GPL, version 3 or later |
| Packaging, build files and everything else | GNU GPL, version 3 or later |
| Documentation (`docs/`, the READMEs) | CC BY-SA 4.0 |

Bundled third-party code keeps its own licence (cJSON, MIT, in the printer app).

## Packaging

```
packaging/
  systemd/    system units, service user (sysusers), presets
  config/     bridge.toml for /etc/phomemo/, phomemo-printer-app.conf for /etc/
  rpm/        phomemo-driver.spec (driver + python3-phomemo), python-bleak.spec
```

Files shared by every package format live in the format-neutral directories (`systemd/`, `config/`); each format gets its own directory. The Python package goes to PyPI from `src/phomemo/` and needs nothing from here.

The Fedora route:

- The COPR project `passionatebytes/phomemo-driver` builds both specs from git with the `make_srpm` method, which runs `.copr/Makefile`.
- `phomemo-driver.spec` builds from a `git archive` of the repository.
- Fedora has no bleak, so `python-bleak.spec` is built at the bleak version locked in `uv.lock`. Update it with `uv lock --upgrade-package bleak`; `src/phomemo/pyproject.toml` caps it below 4.

### Add a package format

1. Create a directory named after the format (`debian/`, `snap/`, ...) with its manifests and any build scripts it needs.
2. Reuse `systemd/` and `config/` instead of copying them. Formats that install units differently (a snap's daemons, for example) take what they need from there or describe the same services in their own terms.
3. Add a target to the root `Makefile` that builds the package locally, and a job to the workflows that builds it in CI and publishes it on a tag.
4. Add the format to the table in `packaging/README.md` and its install instructions to `src/printer-app/README.md`.

```{note}
Not sure how a format should handle the two services or the `phomemo` service user? Open an issue or a draft pull request early; we are happy to help.
```

## Releases

```bash
make bump VERSION=x.y.z
make tag
git push && git push origin vx.y.z
```

`make bump` sets the version in `src/phomemo/pyproject.toml`, the RPM spec and `src/printer-app/phomemo.h`, updates `uv.lock` and commits. `make tag` creates the annotated tag `vx.y.z`.

Pushing the tag runs `.github/workflows/release.yml`:

| Job | Result |
|---|---|
| Build | Wheel and sdist; fails when the tag does not match the package version |
| Publish to PyPI | Trusted publishing, environment `pypi` |
| Source RPMs | `make srpm` in a Fedora container |
| GitHub release | Generated notes, with the wheel, sdist, source RPM and tarball attached |

COPR builds the RPMs through its webhook, from every push to `main` and from the tag.

For local artefacts: `make dist` (wheel and sdist), `make tarball` (source tarball named like the GitHub archive), `make srpm` (source RPM, needs rpm-build), all into `dist/`.
