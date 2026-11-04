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

"""Tests for the bridge client against a served fake printer."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from phomemo.bridge.client import BridgeClient, BridgeError
from phomemo.bridge.server import BridgeConfig, start_server
from phomemo.registry import get_profile
from PIL import Image

from tests.test_bridge_server import FakePrinter


@pytest.fixture
async def served(tmp_path: Path) -> AsyncIterator[BridgeConfig]:
    FakePrinter.instances.clear()
    config = BridgeConfig(
        socket_path=tmp_path / "bridge.sock", idle_disconnect_minutes=0.2 / 60
    )
    server = await start_server(config, printer_factory=FakePrinter)
    try:
        yield config
    finally:
        server.close()
        server.close_clients()


@pytest.mark.asyncio
async def test_client_print_image_streams_rows_and_returns_impressions(
    served: BridgeConfig, tmp_path: Path
) -> None:
    image = tmp_path / "page.png"
    Image.new("L", (1680, 2374), 255).save(image)
    events: list[dict] = []
    async with BridgeClient(served.socket_path, on_event=events.append) as client:
        impressions = await client.print_image(image, media="a4", quality="high")
    assert impressions == 1
    printer = FakePrinter.instances[-1]
    rows = get_profile("M08F-A4").rows_for(297.0)
    assert printer.printed == [(210 * rows, rows, "HIGH")]
    assert printer.ejects == 1
    assert [e["percent"] for e in events if e["event"] == "progress"][-1] == 100


@pytest.mark.asyncio
async def test_client_raises_bridge_error_on_failed_command(
    served: BridgeConfig,
) -> None:
    async with BridgeClient(served.socket_path) as client:
        with pytest.raises(BridgeError, match="no page in progress"):
            await client.page_end()


@pytest.mark.asyncio
async def test_client_reply_skips_the_abort_acknowledgement(
    served: BridgeConfig,
) -> None:
    async with BridgeClient(served.socket_path) as client:
        await client.open()
        printer = FakePrinter.instances[-1]
        printer.release_print = asyncio.Event()
        await client.page_begin(1680, 100, media_length_mm=None)
        await client.lines(100, b"\xff" * (1680 * 100))
        await client.send({"cmd": "page_end"})
        await printer.print_started.wait()
        await client.send({"cmd": "abort"})
        await asyncio.sleep(0.1)
        printer.release_print.set()
        # The bridge answers the abort first; the next reply must be the
        # page_end outcome, not that acknowledgement.
        with pytest.raises(BridgeError, match="cancelled"):
            await client.reply()
