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


def test_every_command_has_a_summary_and_a_description() -> None:
    parser = _parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    summaries = {c.dest: c.help for c in sub._choices_actions}
    for name, command in sub.choices.items():
        assert summaries.get(name), name
        assert command.description and len(command.description) > 40, name


def test_link_and_device_commands_parse() -> None:
    parser = _parser()
    args = parser.parse_args(["connect", "-a", "AA:BB:CC:DD:EE:FF"])
    assert (args.command, args.address) == ("connect", "AA:BB:CC:DD:EE:FF")
    assert parser.parse_args(["disconnect"]).command == "disconnect"
    assert parser.parse_args(["auto-off"]).minutes is None
    assert parser.parse_args(["auto-off", "15"]).minutes == 15


@pytest.mark.parametrize(
    "command",
    [
        ["connect"],
        ["status"],
        ["auto-off"],
        ["eject"],
        ["identify"],
        ["testpage"],
        ["print", "page.png"],
    ],
)
def test_printer_commands_take_an_address(command: list[str]) -> None:
    args = _parser().parse_args([*command, "--address", "AA:BB:CC:DD:EE:FF"])
    assert args.address == "AA:BB:CC:DD:EE:FF"
    assert _parser().parse_args(command).address is None


@pytest.mark.parametrize("command", ["server", "devices", "disconnect"])
def test_commands_without_a_printer_take_no_address(command: str) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args([command, "-a", "AA:BB:CC:DD:EE:FF"])


def test_address_is_no_longer_a_global_option() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["-a", "AA:BB:CC:DD:EE:FF", "connect"])


@pytest.mark.parametrize("flag", ["-V", "--version"])
def test_version_flag_prints_the_package_version(
    flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from importlib.metadata import version

    with pytest.raises(SystemExit) as exit_info:
        _parser().parse_args([flag])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"phomemo-bridge {version('phomemo')}"


def test_dash_v_still_means_verbose() -> None:
    assert _parser().parse_args(["-v", "status"]).verbose is True
