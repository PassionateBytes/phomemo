"""Client for the bridge socket, used by the CLI and by printer-application tests."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self

from PIL import Image

from phomemo.bridge.protocol import encode_message, read_message

MEDIA = {
    "a4": (297.0, False),
    "a5": (148.0, True),
    "roll": (None, False),
}
QUALITY = {"draft": "low", "normal": "medium", "high": "high"}
_ROWS_PER_MESSAGE = 64


class BridgeError(RuntimeError):
    """The bridge refused or failed a command; the message is its ``error``."""


class BridgeClient:
    """One connection to the bridge.

    Args:
        socket_path: The bridge's unix socket.
        on_event: Called with each pushed event while a reply is pending.
    """

    def __init__(
        self,
        socket_path: Path,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._path = socket_path
        self._on_event = on_event
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: str | None = None

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Open the socket connection."""
        self._reader, self._writer = await asyncio.open_unix_connection(str(self._path))

    async def disconnect(self) -> None:
        """Close the socket connection."""
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def send(self, obj: dict[str, Any], payload: bytes = b"") -> None:
        """Send a command without waiting for its reply."""
        assert self._writer is not None, "not connected"
        if obj.get("cmd") != "abort":
            self._pending = obj.get("cmd")
        self._writer.write(encode_message(obj, payload))
        await self._writer.drain()

    async def reply(self) -> dict[str, Any]:
        """Read the reply to the pending command, dispatching events on the way.

        The bridge acknowledges an ``abort`` sent while another command is
        pending before it answers that command; the acknowledgement is
        skipped here.

        Raises:
            BridgeError: If the reply reports ``ok: false``.
        """
        assert self._reader is not None, "not connected"
        while True:
            obj, _ = await read_message(self._reader)
            if "event" in obj:
                if self._on_event is not None:
                    self._on_event(obj)
                continue
            if obj.get("cmd") == "abort" and self._pending != "abort":
                continue
            if not obj.get("ok"):
                raise BridgeError(obj.get("error", "unknown error"))
            return obj

    async def call(self, obj: dict[str, Any], payload: bytes = b"") -> dict[str, Any]:
        """Send a command and return its reply."""
        await self.send(obj, payload)
        return await self.reply()

    async def discover(self, timeout: float = 5.0) -> list[dict[str, str]]:
        return (await self.call({"cmd": "discover", "timeout": timeout}))["printers"]

    async def open(self) -> None:
        await self.call({"cmd": "open"})

    async def close(self) -> None:
        await self.call({"cmd": "close"})

    async def status(self) -> dict[str, Any]:
        reply = await self.call({"cmd": "status"})
        return {k: v for k, v in reply.items() if k not in ("ok", "cmd")}

    async def wait_ready(self, settle: float | None = None) -> None:
        obj: dict[str, Any] = {"cmd": "wait_ready"}
        if settle is not None:
            obj["settle"] = settle
        await self.call(obj)

    async def page_begin(
        self,
        width: int,
        length_rows: int,
        bits: int = 8,
        tone: str = "auto",
        content: str = "auto",
        density: str = "medium",
        media_length_mm: float | None = 297.0,
        rotate: bool = False,
    ) -> None:
        await self.call(
            {
                "cmd": "page_begin",
                "width": width,
                "length_rows": length_rows,
                "bits": bits,
                "tone": tone,
                "content": content,
                "density": density,
                "media_length_mm": media_length_mm,
                "rotate": rotate,
            }
        )

    async def lines(self, count: int, payload: bytes) -> None:
        await self.call({"cmd": "lines", "count": count}, payload)

    async def page_end(self) -> int:
        return int((await self.call({"cmd": "page_end"}))["impressions"])

    async def eject(self) -> bool:
        return bool((await self.call({"cmd": "eject"}))["ejected"])

    async def identify(self) -> None:
        """Eject a loaded sheet, then pulse the feed three times."""
        await self.call({"cmd": "identify"})

    async def test_page(self, versions: dict[str, str] | None = None) -> Path:
        """Render the test page and return the PNG's path.

        Args:
            versions: Component versions to print, by name.
        """
        reply = await self.call(
            {
                "cmd": "test_page",
                "printer_name": "Phomemo M08F",
                "versions": versions or {},
            }
        )
        return Path(reply["path"])

    async def print_test_page(self, quality: str = "normal") -> int:
        """Render the test page and print it through the bridge.

        The page covers the area below the sheet's unprintable lead, so it
        gets that lead as white rows on top before the normal page
        preparation drops them again.

        Args:
            quality: ``draft``, ``normal`` or ``high``.

        Returns:
            Impressions printed (1).
        """
        path = await self.test_page()
        page = Image.open(path).convert("L")
        lead = round(10 / 25.4 * 203)
        canvas = Image.new("L", (page.width, page.height + lead), 255)
        canvas.paste(page, (0, lead))
        padded = path.with_name("phomemo-testpage-sheet.png")
        canvas.save(padded)
        return await self.print_image(padded, media="a4", quality=quality)

    async def abort(self) -> None:
        await self.call({"cmd": "abort"})

    async def print_image(
        self,
        path: Path,
        media: str = "a4",
        tone: str = "auto",
        quality: str = "normal",
        content: str = "auto",
        abort_after: float | None = None,
    ) -> int:
        """Print an image file as one page: open, wait for a sheet, stream, end.

        Args:
            path: Image file readable by Pillow.
            media: ``a4``, ``a5`` (fed long edge first, page rotated) or ``roll``.
            tone: ``auto`` or a ``ToneMode`` value.
            quality: ``draft``, ``normal`` or ``high`` (maps to density).
            content: ``auto``, ``text``, ``graphic`` or ``photo``.
            abort_after: Seconds after ``page_end`` to send ``abort``; for testing.

        Returns:
            Impressions printed (1).

        Raises:
            BridgeError: If any step fails.
            KeyError: If ``media`` or ``quality`` is not known.
        """
        length_mm, rotate = MEDIA[media]
        density = QUALITY[quality]
        img = Image.open(path).convert("L")
        await self.open()
        await self.wait_ready()
        await self.page_begin(
            img.width,
            img.height,
            bits=8,
            tone=tone,
            content=content,
            density=density,
            media_length_mm=length_mm,
            rotate=rotate,
        )
        raw = img.tobytes()
        for start in range(0, img.height, _ROWS_PER_MESSAGE):
            count = min(_ROWS_PER_MESSAGE, img.height - start)
            await self.lines(
                count, raw[start * img.width : (start + count) * img.width]
            )
        await self.send({"cmd": "page_end"})
        if abort_after is not None:
            await asyncio.sleep(abort_after)
            await self.send({"cmd": "abort"})
        reply = await self.reply()
        await self.close()
        return int(reply["impressions"])
