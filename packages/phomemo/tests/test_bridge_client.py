"""Tests for the bridge client against a served fake printer."""

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
    config = BridgeConfig(socket_path=tmp_path / "bridge.sock", hold_seconds=0.2)
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
