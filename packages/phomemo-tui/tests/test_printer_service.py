"""Tests for PrinterService state machine and auto-connect logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from phomemo_tui.config import AppConfig
from phomemo_tui.messages import (
    DeviceConnected,
    DeviceDisconnected,
)
from phomemo_tui.printer_service import PrinterService, ServiceState, match_profile


def _make_service() -> tuple[PrinterService, list]:
    """Return a service with a list that accumulates posted messages."""
    posted: list = []
    cfg = AppConfig(_path=None)
    svc = PrinterService(post_message=posted.append, config=cfg)
    return svc, posted


def test_initial_state() -> None:
    svc, _ = _make_service()
    assert svc.state == ServiceState.DISCONNECTED


def test_match_profile_known_name() -> None:
    assert match_profile("M08F-001") == "M08F-A4"


def test_match_profile_unknown_name() -> None:
    assert match_profile("SomeRandomDevice") is None


def test_match_profile_none_name() -> None:
    assert match_profile(None) is None


@pytest.mark.asyncio
async def test_connect_to_posts_connected_message() -> None:
    svc, posted = _make_service()

    mock_printer = MagicMock()
    mock_printer.is_connected = True
    mock_printer.connect = AsyncMock()
    mock_printer.on_event = MagicMock()
    mock_printer.disconnect = AsyncMock()

    with patch("phomemo_tui.printer_service.Printer", return_value=mock_printer):
        await svc.connect_to("AA:BB:CC:DD:EE:FF", "M08F-001", "M08F-A4")

    assert svc.state == ServiceState.CONNECTED
    assert any(isinstance(m, DeviceConnected) for m in posted)
    connected = next(m for m in posted if isinstance(m, DeviceConnected))
    assert connected.address == "AA:BB:CC:DD:EE:FF"
    assert connected.profile_name == "M08F-A4"


@pytest.mark.asyncio
async def test_disconnect_posts_disconnected() -> None:
    svc, posted = _make_service()

    mock_printer = MagicMock()
    mock_printer.is_connected = True
    mock_printer.connect = AsyncMock()
    mock_printer.disconnect = AsyncMock()
    mock_printer.on_event = MagicMock()

    with patch("phomemo_tui.printer_service.Printer", return_value=mock_printer):
        await svc.connect_to("AA:BB:CC:DD:EE:FF", "M08F-001", "M08F-A4")
        await svc.disconnect()

    assert svc.state == ServiceState.DISCONNECTED
    assert any(isinstance(m, DeviceDisconnected) for m in posted)
