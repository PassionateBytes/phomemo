"""Rendering of the printer application's test page.

The page covers the imageable A4 area at the printer's resolution so the
printer application places it 1:1: device details as text, rulers along
the top and left edges, a gray ramp for the dithering, line and text size
samples.
"""

from __future__ import annotations

import datetime as dt
import importlib.metadata
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from phomemo.registry import PrinterProfile

_MM_PER_INCH = 25.4


@dataclass(frozen=True)
class PageInfo:
    """What the page says about the printer and the software driving it.

    Attributes:
        printer_name: Queue name the printer application uses.
        address: BLE address.
        firmware: Printer firmware version, if known.
        serial: Printer serial, if known.
        battery: Charge in percent, if known.
        auto_off_minutes: Printer auto-off timer, if known.
        chunk_bytes: Bytes per BLE write on the current link.
        versions: Component versions by name.
        socket_path: The bridge socket.
    """

    printer_name: str
    address: str | None
    firmware: str | None = None
    serial: str | None = None
    battery: int | None = None
    auto_off_minutes: int | None = None
    chunk_bytes: int | None = None
    versions: dict[str, str] = field(default_factory=dict)
    socket_path: str | None = None


def page_lines(info: PageInfo, profile: PrinterProfile, length_mm: float) -> list[str]:
    """The text lines of the page, in order.

    Args:
        info: Device and software details.
        profile: Printer profile the bridge runs with.
        length_mm: Sheet length along the feed.

    Returns:
        Lines ready to draw.
    """

    def show(value: object) -> str:
        return "unknown" if value is None else str(value)

    versions = dict(info.versions)
    versions.setdefault("phomemo", _library_version())
    rows = profile.rows_for(length_mm)
    return [
        f"Printer: {info.printer_name}",
        f"Address: {show(info.address)}",
        f"Firmware: {show(info.firmware)}    Serial: {show(info.serial)}",
        f"Battery: {show(info.battery)} %    "
        f"Auto-off: {show(info.auto_off_minutes)} min",
        f"Profile: {profile.name}, {profile.print_width_px} px at {profile.dpi} dpi, "
        f"sheet {length_mm:g} mm, lead {profile.top_margin_mm:g} mm, "
        f"bottom margin {profile.bottom_margin_mm:g} mm, {rows} printable rows",
        f"Link: {show(info.chunk_bytes)} bytes per write, "
        f"{'with' if profile.write_with_response else 'without'} response, "
        f"bands of {profile.band_height} rows",
        "Versions: " + ", ".join(f"{k} {v}" for k, v in versions.items()),
        f"Bridge socket: {show(info.socket_path)}",
        f"Printed: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]


def render_test_page(
    info: PageInfo,
    profile: PrinterProfile,
    length_mm: float,
    margin_mm: float = 10.0,
) -> Image.Image:
    """Draw the page.

    Args:
        info: Device and software details.
        profile: Printer profile; sets the width and resolution.
        length_mm: Sheet length along the feed.
        margin_mm: Margin the printer application keeps at both ends.

    Returns:
        An 8-bit grayscale image of the imageable area, 255 = white.
    """
    px_per_mm = profile.dpi / _MM_PER_INCH
    # The printer application's imageable area: A4 width, the sheet minus
    # its symmetric margin at each end, truncated the way PAPPL does.
    width = int(21000 * profile.dpi / 2540)
    height = int(round((length_mm - 2 * margin_mm) * 100) * profile.dpi / 2540)
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.load_default(size=64)
    text_font = ImageFont.load_default(size=28)
    small_font = ImageFont.load_default(size=20)

    draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=2)
    _rulers(draw, width, height, px_per_mm, small_font)

    x = round(12 * px_per_mm)
    y = round(12 * px_per_mm)
    draw.text((x, y), f"{info.printer_name} test page", font=title_font, fill=0)
    y += 100
    for line in page_lines(info, profile, length_mm):
        draw.text((x, y), line, font=text_font, fill=0)
        y += 40

    y += 30
    draw.text((x, y), "Gray ramp (dithered by the bridge):", font=text_font, fill=0)
    y += 44
    patch = round(18 * px_per_mm)
    for i in range(8):
        value = round(255 * i / 7)
        left = x + i * (patch + 8)
        draw.rectangle((left, y, left + patch, y + patch), fill=value, outline=0)
        draw.text((left, y + patch + 6), str(value), font=small_font, fill=0)
    y += patch + 50

    draw.text((x, y), "Lines of 1, 2, 3 px:", font=text_font, fill=0)
    y += 44
    for w in (1, 2, 3):
        draw.line((x, y, x + round(80 * px_per_mm), y), fill=0, width=w)
        y += 16
    draw.line((x, y, x + round(80 * px_per_mm), y + round(10 * px_per_mm)), fill=0)
    y += round(10 * px_per_mm) + 30

    sample = "The quick brown fox jumps over the lazy dog"
    for size in (20, 28, 40, 56):
        font = ImageFont.load_default(size=size)
        draw.text((x, y), f"{size} px: {sample}", font=font, fill=0)
        y += size + 16
    return img


def _rulers(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    px_per_mm: float,
    font: ImageFont.FreeTypeFont,
) -> None:
    """Millimetre ticks along the top and left edges, labelled every 10 mm."""
    mm = 0
    while mm * px_per_mm < width:
        x = round(mm * px_per_mm)
        tick = 24 if mm % 10 == 0 else 12 if mm % 5 == 0 else 6
        draw.line((x, 0, x, tick), fill=0)
        if mm % 10 == 0 and mm:
            draw.text((x + 3, tick), str(mm), font=font, fill=0)
        mm += 1
    mm = 0
    while mm * px_per_mm < height:
        y = round(mm * px_per_mm)
        tick = 24 if mm % 10 == 0 else 12 if mm % 5 == 0 else 6
        draw.line((0, y, tick, y), fill=0)
        if mm % 10 == 0 and mm:
            draw.text((tick + 2, y - 10), str(mm), font=font, fill=0)
        mm += 1


def save_test_page(img: Image.Image, path: Path, dpi: int = 203) -> Path:
    """Write the page as a PNG tagged with the printer resolution.

    Args:
        img: Rendered page.
        path: Destination file.
        dpi: Resolution to record so the page prints 1:1.

    Returns:
        The written path.
    """
    img.save(path, format="PNG", dpi=(dpi, dpi))
    return path


def _library_version() -> str:
    try:
        return importlib.metadata.version("phomemo")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
