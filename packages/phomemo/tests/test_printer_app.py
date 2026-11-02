"""End-to-end tests of the C printer application against a fake bridge.

The tests start the built ``phomemo-printer-app`` as a private server whose
state, spool and control socket live under the test's temporary directory,
and serve it a bridge daemon whose printer is the scripted ``FakePrinter``.
They are skipped when the binary has not been built (``make -C printer-app``).
"""

import asyncio
import os
import re
import socket
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import phomemo.bridge.server as server_module
import pytest
from bleak.backends.device import BLEDevice
from phomemo.bridge.server import BridgeConfig, start_server

from tests.test_bridge_server import FakePrinter

REPO_ROOT = Path(__file__).resolve().parents[3]
BINARY = REPO_ROOT / "printer-app" / "phomemo-printer-app"
ADDRESS = "60:6E:41:23:0B:D6"
DEVICE_URI = "phomemo://" + ADDRESS.replace(":", "-")
PRINTER = "phomemo"

if not BINARY.exists():
    pytest.skip(f"{BINARY} not built", allow_module_level=True)


@pytest.fixture
async def fake_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[dict[str, str]]:
    """Serve a fake bridge and return the environment that points at it."""

    async def fake_discover(name_pattern: str, timeout: float) -> list[BLEDevice]:
        return [BLEDevice(address=ADDRESS, name="M08F", details=None)]

    monkeypatch.setattr(server_module, "discover", fake_discover)
    FakePrinter.instances.clear()
    config = BridgeConfig(
        socket_path=tmp_path / "bridge.sock", hold_seconds=0.2, drain_seconds=0.0
    )
    server = await start_server(config, printer_factory=FakePrinter)
    env = {**os.environ, "PHOMEMO_BRIDGE_SOCKET": str(config.socket_path)}
    try:
        yield env
    finally:
        server.close()
        server.close_clients()


class AppServer:
    """A running printer application server.

    Attributes:
        env: Environment for client subcommands (points at the server's
            control socket and the fake bridge).
        url: Base IPP URL of the server.
    """

    def __init__(self, env: dict[str, str], port: int) -> None:
        self.env = env
        self.url = f"ipp://localhost:{port}"

    def printer_url(self, name: str = PRINTER) -> str:
        return f"{self.url}/ipp/print/{name}"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


@pytest.fixture
async def app_server(
    fake_bridge: dict[str, str], tmp_path: Path
) -> AsyncIterator[AppServer]:
    """Run the printer application server for the duration of a test.

    PAPPL derives its control socket from ``TMPDIR`` and its state and
    configuration files from ``HOME`` and ``XDG_CONFIG_HOME``, so all three
    point into the temporary directory. The IPP listener is bound to
    localhost on a free port for ipptool.
    """
    env = {
        **fake_bridge,
        "TMPDIR": str(tmp_path),
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    (tmp_path / "config").mkdir()
    log_file = tmp_path / "app.log"
    port = free_port()
    proc = subprocess.Popen(
        [
            str(BINARY),
            "server",
            "-o",
            "listen-hostname=localhost",
            "-o",
            f"server-port={port}",
            "-o",
            f"spool-directory={tmp_path / 'spool'}",
            "-o",
            f"log-file={log_file}",
            "-o",
            "log-level=debug",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    socket = tmp_path / f"phomemo-printer-app{os.getuid()}.sock"
    for _ in range(100):
        if socket.exists() or proc.poll() is not None:
            break
        await asyncio.sleep(0.1)
    assert proc.poll() is None, f"server exited early, see {log_file}"
    assert socket.exists(), f"server socket never appeared, see {log_file}"
    try:
        yield AppServer(env, port)
    finally:
        proc.terminate()
        await asyncio.to_thread(proc.wait, 10)


async def run_app(env: dict[str, str], *args: str) -> tuple[int, str, str]:
    """Run a printer application subcommand and return exit code, stdout and stderr."""
    proc = await asyncio.to_thread(
        subprocess.run,
        [str(BINARY), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


async def add_printer(server: AppServer, name: str = PRINTER) -> None:
    """Add a printer for the fake device to the running server."""
    code, _, err = await run_app(
        server.env, "add", "-d", name, "-m", "m08f", "-v", DEVICE_URI
    )
    assert code == 0, err


GET_ATTRIBUTES_TEST = """{
  NAME "Get all printer attributes"
  OPERATION Get-Printer-Attributes
  GROUP operation-attributes-tag
  ATTR charset attributes-charset utf-8
  ATTR language attributes-natural-language en
  ATTR uri printer-uri $uri
  ATTR keyword requested-attributes all
  STATUS successful-ok
}
"""


async def printer_attributes(
    server: AppServer, tmp_path: Path, name: str = PRINTER
) -> dict[str, str]:
    """Fetch the printer's attributes through ipptool, as name to value text.

    The request asks for ``all`` alone: CUPS expands a list such as
    ``all,media-col-database`` into its table of standard attribute names,
    which drops vendor attributes from the response.
    """
    test_file = tmp_path / "get-attributes.test"
    test_file.write_text(GET_ATTRIBUTES_TEST)
    proc = await asyncio.to_thread(
        subprocess.run,
        ["ipptool", "-tv", server.printer_url(name), str(test_file)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    attrs: dict[str, str] = {}
    for match in re.finditer(r"^\s+([\w-]+) \([^)]*\) = (.*)$", proc.stdout, re.M):
        attrs[match.group(1)] = match.group(2)
    return attrs


async def test_devices_lists_fake_printer(app_server: AppServer) -> None:
    code, out, err = await run_app(app_server.env, "devices")
    assert code == 0, err
    assert DEVICE_URI in out


async def test_printer_attributes(app_server: AppServer, tmp_path: Path) -> None:
    await add_printer(app_server)
    attrs = await printer_attributes(app_server, tmp_path)
    assert attrs["printer-make-and-model"] == "Phomemo M08F"
    assert set(attrs["media-supported"].split(",")) == {
        "iso_a4_210x297mm",
        "iso_a5_148x210mm",
    }
    assert attrs["media-default"] == "iso_a4_210x297mm"
    assert attrs["pwg-raster-document-resolution-supported"] == "203dpi"
    assert set(attrs["pwg-raster-document-type-supported"].split(",")) >= {
        "sgray_8",
        "black_1",
    }
    assert attrs["phomemo-tone-supported"] == "auto,threshold,ordered,diffusion"
    assert attrs["phomemo-tone-default"] == "auto"
