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

"""Build hook: ships the shared model descriptions as package data.

The descriptions live next to this project in the repository (``../models``),
shared with the printer application. Built from the repository, the wheel
gets them as ``phomemo/models`` and the sdist as ``src/phomemo/models``, so a
wheel built from that sdist finds them inside the package.
"""

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class ModelsBuildHook(BuildHookInterface):
    """Adds the repository's model descriptions to wheel and sdist."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        shared = Path(self.root).parent / "models"
        if version == "editable" or not shared.is_dir():
            return
        target = (
            "phomemo/models" if self.target_name == "wheel" else "src/phomemo/models"
        )
        build_data["force_include"][str(shared)] = target
