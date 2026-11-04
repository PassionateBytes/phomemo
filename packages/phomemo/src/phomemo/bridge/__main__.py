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
from pathlib import Path

from phomemo.bridge.client import MEDIA, QUALITY, BridgeClient, BridgeError
from phomemo.bridge.config import ConfigError, load_config
from phomemo.bridge.server import serve
from phomemo.imaging import ToneMode


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="phomemo-bridge", description=__doc__)
    ap.add_argument(
        "--config", type=Path, help="read this TOML file instead of the defaults"
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("server", help="run the bridge daemon")
    pr = sub.add_parser("print", help="print one image file as a page")
    pr.add_argument("file", type=Path)
    pr.add_argument("--media", choices=sorted(MEDIA), default="a4")
    pr.add_argument(
        "--tone", choices=["auto", *[t.value for t in ToneMode]], default="auto"
    )
    pr.add_argument("--quality", choices=sorted(QUALITY), default="normal")
    pr.add_argument(
        "--content", choices=["auto", "text", "graphic", "photo"], default="auto"
    )
    pr.add_argument(
        "--abort-after", type=float, help="send abort N seconds into the transfer"
    )
    sub.add_parser("status", help="show link and sensor state")
    devices = sub.add_parser("devices", help="list printers in range")
    devices.add_argument("--timeout", type=float, default=5.0)
    sub.add_parser("eject", help="feed the sheet out")
    sub.add_parser("identify", help="eject a loaded sheet, then pulse the feed")
    tp = sub.add_parser("testpage", help="print the test page")
    tp.add_argument("--quality", choices=sorted(QUALITY), default="normal")
    return ap


async def _run_client(args: argparse.Namespace, socket_path: Path) -> int:
    def show(event: dict) -> None:
        print(json.dumps(event), file=sys.stderr)

    async with BridgeClient(socket_path, on_event=show) as client:
        if args.command == "print":
            impressions = await client.print_image(
                args.file,
                media=args.media,
                tone=args.tone,
                quality=args.quality,
                content=args.content,
                abort_after=args.abort_after,
            )
            print(f"printed {impressions} page(s)")
        elif args.command == "status":
            print(json.dumps(await client.status(), indent=2))
        elif args.command == "devices":
            printers = await client.discover(args.timeout)
            for printer in printers:
                print(f"{printer['address']}  {printer['name']}")
            if not printers:
                print("no printer in range", file=sys.stderr)
                return 1
        elif args.command == "eject":
            await client.open()
            print("ejected" if await client.eject() else "sheet still present")
            await client.close()
        elif args.command == "identify":
            await client.open()
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
