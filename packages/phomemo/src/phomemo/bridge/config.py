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

"""Bridge configuration: TOML files layered under environment overrides."""

import logging
import os
import tomllib
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

import phomemo.profiles  # noqa: F401, registers the built-in profiles
from phomemo.bridge.server import BridgeConfig
from phomemo.printer import AUTO_OFF_MAX_MINUTES
from phomemo.registry import list_profiles

logger = logging.getLogger(__name__)

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
_PRINTER_TABLE = {"address", "profile", "auto_off_minutes"}
AUTO_OFF_DEFAULT = 5
AUTO_OFF_MAX = AUTO_OFF_MAX_MINUTES


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


def default_socket(env: Mapping[str, str], system_socket: Path | None = None) -> Path:
    """The system bridge's socket when it exists, else one under ``XDG_RUNTIME_DIR``.

    The system service listens at ``/run/phomemo/bridge.sock``; a user's
    command line talks to it when it is there. Without it (development, a
    user service) the socket lives in the user's runtime directory.

    Args:
        env: Environment providing ``XDG_RUNTIME_DIR``.
        system_socket: The system bridge's socket; ``SYSTEM_SOCKET`` by default.

    Returns:
        The socket path to listen on or connect to.
    """
    system_socket = system_socket or SYSTEM_SOCKET
    if system_socket.exists():
        return system_socket
    runtime = env.get("XDG_RUNTIME_DIR")
    return Path(runtime) / SOCKET_NAME if runtime else system_socket


def _auto_off(path: Path, value: Any) -> int:
    valid = (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= AUTO_OFF_MAX
        and value % 5 == 0
    )
    if valid:
        return value
    logger.warning(
        "%s: auto_off_minutes: %r is not a multiple of 5 between 0 and %d, using %d",
        path,
        value,
        AUTO_OFF_MAX,
        AUTO_OFF_DEFAULT,
    )
    return AUTO_OFF_DEFAULT


def _check(path: Path, key: str, value: Any) -> Any:
    if key == "auto_off_minutes":
        return _auto_off(path, value)
    if key in _NUMERIC:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{path}: {key}: expected a number, got {value!r}")
        if value < 0:
            raise ConfigError(f"{path}: {key}: must not be negative, got {value!r}")
        return float(value)
    if key in _INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{path}: {key}: expected an integer, got {value!r}")
        if value <= 0:
            raise ConfigError(f"{path}: {key}: must be positive, got {value!r}")
        return value
    if key in _STRING:
        if not isinstance(value, str):
            raise ConfigError(f"{path}: {key}: expected a string, got {value!r}")
        if key == "profile" and value not in list_profiles():
            raise ConfigError(
                f"{path}: {key}: unknown profile {value!r}, "
                f"known: {', '.join(list_profiles())}"
            )
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
    require_files: bool = False,
) -> BridgeConfig:
    """Build the bridge configuration.

    Later files override earlier ones; ``PHOMEMO_BRIDGE_SOCKET`` overrides
    the socket path from any file.

    Args:
        paths: Files to read in override order; ``None`` means the system
            file then the user's XDG file.
        env: Environment for the socket override and default locations.
        require_files: Treat a missing file in ``paths`` as an error (for
            a path the user named explicitly).

    Returns:
        The merged configuration.

    Raises:
        ConfigError: On a missing explicit file, an unreadable file, an
            unknown key, a wrong type, or an out-of-range value.
    """
    merged: dict[str, Any] = {}
    for path in default_paths(env) if paths is None else paths:
        if path.is_file():
            merged.update(_read(path))
        elif require_files:
            raise ConfigError(f"{path}: no such file")
    if SOCKET_ENV in env:
        merged["socket_path"] = env[SOCKET_ENV]
    socket_path = Path(merged.pop("socket_path", default_socket(env)))
    known = {f.name for f in fields(BridgeConfig)}
    return BridgeConfig(
        socket_path=socket_path, **{k: v for k, v in merged.items() if k in known}
    )
