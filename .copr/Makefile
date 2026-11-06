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

# Builds a source RPM for COPR's "make_srpm" source method. COPR runs
#   make -f .copr/Makefile srpm outdir="<dir>" spec="<path to the spec>"
# in a checkout of the repository, inside a build environment where
# packages may be installed and the network is reachable.
#
# phomemo-driver.spec builds the newest release: the highest v* tag, with
# the spec and the source tarball (git archive) taken from that tag, so a
# build never ships unreleased code from main. python-bleak.spec is built
# at the version the spec names (kept current by Renovate); spectool
# downloads the sources.

srpm:
	dnf -y install git rpm-build rpmdevtools python3-rpm-macros
	git config --global --add safe.directory "$$PWD"
	mkdir -p "$(outdir)"
	set -e; \
	spec="$(spec)"; \
	case "$$(basename "$$spec")" in \
	  phomemo-driver.spec) \
	    git fetch --quiet --tags origin 2>/dev/null || true; \
	    tag=$$(git tag --list 'v*' --sort=-version:refname | head -n 1); \
	    test -n "$$tag" || { echo "no v* tag to build"; exit 1; }; \
	    echo "phomemo-driver $$tag (newest tag)"; \
	    path=$$(realpath --relative-to="$$(git rev-parse --show-toplevel)" "$$spec"); \
	    git show "$$tag:$$path" > "$(outdir)/phomemo-driver.spec"; \
	    spec="$(outdir)/phomemo-driver.spec"; \
	    version=$$(sed -n 's/^Version:[[:space:]]*//p' "$$spec"); \
	    git archive --format=tar.gz --prefix=phomemo-driver-$$version/ \
	      -o "$(outdir)/phomemo-driver-$$version.tar.gz" "$$tag" ;; \
	  *) cp "$$spec" "$(outdir)/"; spec="$(outdir)/$$(basename "$$spec")"; \
	     spectool -g -C "$(outdir)" "$$spec" ;; \
	esac; \
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" "$$spec"
