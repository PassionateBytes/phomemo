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

"""Tests for the phomemo-bridge command line parsing."""

import pytest
from phomemo.bridge.__main__ import _parser


def test_subcommands_match_the_printer_application_where_they_overlap() -> None:
    parser = _parser()
    for command in ("server", "devices", "status", "identify", "testpage", "eject"):
        assert parser.parse_args([command]).command == command
    args = parser.parse_args(["print", "page.png", "--media", "a5"])
    assert args.command == "print"
    assert args.media == "a5"


def test_old_names_are_gone() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["serve"])
    with pytest.raises(SystemExit):
        _parser().parse_args(["discover"])
