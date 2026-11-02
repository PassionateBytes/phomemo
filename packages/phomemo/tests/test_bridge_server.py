"""Tests for the bridge daemon with a scripted fake printer."""

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import phomemo.bridge.server as server_module
import phomemo.profiles  # noqa: F401, registers built-in profiles
import pytest
from bleak.backends.device import BLEDevice
from phomemo.bridge.protocol import encode_message, read_message
from phomemo.bridge.server import BridgeConfig, start_server
from phomemo.events import LidState, PaperState
from phomemo.printer import PrintAborted, SheetRanOut
from phomemo.registry import PrinterProfile, get_profile

A4 = get_profile("M08F-A4")


class FakePrinter:
    """Scripted stand-in for ``phomemo.Printer``."""

    instances: list["FakePrinter"] = []

    def __init__(self, profile: PrinterProfile, address: object = None) -> None:
        self.profile = profile
        self.address = address
        self.reachable = True
        self.connected = False
        self.connects = 0
        self.lid = LidState.CLOSED
        self.paper = PaperState.PRESENT
        self.battery = 77
        self.muted = False
        self.ejects = 0
        self.printed: list[tuple[int, int, str]] = []
        self.print_error: Exception | None = None
        self.print_started = asyncio.Event()
        self.release_print: asyncio.Event | None = None
        self.rows_sent = 0
        FakePrinter.instances.append(self)

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect(self, discovery_timeout: float = 5.0) -> None:
        if not self.reachable:
            raise ConnectionError("Device not found")
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

    async def query_battery(self, timeout: float = 1.0) -> int | None:
        return None if self.muted else self.battery

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

    async def eject_paper(self, **kwargs: Any) -> bool:
        self.ejects += 1
        return True

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
            raise self.print_error
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
        socket_path=tmp_path / "bridge.sock", hold_seconds=0.2, drain_seconds=0.0
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
async def test_discover_lists_printers(
    bridge: BridgeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_discover(name_pattern: str, timeout: float) -> list[BLEDevice]:
        return [BLEDevice(address="60:6E:41:23:0B:D6", name="M08F", details=None)]

    monkeypatch.setattr(server_module, "discover", fake_discover)
    client = await _connect(bridge)
    reply = await client.call({"cmd": "discover", "timeout": 1})
    assert reply == {
        "ok": True,
        "cmd": "discover",
        "printers": [{"name": "M08F", "address": "60:6E:41:23:0B:D6"}],
    }
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
async def test_hold_timer_disconnects_after_hold_seconds(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    await client.call({"cmd": "close"})
    await asyncio.sleep(0.4)
    assert _printer().connected is False
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
    assert reasons == ["printer-off", "no-sheet"]
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
    assert printer.printed == [(210 * 2245, 2245, "HIGH")]
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
async def test_sheet_ran_out_maps_to_error_reply(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.print_error = SheetRanOut("paper ran out")
    reply = await _send_page(client, 400)
    assert reply == {"ok": False, "cmd": "page_end", "error": "paper ran out"}
    assert printer.connects == 2
    assert printer.ejects == 1
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

    config = BridgeConfig(socket_path=tmp_path / "off.sock", hold_seconds=0.2)
    server = await start_server(config, printer_factory=unreachable)
    try:
        client = await _connect(config)
        assert await client.call({"cmd": "open"}) == {
            "ok": True,
            "cmd": "open",
            "connected": False,
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
        "printer-off"
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
    reply = await client.call({"cmd": "open", "address": "11:22:33:44:55:66"})
    assert reply["connected"] is True
    assert _printer().address == "11:22:33:44:55:66"
    assert len(FakePrinter.instances) == 2
    await client.close()


@pytest.mark.asyncio
async def test_lid_open_page_ends_aborted(bridge: BridgeConfig) -> None:
    client = await _connect(bridge)
    await client.call({"cmd": "open"})
    printer = _printer()
    printer.print_error = PrintAborted("lid opened")
    reply = await _send_page(client, 400)
    assert reply == {"ok": False, "cmd": "page_end", "error": "lid opened"}
    assert printer.ejects == 0
    await client.close()
