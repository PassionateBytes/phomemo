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

"""Tests for the phomemo-bridge link and device commands against a fake printer."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from phomemo.bridge.__main__ import _parser, _run_client
from phomemo.bridge.server import BridgeConfig, start_server

from tests.test_bridge_server import FakePrinter

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
async def served(tmp_path: Path) -> AsyncIterator[BridgeConfig]:
    FakePrinter.instances.clear()
    config = BridgeConfig(
        socket_path=tmp_path / "bridge.sock",
        idle_disconnect_minutes=5.0 / 60,
        auto_off_minutes=5,
    )
    server = await start_server(config, printer_factory=FakePrinter)
    try:
        yield config
    finally:
        server.close()
        server.close_clients()


async def run(
    config: BridgeConfig, capsys: pytest.CaptureFixture[str], *argv: str
) -> tuple[int, str, str]:
    code = await _run_client(_parser().parse_args(list(argv)), config.socket_path)
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.asyncio
async def test_connect_brings_the_link_up_and_leaves_it_held(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = await run(served, capsys, "connect", "--address", ADDRESS)
    assert code == 0
    assert f"connected to {ADDRESS}" in out
    assert FakePrinter.instances[-1].connected


@pytest.mark.asyncio
async def test_connect_reports_why_it_failed(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    original = FakePrinter.__init__

    def unreachable(self: FakePrinter, *args: object) -> None:
        original(self, *args)
        self.reachable = False

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(FakePrinter, "__init__", unreachable)
        code, _, err = await run(served, capsys, "connect")
    assert code == 1
    assert "not reachable: Device not found" in err


@pytest.mark.asyncio
async def test_disconnect_drops_the_link(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(served, capsys, "connect", "--address", ADDRESS)
    code, out, _ = await run(served, capsys, "disconnect")
    assert code == 0
    assert "disconnected" in out
    assert not FakePrinter.instances[-1].connected


@pytest.mark.asyncio
async def test_status_without_a_link_says_so(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = await run(served, capsys, "status")
    assert code == 0
    assert json.loads(out) == {"connected": False}


@pytest.mark.asyncio
async def test_status_shows_sensors_and_device_details_when_linked(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(served, capsys, "connect", "--address", ADDRESS)
    code, out, _ = await run(served, capsys, "status")
    assert code == 0
    assert json.loads(out) == {
        "connected": True,
        "address": ADDRESS,
        "lid": "closed",
        "paper": "present",
        "battery": 77,
        "firmware": "1.1.3",
        "serial": "<serial>",
        "auto_off_minutes": 5,
    }


@pytest.mark.asyncio
async def test_status_for_another_printer_than_the_linked_one(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(served, capsys, "connect", "--address", ADDRESS)
    code, out, _ = await run(served, capsys, "status", "--address", "11:22:33:44:55:66")
    assert code == 0
    assert json.loads(out) == {
        "connected": False,
        "address": "11:22:33:44:55:66",
        "linked_to": ADDRESS,
    }


@pytest.mark.asyncio
async def test_auto_off_reads_and_sets(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(served, capsys, "connect", "--address", ADDRESS)
    code, out, _ = await run(served, capsys, "auto-off")
    assert (code, out.strip()) == (0, f"{ADDRESS}: auto-off 5 min")
    code, out, _ = await run(served, capsys, "auto-off", "0")
    assert (code, out.strip()) == (0, f"{ADDRESS}: auto-off never")
    assert FakePrinter.instances[-1].auto_off == 0


@pytest.mark.asyncio
async def test_auto_off_needs_a_link(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = await run(served, capsys, "auto-off")
    assert code == 1
    assert "not connected" in err


@pytest.mark.asyncio
async def test_status_after_disconnect_shows_last_seen_values(
    served: BridgeConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(served, capsys, "connect", "--address", ADDRESS)
    await run(served, capsys, "status")
    await run(served, capsys, "disconnect")
    code, out, _ = await run(served, capsys, "status")
    reply = json.loads(out)
    assert code == 0
    assert reply["connected"] is False
    assert reply["address"] == ADDRESS
    assert reply["last_seen"]["battery"] == 77
    assert reply["last_seen"]["firmware"] == "1.1.3"
