"""One client connection to the bridge: command dispatch and the page pipeline."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from phomemo.bridge.protocol import ProtocolError, encode_message, read_message
from phomemo.bridge.server import Bridge
from phomemo.imaging import ToneMode, image_to_bitmap, prepare_page
from phomemo.printer import PrintAborted, SheetRanOut
from phomemo.protocol import Density

logger = logging.getLogger(__name__)

_DENSITY = {"low": Density.LOW, "medium": Density.MEDIUM, "high": Density.HIGH}
_RETRY_SECONDS = 0.2
_POLL_SECONDS = 0.5
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
            bridge.start_hold()
            self._writer.close()

    async def _loop(self) -> None:
        while True:
            try:
                obj, payload = await read_message(self._reader)
            except ProtocolError as exc:
                await self._send({"ok": False, "error": str(exc)})
                continue
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
        if self._pending is not None and self._pending_cmd == "wait_ready":
            self._pending.cancel()

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

    async def _cmd_open(self, _obj: dict[str, Any], _payload: bytes) -> dict[str, Any]:
        """Bring the link up if reachable; ``wait_ready`` keeps retrying otherwise."""
        try:
            await self._bridge.connect(discovery_timeout=5.0)
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
            return {"connected": False}
        printer = bridge.printer
        lid = await printer.query_lid(timeout=1.0)
        paper = await printer.query_paper(timeout=1.0)
        battery = await printer.query_battery(timeout=1.0)
        return {
            "connected": True,
            "lid": lid.value if lid is not None else None,
            "paper": paper.value if paper is not None else None,
            "battery": battery,
        }

    async def _cmd_eject(self, _obj: dict[str, Any], _payload: bytes) -> dict[str, Any]:
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
        bridge = self._bridge
        settle = float(obj.get("settle", bridge.config.settle_seconds))
        self._abort = asyncio.Event()
        state: str | None = None
        timeouts = 0

        async def report(reason: str) -> None:
            nonlocal state
            if state != reason:
                state = reason
                await self._event("waiting", reason=reason)

        while True:
            if not bridge.connected:
                await report("printer-off")
                try:
                    await bridge.connect(discovery_timeout=5.0)
                except ConnectionError:
                    await asyncio.sleep(_RETRY_SECONDS)
                continue
            printer = bridge.printer
            assert printer is not None
            ready, reason = await printer.check_ready(timeout=2.0)
            if ready:
                break
            if reason.startswith("Could not query"):
                timeouts += 1
                if timeouts >= _MUTE_THRESHOLD:
                    timeouts = 0
                    logger.info("Printer not answering; reconnecting")
                    try:
                        await printer.reconnect()
                    except ConnectionError:
                        await asyncio.sleep(_RETRY_SECONDS)
                    continue
            else:
                timeouts = 0
                await report("lid-open" if reason.startswith("Lid") else "no-sheet")
            await asyncio.sleep(_POLL_SECONDS)

        if settle > 0:
            printer = bridge.printer
            assert printer is not None
            await printer.wait_for_ready(
                timeout=10.0, poll=_POLL_SECONDS, settle=settle
            )
        return {}

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
        try:
            prepared = prepare_page(
                page.image(),
                bridge.profile,
                page.media_length_mm,
                page.tone,
                page.rotate,
            )
            bitmap = image_to_bitmap(prepared)
            height = prepared.height
            abort = asyncio.Event()
            self._abort = abort
            last = -1

            def on_progress(_sent: int, _total: int) -> None:
                nonlocal last
                percent = (
                    int(100 * printer.rows_sent / height) // 5 * 5 if height else 100
                )
                if percent != last:
                    last = percent
                    self._push("progress", percent=percent)

            try:
                await printer.print_bitmap(
                    bitmap,
                    height,
                    density=page.density,
                    abort=abort,
                    on_progress=on_progress,
                    completion_timeout=bridge.config.completion_timeout,
                )
            except SheetRanOut as exc:
                logger.warning("Sheet ran out: %s", exc)
                await self._recover_link()
                raise CommandError(exc.reason) from exc
            except PrintAborted as exc:
                await asyncio.sleep(bridge.config.drain_seconds)
                await printer.eject_paper()
                raise CommandError(exc.reason) from exc
            except (TimeoutError, ConnectionError, OSError) as exc:
                raise CommandError(f"connection lost: {exc}") from exc
            if last != 100:
                await self._event("progress", percent=100)
            await printer.eject_paper()
            return {"impressions": 1}
        finally:
            self._page = None

    async def _recover_link(self) -> None:
        printer = self._bridge.printer
        if printer is None:
            return
        try:
            await printer.reconnect()
        except ConnectionError as exc:
            logger.warning("Reconnect after sheet overrun failed: %s", exc)
