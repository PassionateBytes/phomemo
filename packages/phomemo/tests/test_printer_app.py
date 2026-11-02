"""End-to-end tests of the C printer application against a fake bridge.

The tests start the built ``phomemo-printer-app`` as a private server whose
state, spool and control socket live under the test's temporary directory,
and serve it a bridge daemon whose printer is the scripted ``FakePrinter``.
They are skipped when the binary has not been built (``make -C printer-app``).
"""

import asyncio
import os
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


@pytest.fixture
async def app_server(
    fake_bridge: dict[str, str], tmp_path: Path
) -> AsyncIterator[dict[str, str]]:
    """Run the printer application server and return the environment for its clients.

    PAPPL derives its control socket from ``TMPDIR`` and its state and
    configuration files from ``HOME`` and ``XDG_CONFIG_HOME``, so all three
    point into the temporary directory.
    """
    env = {
        **fake_bridge,
        "TMPDIR": str(tmp_path),
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    (tmp_path / "config").mkdir()
    log_file = tmp_path / "app.log"
    proc = subprocess.Popen(
        [
            str(BINARY),
            "server",
            "-o",
            "private-server=true",
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
        yield env
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


async def test_devices_lists_fake_printer(app_server: dict[str, str]) -> None:
    code, out, err = await run_app(app_server, "devices")
    assert code == 0, err
    assert f"phomemo://{ADDRESS}" in out
