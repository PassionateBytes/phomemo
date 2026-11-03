"""End-to-end tests of the C printer application against a fake bridge.

The tests start the built ``phomemo-printer-app`` as a private server whose
state, spool and control socket live under the test's temporary directory,
and serve it a bridge daemon whose printer is the scripted ``FakePrinter``.
They are skipped when the binary has not been built (``make -C printer-app``).
"""

import asyncio
import gzip
import os
import re
import shutil
import socket
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import phomemo.bridge.server as server_module
import pytest
from bleak.backends.device import BLEDevice
from phomemo.bridge.server import BridgeConfig, start_server
from phomemo.bridge.session import Session
from phomemo.events import LidState, PaperState
from phomemo.printer import SheetRanOut
from phomemo.registry import PrinterProfile, get_profile

from tests.test_bridge_server import FakePrinter

REPO_ROOT = Path(__file__).resolve().parents[3]
BINARY = REPO_ROOT / "printer-app" / "phomemo-printer-app"
ADDRESS = "AA:BB:CC:DD:EE:FF"
DEVICE_URI = "phomemo://" + ADDRESS.replace(":", "-")
PRINTER = "phomemo"

SOURCE_PDF = Path("/usr/share/cups/ipptool/onepage-a4.pdf.gz")
MULTIPAGE_PDF = Path("/usr/share/cups/ipptool/document-a4.pdf.gz")
A4_ROWS = get_profile("M08F-A4").rows_for(297.0)

if not BINARY.exists():
    pytest.skip(f"{BINARY} not built", allow_module_level=True)


class ScriptedPrinter(FakePrinter):
    """FakePrinter whose initial state a test can script before the bridge opens it."""

    paper_default = PaperState.PRESENT
    print_error_default: Exception | None = None
    reachable_default = True

    def __init__(self, profile: PrinterProfile, address: object = None) -> None:
        super().__init__(profile, address)
        self.paper = ScriptedPrinter.paper_default
        self.print_error = ScriptedPrinter.print_error_default
        self.reachable = ScriptedPrinter.reachable_default


@dataclass
class FakeBridge:
    """A served fake bridge.

    Attributes:
        env: Environment pointing clients at the bridge socket.
        page_begins: Every ``page_begin`` request the bridge received.
    """

    env: dict[str, str]
    server: Any
    page_begins: list[dict[str, Any]] = field(default_factory=list)

    @property
    def printer(self) -> FakePrinter:
        assert FakePrinter.instances, "the bridge never opened the printer"
        return FakePrinter.instances[-1]


@pytest.fixture
async def fake_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncIterator[FakeBridge]:
    """Serve a fake bridge whose printer is a ScriptedPrinter.

    An indirect parameter ``{"hold_seconds": s}`` keeps the printer link
    open that long after a job.
    """

    async def fake_discover(name_pattern: str, timeout: float) -> list[BLEDevice]:
        return [BLEDevice(address=ADDRESS, name="M08F", details=None)]

    page_begins: list[dict[str, Any]] = []
    original_page_begin = Session._cmd_page_begin

    async def recording_page_begin(
        self: Session, obj: dict[str, Any], payload: bytes
    ) -> dict[str, Any]:
        page_begins.append(obj)
        return await original_page_begin(self, obj, payload)

    monkeypatch.setattr(server_module, "discover", fake_discover)
    monkeypatch.setattr(Session, "_cmd_page_begin", recording_page_begin)
    FakePrinter.instances.clear()
    ScriptedPrinter.paper_default = PaperState.PRESENT
    ScriptedPrinter.print_error_default = None
    ScriptedPrinter.reachable_default = True
    hold = getattr(request, "param", {}).get("hold_seconds", 0.2)
    config = BridgeConfig(
        socket_path=tmp_path / "bridge.sock", hold_seconds=hold, drain_seconds=0.0
    )
    server = await start_server(config, printer_factory=ScriptedPrinter)
    env = {**os.environ, "PHOMEMO_BRIDGE_SOCKET": str(config.socket_path)}
    bridge = FakeBridge(env, server, page_begins)
    try:
        yield bridge
    finally:
        bridge.server.close()
        bridge.server.close_clients()


class AppServer:
    """A running printer application server.

    Attributes:
        env: Environment for client subcommands (points at the server's
            control socket and the fake bridge).
        url: Base IPP URL of the server.
    """

    def __init__(self, env: dict[str, str], port: int, bridge: FakeBridge) -> None:
        self.env = env
        self.url = f"ipp://localhost:{port}"
        self.bridge = bridge

    def printer_url(self, name: str = PRINTER) -> str:
        return f"{self.url}/ipp/print/{name}"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


@pytest.fixture
async def app_server(
    fake_bridge: FakeBridge, tmp_path: Path, request: pytest.FixtureRequest
) -> AsyncIterator[AppServer]:
    """Run the printer application server for the duration of a test.

    PAPPL derives its control socket from ``TMPDIR`` and its state and
    configuration files from ``HOME`` and ``XDG_CONFIG_HOME``, so all three
    point into the temporary directory. The IPP listener is bound to
    localhost on a free port for ipptool.
    """
    env = {
        **fake_bridge.env,
        "TMPDIR": str(tmp_path),
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    param = getattr(request, "param", {})
    if "bridge_socket" in param:
        env["PHOMEMO_BRIDGE_SOCKET"] = str(tmp_path / param["bridge_socket"])
    (tmp_path / "config").mkdir()
    (tmp_path / "spool").mkdir()
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
        yield AppServer(env, port, fake_bridge)
    finally:
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, 10)
        except subprocess.TimeoutExpired:
            proc.kill()
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


@pytest.fixture
async def printer(app_server: AppServer) -> AppServer:
    """The application server with the phomemo queue added."""
    await add_printer(app_server)
    return app_server


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
    assert attrs["pwg-raster-document-type-supported"] == "sgray_8"
    assert attrs["print-color-mode-supported"] == "monochrome"
    assert attrs["phomemo-tone-supported"] == "auto,threshold,ordered,diffusion"
    assert attrs["printer-icons"].count("http") == 3
    assert attrs["phomemo-tone-default"] == "auto"


PRINT_JOB_TEST = """{{
  NAME "Print a raster"
  OPERATION Print-Job
  GROUP operation-attributes-tag
  ATTR charset attributes-charset utf-8
  ATTR language attributes-natural-language en
  ATTR uri printer-uri $uri
  ATTR name requesting-user-name tester
  ATTR mimeMediaType document-format {document_format}
  GROUP job-attributes-tag
{attributes}
  FILE $filename
  STATUS successful-ok
  STATUS successful-ok-ignored-or-substituted-attributes
  EXPECT job-uri
}}
"""


async def make_raster(
    tmp_path: Path, name: str, width_pt: int, height_pt: int, pages: int = 1
) -> Path:
    """Render the first pages of the CUPS sample document as sgray_8 PWG raster."""
    gs = shutil.which("gs")
    if gs is None:
        pytest.skip("ghostscript not installed")
    pdf = tmp_path / "source.pdf"
    source = SOURCE_PDF if pages == 1 else MULTIPAGE_PDF
    pdf.write_bytes(gzip.decompress(source.read_bytes()))
    out = tmp_path / name
    await asyncio.to_thread(
        subprocess.run,
        [
            gs,
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-dFirstPage=1",
            f"-dLastPage={pages}",
            "-sDEVICE=pwgraster",
            "-r203",
            "-dFIXEDMEDIA",
            f"-dDEVICEWIDTHPOINTS={width_pt}",
            f"-dDEVICEHEIGHTPOINTS={height_pt}",
            "-dcupsColorSpace=18",
            "-dcupsBitsPerColor=8",
            f"-sOutputFile={out}",
            str(pdf),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return out


def parse_attributes(text: str) -> dict[str, str]:
    """Turn ipptool -tv output into a name to value mapping."""
    attrs: dict[str, str] = {}
    for match in re.finditer(r"^\s+([\w-]+) \([^)]*\) = (.*)$", text, re.M):
        attrs[match.group(1)] = match.group(2)
    return attrs


def start_job(
    server: AppServer,
    tmp_path: Path,
    document: Path,
    *,
    quality: int | None = None,
    tone: str | None = None,
    media: str | None = None,
    document_format: str = "image/pwg-raster",
) -> asyncio.Task[subprocess.CompletedProcess[str]]:
    """Submit a raster with ipptool in the background.

    PAPPL streams pwg-raster Print-Job requests straight into the driver and
    answers only when the job has finished, so the request runs as a task.
    """
    attributes = []
    if quality is not None:
        attributes.append(f"  ATTR enum print-quality {quality}")
    if tone is not None:
        attributes.append(f"  ATTR keyword phomemo-tone {tone}")
    if media is not None:
        attributes.append(f"  ATTR keyword media {media}")
    test_file = tmp_path / f"print-{document.name}.test"
    test_file.write_text(
        PRINT_JOB_TEST.format(
            attributes="\n".join(attributes), document_format=document_format
        )
    )
    return asyncio.create_task(
        asyncio.to_thread(
            subprocess.run,
            [
                "ipptool",
                "-tv",
                "-f",
                str(document),
                server.printer_url(),
                str(test_file),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
    )


async def finish_job(
    task: asyncio.Task[subprocess.CompletedProcess[str]],
) -> dict[str, str]:
    """Wait for a submission to return and for its job to reach a final state."""
    proc = await task
    job_uri = parse_attributes(proc.stdout).get("job-uri")
    assert job_uri, proc.stdout + proc.stderr
    return await wait_job(job_uri)


async def active_job_id(server: AppServer) -> str:
    """Poll the jobs subcommand until a job is pending or processing; return its id."""
    for _ in range(80):
        code, out, err = await run_app(server.env, "jobs", "-d", PRINTER)
        assert code == 0, err
        for line in out.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1] in {"pending", "processing"}:
                return fields[0]
        await asyncio.sleep(0.25)
    raise AssertionError("no active job appeared")


async def job_attributes(job_uri: str) -> dict[str, str]:
    proc = await asyncio.to_thread(
        subprocess.run,
        ["ipptool", "-tv", job_uri, "/usr/share/cups/ipptool/get-job-attributes.test"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return parse_attributes(proc.stdout)


async def wait_job(job_uri: str, timeout: float = 30.0) -> dict[str, str]:
    """Poll until the job reaches a final state and return its attributes."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        attrs = await job_attributes(job_uri)
        if attrs.get("job-state") in {"completed", "canceled", "aborted"}:
            return attrs
        assert asyncio.get_running_loop().time() < deadline, attrs
        await asyncio.sleep(0.25)


async def test_a4_job_prints_through_bridge(printer: AppServer, tmp_path: Path) -> None:
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    attrs = await finish_job(start_job(printer, tmp_path, raster))
    assert attrs["job-state"] == "completed", attrs
    assert attrs["job-impressions-completed"] == "1"
    assert attrs["job-state-message"] == "Page 1 printed."
    assert printer.bridge.printer.printed == [(210 * A4_ROWS, A4_ROWS, "MEDIUM")]
    assert printer.bridge.printer.ejects == 1


async def test_quality_high_maps_to_density_high(
    printer: AppServer, tmp_path: Path
) -> None:
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    attrs = await finish_job(start_job(printer, tmp_path, raster, quality=5))
    assert attrs["job-state"] == "completed", attrs
    assert printer.bridge.printer.printed[0][2] == "HIGH"


async def test_vendor_tone_option_reaches_bridge(
    printer: AppServer, tmp_path: Path
) -> None:
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    attrs = await finish_job(start_job(printer, tmp_path, raster, tone="ordered"))
    assert attrs["job-state"] == "completed", attrs
    assert printer.bridge.page_begins[0]["tone"] == "ordered"


async def test_a5_portrait_raster_is_rotated(
    printer: AppServer, tmp_path: Path
) -> None:
    raster = await make_raster(tmp_path, "a5.pwg", 420, 595)
    attrs = await finish_job(
        start_job(printer, tmp_path, raster, media="iso_a5_148x210mm")
    )
    assert attrs["job-state"] == "completed", attrs
    page = printer.bridge.page_begins[0]
    assert page["rotate"] is True
    assert page["media_length_mm"] == 148.0
    assert printer.bridge.printer.printed[0][1] == get_profile("M08F-A4").rows_for(
        148.0
    )


async def test_a5_landscape_raster_is_not_rotated_twice(
    printer: AppServer, tmp_path: Path
) -> None:
    raster = await make_raster(tmp_path, "a5.pwg", 595, 420)
    attrs = await finish_job(
        start_job(printer, tmp_path, raster, media="iso_a5_148x210mm")
    )
    assert attrs["job-state"] == "completed", attrs
    page = printer.bridge.page_begins[0]
    assert page["rotate"] is False
    assert page["media_length_mm"] == 148.0


async def test_cancel_while_waiting_for_sheet(
    printer: AppServer, tmp_path: Path
) -> None:
    ScriptedPrinter.paper_default = PaperState.ABSENT
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    task = start_job(printer, tmp_path, raster)
    job_id = await active_job_id(printer)
    await asyncio.sleep(2)
    code, _, err = await run_app(printer.env, "cancel", "-d", PRINTER, "-j", job_id)
    assert code == 0, err
    attrs = await finish_job(task)
    assert attrs["job-state"] == "canceled", attrs
    assert "job-canceled-at-device" not in attrs["job-state-reasons"]
    assert printer.bridge.printer.printed == []


async def test_short_sheet_reprints_on_the_next_sheet(
    printer: AppServer, tmp_path: Path
) -> None:
    ScriptedPrinter.print_error_default = SheetRanOut("paper ran out")
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    task = start_job(printer, tmp_path, raster)
    for _ in range(60):
        _, reasons = await printer_state(printer, tmp_path)
        if "media-empty" in reasons:
            break
        await asyncio.sleep(0.5)
    assert "media-empty" in reasons
    assert not task.done()
    printer.bridge.printer.paper = PaperState.PRESENT
    attrs = await finish_job(task)
    assert attrs["job-state"] == "completed", attrs
    assert len(printer.bridge.printer.printed) == 2
    assert "media-empty" not in (await printer_state(printer, tmp_path))[1]


async def printer_state(server: AppServer, tmp_path: Path) -> tuple[str, str]:
    attrs = await printer_attributes(server, tmp_path)
    return attrs["printer-state"], attrs.get("printer-state-reasons", "")


@pytest.mark.parametrize("app_server", [{"bridge_socket": "late.sock"}], indirect=True)
async def test_bridge_down_pauses_queue_until_bridge_returns(
    printer: AppServer, tmp_path: Path
) -> None:
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    task = start_job(printer, tmp_path, raster)
    job_id = await active_job_id(printer)
    for _ in range(40):
        state, reasons = await printer_state(printer, tmp_path)
        if state == "stopped":
            break
        await asyncio.sleep(0.25)
    assert state == "stopped", (state, reasons)
    assert not task.done()
    assert str(tmp_path / "late.sock") in (tmp_path / "app.log").read_text()

    config = BridgeConfig(
        socket_path=tmp_path / "late.sock", hold_seconds=0.2, drain_seconds=0.0
    )
    late = await start_server(config, printer_factory=ScriptedPrinter)
    try:
        attrs = await finish_job(task)
    finally:
        late.close()
        late.close_clients()
    assert attrs["job-state"] == "completed", attrs
    assert attrs["job-id"] == job_id
    assert printer.bridge.printer.printed == [(210 * A4_ROWS, A4_ROWS, "MEDIUM")]
    assert (await printer_state(printer, tmp_path))[0] != "stopped"


@pytest.mark.parametrize("fake_bridge", [{"hold_seconds": 30}], indirect=True)
async def test_idle_status_reports_lid_and_paper(
    printer: AppServer, tmp_path: Path
) -> None:
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    attrs = await finish_job(start_job(printer, tmp_path, raster))
    assert attrs["job-state"] == "completed", attrs
    fake = printer.bridge.printer

    fake.lid = LidState.OPEN
    await asyncio.sleep(2.1)
    assert "cover-open" in (await printer_state(printer, tmp_path))[1]

    fake.lid = LidState.CLOSED
    fake.paper = PaperState.ABSENT
    await asyncio.sleep(2.1)
    state, reasons = await printer_state(printer, tmp_path)
    assert "media-empty" in reasons
    assert "cover-open" not in reasons

    fake.paper = PaperState.PRESENT
    await asyncio.sleep(2.1)
    assert (await printer_state(printer, tmp_path))[1] in {"", "none"}


async def test_printer_off_shows_offline_until_it_returns(
    printer: AppServer, tmp_path: Path
) -> None:
    ScriptedPrinter.reachable_default = False
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    task = start_job(printer, tmp_path, raster)
    for _ in range(60):
        _, reasons = await printer_state(printer, tmp_path)
        if "offline" in reasons:
            break
        await asyncio.sleep(0.5)
    assert "offline" in reasons
    assert not task.done()
    printer.bridge.printer.reachable = True
    attrs = await finish_job(task)
    assert attrs["job-state"] == "completed", attrs
    assert "offline" not in (await printer_state(printer, tmp_path))[1]


async def test_identify_printer_pulses_the_feed(printer: AppServer) -> None:
    proc = await asyncio.to_thread(
        subprocess.run,
        [
            "ipptool",
            "-t",
            printer.printer_url(),
            "/usr/share/cups/ipptool/identify-printer.test",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for _ in range(40):
        if FakePrinter.instances and len(printer.bridge.printer.feeds) == 3:
            break
        await asyncio.sleep(0.25)
    assert len(printer.bridge.printer.feeds) == 3


@pytest.mark.parametrize("fake_bridge", [{"hold_seconds": 30}], indirect=True)
async def test_idle_status_reports_the_battery_as_a_supply(
    printer: AppServer, tmp_path: Path
) -> None:
    raster = await make_raster(tmp_path, "a4.pwg", 595, 842)
    attrs = await finish_job(start_job(printer, tmp_path, raster))
    assert attrs["job-state"] == "completed", attrs
    await asyncio.sleep(2.1)
    attrs = await printer_attributes(printer, tmp_path)
    assert "Battery" in attrs["printer-supply-description"]
    assert "level=77" in attrs["printer-supply"]
