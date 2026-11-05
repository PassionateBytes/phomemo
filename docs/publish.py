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

"""Put one documentation build into the versioned site.

The site holds one directory per version: ``latest/`` (built from main),
one per release (``0.3.0/``, ...) and ``stable/``, a copy of the newest
release. Its root carries ``versions.json`` (read by the version menu),
``index.html`` and one redirect per top-level page, all pointing into
``stable/`` (``latest/`` until there is a release), so unversioned links
keep working.

Usage::

    python docs/publish.py SITE_DIR BUILD_DIR VERSION
"""

import json
import shutil
import sys
from html import escape
from pathlib import Path

from packaging.version import InvalidVersion, Version

LATEST = "latest"
STABLE = "stable"

REDIRECT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redirecting</title>
<meta http-equiv="refresh" content="0; url={url}">
<link rel="canonical" href="{url}">
</head>
<body><p>Moved to <a href="{url}">{url}</a>.</p></body>
</html>
"""


def _release(name: str) -> Version | None:
    """Parse a directory name as a release version.

    Args:
        name: Directory name in the site root.

    Returns:
        The version, or None when the name is not a release.
    """
    try:
        return Version(name)
    except InvalidVersion:
        return None


def _replace(source: Path, target: Path) -> None:
    """Replace ``target`` with a copy of ``source``.

    Args:
        source: Directory to copy.
        target: Directory to (re)create.
    """
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def publish(site: Path, build: Path, version: str) -> None:
    """Copy a build into the site and regenerate the root files.

    Args:
        site: Checkout of the site (the ``gh-pages`` branch).
        build: Sphinx HTML output of one version.
        version: ``latest`` or a release number such as ``0.3.0``.

    Raises:
        ValueError: The version is neither ``latest`` nor a release number.
    """
    if version != LATEST and _release(version) is None:
        raise ValueError(f"not a version: {version!r}")

    _replace(build, site / version)

    releases = sorted(
        (v for p in site.iterdir() if p.is_dir() and (v := _release(p.name))),
        reverse=True,
    )
    final = [v for v in releases if not v.is_prerelease] or releases
    stable = str(max(final)) if final else None
    if stable:
        _replace(site / stable, site / STABLE)

    names = [str(v) for v in releases]
    if (site / LATEST).is_dir():
        names.insert(0, LATEST)
    (site / "versions.json").write_text(
        json.dumps({"stable": stable, "versions": names}, indent=2) + "\n"
    )

    home = STABLE if stable else LATEST
    for page in site.glob("*.html"):
        page.unlink()
    for page in (site / home).glob("*.html"):
        url = escape(f"{home}/{page.name}")
        (site / page.name).write_text(REDIRECT.format(url=url))
    (site / ".nojekyll").touch()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    publish(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
