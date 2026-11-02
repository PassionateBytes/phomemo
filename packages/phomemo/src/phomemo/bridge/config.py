"""Bridge configuration: TOML files layered under environment overrides."""

import os
import tomllib
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

from phomemo.bridge.server import BridgeConfig

SYSTEM_CONFIG = Path("/etc/phomemo/bridge.toml")
SYSTEM_SOCKET = Path("/run/phomemo/bridge.sock")
SOCKET_NAME = "phomemo-bridge.sock"
SOCKET_ENV = "PHOMEMO_BRIDGE_SOCKET"

_NUMERIC = {
    "hold_seconds",
    "settle_seconds",
    "completion_timeout",
    "drain_seconds",
    "top_margin_mm",
    "bottom_margin_mm",
}
_INTEGER = {"band_height", "dpi", "print_width_px"}
_STRING = {"socket_path", "address", "profile"}
_PRINTER_TABLE = {"address", "profile"}


class ConfigError(ValueError):
    """A configuration file could not be used; the message names file and key."""


def default_paths(env: Mapping[str, str]) -> list[Path]:
    """System file first, then the user's XDG config file.

    Args:
        env: Environment to read ``XDG_CONFIG_HOME`` and ``HOME`` from.

    Returns:
        Candidate paths in override order; missing files are skipped later.
    """
    xdg = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME", "~"), ".config")
    return [SYSTEM_CONFIG, Path(xdg).expanduser() / "phomemo" / "bridge.toml"]


def default_socket(env: Mapping[str, str]) -> Path:
    """Socket under ``XDG_RUNTIME_DIR`` for a user service, else the system path."""
    runtime = env.get("XDG_RUNTIME_DIR")
    return Path(runtime) / SOCKET_NAME if runtime else SYSTEM_SOCKET


def _check(path: Path, key: str, value: Any) -> Any:
    if key in _NUMERIC:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{path}: {key}: expected a number, got {value!r}")
        return float(value)
    if key in _INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{path}: {key}: expected an integer, got {value!r}")
        return value
    if key in _STRING:
        if not isinstance(value, str):
            raise ConfigError(f"{path}: {key}: expected a string, got {value!r}")
        return value
    raise ConfigError(f"{path}: {key}: unknown key")


def _read(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    values: dict[str, Any] = {}
    for key, value in data.items():
        if key == "printer":
            if not isinstance(value, dict):
                raise ConfigError(f"{path}: printer: expected a table")
            for sub, subvalue in value.items():
                if sub not in _PRINTER_TABLE:
                    raise ConfigError(f"{path}: printer.{sub}: unknown key")
                values[sub] = _check(path, sub, subvalue)
            continue
        values[key] = _check(path, key, value)
    return values


def load_config(
    paths: list[Path] | None = None,
    env: Mapping[str, str] = os.environ,
) -> BridgeConfig:
    """Build the bridge configuration.

    Later files override earlier ones; ``PHOMEMO_BRIDGE_SOCKET`` overrides
    the socket path from any file.

    Args:
        paths: Files to read in override order; ``None`` means the system
            file then the user's XDG file.
        env: Environment for the socket override and default locations.

    Returns:
        The merged configuration.

    Raises:
        ConfigError: On an unreadable file, an unknown key, or a wrong type.
    """
    merged: dict[str, Any] = {}
    for path in default_paths(env) if paths is None else paths:
        if path.is_file():
            merged.update(_read(path))
    if SOCKET_ENV in env:
        merged["socket_path"] = env[SOCKET_ENV]
    socket_path = Path(merged.pop("socket_path", default_socket(env)))
    known = {f.name for f in fields(BridgeConfig)}
    return BridgeConfig(
        socket_path=socket_path, **{k: v for k, v in merged.items() if k in known}
    )
