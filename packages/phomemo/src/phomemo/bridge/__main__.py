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

"""``phomemo-bridge`` command line: run the daemon or drive it directly.

Sub-command names follow the printer application's where both do the same
thing (``server``, ``devices``, ``status``).
"""

import argparse
import asyncio
import json
import logging
import sys
import textwrap
from pathlib import Path

from phomemo.bridge.client import MEDIA, QUALITY, BridgeClient, BridgeError
from phomemo.bridge.config import ConfigError, load_config
from phomemo.bridge.server import serve
from phomemo.imaging import ToneMode

_PRINTER_CHOICE = (
    "Which printer: the one given with --address, else the [printer] address "
    "from the configuration, else the printer linked or used last, else the only "
    "M08F a scan finds. With several printers in range and none of these, the "
    'command refuses and lists them; pick one with --address (see "devices").'
)

_COMMANDS: dict[str, tuple[str, str]] = {
    "server": (
        "run the bridge daemon",
        "Run the bridge daemon in the foreground: listen on the socket, own the "
        "Bluetooth link to the printer and serve the printer application and "
        "this command line. The packaged system service runs this.",
    ),
    "devices": (
        "list printers in range",
        "Scan for M08F printers and list their Bluetooth addresses and names. "
        "A printer shows up only while it is switched on and not linked to "
        "another host.",
    ),
    "connect": (
        "bring the printer link up",
        "Bring the Bluetooth link to the printer up. The bridge keeps it for "
        "hold_seconds afterwards (see the configuration), so later commands and "
        "jobs skip the reconnect. At each new link the bridge sets the printer's "
        "auto-off timer to auto_off_minutes.\n\n" + _PRINTER_CHOICE,
    ),
    "disconnect": (
        "drop the printer link now",
        "Drop the Bluetooth link right away instead of after the hold time, so "
        "another host (a phone, another computer) can reach the printer.",
    ),
    "status": (
        "show link, sensors and device details",
        "Show whether the bridge holds a link and, when it does, the linked "
        "printer's address, lid and paper sensors, battery, firmware, serial "
        'number and auto-off timer. Does not connect by itself; run "connect" '
        "first. With --address, reports whether that printer is the linked one.",
    ),
    "auto-off": (
        "show or set the auto-off timer",
        "Show the linked printer's auto-off timer, or set it first when MINUTES "
        "is given (a multiple of 5 up to 1275; 0 = never switch off). The "
        "bridge sets "
        "auto_off_minutes from its configuration at the next link, so change "
        'that key for a lasting setting. Needs a link; run "connect" first.',
    ),
    "print": (
        "print one image file as a page",
        "Print an image file (PNG, JPEG, anything Pillow reads) as one page, "
        "scaled to the media width, then eject the sheet.\n\n" + _PRINTER_CHOICE,
    ),
    "eject": (
        "feed the sheet out",
        "Feed the loaded sheet out of the printer.\n\n" + _PRINTER_CHOICE,
    ),
    "identify": (
        "make the printer show itself",
        "Eject a loaded sheet, then pulse the paper feed three times so you can "
        "tell which printer this is.\n\n" + _PRINTER_CHOICE,
    ),
    "testpage": (
        "print the test page",
        "Print the test page: device details, millimetre scales, a gray ramp, "
        "line widths and text samples.\n\n" + _PRINTER_CHOICE,
    ),
}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="phomemo-bridge", description=__doc__)
    ap.add_argument(
        "--config", type=Path, help="read this TOML file instead of the defaults"
    )
    ap.add_argument(
        "-a",
        "--address",
        help="Bluetooth address of the printer to use (AA:BB:CC:DD:EE:FF)",
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = ap.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add(name: str) -> argparse.ArgumentParser:
        summary, description = _COMMANDS[name]
        paragraphs = description.split("\n\n")
        return sub.add_parser(
            name,
            help=summary,
            description="\n\n".join(textwrap.fill(p, 79) for p in paragraphs),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

    add("server")
    devices = add("devices")
    devices.add_argument(
        "--timeout", type=float, default=5.0, help="scan seconds (default: 5)"
    )
    add("connect")
    add("disconnect")
    add("status")
    auto_off = add("auto-off")
    auto_off.add_argument(
        "minutes", type=int, nargs="?", help="new timeout in minutes, 0 = never"
    )
    pr = add("print")
    pr.add_argument("file", type=Path, help="image file to print")
    pr.add_argument(
        "--media", choices=sorted(MEDIA), default="a4", help="sheet size (default: a4)"
    )
    pr.add_argument(
        "--tone",
        choices=["auto", *[t.value for t in ToneMode]],
        default="auto",
        help="how gray becomes dots (default: auto, chosen from the content)",
    )
    pr.add_argument(
        "--quality",
        choices=sorted(QUALITY),
        default="normal",
        help="print density (default: normal)",
    )
    pr.add_argument(
        "--content",
        choices=["auto", "text", "graphic", "photo"],
        default="auto",
        help="content hint for --tone auto (default: auto)",
    )
    pr.add_argument(
        "--abort-after",
        type=float,
        metavar="SECONDS",
        help="cancel the page this many seconds into the transfer (testing)",
    )
    add("eject")
    add("identify")
    tp = add("testpage")
    tp.add_argument(
        "--quality",
        choices=sorted(QUALITY),
        default="normal",
        help="print density (default: normal)",
    )
    return ap


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


async def _linked(client: BridgeClient, address: str | None) -> dict | None:
    """The bridge's status when it holds a link to ``address`` (or any printer)."""
    status = await client.status()
    if not status["connected"]:
        return None
    if address is not None and status.get("address") != address:
        return None
    return status


async def _status(client: BridgeClient, address: str | None) -> dict:
    status = await client.status()
    if not status["connected"]:
        return status
    if address is not None and status.get("address") != address:
        return {"connected": False, "address": address, "linked_to": status["address"]}
    info = await client.info()
    for key in ("firmware", "serial", "auto_off_minutes"):
        status[key] = info[key]
    return status


async def _run_client(args: argparse.Namespace, socket_path: Path) -> int:
    def show(event: dict) -> None:
        print(json.dumps(event), file=sys.stderr)

    async with BridgeClient(socket_path, on_event=show) as client:
        if args.command in ("connect", "print", "eject", "identify", "testpage"):
            opened = await client.open(args.address)
            if not opened["connected"] and args.command != "print":
                return _fail(f"not reachable: {opened.get('reason', 'unknown')}")
        if args.command == "connect":
            status = await client.status()
            print(f"connected to {status.get('address')}")
        elif args.command == "disconnect":
            await client.drop_link()
            print("disconnected")
        elif args.command == "status":
            print(json.dumps(await _status(client, args.address), indent=2))
        elif args.command == "auto-off":
            status = await _linked(client, args.address)
            if status is None:
                return _fail('not connected; run "phomemo-bridge connect" first')
            minutes = await client.auto_off(args.minutes)
            shown = "never" if minutes == 0 else f"{minutes} min"
            print(f"{status['address']}: auto-off {shown}")
        elif args.command == "print":
            impressions = await client.print_image(
                args.file,
                media=args.media,
                tone=args.tone,
                quality=args.quality,
                content=args.content,
                abort_after=args.abort_after,
            )
            print(f"printed {impressions} page(s)")
        elif args.command == "devices":
            printers = await client.discover(args.timeout)
            for printer in printers:
                print(f"{printer['address']}  {printer['name']}")
            if not printers:
                print("no printer in range", file=sys.stderr)
                return 1
        elif args.command == "eject":
            print("ejected" if await client.eject() else "sheet still present")
            await client.close()
        elif args.command == "identify":
            await client.identify()
            await client.close()
            print("identified")
        elif args.command == "testpage":
            impressions = await client.print_test_page(quality=args.quality)
            print(f"printed {impressions} page(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Arguments without the program name; ``None`` uses ``sys.argv``.

    Returns:
        Process exit status.
    """
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        config = load_config(
            paths=[args.config] if args.config else None,
            require_files=args.config is not None,
        )
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "server":
            asyncio.run(serve(config))
            return 0
        return asyncio.run(_run_client(args, config.socket_path))
    except KeyboardInterrupt:
        return 130
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ConnectionError, FileNotFoundError) as exc:
        print(
            f"cannot reach the bridge at {config.socket_path}: {exc}", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
