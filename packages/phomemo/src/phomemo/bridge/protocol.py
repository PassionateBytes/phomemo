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

"""Wire format of the bridge socket.

Every message is one JSON object on its own line. A message that carries
raw bytes (raster rows) states their length in ``"bytes"`` and the bytes
follow the newline immediately. Replies and pushed events use the same
framing in the other direction.
"""

import asyncio
import json
from typing import Any

MAX_LINE = 64 * 1024
MAX_PAYLOAD = 16 * 1024 * 1024


class ProtocolError(ValueError):
    """A message violated the wire format."""


def encode_message(obj: dict[str, Any], payload: bytes = b"") -> bytes:
    """Serialise a message, attaching ``payload`` and its ``bytes`` count.

    Args:
        obj: The message fields.
        payload: Raw bytes to send after the line.

    Returns:
        Bytes ready to write to the socket.
    """
    if payload:
        obj = {**obj, "bytes": len(payload)}
    return json.dumps(obj).encode() + b"\n" + payload


async def read_message(reader: asyncio.StreamReader) -> tuple[dict[str, Any], bytes]:
    """Read one message and its payload, if any.

    Args:
        reader: Stream to read from.

    Returns:
        The message object and its raw payload (empty when none).

    Raises:
        ProtocolError: On malformed JSON, a non-object message, an
            over-long line, or an out-of-range payload length.
        asyncio.IncompleteReadError: If the stream ends mid-message.
    """
    try:
        line = await reader.readuntil(b"\n")
    except asyncio.LimitOverrunError as exc:
        raise ProtocolError(f"line exceeds {MAX_LINE} bytes") from exc
    if len(line) > MAX_LINE:
        raise ProtocolError(f"line exceeds {MAX_LINE} bytes")
    try:
        obj = json.loads(line)
    except ValueError as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("message must be a JSON object")
    size = obj.get("bytes", 0)
    if not isinstance(size, int) or size < 0 or size > MAX_PAYLOAD:
        raise ProtocolError(f"invalid payload length {size!r}")
    payload = await reader.readexactly(size) if size else b""
    return obj, payload
