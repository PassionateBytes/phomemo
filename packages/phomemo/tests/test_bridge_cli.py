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
