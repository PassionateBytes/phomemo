# Builds the source RPM for COPR's "make_srpm" source method. COPR runs
#   make -f .copr/Makefile srpm outdir="<dir>" spec="<path to the spec>"
# in a checkout of the repository, inside a build environment where
# packages may be installed.

srpm:
	dnf -y install git rpm-build
	git config --global --add safe.directory "$$PWD"
	version=$$(sed -n 's/^Version:[[:space:]]*//p' "$(spec)"); \
	mkdir -p "$(outdir)"; \
	git archive --format=tar.gz --prefix=phomemo-driver-$$version/ \
	  -o "$(outdir)/phomemo-driver-$$version.tar.gz" HEAD; \
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" "$(spec)"
