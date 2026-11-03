"""Sphinx configuration for the phomemo-driver documentation site."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "phomemo" / "src"))

project = "phomemo-driver"
author = "Paul Bütof"
copyright = "2026, Paul Bütof"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 3

autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

exclude_patterns = ["_build", "superpowers", "reports"]
# The included READMEs link to files by repository path.
suppress_warnings = ["myst.xref_missing"]

html_theme = "furo"
html_title = "phomemo-driver"
html_static_path: list[str] = []
