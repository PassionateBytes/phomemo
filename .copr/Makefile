# Builds a source RPM for COPR's "make_srpm" source method. COPR runs
#   make -f .copr/Makefile srpm outdir="<dir>" spec="<path to the spec>"
# in a checkout of the repository, inside a build environment where
# packages may be installed.
#
# phomemo-driver.spec builds from this repository, so its source tarball is
# made with git archive; any other spec (python-bleak.spec) has remote
# sources, which spectool downloads.

srpm:
	dnf -y install git rpm-build rpmdevtools python3-rpm-macros
	git config --global --add safe.directory "$$PWD"
	mkdir -p "$(outdir)"
	if [ "$$(basename "$(spec)")" = phomemo-driver.spec ]; then \
	  version=$$(sed -n 's/^Version:[[:space:]]*//p' "$(spec)"); \
	  git archive --format=tar.gz --prefix=phomemo-driver-$$version/ \
	    -o "$(outdir)/phomemo-driver-$$version.tar.gz" HEAD; \
	else \
	  spectool -g -C "$(outdir)" "$(spec)"; \
	fi
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" "$(spec)"
