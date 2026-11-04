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

# Build and install the whole printer driver from a fresh clone:
#
#   sudo make               build everything and install it as system services
#                           (PREFIX=/usr/local; services enabled and started)
#   make build              build only (the printer application)
#   sudo make uninstall     remove what install put in place
#
# Development and release targets:
#
#   make check              lint, Python tests, C tests (what CI runs)
#   make dist               wheel and sdist of the phomemo package into dist/
#   make tarball            source tarball named like the GitHub release archive
#   make srpm               source RPM into dist/ (needs rpm-build)
#   make bump VERSION=x.y.z set the version everywhere and commit it
#   make tag                tag the current commit as v$(VERSION)

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

.PHONY: build install uninstall check dist tarball srpm bump tag clean

build:
	$(MAKE) -C src/printer-app PREFIX=$(PREFIX)

# The Python package goes into its own virtual environment under PREFIX
# (system Pythons refuse direct installs); the units point at PREFIX.
install: build
	$(MAKE) -C src/printer-app install PREFIX=$(PREFIX) DESTDIR=$(DESTDIR) \
	  UNITDIR=$(UNITDIR) PRESETDIR=$(PRESETDIR)
	$(PYTHON) -m venv --clear $(DESTDIR)$(VENV)
	$(DESTDIR)$(VENV)/bin/pip install --quiet --upgrade pip
	$(DESTDIR)$(VENV)/bin/pip install --quiet ./src/phomemo
	install -d $(DESTDIR)$(PREFIX)/share/phomemo/models
	cp -a src/models/. $(DESTDIR)$(PREFIX)/share/phomemo/models/
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
	@echo "installed; printer application at http://localhost:8000/"
endif

uninstall:
	-systemctl disable --now phomemo-printer-app phomemo-bridge
	rm -f $(UNITDIR)/phomemo-bridge.service $(UNITDIR)/phomemo-printer-app.service
	rm -f $(PRESETDIR)/90-phomemo-bridge.preset $(PRESETDIR)/90-phomemo-printer-app.preset
	rm -f $(SYSCONF)/sysusers.d/phomemo.conf
	rm -f $(PREFIX)/bin/phomemo-bridge $(PREFIX)/bin/phomemo-printer-app
	rm -rf $(VENV) $(PREFIX)/share/phomemo
	systemctl daemon-reload
	@echo "kept: $(SYSCONF)/phomemo/bridge.toml, $(SYSCONF)/phomemo-printer-app.conf and the printer application's state in /var/lib"

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q src/phomemo/tests
	$(MAKE) -C src/printer-app test

dist:
	uv build src/phomemo --out-dir $(DIST)

tarball:
	mkdir -p $(DIST)
	git archive --format=tar.gz --prefix=$(NAME)-$(VERSION)/ \
	  -o $(DIST)/$(NAME)-$(VERSION).tar.gz HEAD

srpm: tarball
	rpmbuild -bs --define "_sourcedir $(CURDIR)/$(DIST)" \
	  --define "_srcrpmdir $(CURDIR)/$(DIST)" packaging/rpm/phomemo-driver.spec

bump:
	@test -n "$(VERSION)" || { echo "usage: make bump VERSION=x.y.z"; exit 1; }
	sed -i 's/^version = ".*"/version = "$(VERSION)"/' src/phomemo/pyproject.toml
	sed -i 's/^Version:        .*/Version:        $(VERSION)/' packaging/rpm/phomemo-driver.spec
	sed -i 's/^#define PHOMEMO_VERSION ".*"/#define PHOMEMO_VERSION "$(VERSION)"/' src/printer-app/phomemo.h
	uv lock
	git add src/phomemo/pyproject.toml packaging/rpm/phomemo-driver.spec src/printer-app/phomemo.h uv.lock
	git commit -m "chore: version $(VERSION)"

tag:
	git tag -a v$(VERSION) -m "phomemo-driver $(VERSION)"
	@echo "now: git push && git push origin v$(VERSION)"

clean:
	rm -rf $(DIST)
	$(MAKE) -C src/printer-app clean
