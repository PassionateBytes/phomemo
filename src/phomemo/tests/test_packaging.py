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


def test_make_install_installs_no_model_directory() -> None:
    makefile = (REPO / "Makefile").read_text()
    assert "phomemo/models" not in makefile


def test_package_metadata_marks_the_beta_and_links_the_docs() -> None:
    import tomllib

    project = tomllib.loads((REPO / "src" / "phomemo" / "pyproject.toml").read_text())[
        "project"
    ]
    assert "Development Status :: 4 - Beta" in project["classifiers"]
    assert project["urls"]["Documentation"].startswith(
        "https://passionatebytes.github.io/phomemo-driver"
    )


def test_release_resets_the_rpm_release_and_starts_the_changelog() -> None:
    makefile = (REPO / "Makefile").read_text()
    release = makefile.split("\nrelease:")[1].split("\nclean:")[0]
    assert "s/^Release:        .*/Release:        1%{?dist}/" in release
    assert "%changelog" in release


def test_spec_changelog_starts_with_the_current_version() -> None:
    spec = (REPO / "packaging" / "rpm" / "phomemo-driver.spec").read_text()
    version = re.search(r"^Version:\s+(\S+)", spec, re.M).group(1)
    release = re.search(r"^Release:\s+(\d+)", spec, re.M).group(1)
    first_entry = spec.split("%changelog\n")[1].splitlines()[0]
    assert first_entry.endswith(f" - {version}-{release}")


DEBIAN = REPO / "packaging" / "debian"


def _project_version() -> str:
    import tomllib

    pyproject = (REPO / "src" / "phomemo" / "pyproject.toml").read_text()
    return tomllib.loads(pyproject)["project"]["version"]


def _control_field(text: str, field: str) -> str:
    """Returns a multi-line field of a Debian control file, folded to one line."""
    match = re.search(rf"^{field}:(.*(?:\n[ \t].*)*)", text, re.M)
    assert match, field
    return " ".join(match.group(1).split())


def test_debian_changelog_and_dsc_carry_the_current_version() -> None:
    version = _project_version()
    changelog = (DEBIAN / "debian.changelog").read_text()
    assert changelog.startswith(f"phomemo-driver ({version}-1) ")
    dsc = (DEBIAN / "phomemo-driver.dsc").read_text()
    assert re.search(rf"^Version: {re.escape(version)}-1$", dsc, re.M)


def test_dsc_mirrors_the_control_file() -> None:
    control = (DEBIAN / "debian.control").read_text()
    dsc = (DEBIAN / "phomemo-driver.dsc").read_text()
    for field in ("Source", "Maintainer", "Standards-Version", "Build-Depends"):
        assert _control_field(dsc, field) == _control_field(control, field), field
    packages = re.findall(r"^Package: (\S+)", control, re.M)
    assert _control_field(dsc, "Binary").split(", ") == packages
    assert re.search(r"^Format: 3\.0 \(quilt\)$", dsc, re.M)


def test_release_bumps_the_debian_files_too() -> None:
    makefile = (REPO / "Makefile").read_text()
    release = makefile.split("\nrelease:")[1].split("\nclean:")[0]
    assert "packaging/debian/phomemo-driver.dsc" in release
    assert "packaging/debian/debian.changelog" in release


def test_obs_service_extracts_every_debian_file() -> None:
    service = (REPO / "packaging" / "obs" / "phomemo-driver" / "_service").read_text()
    extracted = set(re.findall(r'<param name="extract">(.*?)</param>', service))
    expected = {
        f"packaging/debian/{path.name}" for path in DEBIAN.iterdir() if path.is_file()
    }
    expected.add("packaging/rpm/phomemo-driver.spec")
    assert extracted == expected


def test_python_bleak_spec_version_is_inside_the_library_range() -> None:
    import tomllib

    spec = (REPO / "packaging" / "rpm" / "python-bleak.spec").read_text()
    version = re.search(r"^Version:\s+(\S+)", spec, re.M).group(1)
    pyproject = tomllib.loads((REPO / "src" / "phomemo" / "pyproject.toml").read_text())
    requirement = next(
        d for d in pyproject["project"]["dependencies"] if d.startswith("bleak")
    )
    low, high = re.search(r">=([\d.]+),<([\d.]+)", requirement).groups()
    as_tuple = lambda v: tuple(int(part) for part in v.split("."))  # noqa: E731
    assert as_tuple(low) <= as_tuple(version) < as_tuple(high)
