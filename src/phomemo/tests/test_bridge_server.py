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

"""Tests for the bridge daemon with a scripted fake printer."""

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import phomemo.profiles  # noqa: F401, registers built-in profiles
import pytest
from bleak.backends.device import BLEDevice
from phomemo.bridge.protocol import encode_message, read_message
from phomemo.bridge.server import BridgeConfig, start_server
from phomemo.events import LidState, PaperState
from phomemo.printer import DeviceInfo, PrintAborted, SheetRanOut
from phomemo.registry import PrinterProfile, get_profile

A4 = get_profile("m08f")


class FakePrinter:
    """Scripted stand-in for ``phomemo.Printer``."""

    instances: list["FakePrinter"] = []

    def __init__(self, profile: PrinterProfile, address: object = None) -> None:
        self.profile = profile
        # Like Printer.address: a device found by a scan stands for its address.
        self.address = getattr(address, "address", address)
        self.reachable = True
        self.connect_error = "Device not found"
        self.connected = False
        self.connects = 0
        self.lid = LidState.CLOSED
        self.paper = PaperState.PRESENT
        self.battery = 77
        self.muted = False
        self.ejects = 0
        self.feeds: list[int] = []
        self.eject_result = True
        self.printed: list[tuple[int, int, str]] = []
        self.print_error: Exception | None = None
        self.print_started = asyncio.Event()
        self.release_print: asyncio.Event | None = None
        self.rows_sent = 0
        self.auto_off: int | None = 10
        self.auto_off_writes: list[int] = []
        self.auto_off_error: Exception | None = None
        FakePrinter.instances.append(self)

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect(self, discovery_timeout: float = 5.0) -> None:
        if not self.reachable:
            raise ConnectionError(self.connect_error)
        self.connected = True
        self.connects += 1

    async def disconnect(self) -> None:
        self.connected = False

    async def reconnect(self, discovery_timeout: float = 5.0) -> None:
        await self.disconnect()
        await self.connect(discovery_timeout)
        self.muted = False

    async def query_lid(self, timeout: float = 1.0) -> LidState | None:
        return None if self.muted else self.lid

    async def query_paper(self, timeout: float = 1.0) -> PaperState | None:
        return None if self.muted else self.paper

    async def query_device_info(self, timeout: float = 1.0) -> DeviceInfo:
        return DeviceInfo(
            battery=self.battery,
            lid=self.lid,
            paper=self.paper,
            firmware="1.1.3",
            serial="<serial>",
            auto_off_minutes=self.auto_off,
        )

    @property
    def chunk_bytes(self) -> int:
        return 244

    async def query_battery(self, timeout: float = 1.0) -> int | None:
        return None if self.muted else self.battery

    async def query_auto_off(self, timeout: float = 1.0) -> int | None:
        return None if self.muted else self.auto_off

    async def set_auto_off_timer(self, minutes: int) -> None:
        if self.auto_off_error is not None:
            raise self.auto_off_error
        if not 0 <= minutes <= 1275 or minutes % 5:
            raise ValueError(f"Timer must be a multiple of 5, got {minutes}")
        self.auto_off_writes.append(minutes)
        self.auto_off = minutes

    async def check_ready(self, timeout: float = 1.0) -> tuple[bool, str]:
        if self.muted:
            return False, "Could not query lid state"
        if self.lid == LidState.OPEN:
            return False, "Lid is open"
        if self.paper == PaperState.ABSENT:
            return False, "No paper loaded"
        return True, "ready"

    async def wait_for_ready(self, **kwargs: Any) -> None:
        return None

    async def feed(self, lines: int = 20) -> None:
        self.feeds.append(lines)

    async def eject_paper(self, **kwargs: Any) -> bool:
        self.ejects += 1
        if self.eject_result:
            self.paper = PaperState.ABSENT
        return self.eject_result

    async def print_bitmap(
        self,
        bitmap: bytes,
        height: int,
        density: Any = None,
        abort: asyncio.Event | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        **kwargs: Any,
    ) -> None:
        self.printed.append(
            (len(bitmap), height, getattr(density, "name", str(density)))
        )
        self.print_started.set()
        if self.release_print is not None:
            await self.release_print.wait()
        if abort is not None and abort.is_set():
            raise PrintAborted("cancelled")
        if self.print_error is not None:
            error, self.print_error = self.print_error, None
            raise error
        for i in range(1, 21):
            self.rows_sent = height * i // 20
            if on_progress is not None:
                on_progress(i, 20)
        self.rows_sent = 0


class Client:
    """Minimal test client speaking the bridge wire format."""

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.events: list[dict[str, Any]] = []

    async def send(self, obj: dict[str, Any], payload: bytes = b"") -> None:
        self.writer.write(encode_message(obj, payload))
        await self.writer.drain()

    async def reply(self) -> dict[str, Any]:
        while True:
            obj, _ = await read_message(self.reader)
            if "event" in obj:
                self.events.append(obj)
                continue
            return obj

    async def call(self, obj: dict[str, Any], payload: bytes = b"") -> dict[str, Any]:
        await self.send(obj, payload)
        return await self.reply()

    async def close(self) -> None:
        self.writer.close()
        await self.writer.wait_closed()


@pytest.fixture
def config(tmp_path: Path) -> BridgeConfig:
    return BridgeConfig(
        socket_path=tmp_path / "bridge.sock",
        idle_disconnect_minutes=0.2 / 60,
        drain_seconds=0.0,
        auto_off_minutes=5,
    )


@pytest.fixture
async def bridge(config: BridgeConfig) -> AsyncIterator[BridgeConfig]:
    FakePrinter.instances.clear()
    server = await start_server(config, printer_factory=FakePrinter)
    try:
        yield config
    finally:
        server.close()
        server.close_clients()


async def _connect(config: BridgeConfig) -> Client:
    reader, writer = await asyncio.open_unix_connection(str(config.socket_path))
    return Client(reader, writer)


def _printer() -> FakePrinter:
    assert FakePrinter.instances, "no printer created yet"
    return FakePrinter.instances[-1]


@pytest.mark.asyncio
async def test_discover_lists_known_models_only(
    bridge: BridgeConfig, one_m08f_in_range: list[BLEDevice]
) -> None:
    one_m08f_in_range.append(
        BLEDevice(address="11:22:33:44:55:66", name="Q30", details=None)
    )
    client = await _connect(bridge)
    reply = await client.call({"cmd": "discover", "timeout": 1})
    assert reply == {
        "ok": True,
        "cmd": "discover",
        "printers": [{"name": "M08F", "address": "AA:BB:CC:DD:EE:FF", "model": "m08f"}],
    }
    await client.close()


@pytest.mark.asyncio
async def test_open_with_a_model_uses_its_profile_without_scanning(
    bridge: BridgeConfig, one_m08f_in_range: list[BLEDevice]
) -> None:
    one_m08f_in_range.clear()
    client = await _connect(bridge)
    reply = await client.call(
        {"cmd": "open", "address": "AA:BB:CC:00:00:01", "model": "m08f"}
    )
    assert reply["connected"] is True
    assert _printer().profile.name == "m08f"
    assert _printer().address == "AA:BB:CC:00:00:01"
    await client.close()


@pytest.mark.asyncio
async def test_open_with_an_unknown_model_fails_with_a_reason(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    reply = await client.call({"cmd": "open", "model": "q30"})
    assert reply["connected"] is False
    assert "unknown printer model 'q30'" in reply["reason"]
    await client.close()


@pytest.mark.asyncio
async def test_open_without_a_model_takes_it_from_the_advertised_name(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    reply = await client.call({"cmd": "open", "address": "AA:BB:CC:DD:EE:FF"})
    assert reply["connected"] is True
    assert _printer().profile.name == "m08f"
    await client.close()


@pytest.mark.asyncio
async def test_open_without_a_model_for_a_printer_not_in_range(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    reply = await client.call({"cmd": "open", "address": "11:22:33:44:55:66"})
    assert reply["connected"] is False
    assert "11:22:33:44:55:66" in reply["reason"]
    await client.close()


@pytest.mark.asyncio
async def test_open_without_address_refuses_several_printers(
    bridge: BridgeConfig, one_m08f_in_range: list[BLEDevice]
) -> None:
    one_m08f_in_range.append(
        BLEDevice(address="AA:BB:CC:00:00:02", name="M08F", details=None)
    )
    client = await _connect(bridge)
    reply = await client.call({"cmd": "open"})
    assert reply["connected"] is False
    assert "AA:BB:CC:00:00:02, AA:BB:CC:DD:EE:FF" in reply["reason"]
    await client.close()


@pytest.mark.asyncio
async def test_status_and_info_report_the_model(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    assert (await client.call({"cmd": "status"}))["model"] == "m08f"
    assert (await client.call({"cmd": "info"}))["model"] == "m08f"
    _printer().connected = False
    assert (await client.call({"cmd": "status"}))["last_seen"]["model"] == "m08f"
    await client.close()


@pytest.mark.asyncio
async def test_open_connects_once_within_hold_window(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    assert (await client.call({"cmd": "open"}))["connected"] is True
    assert (await client.call({"cmd": "close"}))["ok"]
    assert (await client.call({"cmd": "open"}))["connected"] is True
    assert _printer().connects == 1
    await client.close()


@pytest.mark.asyncio
async def test_status_session_does_not_rearm_hold(tmp_path: Path) -> None:
    FakePrinter.instances.clear()
    config = BridgeConfig(
        socket_path=tmp_path / "bridge.sock", idle_disconnect_minutes=0.4 / 60
    )
    server = await start_server(config, printer_factory=FakePrinter)
    try:
        client = await _connect(config)
        assert (await client.call({"cmd": "open"}))["connected"] is True
        assert (await client.call({"cmd": "close"}))["ok"]
        await client.close()
        await asyncio.sleep(0.2)
        poll = await _connect(config)
        assert (await poll.call({"cmd": "status"}))["connected"] is True
        await poll.close()
        await asyncio.sleep(0.3)
        assert _printer().connected is False
    finally:
        server.close()
        server.close_clients()


@pytest.mark.asyncio
async def test_idle_link_is_dropped_after_idle_disconnect_minutes(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    await client.call({"cmd": "close"})
    await asyncio.sleep(0.4)
    assert _printer().connected is False
    await client.close()


@pytest.mark.asyncio
async def test_status_without_a_link_reports_the_last_seen_values(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open", "address": "AA:BB:CC:DD:EE:FF"})
    await client.call({"cmd": "status"})
    await client.call({"cmd": "info"})
    _printer().connected = False
    reply = await client.call({"cmd": "status"})
    seen = reply.pop("last_seen")
    assert reply == {
        "ok": True,
        "cmd": "status",
        "connected": False,
        "address": "AA:BB:CC:DD:EE:FF",
    }
    assert seen.pop("at")
    assert seen == {
        "model": "m08f",
        "battery": 77,
        "lid": "closed",
        "paper": "present",
        "firmware": "1.1.3",
        "serial": "<serial>",
        "auto_off_minutes": 5,
    }
    await client.close()


@pytest.mark.asyncio
async def test_status_never_linked_has_nothing_last_seen(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    assert await client.call({"cmd": "status"}) == {
        "ok": True,
        "cmd": "status",
        "connected": False,
    }
    await client.close()


@pytest.mark.asyncio
async def test_status_keeps_last_seen_values_per_printer(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open", "address": "AA:BB:CC:00:00:01", "model": "m08f"})
    _printer().battery = 40
    await client.call({"cmd": "status"})
    await client.call({"cmd": "open", "address": "AA:BB:CC:00:00:02", "model": "m08f"})
    _printer().battery = 90
    await client.call({"cmd": "status"})
    first = await client.call({"cmd": "status", "address": "AA:BB:CC:00:00:01"})
    assert first["connected"] is False
    assert first["linked_to"] == "AA:BB:CC:00:00:02"
    assert first["last_seen"]["battery"] == 40
    second = await client.call({"cmd": "status", "address": "AA:BB:CC:00:00:02"})
    assert second["connected"] is True
    assert second["battery"] == 90
    await client.close()


@pytest.mark.asyncio
async def test_status_reports_sensors_and_connected_flag(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    before = await client.call({"cmd": "status"})
    assert before == {"ok": True, "cmd": "status", "connected": False}
    await client.call({"cmd": "open"})
    after = await client.call({"cmd": "status"})
    assert after == {
        "ok": True,
        "cmd": "status",
        "connected": True,
        "address": "AA:BB:CC:DD:EE:FF",
        "model": "m08f",
        "lid": "closed",
        "paper": "present",
        "battery": 77,
    }
    await client.close()


@pytest.mark.asyncio
async def test_wait_ready_pushes_printer_off_then_no_sheet_then_ok(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    reply = await client.call({"cmd": "open"})
    assert reply["ok"]
    printer = _printer()
    printer.connected = False
    printer.reachable = False
    printer.paper = PaperState.ABSENT

    async def operator() -> None:
        await asyncio.sleep(0.15)
        printer.reachable = True
        await asyncio.sleep(0.6)
        printer.paper = PaperState.PRESENT

    asyncio.create_task(operator())
    reply = await client.call({"cmd": "wait_ready", "settle": 0})
    assert reply == {"ok": True, "cmd": "wait_ready"}
    reasons = [e["reason"] for e in client.events if e["event"] == "waiting"]
    assert reasons == ["connecting", "printer-off", "no-sheet"]
    await client.close()


async def _send_page(
    client: Client, rows: int, bits: int = 8, **extra: Any
) -> dict[str, Any]:
    width = 1680
    page = {
        "cmd": "page_begin",
        "width": width,
        "length_rows": rows,
        "bits": bits,
        "tone": "threshold",
        "content": "auto",
        "density": "high",
        "media_length_mm": 297.0,
        "rotate": False,
    }
    page.update(extra)
    assert (await client.call(page))["ok"]
    row_bytes = width * bits // 8
    half = rows // 2
    assert (
        await client.call({"cmd": "lines", "count": half}, b"\xff" * (row_bytes * half))
    )["ok"]
    assert (
        await client.call(
            {"cmd": "lines", "count": rows - half},
            b"\xff" * (row_bytes * (rows - half)),
        )
    )["ok"]
    return await client.call({"cmd": "page_end"})


@pytest.mark.asyncio
async def test_page_roundtrip_prints_prepared_page(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    reply = await _send_page(client, 2374)
    assert reply == {"ok": True, "cmd": "page_end", "impressions": 1}
    printer = _printer()
    assert printer.printed == [(210 * 2253, 2253, "HIGH")]
    assert printer.ejects == 1
    await client.close()


@pytest.mark.asyncio
async def test_page_end_reports_progress_events(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    await _send_page(client, 400)
    percents = [e["percent"] for e in client.events if e["event"] == "progress"]
    assert percents and percents == sorted(percents) and percents[-1] == 100
    assert all(p % 5 == 0 for p in percents)
    await client.close()


@pytest.mark.asyncio
async def test_lines_beyond_declared_length_is_an_error(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    page = {
        "cmd": "page_begin",
        "width": 1680,
        "length_rows": 10,
        "bits": 8,
        "tone": "threshold",
        "content": "auto",
        "density": "medium",
        "media_length_mm": None,
        "rotate": False,
    }
    assert (await client.call(page))["ok"]
    reply = await client.call({"cmd": "lines", "count": 11}, b"\xff" * (1680 * 11))
    assert reply["ok"] is False
    assert "length_rows" in reply["error"]
    await client.close()


@pytest.mark.asyncio
async def test_cancelled_page_warns_when_the_sheet_stays(
    bridge: BridgeConfig, caplog: pytest.LogCaptureFixture
) -> None:
    client = await _connect(bridge)
    assert (await client.call({"cmd": "open"}))["connected"] is True
    printer = _printer()
    printer.eject_result = False
    printer.release_print = asyncio.Event()
    await client.call(
        {
            "cmd": "page_begin",
            "width": 1680,
            "length_rows": 100,
            "bits": 8,
            "tone": "threshold",
            "content": "auto",
            "density": "medium",
            "media_length_mm": None,
            "rotate": False,
        }
    )
    await client.call({"cmd": "lines", "count": 100}, b"\xff" * (1680 * 100))
    await client.send({"cmd": "page_end"})
    await printer.print_started.wait()
    with caplog.at_level("WARNING", logger="phomemo.bridge.session"):
        assert (await client.call({"cmd": "abort"}))["ok"]
        printer.release_print.set()
        reply = await client.reply()
    assert reply["error"] == "cancelled"
    assert any("eject" in r.getMessage().lower() for r in caplog.records)
    await client.close()


@pytest.mark.asyncio
async def test_abort_during_page_end_replies_cancelled_and_ejects(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.release_print = asyncio.Event()
    page = {
        "cmd": "page_begin",
        "width": 1680,
        "length_rows": 400,
        "bits": 8,
        "tone": "threshold",
        "content": "auto",
        "density": "medium",
        "media_length_mm": None,
        "rotate": False,
    }
    await client.call(page)
    await client.call({"cmd": "lines", "count": 400}, b"\xff" * (1680 * 400))
    await client.send({"cmd": "page_end"})
    await printer.print_started.wait()
    abort_reply = await client.call({"cmd": "abort"})
    assert abort_reply == {"ok": True, "cmd": "abort"}
    printer.release_print.set()
    reply = await client.reply()
    assert reply == {"ok": False, "cmd": "page_end", "error": "cancelled"}
    assert printer.ejects == 1
    await client.close()


@pytest.mark.asyncio
async def test_abort_when_idle_is_ok(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    assert await client.call({"cmd": "abort"}) == {"ok": True, "cmd": "abort"}
    await client.close()


@pytest.mark.asyncio
async def test_second_client_is_busy(bridge: BridgeConfig) -> None:
    first = await _connect(bridge)
    await first.call({"cmd": "open"})
    second = await _connect(bridge)
    reply = await second.reply()
    assert reply == {"ok": False, "error": "busy"}
    await first.close()
    await second.close()


@pytest.mark.asyncio
async def test_client_eof_mid_page_aborts_and_recovers(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.release_print = asyncio.Event()
    page = {
        "cmd": "page_begin",
        "width": 1680,
        "length_rows": 400,
        "bits": 8,
        "tone": "threshold",
        "content": "auto",
        "density": "medium",
        "media_length_mm": None,
        "rotate": False,
    }
    await client.call(page)
    await client.call({"cmd": "lines", "count": 400}, b"\xff" * (1680 * 400))
    await client.send({"cmd": "page_end"})
    await printer.print_started.wait()
    await client.close()
    printer.release_print.set()
    await asyncio.sleep(0.1)
    assert printer.ejects == 1
    again = await _connect(bridge)
    assert (await again.call({"cmd": "status"}))["ok"]
    await again.close()


@pytest.mark.asyncio
async def test_open_with_printer_off_is_ok_and_not_connected(tmp_path: Path) -> None:
    def unreachable(profile: PrinterProfile, address: object = None) -> FakePrinter:
        printer = FakePrinter(profile, address)
        printer.reachable = False
        return printer

    config = BridgeConfig(
        socket_path=tmp_path / "off.sock", idle_disconnect_minutes=0.2 / 60
    )
    server = await start_server(config, printer_factory=unreachable)
    try:
        client = await _connect(config)
        assert await client.call({"cmd": "open"}) == {
            "ok": True,
            "cmd": "open",
            "connected": False,
            "reason": "Device not found",
        }
        await client.close()
    finally:
        server.close()
        server.close_clients()


@pytest.mark.asyncio
async def test_wait_ready_survives_a_dropped_link(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    original = printer.check_ready
    dropped = False

    async def check_ready(timeout: float = 1.0) -> tuple[bool, str]:
        nonlocal dropped
        if not dropped:
            dropped = True
            printer.connected = False
            raise ConnectionError("Printer connection lost")
        return await original(timeout)

    printer.check_ready = check_ready  # type: ignore[method-assign]
    reply = await client.call({"cmd": "wait_ready", "settle": 0})
    assert reply["ok"]
    assert [e["reason"] for e in client.events if e["event"] == "waiting"] == [
        "connecting"
    ]
    assert printer.connects == 2
    await client.close()


@pytest.mark.asyncio
async def test_wait_ready_and_abort_in_one_write_reply_both(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    _printer().paper = PaperState.ABSENT
    client.writer.write(
        encode_message({"cmd": "wait_ready"}) + encode_message({"cmd": "abort"})
    )
    await client.writer.drain()
    replies = [await client.reply(), await client.reply()]
    by_cmd = {r["cmd"]: r for r in replies}
    assert by_cmd["abort"]["ok"] is True
    assert by_cmd["wait_ready"] == {
        "ok": False,
        "cmd": "wait_ready",
        "error": "cancelled",
    }
    await client.close()


@pytest.mark.asyncio
async def test_wait_ready_settle_timeout_keeps_waiting(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    calls = 0

    async def flaky_settle(**kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("No paper loaded")

    printer.wait_for_ready = flaky_settle  # type: ignore[method-assign]
    reply = await client.call({"cmd": "wait_ready", "settle": 1.0})
    assert reply["ok"]
    assert calls == 2
    await client.close()


@pytest.mark.asyncio
async def test_oversized_line_ends_the_session_and_frees_the_bridge(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    client.writer.write(b"x" * (70 * 1024) + b"\n")
    await client.writer.drain()
    reply = await client.reply()
    assert reply["ok"] is False
    assert client.reader.at_eof() or (await client.reader.read(1)) == b""
    again = await _connect(bridge)
    assert (await again.call({"cmd": "status"}))["ok"]
    await again.close()


@pytest.mark.asyncio
async def test_open_with_address_targets_that_printer(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    reply = await client.call({"cmd": "open", "address": "AA:BB:CC:DD:EE:FF"})
    assert reply["connected"] is True
    assert _printer().address == "AA:BB:CC:DD:EE:FF"
    reply = await client.call(
        {"cmd": "open", "address": "11:22:33:44:55:66", "model": "m08f"}
    )
    assert reply["connected"] is True
    assert _printer().address == "11:22:33:44:55:66"
    assert len(FakePrinter.instances) == 2
    await client.close()


@pytest.mark.asyncio
async def test_serve_disconnects_the_printer_when_cancelled(tmp_path: Path) -> None:
    from phomemo.bridge.server import serve

    FakePrinter.instances.clear()
    config = BridgeConfig(
        socket_path=tmp_path / "serve.sock", idle_disconnect_minutes=60.0 / 60
    )
    task = asyncio.create_task(serve(config, printer_factory=FakePrinter))
    for _ in range(50):
        if config.socket_path.exists():
            break
        await asyncio.sleep(0.02)
    client = await _connect(config)
    await client.call({"cmd": "open"})
    await client.close()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert FakePrinter.instances[-1].connected is False
    assert not config.socket_path.exists()


async def _submit_page(client: Client, printer: FakePrinter, rows: int = 100) -> None:
    """Begin a page, send its rows, start page_end and wait for the print attempt."""
    await client.call(
        {
            "cmd": "page_begin",
            "width": 1680,
            "length_rows": rows,
            "bits": 8,
            "tone": "threshold",
            "content": "auto",
            "density": "medium",
            "media_length_mm": None,
            "rotate": False,
        }
    )
    await client.call({"cmd": "lines", "count": rows}, b"\xff" * (1680 * rows))
    await client.send({"cmd": "page_end"})
    await printer.print_started.wait()


def _waiting_reasons(client: Client) -> list[str]:
    return [e["reason"] for e in client.events if e.get("event") == "waiting"]


@pytest.mark.asyncio
async def test_lid_opened_mid_page_reprints_after_a_fresh_sheet(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.release_print = asyncio.Event()
    printer.print_error = PrintAborted("lid opened")
    await _submit_page(client, printer)
    printer.lid = LidState.OPEN
    printer.release_print.set()
    await asyncio.sleep(0.3)
    # Lid closed with the interrupted sheet still inside: it gets ejected.
    printer.lid = LidState.CLOSED
    await asyncio.sleep(0.8)
    assert printer.paper == PaperState.ABSENT
    printer.paper = PaperState.PRESENT
    reply = await client.reply()
    assert reply == {"ok": True, "cmd": "page_end", "impressions": 1}
    assert len(printer.printed) == 2
    assert printer.ejects == 2
    assert printer.connects == 1
    assert "lid-open" in _waiting_reasons(client)
    assert "no-sheet" in _waiting_reasons(client)
    await client.close()


@pytest.mark.asyncio
async def test_sheet_inserted_after_the_lid_closed_is_printed_on(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.release_print = asyncio.Event()
    printer.print_error = PrintAborted("lid opened")
    await _submit_page(client, printer)
    printer.lid = LidState.OPEN
    printer.paper = PaperState.ABSENT
    printer.release_print.set()
    await asyncio.sleep(0.3)
    printer.lid = LidState.CLOSED
    await asyncio.sleep(0.8)
    printer.paper = PaperState.PRESENT
    reply = await client.reply()
    assert reply["ok"]
    assert len(printer.printed) == 2
    assert printer.ejects == 1
    await client.close()


@pytest.mark.asyncio
async def test_short_sheet_reprints_the_page_on_the_next_sheet(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.release_print = asyncio.Event()
    printer.print_error = SheetRanOut("paper ran out")
    await _submit_page(client, printer)
    printer.release_print.set()
    await asyncio.sleep(0.8)
    assert printer.ejects == 1
    printer.paper = PaperState.PRESENT
    reply = await client.reply()
    assert reply == {"ok": True, "cmd": "page_end", "impressions": 1}
    assert "short-sheet" in _waiting_reasons(client)
    assert len(printer.printed) == 2
    assert printer.ejects == 2
    assert printer.connects == 2
    await client.close()


@pytest.mark.asyncio
async def test_cancel_while_waiting_for_the_reprint(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.release_print = asyncio.Event()
    printer.print_error = PrintAborted("lid opened")
    await _submit_page(client, printer)
    printer.lid = LidState.OPEN
    printer.release_print.set()
    await asyncio.sleep(0.3)
    assert (await client.call({"cmd": "abort"}))["ok"]
    reply = await client.reply()
    assert reply == {"ok": False, "cmd": "page_end", "error": "cancelled"}
    assert len(printer.printed) == 1
    await client.close()


@pytest.mark.asyncio
async def test_adapter_off_is_reported_as_such(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.connected = False
    printer.reachable = False
    printer.connect_error = "Bluetooth scan failed, is the adapter powered on?"

    async def operator() -> None:
        await asyncio.sleep(0.3)
        printer.reachable = True

    asyncio.create_task(operator())
    reply = await client.call({"cmd": "wait_ready", "settle": 0})
    assert reply["ok"]
    assert _waiting_reasons(client)[:2] == ["connecting", "adapter-off"]
    await client.close()


@pytest.mark.asyncio
async def test_link_lost_mid_page_waits_for_the_printer_and_reprints(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.release_print = asyncio.Event()
    printer.print_error = ConnectionError("Printer connection lost")
    await _submit_page(client, printer)
    printer.connected = False
    printer.reachable = False
    printer.release_print.set()
    await asyncio.sleep(0.5)
    # Printer back on with the interrupted sheet still inside.
    printer.reachable = True
    await asyncio.sleep(0.8)
    assert printer.paper == PaperState.ABSENT
    printer.paper = PaperState.PRESENT
    reply = await client.reply()
    assert reply == {"ok": True, "cmd": "page_end", "impressions": 1}
    assert len(printer.printed) == 2
    assert printer.connects == 2
    assert "printer-off" in _waiting_reasons(client)
    await client.close()


@pytest.mark.asyncio
async def test_identify_ejects_a_loaded_sheet_then_pulses_the_feed(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    assert (await client.call({"cmd": "identify"}))["ok"]
    assert printer.ejects == 1
    assert len(printer.feeds) == 3
    await client.close()


@pytest.mark.asyncio
async def test_identify_connects_first_and_skips_the_eject_without_paper(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    await client.call({"cmd": "close"})
    await asyncio.sleep(0.3)
    assert printer.connected is False
    printer.paper = PaperState.ABSENT
    assert (await client.call({"cmd": "identify"}))["ok"]
    assert printer.connected is True
    assert printer.ejects == 0
    assert len(printer.feeds) == 3
    await client.close()


@pytest.mark.asyncio
async def test_test_page_renders_a_png_with_the_device_details(
    bridge: BridgeConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    reply = await client.call(
        {
            "cmd": "test_page",
            "printer_name": "Phomemo M08F",
            "versions": {"phomemo-printer-app": "0.1.0", "pappl": "1.4.12"},
        }
    )
    assert reply["ok"]
    path = Path(reply["path"])
    assert path.parent == tmp_path
    from PIL import Image

    with Image.open(path) as img:
        assert img.size == (1678, 2213)
    await client.close()


@pytest.mark.asyncio
async def test_status_reconnects_a_silent_printer(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.muted = True
    reply = await client.call({"cmd": "status"})
    assert reply["lid"] == "closed"
    assert printer.connects == 2
    await client.close()


@pytest.mark.asyncio
async def test_identify_reconnects_a_silent_printer(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.muted = True
    printer.paper = PaperState.ABSENT
    assert (await client.call({"cmd": "identify"}))["ok"]
    assert printer.connects == 2
    assert len(printer.feeds) == 3
    await client.close()


@pytest.mark.asyncio
async def test_connect_sets_the_configured_auto_off(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    assert (await client.call({"cmd": "open"}))["connected"] is True
    assert _printer().auto_off_writes == [5]
    await client.close()


@pytest.mark.asyncio
async def test_connect_leaves_a_matching_auto_off_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePrinter.instances.clear()
    config = BridgeConfig(socket_path=tmp_path / "b.sock", auto_off_minutes=10)
    server = await start_server(config, printer_factory=FakePrinter)
    try:
        client = await _connect(config)
        await client.call({"cmd": "open"})
        assert _printer().auto_off_writes == []
        await client.close()
    finally:
        server.close()
        server.close_clients()


@pytest.mark.asyncio
async def test_reused_link_does_not_rewrite_auto_off(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    _printer().auto_off = 10
    await client.call({"cmd": "open"})
    assert _printer().auto_off_writes == [5]
    await client.close()


@pytest.mark.asyncio
async def test_failed_auto_off_write_does_not_fail_the_connect(
    bridge: BridgeConfig, caplog: pytest.LogCaptureFixture
) -> None:
    FakePrinter.instances.clear()
    client = await _connect(bridge)

    original = FakePrinter.__init__

    def failing(self: FakePrinter, *args: Any) -> None:
        original(self, *args)
        self.auto_off_error = OSError("write failed")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(FakePrinter, "__init__", failing)
        with caplog.at_level("WARNING"):
            reply = await client.call({"cmd": "open"})
    assert reply["connected"] is True
    assert "auto-off" in caplog.text
    await client.close()


@pytest.mark.asyncio
async def test_info_reports_the_device_details(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open", "address": "AA:BB:CC:DD:EE:FF"})
    reply = await client.call({"cmd": "info"})
    assert reply["ok"] is True
    assert reply["address"] == "AA:BB:CC:DD:EE:FF"
    assert reply["firmware"] == "1.1.3"
    assert reply["serial"] == "<serial>"
    assert reply["battery"] == 77
    assert reply["auto_off_minutes"] == 5
    assert reply["lid"] == "closed"
    assert reply["paper"] == "present"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cmd", ["info", "auto_off"])
async def test_device_commands_need_a_link(bridge: BridgeConfig, cmd: str) -> None:
    client = await _connect(bridge)
    reply = await client.call({"cmd": cmd})
    assert reply == {"ok": False, "cmd": cmd, "error": "not connected"}
    await client.close()


@pytest.mark.asyncio
async def test_auto_off_reads_and_sets_the_timer(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    assert (await client.call({"cmd": "auto_off"}))["auto_off_minutes"] == 5
    reply = await client.call({"cmd": "auto_off", "minutes": 30})
    assert reply["auto_off_minutes"] == 30
    assert _printer().auto_off_writes == [5, 30]
    await client.close()


@pytest.mark.asyncio
async def test_auto_off_rejects_an_invalid_value(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    reply = await client.call({"cmd": "auto_off", "minutes": 7})
    assert reply["ok"] is False
    assert "multiple of 5" in reply["error"]
    assert _printer().auto_off_writes == [5]
    await client.close()


@pytest.mark.asyncio
async def test_disconnect_drops_the_link_without_a_hold(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    assert (await client.call({"cmd": "disconnect"}))["ok"] is True
    assert not _printer().connected
    await client.close()
    await asyncio.sleep(0.05)
    assert not _printer().connected


@pytest.mark.asyncio
async def test_status_names_the_linked_printer(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open", "address": "AA:BB:CC:DD:EE:FF"})
    assert (await client.call({"cmd": "status"}))["address"] == "AA:BB:CC:DD:EE:FF"
    await client.close()


@pytest.mark.asyncio
async def test_open_reports_why_the_printer_is_not_reachable(
    bridge: BridgeConfig,
) -> None:
    client = await _connect(bridge)
    FakePrinter.instances.clear()
    original = FakePrinter.__init__

    def unreachable(self: FakePrinter, *args: Any) -> None:
        original(self, *args)
        self.reachable = False
        self.connect_error = "Several printers in range (A, B); choose one by address"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(FakePrinter, "__init__", unreachable)
        reply = await client.call({"cmd": "open"})
    assert reply["connected"] is False
    assert reply["reason"].startswith("Several printers in range")
    await client.close()


@pytest.mark.asyncio
async def test_connect_without_an_auto_off_setting_leaves_the_timer(
    tmp_path: Path,
) -> None:
    FakePrinter.instances.clear()
    config = BridgeConfig(socket_path=tmp_path / "n.sock", auto_off_minutes=None)
    server = await start_server(config, printer_factory=FakePrinter)
    try:
        client = await _connect(config)
        await client.call({"cmd": "open"})
        assert _printer().auto_off_writes == []
        await client.close()
    finally:
        server.close()
        server.close_clients()


@pytest.mark.asyncio
async def test_idle_disconnect_zero_keeps_the_link(tmp_path: Path) -> None:
    FakePrinter.instances.clear()
    config = BridgeConfig(socket_path=tmp_path / "k.sock", idle_disconnect_minutes=0)
    server = await start_server(config, printer_factory=FakePrinter)
    try:
        client = await _connect(config)
        await client.call({"cmd": "open"})
        await client.close()
        await asyncio.sleep(0.1)
        assert _printer().connected
    finally:
        server.close()
        server.close_clients()
