"""Tests for AppConfig persistence."""

from pathlib import Path

import pytest

from phomemo_tui.config import AppConfig, load_config, save_config


def test_defaults(tmp_path: Path) -> None:
    cfg = AppConfig(_path=None)
    assert cfg.last_device_address is None
    assert cfg.profile_override is None
    assert cfg.dither == "floyd_steinberg"
    assert cfg.density == "medium"
    assert cfg.fit == "fit_width"
    assert cfg.feed_lines == 20
    assert cfg.multi_page_mode == "auto"
    assert cfg.recent_files == []
    assert cfg.last_directory is None


def test_auto_save_on_setattr(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig(_path=path)
    cfg.last_device_address = "AA:BB:CC:DD:EE:FF"
    assert path.exists()


def test_no_save_when_path_none() -> None:
    cfg = AppConfig(_path=None)
    cfg.last_device_address = "AA:BB:CC:DD:EE:FF"
    # No exception raised


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.dither == "floyd_steinberg"


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig(_path=path)
    cfg.last_device_address = "AA:BB:CC:DD:EE:FF"
    cfg.dither = "threshold"
    cfg.recent_files = ["/tmp/a.png", "/tmp/b.pdf"]

    loaded = load_config(path)
    assert loaded.last_device_address == "AA:BB:CC:DD:EE:FF"
    assert loaded.dither == "threshold"
    assert loaded.recent_files == ["/tmp/a.png", "/tmp/b.pdf"]


def test_recent_files_capped_at_5(tmp_path: Path) -> None:
    cfg = AppConfig(_path=None)
    cfg.add_recent_file("/a.png")
    cfg.add_recent_file("/b.png")
    cfg.add_recent_file("/c.png")
    cfg.add_recent_file("/d.png")
    cfg.add_recent_file("/e.png")
    cfg.add_recent_file("/f.png")
    assert len(cfg.recent_files) == 5
    assert cfg.recent_files[0] == "/f.png"


def test_add_recent_file_deduplicates(tmp_path: Path) -> None:
    cfg = AppConfig(_path=None)
    cfg.add_recent_file("/a.png")
    cfg.add_recent_file("/b.png")
    cfg.add_recent_file("/a.png")
    assert cfg.recent_files == ["/a.png", "/b.png"]
    assert len(cfg.recent_files) == 2
