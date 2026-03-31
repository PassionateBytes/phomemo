"""Persistent application configuration.

AppConfig auto-saves to a TOML file whenever any public field changes.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

import tomli_w

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "phomemo-tui" / "config.toml"

_FIELDS = {
    "last_device_address",
    "last_device_name",
    "profile_override",
    "dither",
    "density",
    "fit",
    "feed_lines",
    "multi_page_mode",
    "recent_files",
    "last_directory",
}

_DEFAULTS: dict[str, object] = {
    "last_device_address": None,
    "last_device_name": None,
    "profile_override": None,
    "dither": "floyd_steinberg",
    "density": "medium",
    "fit": "fit_width",
    "feed_lines": 20,
    "multi_page_mode": "auto",
    "recent_files": [],
    "last_directory": None,
}


class AppConfig:
    """Persistent application settings with auto-save on attribute change.

    Args:
        _path: File path for persistence. None disables auto-persist.
        **kwargs: Override any default setting value.
    """

    # Type annotations for static analysis
    last_device_address: str | None
    last_device_name: str | None
    profile_override: str | None
    dither: Literal["floyd_steinberg", "threshold"]
    density: Literal["light", "medium", "dark"]
    fit: Literal["fit_width", "fit_height", "stretch", "original"]
    feed_lines: int
    multi_page_mode: Literal["manual", "auto"]
    recent_files: list[str]
    last_directory: str | None

    def __init__(
        self,
        _path: Path | None = DEFAULT_CONFIG_PATH,
        **kwargs: object,
    ) -> None:
        object.__setattr__(self, "_path", _path)
        object.__setattr__(self, "_initializing", True)
        for name, default in _DEFAULTS.items():
            val = kwargs.get(name, default)
            # Ensure lists are not shared
            object.__setattr__(self, name, list(val) if isinstance(val, list) else val)
        object.__setattr__(self, "_initializing", False)

    def __setattr__(self, name: str, value: object) -> None:
        """Set attribute and auto-persist public config fields.

        Args:
            name: Attribute name.
            value: New value.
        """
        object.__setattr__(self, name, value)
        if not self._initializing and name in _FIELDS:
            self._save()

    def add_recent_file(self, path: str) -> None:
        """Prepend path to recent_files, deduplicate, cap at 5.

        Args:
            path: Absolute path string to prepend.
        """
        files = [f for f in self.recent_files if f != path]
        files.insert(0, path)
        self.recent_files = files[:5]

    def _save(self) -> None:
        """Write current config state to disk."""
        path: Path | None = self._path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, object] = {}
        for name in _FIELDS:
            val = getattr(self, name)
            if val is not None and val != [] and val != "":
                data[name] = val
        with open(path, "wb") as f:
            tomli_w.dump(data, f)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load config from TOML file, returning defaults if missing.

    Args:
        path: Path to the config file.

    Returns:
        Loaded AppConfig bound to the same path for auto-persist.
    """
    if not path.exists():
        return AppConfig(_path=path)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    kwargs = {k: v for k, v in data.items() if k in _FIELDS}
    return AppConfig(_path=path, **kwargs)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Explicitly save config to a TOML file.

    Args:
        config: The AppConfig to persist.
        path: Override path. Defaults to config's bound path.
    """
    if path is not None:
        object.__setattr__(config, "_path", path)
    config._save()
