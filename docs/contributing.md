# Contributing

Thanks for wanting to help! Bug reports, fixes, documentation and new features are all welcome. Two kinds of contribution we especially hope for:

- **New printer models.** A Phomemo model with the same protocol needs only a model manifest; see [Printer models](models.md). Own one, especially a Bluetooth model, but do not want to write the manifest yourself? [Open a new-model issue](https://github.com/PassionateBytes/phomemo-driver/issues/new?template=new-model.yml): the model name, the name it advertises over Bluetooth and a few test prints are what it takes.
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
sudo dnf install gcc make pkgconf-pkg-config pappl-devel cjson-devel cups-devel
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

The published site is versioned. `.github/workflows/docs.yml` builds `latest/` from every push to main and a directory per release (`0.3.0/`, ...) from every `v*` tag; the newest release is also copied to `stable/`, where the site root and the unversioned page links lead. `docs/publish.py` assembles the site on the `gh-pages` branch, and the version menu reads its `versions.json`. Local builds leave the menu out (the workflow sets `DOCS_VERSION`). To rebuild an older release, run the Docs workflow by hand with its tag.

CI (`.github/workflows/ci.yml`) runs on every Fedora release that still gets updates (it asks Fedora's Bodhi which ones, from `MIN_FEDORA` on) and on Rawhide, each in its own container: the checks as an ordinary user, and the RPM packages as COPR and OBS build them, `python-bleak` at the version its spec names and `phomemo-driver` against it, both installed. Lint and the documentation build run on the newest release only. Rawhide is informational: a failure there shows in the run's summary and as a warning, but does not fail CI. The Debian packages are built as OBS builds them (`make deb`) on Debian 13 and Ubuntu 24.04, checked with lintian and installed. A further job runs the Python tests on Ubuntu 24.04 with the distribution's own packages (Python 3.12, bleak 0.21, Pillow 10.2): the library's declared floors are `python>=3.12`, `bleak>=0.21.0` and `pillow>=10.1.0`, so a change that needs a newer API fails there.

Dependencies are kept current by [Renovate](https://docs.renovatebot.com/) (`.github/renovate.json5`), weekly: it moves `uv.lock` within the ranges in the `pyproject.toml` files, bumps the `Version:` of `packaging/rpm/python-bleak.spec` from PyPI and bumps the GitHub Actions. The runtime dependencies are capped below their next major version (`bleak>=0.21.0,<4`, `pillow>=10.1.0,<14`); a new major comes as a pull request that raises the cap and waits for review, their minor and patch updates arrive with the weekly lock refresh. A test keeps the packaged bleak version inside the library's range, so a bleak major in the spec waits for the cap. Development and documentation tools are uncapped. Everything else merges on its own once CI is green; GitHub Actions majors also wait for review.

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

## Packaging

```
packaging/
  systemd/    system units, service user (sysusers), presets
  config/     bridge.toml for /etc/phomemo/, phomemo-printer-app.conf for /etc/
  rpm/        phomemo-driver.spec (driver + python3-phomemo), python-bleak.spec
  debian/     Debian source package: phomemo-driver.dsc and the debian.* files
  obs/        the source services of the two Open Build Service packages
```

Files shared by every package format live in the format-neutral directories (`systemd/`, `config/`); each format gets its own directory. The Python package goes to PyPI from `src/phomemo/` and needs nothing from here.

The COPR route (Fedora):

- The COPR project `passionatebytes/phomemo-driver` builds both specs from git with the `make_srpm` method, which runs `.copr/Makefile`. `phomemo-driver` is built from the newest `v*` tag, never from unreleased code on `main`. The builds are started from GitHub through the project's custom webhook (repository secret `COPR_WEBHOOK`): `release.yml` on each tag, `bleak.yml` when a push to `main` changes the version in `python-bleak.spec`.
- `phomemo-driver.spec` builds from a `git archive` of the repository.
- Fedora has no bleak, so `python-bleak.spec` is built at the version it names. Renovate bumps that version from PyPI; a test keeps it inside the range in `src/phomemo/pyproject.toml`.

The OBS route (Debian, Ubuntu, and the RPMs as an alternative to COPR):

- The Open Build Service project `home:passionatebytes:phomemo-driver` holds two packages, `phomemo-driver` and `python-bleak`, whose `_service` files are kept in `packaging/obs/`. Each service run fetches from this repository: `phomemo-driver` checks out the newest `v*` tag (`revision` `@PARENT_TAG@`), packs it as the source tarball and takes the spec and the `packaging/debian/` files from that tag; `python-bleak` takes its spec from `main` and downloads the bleak release it names from PyPI. OBS builds the RPM targets from the spec and the Debian and Ubuntu targets from `phomemo-driver.dsc` plus the `debian.*` files (`debian.X` becomes `debian/X`).
- The service runs are started from GitHub with a token (secret `OBS_TOKEN`, project name in the repository variable `OBS_PROJECT`): `release.yml` on each tag, `bleak.yml` on a bleak version change. `packaging/obs/README.md` describes the project setup.
- `make deb` builds the Debian packages locally the same way; CI does it on Debian 13 and Ubuntu 24.04.
- `make release` bumps the version in `phomemo-driver.dsc` and starts the `debian.changelog` entry next to the spec's.

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
make release VERSION=minor      # or major, patch, or an explicit x.y.z
git push && git push origin vx.y.z
```

`make release` runs on a clean `main`: it sets the version in `src/phomemo/pyproject.toml`, the RPM spec and `src/printer-app/phomemo.h`, starts a `%changelog` entry in the spec (one line, `Release x.y.z`), updates `uv.lock`, commits and creates the annotated tag `vx.y.z`. It refuses a tag that exists. The push is yours: pushing the tag publishes. Notes for the RPM changelog go into the spec before the release, in their own commit; the stub line marks releases without notes.

Pushing the tag runs `.github/workflows/release.yml`:

| Job | Result |
|---|---|
| Build | Wheel and sdist; fails when the tag does not match the package version |
| Publish to PyPI | Trusted publishing, environment `pypi` |
| Source RPMs | `make srpm` in a Fedora container |
| GitHub release | Generated notes, with the wheel, sdist, source RPM and tarball attached |
| COPR build | Asks COPR to build `phomemo-driver` (job `copr`) |
| OBS build | Asks the Open Build Service to run the `phomemo-driver` source service (job `obs`) |

For local artefacts: `make dist` (wheel and sdist), `make tarball` (source tarball named like the GitHub archive), `make srpm` (source RPM, needs rpm-build), `make deb` (Debian packages, needs dpkg-dev, debhelper and the build dependencies), all into `dist/`. `make help` lists every target.
