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

"""Writes the default configuration files with comments for the snap.

The files in packaging/config describe where the system packages read them
and how to restart the services; inside the snap both differ. This script
copies the files into the snap's etc/ with those passages replaced, and
fails when a passage it expects is missing, so a change to the originals
cannot ship a stale comment unnoticed.

    python3 adapt-config.py packaging/config DEST_DIR
"""

import sys
from pathlib import Path

COMMON = "/var/snap/phomemo-printer-app/common"

# (source file, destination relative to DEST_DIR, [(old passage, new passage)])
FILES = [
    (
        "bridge.toml",
        "phomemo/bridge.toml",
        [
            (
                "# Read from this file, then $XDG_CONFIG_HOME/phomemo/bridge.toml"
                " for a bridge\n"
                "# run by that user; the later file wins. Unusable settings are"
                " logged\n"
                "# (journalctl -u phomemo-bridge) and keep their default.\n",
                "# Read from this file only. Unusable settings are logged\n"
                "# (snap logs phomemo-printer-app.phomemo-bridge) and keep their"
                " default.\n",
            ),
            (
                "# Apply changes with: sudo systemctl restart phomemo-bridge\n",
                "# Apply changes with:"
                " sudo snap restart phomemo-printer-app.phomemo-bridge\n",
            ),
        ],
    ),
    (
        "phomemo-printer-app.conf",
        "phomemo-printer-app.conf",
        [
            (
                "# Read after -o options on the command line,"
                " ~/.config/phomemo-printer-app.conf\n"
                "# and /usr/local/etc/phomemo-printer-app.conf; the first that"
                " sets one wins.\n",
                "# Read after -o options on the command line; the first that"
                " sets one wins.\n",
            ),
            (
                "# Apply changes with: sudo systemctl restart phomemo-printer-app\n",
                "# Apply changes with:"
                " sudo snap restart phomemo-printer-app.phomemo-printer-app-server\n",
            ),
            (
                "# Log detail in the journal:",
                "# Log detail (snap logs phomemo-printer-app):",
            ),
            (
                "#spool-directory=/var/spool/phomemo-printer-app\n",
                f"#spool-directory={COMMON}/spool\n",
            ),
        ],
    ),
]


def adapt(text: str, replacements: list[tuple[str, str]], name: str) -> str:
    """The text with every passage replaced; a missing passage is an error."""
    for old, new in replacements:
        if text.count(old) != 1:
            sys.exit(f"{name}: expected passage not found once: {old!r}")
        text = text.replace(old, new)
    return text


def main() -> None:
    """Copies and adapts every file in FILES."""
    if len(sys.argv) != 3:
        sys.exit("usage: adapt-config.py SOURCE_DIR DEST_DIR")
    source, dest = Path(sys.argv[1]), Path(sys.argv[2])
    for name, target, replacements in FILES:
        text = adapt((source / name).read_text(), replacements, name)
        out = dest / target
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"{source / name} -> {out}")


if __name__ == "__main__":
    main()
