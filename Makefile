# Repository-level targets: checks, release artefacts, version bumps.
#
#   make check              lint, Python tests, C tests
#   make dist               wheel and sdist of the phomemo package into dist/
#   make tarball            source tarball named like the GitHub release archive
#   make srpm               source RPMs for both packages into dist/ (needs rpm-build)
#   make bump VERSION=x.y.z set the version everywhere and commit it
#   make tag                tag the current commit as v$(VERSION)

VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' packages/phomemo/pyproject.toml)
NAME    := phomemo-driver
DIST    := dist

.PHONY: check dist tarball srpm bump tag clean

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
	  --define "_srcrpmdir $(CURDIR)/$(DIST)" packaging/python-phomemo.spec
	rpmbuild -bs --define "_sourcedir $(CURDIR)/$(DIST)" \
	  --define "_srcrpmdir $(CURDIR)/$(DIST)" packaging/phomemo-printer-app.spec

bump:
	@test -n "$(VERSION)" || { echo "usage: make bump VERSION=x.y.z"; exit 1; }
	sed -i 's/^version = ".*"/version = "$(VERSION)"/' packages/phomemo/pyproject.toml
	sed -i 's/^Version:        .*/Version:        $(VERSION)/' packaging/python-phomemo.spec packaging/phomemo-printer-app.spec
	sed -i 's/^#define PHOMEMO_VERSION ".*"/#define PHOMEMO_VERSION "$(VERSION)"/' printer-app/phomemo.h
	uv lock
	git add packages/phomemo/pyproject.toml packaging/python-phomemo.spec packaging/phomemo-printer-app.spec printer-app/phomemo.h uv.lock
	git commit -m "chore: version $(VERSION)"

tag:
	git tag -a v$(VERSION) -m "phomemo-driver $(VERSION)"
	@echo "now: git push && git push origin v$(VERSION)"

clean:
	rm -rf $(DIST)
	$(MAKE) -C printer-app clean
