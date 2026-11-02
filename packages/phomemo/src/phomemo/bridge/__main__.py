"""``phomemo-bridge`` command line: run the daemon or drive it for testing."""

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
    sub.add_parser("serve", help="run the bridge daemon")
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
    disc = sub.add_parser("discover", help="scan for printers")
    disc.add_argument("--timeout", type=float, default=5.0)
    sub.add_parser("eject", help="feed the sheet out")
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
        elif args.command == "discover":
            for printer in await client.discover(args.timeout):
                print(f"{printer['address']}  {printer['name']}")
        elif args.command == "eject":
            await client.open()
            print("ejected" if await client.eject() else "sheet still present")
            await client.close()
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
        config = load_config(paths=[args.config] if args.config else None)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "serve":
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
