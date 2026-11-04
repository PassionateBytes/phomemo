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

"""Built-in profiles, loaded from the model descriptions on import.

Each model is a directory named after its identifier, holding ``model.json``
and the model's icons. The printer application reads the same directories.
"""

import logging
import os
from pathlib import Path

from phomemo.registry import load_description, register_profile

logger = logging.getLogger(__name__)

MODELS_ENV = "PHOMEMO_MODELS_DIR"


def models_dir() -> Path:
    """Where the model descriptions are read from.

    ``PHOMEMO_MODELS_DIR`` when set; otherwise the copy installed with the
    package, else the descriptions of a source checkout.

    Returns:
        The first of these that exists, else the installed location.
    """
    if env := os.environ.get(MODELS_ENV):
        return Path(env)
    here = Path(__file__).resolve()
    installed = here.parents[1] / "models"  # phomemo/models in the package
    checkout = here.parents[4] / "models"  # src/models next to the project
    return next((p for p in (installed, checkout) if p.is_dir()), installed)


def _register_builtin() -> None:
    root = models_dir()
    if not root.is_dir():
        logger.warning("No model descriptions at %s", root)
        return
    for model_dir in sorted(p for p in root.iterdir() if (p / "model.json").is_file()):
        register_profile(load_description(model_dir))


_register_builtin()
