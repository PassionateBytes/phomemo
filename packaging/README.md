# Packaging

Everything that turns the repository into installable packages, grouped by
what it is for. Files shared by every package format live in the
format-neutral directories; each package format gets its own directory.

| Directory | Contents | Used by |
|-----------|----------|---------|
| `systemd/` | System units, the service user (sysusers), presets that enable the units on installation | `make install`, `rpm/` |
| `config/` | Default configuration: `bridge.toml` to `/etc/phomemo/`, `phomemo-printer-app.conf` to `/etc/` | `make install`, `rpm/` |
| `rpm/` | Spec files: `phomemo-driver.spec` (the driver and the `python3-phomemo` subpackage), `python-bleak.spec` (bleak, which Fedora lacks) | COPR (through `.copr/Makefile`), CI, `make srpm` |
| `../snap/` | The snap: `snapcraft.yaml`, wrapper scripts and `adapt-config.py` in `local/`. At the repository root because snapcraft looks for it there | `.github/workflows/snap.yml`, `make snap` |

The Python package itself is published to PyPI from `src/phomemo/` by
the release workflow; it needs nothing from here.

## The Fedora route

- COPR project `passionatebytes/phomemo-driver` builds both specs from git
  with the `make_srpm` method, which runs `.copr/Makefile` (COPR expects it
  at that path).
- `phomemo-driver.spec` builds from a `git archive` of the repository;
  `python-bleak.spec` is built at the bleak version locked in `uv.lock`.
- CI (`.github/workflows/ci.yml`) lints and builds `phomemo-driver.spec` in
  a Fedora container, taking bleak from the COPR repository.

## The snap route

- One strictly confined snap, `phomemo-printer-app`, built like the
  OpenPrinting printer-application snaps: PAPPL from its release tag, the
  printer app against it, the library and the bridge in a Python virtual
  environment (Python 3.13 from the deadsnakes PPA, the core24 base has
  3.12). Both services run as snap daemons, as root, with the interfaces
  `bluez` (bridge) and `avahi-control`, `network`, `network-bind` (printer
  app).
- Everything writable sits in `$SNAP_COMMON`
  (`/var/snap/phomemo-printer-app/common`): the configuration files, copied
  from `config/` with their comments adapted by `snap/local/adapt-config.py`,
  the bridge socket, PAPPL's state and spool.
- `.github/workflows/snap.yml` builds it on pull requests and publishes
  pushes to `main` to the channel `edge` and `v*` tags to `stable` (secret
  `SNAPCRAFT_STORE_CREDENTIALS`).

## Adding a package format

1. Create a directory named after the format (`debian/`, …) with
   its manifests and any build scripts it needs; at the repository root
   only when the format's tooling insists, as snapcraft does.
2. Reuse `systemd/` and `config/` instead of copying them. Formats that
   install units differently (a snap's daemons, for example) take what
   they need from there or describe the same services in their own terms.
3. Add a target to the root `Makefile` that builds the package locally,
   and a job to the workflows that builds it in CI and, on a tag, publishes
   it.
4. Add the format to the table above and its install instructions to
   `docs/installation.md`.
