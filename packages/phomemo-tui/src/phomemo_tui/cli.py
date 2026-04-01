"""CLI entry point for phomemo-tui.

Supports both interactive TUI mode and headless print-and-exit mode.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="phomemo-tui",
        description="Phomemo thermal printer terminal UI",
    )
    parser.add_argument("--file", type=Path, metavar="PATH", help="Image or PDF to load")
    parser.add_argument("--profile", metavar="NAME", help="Printer profile override")
    parser.add_argument("--address", metavar="ADDR", help="BLE device address (skips scan)")
    parser.add_argument(
        "--dither",
        choices=["floyd_steinberg", "threshold"],
        help="Dithering algorithm",
    )
    parser.add_argument(
        "--density",
        choices=["light", "medium", "dark"],
        help="Print density",
    )
    parser.add_argument("--page", type=int, metavar="N", help="Starting page for PDFs (default 1)")
    parser.add_argument("--headless", action="store_true", help="Print and exit, no TUI")
    return parser


async def _headless_print(
    file: Path,
    profile: str | None,
    address: str | None,
    dither: str | None,
    density: str | None,
    page: int | None,
) -> None:
    """Run a single print job without the TUI.

    Args:
        file: File to print.
        profile: Profile name override, or None for auto.
        address: BLE address override, or None for auto-connect.
        dither: Dither mode override.
        density: Density override.
        page: Starting page (None = page 1, auto-sequence for multi-page PDFs).

    Raises:
        SystemExit: Exits 1 on error.
    """
    from phomemo_tui.config import load_config
    from phomemo_tui.messages import (
        PrintCancelled,
        PrintComplete,
        PrintError,
    )
    from phomemo_tui.printer_service import PrinterService

    cfg = load_config()

    # Apply CLI overrides (do not persist)
    if profile is not None:
        object.__setattr__(cfg, "profile_override", profile)
    if dither is not None:
        object.__setattr__(cfg, "dither", dither)
    if density is not None:
        object.__setattr__(cfg, "density", density)
    if address is not None:
        object.__setattr__(cfg, "last_device_address", address)

    result: list[str] = []  # ["ok"] | ["error: ..."] | ["cancelled"]

    def _on_message(msg: object) -> bool:
        if isinstance(msg, PrintComplete):
            result.append("ok")
        elif isinstance(msg, PrintError):
            result.append(f"error: {msg.message}")
        elif isinstance(msg, PrintCancelled):
            result.append("cancelled")
        return True

    svc = PrinterService(post_message=_on_message, config=cfg)

    # Connect
    print("Connecting…", file=sys.stderr)
    try:
        await asyncio.wait_for(svc._run_until_connected(), timeout=30.0)
    except asyncio.TimeoutError:
        print("Error: could not connect within 30 s", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Connected. Printing {file.name}…", file=sys.stderr)

    try:
        await asyncio.wait_for(svc.print_job(file, page), timeout=300.0)
    except asyncio.TimeoutError:
        print("Error: print job timed out", file=sys.stderr)
        sys.exit(1)

    await svc.disconnect()

    if not result:
        print("Error: no completion signal received", file=sys.stderr)
        sys.exit(1)

    outcome = result[0]
    if outcome == "ok":
        print("Done.", file=sys.stderr)
    elif outcome == "cancelled":
        print("Cancelled.", file=sys.stderr)
        sys.exit(1)
    else:
        print(outcome, file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Entry point for the phomemo-tui command."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.headless:
        if args.file is None:
            parser.error("--file is required in headless mode")
        asyncio.run(
            _headless_print(
                file=args.file,
                profile=args.profile,
                address=args.address,
                dither=args.dither,
                density=args.density,
                page=args.page,
            )
        )
        return

    # Interactive TUI
    from phomemo_tui.app import PhomemoApp

    app = PhomemoApp()

    # Apply CLI overrides to the loaded config before launch
    if args.profile:
        app.config.profile_override = args.profile
    if args.address:
        app.config.last_device_address = args.address
    if args.dither:
        app.config.dither = args.dither  # type: ignore[assignment]
    if args.density:
        app.config.density = args.density  # type: ignore[assignment]
    if args.file:
        app.current_file = args.file
        if args.page:
            app.current_page = args.page

    app.run()
