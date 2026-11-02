"""Tests for bridge configuration loading."""

from pathlib import Path

import pytest
from phomemo.bridge.config import ConfigError, load_config


def test_config_defaults_without_files() -> None:
    config = load_config(paths=[], env={"XDG_RUNTIME_DIR": "/run/user/1000"})
    assert config.socket_path == Path("/run/user/1000/phomemo-bridge.sock")
    assert config.address is None
    assert config.profile == "M08F-A4"
    assert config.hold_seconds == 120.0
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
        'hold_seconds = 10\nband_height = 64\n[printer]\naddress = "AA:BB"\n'
    )
    user.write_text("hold_seconds = 20\n")
    config = load_config(paths=[system, user], env={})
    assert config.hold_seconds == 20.0
    assert config.band_height == 64
    assert config.address == "AA:BB"


def test_config_env_socket_override(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('socket_path = "/tmp/from-file.sock"\n')
    config = load_config(
        paths=[user], env={"PHOMEMO_BRIDGE_SOCKET": "/tmp/from-env.sock"}
    )
    assert config.socket_path == Path("/tmp/from-env.sock")


def test_config_rejects_unknown_key(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text("hold_secs = 5\n")
    with pytest.raises(ConfigError, match=r"user\.toml: hold_secs"):
        load_config(paths=[user], env={})


def test_config_rejects_non_numeric_timeout(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('completion_timeout = "soon"\n')
    with pytest.raises(ConfigError, match="completion_timeout"):
        load_config(paths=[user], env={})


def test_config_missing_file_is_skipped(tmp_path: Path) -> None:
    config = load_config(paths=[tmp_path / "absent.toml"], env={})
    assert config.hold_seconds == 120.0


def test_config_rejects_non_positive_band_height(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text("band_height = 0\n")
    with pytest.raises(ConfigError, match="band_height"):
        load_config(paths=[user], env={})


def test_config_rejects_negative_timeout(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text("hold_seconds = -1\n")
    with pytest.raises(ConfigError, match="hold_seconds"):
        load_config(paths=[user], env={})


def test_config_rejects_unknown_profile(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('[printer]\nprofile = "nope"\n')
    with pytest.raises(ConfigError, match="profile"):
        load_config(paths=[user], env={})


def test_config_explicit_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="absent.toml"):
        load_config(paths=[tmp_path / "absent.toml"], env={}, require_files=True)
