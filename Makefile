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

VERSION   := $(shell sed -n 's/^version = "\(.*\)"/\1/p' packages/phomemo/pyproject.toml)
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
	$(MAKE) -C printer-app

# The Python package goes into its own virtual environment under PREFIX
# (system Pythons refuse direct installs); the units point at PREFIX.
install: build
	$(MAKE) -C printer-app install PREFIX=$(PREFIX) DESTDIR=$(DESTDIR) \
	  UNITDIR=$(UNITDIR) PRESETDIR=$(PRESETDIR)
	$(PYTHON) -m venv --clear $(DESTDIR)$(VENV)
	$(DESTDIR)$(VENV)/bin/pip install --quiet --upgrade pip
	$(DESTDIR)$(VENV)/bin/pip install --quiet ./packages/phomemo
	install -d $(DESTDIR)$(PREFIX)/bin
	ln -sf $(VENV)/bin/phomemo-bridge $(DESTDIR)$(PREFIX)/bin/phomemo-bridge
	install -d $(DESTDIR)$(UNITDIR) $(DESTDIR)$(PRESETDIR) \
	  $(DESTDIR)$(SYSCONF)/phomemo $(DESTDIR)$(SYSCONF)/sysusers.d
	sed 's|/usr/bin/phomemo-bridge|$(PREFIX)/bin/phomemo-bridge|' \
	  packaging/phomemo-bridge.service > $(DESTDIR)$(UNITDIR)/phomemo-bridge.service
	install -m 644 packaging/90-phomemo-bridge.preset $(DESTDIR)$(PRESETDIR)/
	install -m 644 packaging/phomemo.sysusers.conf $(DESTDIR)$(SYSCONF)/sysusers.d/phomemo.conf
	test -e $(DESTDIR)$(SYSCONF)/phomemo/bridge.toml || \
	  install -m 644 packaging/bridge.toml $(DESTDIR)$(SYSCONF)/phomemo/bridge.toml
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
	rm -rf $(VENV)
	systemctl daemon-reload
	@echo "kept: $(SYSCONF)/phomemo/bridge.toml and the printer application's state in /var/lib"

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q
	$(MAKE) -C printer-app test

dist:
	uv build packages/phomemo --out-dir $(DIST)

tarball:
	mkdir -p $(DIST)
	git archive --format=tar.gz --prefix=$(NAME)-$(VERSION)/ \
	  -o $(DIST)/$(NAME)-$(VERSION).tar.gz HEAD

srpm: tarball
	rpmbuild -bs --define "_sourcedir $(CURDIR)/$(DIST)" \
	  --define "_srcrpmdir $(CURDIR)/$(DIST)" packaging/phomemo-driver.spec

bump:
	@test -n "$(VERSION)" || { echo "usage: make bump VERSION=x.y.z"; exit 1; }
	sed -i 's/^version = ".*"/version = "$(VERSION)"/' packages/phomemo/pyproject.toml
	sed -i 's/^Version:        .*/Version:        $(VERSION)/' packaging/phomemo-driver.spec
	sed -i 's/^#define PHOMEMO_VERSION ".*"/#define PHOMEMO_VERSION "$(VERSION)"/' printer-app/phomemo.h
	uv lock
	git add packages/phomemo/pyproject.toml packaging/phomemo-driver.spec printer-app/phomemo.h uv.lock
	git commit -m "chore: version $(VERSION)"

tag:
	git tag -a v$(VERSION) -m "phomemo-driver $(VERSION)"
	@echo "now: git push && git push origin v$(VERSION)"

clean:
	rm -rf $(DIST)
	$(MAKE) -C printer-app clean
