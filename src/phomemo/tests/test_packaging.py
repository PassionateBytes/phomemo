# This file is part of phomemo.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with phomemo.  If not, see <https://www.gnu.org/licenses/>.

"""Tests for the shipped configuration files and their installation."""

import re
from pathlib import Path

REPO = Path(__file__).parents[3]
APP_CONF = REPO / "packaging" / "config" / "phomemo-printer-app.conf"

# Options PAPPL's default system reads from its configuration files.
PAPPL_OPTIONS = {
    "admin-group",
    "auth-service",
    "listen-hostname",
    "log-file",
    "log-level",
    "private-server",
    "server-hostname",
    "server-options",
    "server-port",
    "spool-directory",
}


def _settings(text: str, commented: bool) -> list[tuple[str, str]]:
    pattern = r"^#?([a-z-]+)=(.*)$" if commented else r"^([a-z-]+)=(.*)$"
    return re.findall(pattern, text, re.M)


def test_printer_app_conf_names_only_options_pappl_reads() -> None:
    text = APP_CONF.read_text()
    names = {name for name, _ in _settings(text, commented=True)}
    assert names <= PAPPL_OPTIONS, names - PAPPL_OPTIONS
    assert {"server-port", "log-level"} <= names


def test_printer_app_conf_sets_only_the_log_level() -> None:
    assert _settings(APP_CONF.read_text(), commented=False) == [("log-level", "info")]


def test_unit_leaves_the_log_level_to_the_conf_file() -> None:
    unit = (REPO / "packaging" / "systemd" / "phomemo-printer-app.service").read_text()
    lines = unit.splitlines()
    exec_start = next(line for line in lines if line.startswith("ExecStart="))
    assert "log-file=-" in exec_start
    assert "log-level" not in exec_start


def test_spec_and_makefile_install_the_conf_file() -> None:
    spec = (REPO / "packaging" / "rpm" / "phomemo-driver.spec").read_text()
    assert "%config(noreplace) %{_sysconfdir}/phomemo-printer-app.conf" in spec
    makefile = (REPO / "Makefile").read_text()
    assert "packaging/config/phomemo-printer-app.conf" in makefile


def test_wheel_and_sdist_carry_the_model_manifests(tmp_path: Path) -> None:
    import subprocess
    import tarfile
    import zipfile

    subprocess.run(
        ["uv", "build", str(REPO / "src" / "phomemo"), "--out-dir", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    wheel = next(tmp_path.glob("phomemo-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    for name in ("model.json", "icon-48.png", "icon-128.png", "icon-512.png"):
        assert f"phomemo/models/m08f/{name}" in names
    sdist = next(tmp_path.glob("phomemo-*.tar.gz"))
    with tarfile.open(sdist) as archive:
        members = archive.getnames()
    assert any(m.endswith("src/phomemo/models/m08f/model.json") for m in members)


def test_spec_installs_no_model_directory() -> None:
    spec = (REPO / "packaging" / "rpm" / "phomemo-driver.spec").read_text()
    assert "phomemo/models" not in spec


def test_spec_declares_the_bundled_cjson() -> None:
    spec = (REPO / "packaging" / "rpm" / "phomemo-driver.spec").read_text()
    header = (REPO / "src" / "printer-app" / "third_party" / "cJSON.h").read_text()
    version = ".".join(
        re.search(rf"#define CJSON_VERSION_{part} (\d+)", header).group(1)
        for part in ("MAJOR", "MINOR", "PATCH")
    )
    assert f"Provides:       bundled(cjson) = {version}" in spec


def test_make_install_installs_no_model_directory() -> None:
    makefile = (REPO / "Makefile").read_text()
    assert "phomemo/models" not in makefile
