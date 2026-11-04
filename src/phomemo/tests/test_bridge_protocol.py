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

"""Tests for the bridge wire format."""

import asyncio
import json

import pytest
from phomemo.bridge.protocol import ProtocolError, encode_message, read_message


async def _reader(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_roundtrip_without_payload() -> None:
    wire = encode_message({"cmd": "status"})
    assert wire == b'{"cmd": "status"}\n'
    obj, payload = await read_message(await _reader(wire))
    assert obj == {"cmd": "status"}
    assert payload == b""


@pytest.mark.asyncio
async def test_roundtrip_with_payload() -> None:
    rows = bytes(range(210)) * 2
    wire = encode_message({"cmd": "lines", "count": 2}, rows)
    obj, payload = await read_message(await _reader(wire))
    assert obj == {"cmd": "lines", "count": 2, "bytes": 420}
    assert payload == rows


@pytest.mark.asyncio
async def test_invalid_json_raises_protocol_error() -> None:
    with pytest.raises(ProtocolError):
        await read_message(await _reader(b"not json\n"))


@pytest.mark.asyncio
async def test_non_object_json_raises_protocol_error() -> None:
    with pytest.raises(ProtocolError):
        await read_message(await _reader(json.dumps([1, 2]).encode() + b"\n"))


@pytest.mark.asyncio
async def test_eof_raises_incomplete_read() -> None:
    with pytest.raises(asyncio.IncompleteReadError):
        await read_message(await _reader(b""))
