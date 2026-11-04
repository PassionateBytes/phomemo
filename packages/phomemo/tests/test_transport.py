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

"""Tests for BleTransport write behaviour."""

from dataclasses import replace

import phomemo.profiles  # noqa: F401, registers built-in profiles
import phomemo.transport as transport_module
import pytest
from phomemo.registry import get_profile
from phomemo.transport import BleTransport


class FakeClient:
    """Records GATT writes instead of talking to a device."""

    def __init__(self) -> None:
        self.is_connected = True
        self.writes: list[tuple[str, bytes, bool]] = []

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool) -> None:
        self.writes.append((uuid, bytes(data), response))


def _make_transport(**overrides: object) -> tuple[BleTransport, FakeClient]:
    profile = replace(get_profile("M08F-A4"), **overrides)  # type: ignore[arg-type]
    transport = BleTransport(profile)
    client = FakeClient()
    transport._client = client  # type: ignore[assignment]
    transport._connected = True
    return transport, client


def test_default_profile_timing() -> None:
    profile = get_profile("M08F-A4")
    assert profile.write_with_response is True
    assert profile.chunk_delay_s == 0.0


@pytest.mark.asyncio
async def test_write_uses_profile_response_flag() -> None:
    transport, client = _make_transport(write_with_response=True)
    await transport.write(b"\x1b\x40")
    assert client.writes == [(transport._profile.write_uuid, b"\x1b\x40", True)]


@pytest.mark.asyncio
async def test_write_without_response_when_profile_says_so() -> None:
    transport, client = _make_transport(write_with_response=False)
    await transport.write(b"\x1b\x40")
    assert client.writes[0][2] is False


@pytest.mark.asyncio
async def test_write_chunked_zero_delay_never_sleeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, client = _make_transport(chunk_delay_s=0.0)

    async def no_sleep(_delay: float) -> None:
        raise AssertionError("sleep called with zero chunk delay")

    monkeypatch.setattr(transport_module.asyncio, "sleep", no_sleep)
    await transport.write_chunked(bytes(600))
    assert [len(w[1]) for w in client.writes] == [244, 244, 112]


@pytest.mark.asyncio
async def test_write_chunked_positive_delay_sleeps_between_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, _client = _make_transport(chunk_delay_s=0.01)
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(transport_module.asyncio, "sleep", record_sleep)
    await transport.write_chunked(bytes(600))
    assert sleeps == [0.01, 0.01]


@pytest.mark.asyncio
async def test_subscribe_failure_is_a_connection_error_even_without_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bleak.exc import BleakError

    class FlakyClient:
        is_connected = True

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def start_notify(self, uuid: str, cb: object) -> None:
            raise BleakError("GATT Protocol Error: Unlikely Error")

        @property
        def services(self) -> object:
            raise BleakError("Service Discovery has not been performed yet")

    transport = BleTransport(replace(get_profile("M08F-A4"), negotiate_mtu=False))
    monkeypatch.setattr(
        transport_module, "BleakClient", lambda address, **kw: FlakyClient()
    )
    with pytest.raises(ConnectionError, match="failed to subscribe"):
        await transport.connect("AA:BB:CC:DD:EE:FF", on_event=lambda data: None)
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_unsolicited_disconnect_clears_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Client:
        is_connected = True

        def __init__(self, address: str, disconnected_callback: object = None) -> None:
            captured["cb"] = disconnected_callback

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def start_notify(self, uuid: str, cb: object) -> None:
            pass

    transport = BleTransport(replace(get_profile("M08F-A4"), negotiate_mtu=False))
    monkeypatch.setattr(transport_module, "BleakClient", Client)
    await transport.connect("AA:BB:CC:DD:EE:FF", on_event=lambda data: None)
    assert transport.is_connected is True
    captured["cb"](None)  # type: ignore[operator]
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_write_maps_bleak_error_to_connection_error() -> None:
    from bleak.exc import BleakError

    transport, client = _make_transport()

    async def failing(uuid: str, data: bytes, response: bool) -> None:
        raise BleakError("Not connected")

    client.write_gatt_char = failing  # type: ignore[method-assign]
    with pytest.raises(ConnectionError, match="Not connected"):
        await transport.write(b"\x1b\x40")
