# This file is part of phomemo-driver.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo-driver is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo-driver is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with phomemo-driver.  If not, see <https://www.gnu.org/licenses/>.

# Build and install the whole printer driver from a fresh clone with
# `sudo make`. `make help` lists every target.

.DEFAULT_GOAL := install

VERSION   := $(shell sed -n 's/^version = "\(.*\)"/\1/p' src/phomemo/pyproject.toml)
NAME      := phomemo-driver
DIST      := dist

PREFIX    ?= /usr/local
DESTDIR   ?=
UNITDIR   ?= /etc/systemd/system
PRESETDIR ?= /usr/lib/systemd/system-preset
SYSCONF   ?= /etc
PYTHON    ?= python3
VENV       = $(PREFIX)/lib/phomemo

.PHONY: help build install uninstall check dist tarball srpm deb release clean

help:  ## List the targets
	@echo "Usage: make [target] [VAR=value]"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(firstword $(MAKEFILE_LIST)) | \
	  sed -E 's/^([a-z-]+):.*## (.*)/  \1\t\2/' | expand -t 14

build:  ## Build only (the printer app)
	$(MAKE) -C src/printer-app

# The Python package goes into its own virtual environment under PREFIX
# (system Pythons refuse direct installs); the units point at PREFIX.
install: build  ## Build and install as system services (default; run with sudo, PREFIX=/usr/local)
	$(MAKE) -C src/printer-app install PREFIX=$(PREFIX) DESTDIR=$(DESTDIR) \
	  UNITDIR=$(UNITDIR) PRESETDIR=$(PRESETDIR)
	$(PYTHON) -m venv --clear $(DESTDIR)$(VENV)
	$(DESTDIR)$(VENV)/bin/pip install --quiet --upgrade pip
	$(DESTDIR)$(VENV)/bin/pip install --quiet ./src/phomemo
	install -d $(DESTDIR)$(PREFIX)/bin
	ln -sf $(VENV)/bin/phomemo-bridge $(DESTDIR)$(PREFIX)/bin/phomemo-bridge
	install -d $(DESTDIR)$(UNITDIR) $(DESTDIR)$(PRESETDIR) \
	  $(DESTDIR)$(SYSCONF)/phomemo $(DESTDIR)$(SYSCONF)/sysusers.d
	sed 's|/usr/bin/phomemo-bridge|$(PREFIX)/bin/phomemo-bridge|' \
	  packaging/systemd/phomemo-bridge.service > $(DESTDIR)$(UNITDIR)/phomemo-bridge.service
	install -m 644 packaging/systemd/90-phomemo-bridge.preset $(DESTDIR)$(PRESETDIR)/
	install -m 644 packaging/systemd/phomemo.sysusers.conf $(DESTDIR)$(SYSCONF)/sysusers.d/phomemo.conf
	test -e $(DESTDIR)$(SYSCONF)/phomemo/bridge.toml || \
	  install -m 644 packaging/config/bridge.toml $(DESTDIR)$(SYSCONF)/phomemo/bridge.toml
	test -e $(DESTDIR)$(SYSCONF)/phomemo-printer-app.conf || \
	  install -m 644 packaging/config/phomemo-printer-app.conf $(DESTDIR)$(SYSCONF)/phomemo-printer-app.conf
ifeq ($(DESTDIR),)
	systemd-sysusers
	systemctl daemon-reload
	systemctl enable --now phomemo-bridge phomemo-printer-app
	@echo "installed; printer app at http://localhost:8000/"
endif

uninstall:  ## Remove what install put in place (run with sudo; keeps configuration)
	-systemctl disable --now phomemo-printer-app phomemo-bridge
	rm -f $(UNITDIR)/phomemo-bridge.service $(UNITDIR)/phomemo-printer-app.service
	rm -f $(PRESETDIR)/90-phomemo-bridge.preset $(PRESETDIR)/90-phomemo-printer-app.preset
	rm -f $(SYSCONF)/sysusers.d/phomemo.conf
	rm -f $(PREFIX)/bin/phomemo-bridge $(PREFIX)/bin/phomemo-printer-app
	rm -rf $(VENV)
	systemctl daemon-reload
	@echo "kept: $(SYSCONF)/phomemo/bridge.toml, $(SYSCONF)/phomemo-printer-app.conf and the printer app's state in /var/lib"

check:  ## Lint, Python tests, C tests (what CI runs)
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q src/phomemo/tests
	$(MAKE) -C src/printer-app test

dist:  ## Wheel and sdist of the phomemo package into dist/
	uv build src/phomemo --out-dir $(DIST)

tarball:  ## Source tarball named like the GitHub release archive
	mkdir -p $(DIST)
	git archive --format=tar.gz --prefix=$(NAME)-$(VERSION)/ \
	  -o $(DIST)/$(NAME)-$(VERSION).tar.gz HEAD

srpm: tarball  ## Source RPM into dist/ (needs rpm-build)
	rpmbuild -bs --define "_sourcedir $(CURDIR)/$(DIST)" \
	  --define "_srcrpmdir $(CURDIR)/$(DIST)" packaging/rpm/phomemo-driver.spec

# debian/ is assembled from packaging/debian/debian.* the way OBS does it
# (debian.X becomes debian/X) and removed again; dpkg-buildpackage writes
# the packages next to the checkout, from where they move into dist/.
deb:  ## Debian packages into dist/ (needs dpkg-dev, debhelper and the build dependencies)
	rm -rf debian
	mkdir -p debian/source $(DIST)
	for f in packaging/debian/debian.*; do cp "$$f" "debian/$${f##*/debian.}"; done
	echo "3.0 (quilt)" > debian/source/format
	dpkg-buildpackage -b -us -uc
	mv ../phomemo-driver_$(VERSION)-*.deb ../python3-phomemo_$(VERSION)-*.deb $(DIST)/
	rm -f ../phomemo-driver_$(VERSION)-*.buildinfo ../phomemo-driver_$(VERSION)-*.changes
	rm -rf debian .pybuild

release:  ## Set the version everywhere, commit and tag it (VERSION=x.y.z|major|minor|patch); you push
	@test -n "$(VERSION)" || { echo "usage: make release VERSION=x.y.z|major|minor|patch"; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo "working tree not clean"; exit 1; }
	@test "$$(git branch --show-current)" = main || { echo "release from main, not $$(git branch --show-current)"; exit 1; }
	@set -e; \
	current=$$(sed -n 's/^version = "\(.*\)"/\1/p' src/phomemo/pyproject.toml); \
	IFS=. read -r major minor patch <<< "$$current"; \
	case "$(VERSION)" in \
	  major) new="$$((major + 1)).0.0" ;; \
	  minor) new="$$major.$$((minor + 1)).0" ;; \
	  patch) new="$$major.$$minor.$$((patch + 1))" ;; \
	  *) new="$(VERSION)"; echo "$$new" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+([a-z]+[0-9]+)?$$' || { echo "not a version: $$new"; exit 1; } ;; \
	esac; \
	! git rev-parse -q --verify "refs/tags/v$$new" >/dev/null || { echo "tag v$$new exists"; exit 1; }; \
	echo "$$current -> $$new"; \
	sed -i "s/^version = \".*\"/version = \"$$new\"/" src/phomemo/pyproject.toml; \
	sed -i "s/^Version:        .*/Version:        $$new/" packaging/rpm/phomemo-driver.spec; \
	sed -i 's/^Release:        .*/Release:        1%{?dist}/' packaging/rpm/phomemo-driver.spec; \
	sed -i "s/^#define PHOMEMO_VERSION \".*\"/#define PHOMEMO_VERSION \"$$new\"/" src/printer-app/phomemo.h; \
	entry="* $$(LC_ALL=C date '+%a %b %d %Y') $$(git config user.name) - $$new-1\n- Release $$new\n"; \
	sed -i "/^%changelog$$/a $$entry" packaging/rpm/phomemo-driver.spec; \
	sed -i "s/^Version: .*/Version: $$new-1/" packaging/debian/phomemo-driver.dsc; \
	{ printf 'phomemo-driver (%s-1) unstable; urgency=medium\n\n  * Release %s\n\n -- %s <%s>  %s\n\n' \
	    "$$new" "$$new" "$$(git config user.name)" "$$(git config user.email)" "$$(LC_ALL=C date -R)"; \
	  cat packaging/debian/debian.changelog; } > packaging/debian/debian.changelog.new; \
	mv packaging/debian/debian.changelog.new packaging/debian/debian.changelog; \
	uv lock; \
	git add src/phomemo/pyproject.toml packaging/rpm/phomemo-driver.spec src/printer-app/phomemo.h uv.lock \
	  packaging/debian/phomemo-driver.dsc packaging/debian/debian.changelog; \
	git commit -q -m "chore: version $$new"; \
	git tag -a "v$$new" -m "phomemo-driver $$new"; \
	echo; \
	echo "Version $$new committed and tagged. To publish (PyPI, GitHub release, COPR, docs):"; \
	echo "  git push && git push origin v$$new"

clean:  ## Remove build output
	rm -rf $(DIST) debian .pybuild
	$(MAKE) -C src/printer-app clean
