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

"""Tests for docs/publish.py, which assembles the versioned docs site."""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("packaging")

_SCRIPT = Path(__file__).parents[3] / "docs" / "publish.py"
_spec = importlib.util.spec_from_file_location("docs_publish", _SCRIPT)
publish_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(publish_module)
publish = publish_module.publish


def _build(root: Path, label: str) -> Path:
    """Fake Sphinx output with two pages that name the build."""
    build = root / f"build-{label}"
    build.mkdir()
    (build / "index.html").write_text(label)
    (build / "library.html").write_text(label)
    return build


def _versions(site: Path) -> dict:
    return json.loads((site / "versions.json").read_text())


def test_latest_only_points_root_to_latest(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    publish(site, _build(tmp_path, "main"), "latest")

    assert _versions(site) == {"stable": None, "versions": ["latest"]}
    assert not (site / "stable").exists()
    assert "latest/library.html" in (site / "library.html").read_text()
    assert (site / ".nojekyll").exists()


def test_newest_release_becomes_stable(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    publish(site, _build(tmp_path, "main"), "latest")
    publish(site, _build(tmp_path, "v030"), "0.3.0")
    publish(site, _build(tmp_path, "v100"), "1.0.0")
    publish(site, _build(tmp_path, "v031"), "0.3.1")

    assert _versions(site) == {
        "stable": "1.0.0",
        "versions": ["latest", "1.0.0", "0.3.1", "0.3.0"],
    }
    assert (site / "stable" / "index.html").read_text() == "v100"
    assert "stable/index.html" in (site / "index.html").read_text()


def test_prerelease_is_not_stable_once_a_final_release_exists(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    publish(site, _build(tmp_path, "v100"), "1.0.0")
    publish(site, _build(tmp_path, "v110rc1"), "1.1.0rc1")

    assert _versions(site)["stable"] == "1.0.0"
    assert (site / "stable" / "index.html").read_text() == "v100"


def test_republish_replaces_the_version(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    old = _build(tmp_path, "old")
    (old / "gone.html").write_text("old")
    publish(site, old, "latest")
    publish(site, _build(tmp_path, "new"), "latest")

    assert not (site / "latest" / "gone.html").exists()
    assert not (site / "gone.html").exists()
    assert (site / "latest" / "index.html").read_text() == "new"


def test_rejects_other_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        publish(tmp_path, _build(tmp_path, "x"), "feature-branch")
