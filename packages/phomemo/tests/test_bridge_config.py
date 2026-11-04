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

"""Tests for bridge configuration loading."""

from pathlib import Path

import phomemo.bridge.config as config_module
import pytest
from phomemo.bridge.config import ConfigError, load_config


def test_config_defaults_without_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A system bridge running on the test machine must not change the default.
    monkeypatch.setattr(config_module, "SYSTEM_SOCKET", tmp_path / "absent.sock")
    config = load_config(paths=[], env={"XDG_RUNTIME_DIR": "/run/user/1000"})
    assert config.socket_path == Path("/run/user/1000/phomemo-bridge.sock")
    assert config.auto_off_minutes is None
    assert config.profile == "M08F-A4"
    assert config.hold_seconds == 300.0
    assert config.settle_seconds == 3.0
    assert config.completion_timeout == 300.0
    assert config.band_height is None


def test_config_system_socket_without_runtime_dir() -> None:
    config = load_config(paths=[], env={})
    assert config.socket_path == Path("/run/phomemo/bridge.sock")


def test_config_user_file_overrides_system_file(tmp_path: Path) -> None:
    system = tmp_path / "system.toml"
    user = tmp_path / "user.toml"
    system.write_text(
        "hold_seconds = 10\nband_height = 64\n[printer]\nauto_off_minutes = 10\n"
    )
    user.write_text("hold_seconds = 20\n")
    config = load_config(paths=[system, user], env={})
    assert config.hold_seconds == 20.0
    assert config.band_height == 64
    assert config.auto_off_minutes == 10


def test_config_env_socket_override(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('socket_path = "/tmp/from-file.sock"\n')
    config = load_config(
        paths=[user], env={"PHOMEMO_BRIDGE_SOCKET": "/tmp/from-env.sock"}
    )
    assert config.socket_path == Path("/tmp/from-env.sock")


@pytest.mark.parametrize(
    ("text", "key", "problem"),
    [
        ("hold_secs = 5\n", "hold_secs", "unknown key"),
        ('completion_timeout = "soon"\n', "completion_timeout", "expected a number"),
        ("hold_seconds = -1\n", "hold_seconds", "must not be negative"),
        ("band_height = 0\n", "band_height", "must be positive"),
        ('[printer]\nprofile = "nope"\n', "printer.profile", "unknown profile"),
        (
            '[printer]\naddress = "AA:BB:CC:DD:EE:FF"\n',
            "printer.address",
            "unknown key",
        ),
        ("printer = 3\n", "printer", "expected a table"),
    ],
)
def test_config_logs_an_invalid_entry_and_ignores_it(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    text: str,
    key: str,
    problem: str,
) -> None:
    user = tmp_path / "user.toml"
    user.write_text("settle_seconds = 9\n" + text)
    with caplog.at_level("WARNING"):
        config = load_config(paths=[user], env={})
    assert f"user.toml: {key}: {problem}" in caplog.text
    assert "ignored" in caplog.text
    assert config.settle_seconds == 9.0
    assert config.hold_seconds == 300.0
    assert config.profile == "M08F-A4"
    assert config.band_height is None


def test_config_unreadable_file_is_logged_and_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text("hold_seconds = = 5\n")
    good = tmp_path / "good.toml"
    good.write_text("settle_seconds = 9\n")
    with caplog.at_level("WARNING"):
        config = load_config(paths=[broken, good], env={})
    assert "broken.toml" in caplog.text
    assert config.settle_seconds == 9.0


def test_config_missing_file_is_skipped(tmp_path: Path) -> None:
    config = load_config(paths=[tmp_path / "absent.toml"], env={})
    assert config.hold_seconds == 300.0


def test_config_explicit_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="absent.toml"):
        load_config(paths=[tmp_path / "absent.toml"], env={}, require_files=True)


def test_default_socket_prefers_the_system_bridge_when_present(tmp_path: Path) -> None:
    from phomemo.bridge.config import default_socket

    system = tmp_path / "bridge.sock"
    env = {"XDG_RUNTIME_DIR": str(tmp_path / "run")}
    assert default_socket(env, system) == tmp_path / "run" / "phomemo-bridge.sock"
    system.touch()
    assert default_socket(env, system) == system


def test_config_without_auto_off_leaves_the_printer_alone() -> None:
    assert load_config(paths=[], env={}).auto_off_minutes is None


def test_packaged_config_enforces_five_minutes() -> None:
    packaged = Path(__file__).parents[3] / "packaging" / "config" / "bridge.toml"
    assert load_config(paths=[packaged], env={}).auto_off_minutes == 5


@pytest.mark.parametrize("minutes", [0, 15, 60, 1275])
def test_config_accepts_auto_off_in_five_minute_steps(
    tmp_path: Path, minutes: int
) -> None:
    path = tmp_path / "bridge.toml"
    path.write_text(f"[printer]\nauto_off_minutes = {minutes}\n")
    assert load_config(paths=[path], env={}).auto_off_minutes == minutes


@pytest.mark.parametrize(
    ("value", "expected"),
    [("7", 5), ("8", 10), ("7.5", 10), ("10.0", 10), ("2", 5), ("1280", 1275)],
)
def test_config_auto_off_number_snaps_to_the_nearest_step(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: str, expected: int
) -> None:
    path = tmp_path / "bridge.toml"
    path.write_text(f"[printer]\nauto_off_minutes = {value}\n")
    with caplog.at_level("WARNING"):
        config = load_config(paths=[path], env={})
    assert config.auto_off_minutes == expected
    assert f"printer.auto_off_minutes: {value} is not a valid timer" in caplog.text
    assert f"using {expected}" in caplog.text


@pytest.mark.parametrize("value", ['"ten"', "true", "-5"])
def test_config_auto_off_that_is_no_timer_is_logged_and_not_enforced(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: str
) -> None:
    path = tmp_path / "bridge.toml"
    path.write_text(f"[printer]\nauto_off_minutes = {value}\n")
    with caplog.at_level("WARNING"):
        config = load_config(paths=[path], env={})
    assert config.auto_off_minutes is None
    assert "printer.auto_off_minutes" in caplog.text
    assert "ignored" in caplog.text
