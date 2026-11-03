"""One client connection to the bridge: command dispatch and the page pipeline."""

import asyncio
import contextlib
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from phomemo.bridge.protocol import ProtocolError, encode_message, read_message
from phomemo.bridge.server import Bridge
from phomemo.bridge.testpage import PageInfo, render_test_page, save_test_page
from phomemo.events import LidState, PaperState
from phomemo.imaging import ToneMode, image_to_bitmap, prepare_page
from phomemo.printer import PrintAborted, SheetRanOut
from phomemo.protocol import Density

logger = logging.getLogger(__name__)

_DENSITY = {"low": Density.LOW, "medium": Density.MEDIUM, "high": Density.HIGH}
_RETRY_SECONDS = 0.2
_POLL_SECONDS = 0.5
_LID_POLL_SECONDS = 0.2
_IDENTIFY_PULSES = 3
_IDENTIFY_FEED_LINES = 40
_IDENTIFY_PAUSE_SECONDS = 0.3
_MUTE_THRESHOLD = 3


class CommandError(Exception):
    """A command could not be carried out; the message goes to the client."""


@dataclass
class PageBuffer:
    """Raster lines received for the page in progress."""

    width: int
    length_rows: int
    bits: int
    tone: ToneMode
    density: Density
    media_length_mm: float | None
    rotate: bool
    rows: int = 0
    data: bytearray = field(default_factory=bytearray)

    @property
    def row_bytes(self) -> int:
        return self.width * self.bits // 8

    def image(self) -> Image.Image:
        """The received rows as a PIL image, 0 = black in both depths."""
        size = (self.width, self.rows)
        if self.bits == 8:
            return Image.frombytes("L", size, bytes(self.data))
        return Image.frombytes("1", size, bytes(self.data), "raw", "1;I")


class _Reporter:
    """Pushes ``waiting`` events, one per state change."""

    def __init__(self, session: "Session") -> None:
        self._session = session
        self.state: str | None = None

    async def __call__(self, reason: str) -> None:
        if self.state != reason:
            self.state = reason
            await self._session._event("waiting", reason=reason)


class Session:
    """Serve one client until it disconnects.

    Commands run one at a time; ``abort`` is the exception and may arrive
    while another command is pending. Long commands push ``event`` lines
    before their reply.
    """

    def __init__(
        self,
        bridge: Bridge,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._bridge = bridge
        self._reader = reader
        self._writer = writer
        self._pending: asyncio.Task[None] | None = None
        self._pending_cmd: str | None = None
        self._abort = asyncio.Event()
        self._page: PageBuffer | None = None
        self._used_link = False

    async def run(self) -> None:
        """Read commands until EOF, then release the printer link to the hold timer."""
        bridge = self._bridge
        if bridge.session_active:
            await self._send({"ok": False, "error": "busy"})
            self._writer.close()
            return
        bridge.session_active = True
        try:
            await self._loop()
        finally:
            if self._pending is not None:
                await self._request_abort()
                await asyncio.gather(self._pending, return_exceptions=True)
            bridge.session_active = False
            if self._used_link:
                bridge.start_hold()
            self._writer.close()

    async def _loop(self) -> None:
        while True:
            try:
                obj, payload = await read_message(self._reader)
            except ProtocolError as exc:
                await self._send({"ok": False, "error": str(exc)})
                return
            except (asyncio.IncompleteReadError, ConnectionError, OSError):
                return
            cmd = obj.get("cmd")
            if cmd == "abort":
                await self._request_abort()
                await self._send({"ok": True, "cmd": "abort"})
                continue
            if self._pending is not None:
                await self._send({"ok": False, "cmd": cmd, "error": "busy"})
                continue
            handler = self._handlers().get(cmd)
            if handler is None:
                await self._send(
                    {"ok": False, "cmd": cmd, "error": f"unknown command {cmd!r}"}
                )
                continue
            self._pending_cmd = cmd
            self._abort = asyncio.Event()
            self._pending = asyncio.create_task(
                self._run_command(cmd, handler, obj, payload)
            )
            self._pending.add_done_callback(lambda _t: self._clear_pending())

    def _clear_pending(self) -> None:
        self._pending = None
        self._pending_cmd = None

    async def _run_command(
        self,
        cmd: str,
        handler: Callable[[dict[str, Any], bytes], Awaitable[dict[str, Any]]],
        obj: dict[str, Any],
        payload: bytes,
    ) -> None:
        try:
            result = await handler(obj, payload)
        except asyncio.CancelledError:
            await self._send({"ok": False, "cmd": cmd, "error": "cancelled"})
        except CommandError as exc:
            await self._send({"ok": False, "cmd": cmd, "error": str(exc)})
        except Exception as exc:
            logger.exception("command %s failed", cmd)
            await self._send(
                {"ok": False, "cmd": cmd, "error": f"{type(exc).__name__}: {exc}"}
            )
        else:
            await self._send({"ok": True, "cmd": cmd, **result})

    async def _request_abort(self) -> None:
        self._abort.set()

    async def _pause(self, seconds: float) -> None:
        """Sleep, waking early when an abort arrives."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._abort.wait(), seconds)

    async def _send(self, obj: dict[str, Any]) -> None:
        with contextlib.suppress(ConnectionError, OSError):
            self._writer.write(encode_message(obj))
            await self._writer.drain()

    async def _event(self, name: str, **data: Any) -> None:
        await self._send({"event": name, **data})

    def _push(self, name: str, **data: Any) -> None:
        """Queue an event without yielding, so it precedes any later reply."""
        with contextlib.suppress(ConnectionError, OSError):
            self._writer.write(encode_message({"event": name, **data}))

    def _handlers(
        self,
    ) -> dict[str, Callable[[dict[str, Any], bytes], Awaitable[dict[str, Any]]]]:
        return {
            "discover": self._cmd_discover,
            "open": self._cmd_open,
            "close": self._cmd_close,
            "status": self._cmd_status,
            "identify": self._cmd_identify,
            "test_page": self._cmd_test_page,
            "wait_ready": self._cmd_wait_ready,
            "page_begin": self._cmd_page_begin,
            "lines": self._cmd_lines,
            "page_end": self._cmd_page_end,
            "eject": self._cmd_eject,
        }

    # ------------------------------------------------------------------
    # Link and status
    # ------------------------------------------------------------------

    async def _cmd_discover(
        self, obj: dict[str, Any], _payload: bytes
    ) -> dict[str, Any]:
        timeout = float(obj.get("timeout", 5.0))
        devices = await self._bridge.discover(timeout)
        return {"printers": [{"name": d.name, "address": d.address} for d in devices]}

    async def _cmd_open(self, obj: dict[str, Any], _payload: bytes) -> dict[str, Any]:
        """Bring the link up if reachable; ``wait_ready`` keeps retrying otherwise."""
        self._used_link = True
        address = obj.get("address")
        try:
            await self._bridge.connect(
                discovery_timeout=5.0, address=str(address) if address else None
            )
        except ConnectionError as exc:
            logger.info("Printer not reachable at open: %s", exc)
            return {"connected": False}
        return {"connected": True}

    async def _cmd_close(self, _obj: dict[str, Any], _payload: bytes) -> dict[str, Any]:
        self._bridge.start_hold()
        return {}

    async def _cmd_status(
        self, _obj: dict[str, Any], _payload: bytes
    ) -> dict[str, Any]:
        bridge = self._bridge
        if not bridge.connected or bridge.printer is None:
            return {"connected": False, "battery": bridge.last_battery}
        printer = bridge.printer
        lid = await printer.query_lid(timeout=1.0)
        paper = await printer.query_paper(timeout=1.0)
        battery = await printer.query_battery(timeout=1.0)
        if battery is not None:
            bridge.last_battery = battery
        else:
            battery = bridge.last_battery
        return {
            "connected": True,
            "lid": lid.value if lid is not None else None,
            "paper": paper.value if paper is not None else None,
            "battery": battery,
        }

    async def _cmd_identify(
        self, _obj: dict[str, Any], _payload: bytes
    ) -> dict[str, Any]:
        """Make the printer noticeable: eject a loaded sheet, then pulse the feed.

        Raises:
            CommandError: When the printer cannot be reached.
        """
        self._used_link = True
        bridge = self._bridge
        if not bridge.connected:
            try:
                await bridge.connect(discovery_timeout=5.0)
            except ConnectionError as exc:
                raise CommandError(f"printer not reachable: {exc}") from exc
        printer = self._require_printer()
        if await printer.query_paper(timeout=1.0) == PaperState.PRESENT:
            await printer.eject_paper()
        for _ in range(_IDENTIFY_PULSES):
            await printer.feed(_IDENTIFY_FEED_LINES)
            await asyncio.sleep(_IDENTIFY_PAUSE_SECONDS)
        return {}

    async def _cmd_test_page(
        self, obj: dict[str, Any], _payload: bytes
    ) -> dict[str, Any]:
        """Render the test page as a PNG and reply with its path.

        Raises:
            CommandError: When the printer cannot be reached.
        """
        self._used_link = True
        bridge = self._bridge
        if not bridge.connected:
            try:
                await bridge.connect(discovery_timeout=5.0)
            except ConnectionError as exc:
                raise CommandError(f"printer not reachable: {exc}") from exc
        printer = self._require_printer()
        device = await printer.query_device_info(timeout=1.0)
        versions = obj.get("versions") or {}
        info = PageInfo(
            printer_name=str(obj.get("printer_name", "Phomemo M08F")),
            address=getattr(printer, "address", None),
            firmware=device.firmware,
            serial=device.serial,
            battery=device.battery,
            auto_off_minutes=device.auto_off_minutes,
            chunk_bytes=getattr(printer, "chunk_bytes", None),
            versions={str(k): str(v) for k, v in versions.items()},
            socket_path=str(bridge.config.socket_path),
        )
        length_mm = bridge.profile.sheet_length_mm or 297.0
        directory = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
        path = directory / "phomemo-testpage.png"
        img = await asyncio.to_thread(render_test_page, info, bridge.profile, length_mm)
        await asyncio.to_thread(save_test_page, img, path, bridge.profile.dpi)
        return {"path": str(path)}

    async def _cmd_eject(self, _obj: dict[str, Any], _payload: bytes) -> dict[str, Any]:
        self._used_link = True
        printer = self._require_printer()
        return {"ejected": await printer.eject_paper()}

    def _require_printer(self) -> Any:
        bridge = self._bridge
        if not bridge.connected or bridge.printer is None:
            raise CommandError("not connected")
        return bridge.printer

    # ------------------------------------------------------------------
    # Waiting for a sheet
    # ------------------------------------------------------------------

    async def _cmd_wait_ready(
        self, obj: dict[str, Any], _payload: bytes
    ) -> dict[str, Any]:
        settle = float(obj.get("settle", self._bridge.config.settle_seconds))
        await self._wait_ready(settle, "no-sheet")
        return {}

    async def _wait_ready(self, settle: float, empty_reason: str) -> None:
        """Block until a sheet is seated, pushing ``waiting`` events meanwhile.

        Args:
            settle: Seconds to let an inserted sheet seat before returning.
            empty_reason: Reason pushed while no sheet is present (``no-sheet``,
                or ``short-sheet`` after a sheet ran out).

        Raises:
            CommandError: ``cancelled`` when an abort arrives.
        """
        bridge = self._bridge
        abort = self._abort
        report = self._reporter()
        timeouts = 0

        while True:
            if abort.is_set():
                raise CommandError("cancelled")
            if not bridge.connected:
                await self._connect_once(report)
                continue
            printer = bridge.printer
            assert printer is not None
            try:
                ready, reason = await printer.check_ready(timeout=2.0)
            except ConnectionError as exc:
                logger.info("Link lost while waiting: %s", exc)
                continue
            if ready:
                if settle <= 0:
                    return
                try:
                    await printer.wait_for_ready(
                        timeout=10.0, poll=_POLL_SECONDS, settle=settle
                    )
                except TimeoutError:
                    continue
                except ConnectionError as exc:
                    logger.info("Link lost while settling: %s", exc)
                    continue
                return
            if reason.startswith("Could not query"):
                timeouts += 1
                if timeouts >= _MUTE_THRESHOLD:
                    timeouts = 0
                    logger.info("Printer not answering; reconnecting")
                    try:
                        await printer.reconnect()
                    except ConnectionError:
                        await self._pause(_RETRY_SECONDS)
                    continue
            else:
                timeouts = 0
                await report("lid-open" if reason.startswith("Lid") else empty_reason)
            await self._pause(_POLL_SECONDS)

    def _reporter(self) -> _Reporter:
        """A ``waiting`` event pusher that only reports state changes."""
        return _Reporter(self)

    async def _connect_once(self, report: _Reporter) -> None:
        """One attempt to bring the link up, reporting why it is down.

        ``connecting`` is pushed before the first attempt of an outage; a
        failed attempt pushes ``adapter-off`` when Bluetooth itself is
        unavailable, else ``printer-off``.
        """
        if report.state is None:
            await report("connecting")
        try:
            await self._bridge.connect(discovery_timeout=5.0)
        except ConnectionError as exc:
            await report(
                "adapter-off" if "adapter" in str(exc).lower() else "printer-off"
            )
            await self._pause(_RETRY_SECONDS)

    # ------------------------------------------------------------------
    # Page pipeline
    # ------------------------------------------------------------------

    async def _cmd_page_begin(
        self, obj: dict[str, Any], _payload: bytes
    ) -> dict[str, Any]:
        try:
            width = int(obj["width"])
            length_rows = int(obj["length_rows"])
            bits = int(obj.get("bits", 8))
        except (KeyError, TypeError, ValueError) as exc:
            raise CommandError(
                f"page_begin needs width and length_rows: {exc}"
            ) from exc
        if bits not in (1, 8):
            raise CommandError("bits must be 1 or 8")
        if bits == 1 and width % 8:
            raise CommandError("1-bit pages need a width that is a multiple of 8")
        if width <= 0 or length_rows <= 0:
            raise CommandError("width and length_rows must be positive")
        tone_name = str(obj.get("tone", "auto"))
        if tone_name == "auto":
            content = str(obj.get("content", "auto"))
            tone = (
                ToneMode.THRESHOLD
                if content in ("text", "graphic")
                else ToneMode.DIFFUSION
            )
        else:
            try:
                tone = ToneMode(tone_name)
            except ValueError as exc:
                raise CommandError(f"unknown tone {tone_name!r}") from exc
        density_name = str(obj.get("density", "medium"))
        if density_name not in _DENSITY:
            raise CommandError(f"unknown density {density_name!r}")
        media_length = obj.get("media_length_mm")
        self._page = PageBuffer(
            width=width,
            length_rows=length_rows,
            bits=bits,
            tone=tone,
            density=_DENSITY[density_name],
            media_length_mm=None if media_length is None else float(media_length),
            rotate=bool(obj.get("rotate", False)),
        )
        return {}

    async def _cmd_lines(self, obj: dict[str, Any], payload: bytes) -> dict[str, Any]:
        page = self._page
        if page is None:
            raise CommandError("no page in progress")
        count = int(obj.get("count", 0))
        if count <= 0 or len(payload) != count * page.row_bytes:
            raise CommandError(
                f"expected {count * page.row_bytes} bytes for {count} rows, "
                f"got {len(payload)}"
            )
        if page.rows + count > page.length_rows:
            raise CommandError(
                f"{page.rows + count} rows exceed the declared length_rows "
                f"{page.length_rows}"
            )
        page.data += payload
        page.rows += count
        return {"rows": page.rows}

    async def _cmd_page_end(
        self, _obj: dict[str, Any], _payload: bytes
    ) -> dict[str, Any]:
        page = self._page
        if page is None:
            raise CommandError("no page in progress")
        if page.rows != page.length_rows:
            raise CommandError(f"received {page.rows} of {page.length_rows} rows")
        printer = self._require_printer()
        bridge = self._bridge
        self._used_link = True
        try:
            # Dithering a full page takes a moment; keep the loop free for
            # the abort command meanwhile.
            prepared = await asyncio.to_thread(
                prepare_page,
                page.image(),
                bridge.profile,
                page.media_length_mm,
                page.tone,
                page.rotate,
            )
            bitmap = await asyncio.to_thread(image_to_bitmap, prepared)
            height = prepared.height
            # An interrupted page is printed again on a fresh sheet; only a
            # cancel or a lost link ends the attempt loop.
            while True:
                try:
                    await self._print_page(printer, bitmap, height, page.density)
                except SheetRanOut as exc:
                    logger.warning("Sheet ran out: %s; waiting for the next sheet", exc)
                    await self._recover_link()
                    await self._eject_remainder(printer)
                    await self._wait_for_fresh_sheet("short-sheet")
                    continue
                except PrintAborted as exc:
                    if exc.reason == "cancelled":
                        await asyncio.sleep(bridge.config.drain_seconds)
                        if not await printer.eject_paper():
                            logger.warning("Sheet not ejected after the cancel")
                        raise CommandError(exc.reason) from exc
                    # No reconnect here: the lid check must start at once so
                    # the moment the lid closes is caught, not a reconnect later.
                    logger.warning(
                        "Page aborted: %s; waiting to print it again", exc.reason
                    )
                    await self._wait_for_fresh_sheet()
                    continue
                except ConnectionError as exc:
                    logger.warning(
                        "Link lost mid-page: %s; waiting for the printer", exc
                    )
                    await self._wait_for_fresh_sheet()
                    continue
                except (TimeoutError, OSError) as exc:
                    raise CommandError(f"connection lost: {exc}") from exc
                break
            await printer.eject_paper()
            return {"impressions": 1}
        finally:
            self._page = None

    async def _print_page(
        self, printer: Any, bitmap: bytes, height: int, density: Density
    ) -> None:
        """Send one page and push progress events until the motor stops."""
        last = -1

        def on_progress(_sent: int, _total: int) -> None:
            nonlocal last
            percent = int(100 * printer.rows_sent / height) // 5 * 5 if height else 100
            if percent != last:
                last = percent
                self._push("progress", percent=percent)

        await printer.print_bitmap(
            bitmap,
            height,
            density=density,
            abort=self._abort,
            on_progress=on_progress,
            completion_timeout=self._bridge.config.completion_timeout,
        )
        if last != 100:
            await self._event("progress", percent=100)

    async def _wait_for_fresh_sheet(self, empty_reason: str = "no-sheet") -> None:
        """Wait for the lid to close, drop a sheet already inside, wait for a new one.

        A sheet sensed as soon as the lid is closed may be the interrupted one
        at an unknown position, so it is ejected. A sheet inserted after that
        first check is taken as fresh and seated. The lid is polled at once
        and quickly so that first check lands right after the lid closes; a
        printer that stops answering is reconnected.

        Raises:
            CommandError: ``cancelled`` when an abort arrives meanwhile.
        """
        bridge = self._bridge
        abort = self._abort
        report = self._reporter()
        while not bridge.connected:
            if abort.is_set():
                raise CommandError("cancelled")
            await self._connect_once(report)
        printer = self._require_printer()
        timeouts = 0
        while True:
            if abort.is_set():
                raise CommandError("cancelled")
            try:
                lid = await printer.query_lid(timeout=1.0)
            except ConnectionError as exc:
                logger.info("Link lost while waiting for the lid: %s", exc)
                lid = None
            if lid == LidState.CLOSED:
                break
            if lid is None:
                timeouts += 1
                if timeouts >= _MUTE_THRESHOLD:
                    timeouts = 0
                    await self._recover_link()
            else:
                await report("lid-open")
            await self._pause(_LID_POLL_SECONDS)

        try:
            paper = await printer.query_paper(timeout=1.0)
        except ConnectionError:
            paper = None
        if paper == PaperState.PRESENT:
            logger.info("Sheet still inside after the interruption; ejecting it")
            await printer.eject_paper()
        await self._wait_ready(self._bridge.config.settle_seconds, empty_reason)

    async def _eject_remainder(self, printer: Any) -> None:
        """Clear a short sheet still held by the rollers after an overrun."""
        try:
            await printer.eject_paper()
        except (ConnectionError, OSError, TimeoutError) as exc:
            logger.warning("Eject after sheet overrun failed: %s", exc)

    async def _recover_link(self) -> None:
        printer = self._bridge.printer
        if printer is None:
            return
        try:
            await printer.reconnect()
        except ConnectionError as exc:
            logger.warning("Reconnect after sheet overrun failed: %s", exc)
