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
# phomemo-driver.spec builds from this repository, so its source tarball is
# made with git archive. python-bleak.spec is built at the bleak version
# locked in uv.lock (the one the test suite runs against), written into a
# copy of the spec before spectool downloads the sources.

srpm:
	dnf -y install git rpm-build rpmdevtools python3-rpm-macros
	git config --global --add safe.directory "$$PWD"
	mkdir -p "$(outdir)"
	set -e; \
	spec="$(spec)"; \
	case "$$(basename "$$spec")" in \
	  phomemo-driver.spec) \
	    version=$$(sed -n 's/^Version:[[:space:]]*//p' "$$spec"); \
	    git archive --format=tar.gz --prefix=phomemo-driver-$$version/ \
	      -o "$(outdir)/phomemo-driver-$$version.tar.gz" HEAD ;; \
	  python-bleak.spec) \
	    version=$$(python3 -c 'import tomllib; print(next(p["version"] for p in tomllib.load(open("uv.lock", "rb"))["package"] if p["name"] == "bleak"))'); \
	    echo "bleak $$version (from uv.lock)"; \
	    sed "s/^Version:.*/Version:        $$version/" "$$spec" > "$(outdir)/python-bleak.spec"; \
	    spec="$(outdir)/python-bleak.spec"; \
	    spectool -g -C "$(outdir)" "$$spec" ;; \
	  *) spectool -g -C "$(outdir)" "$$spec" ;; \
	esac; \
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" "$$spec"
