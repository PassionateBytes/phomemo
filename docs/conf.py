# This file is part of phomemo-driver.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo-driver is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo-driver is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with phomemo-driver.  If not, see <https://www.gnu.org/licenses/>.

"""Sphinx configuration for the phomemo-driver documentation site."""

project = "phomemo-driver"
author = "Paul Bütof"
copyright = (
    "2026, Paul Bütof, Passionate Bytes Solutions. Documentation licensed under "
    "CC BY-SA 4.0"
)

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

html_theme = "shibuya"
html_title = "phomemo-driver"
html_logo = "_static/m08f.png"
html_favicon = "_static/m08f.png"
html_static_path = ["_static"]
templates_path = ["_templates"]
html_css_files = ["custom.css"]
pygments_style = "github-light-default"
pygments_dark_style = "github-dark"
html_theme_options = {
    "accent_color": "cyan",
    "color_mode": "auto",
    "dark_code": True,
    "github_url": "https://github.com/PassionateBytes/phomemo-driver",
    "nav_links": [
        {"title": "Install", "url": "installation"},
        {"title": "First steps", "url": "first-steps"},
        {"title": "Library", "url": "library"},
        {"title": "Contributing", "url": "contributing"},
    ],
    "show_ai_links": False,
}
