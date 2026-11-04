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

"""Image preparation pipeline for thermal printing.

Converts arbitrary images into 1-bit raster bitmaps suitable for
Phomemo printers. The pipeline handles resizing, padding/cropping,
grayscale conversion, and dithering.

Bitmap format (from the M08F Protocol Reference):
- 1 bit per pixel, packed into bytes.
- ``1`` = black (ink on), ``0`` = white (no ink).
- Most significant bit of each byte is the leftmost pixel.
- Rows are sequential top-to-bottom.
"""

import logging
from enum import StrEnum

from PIL import Image, ImageChops

from phomemo.registry import PrinterProfile

logger = logging.getLogger(__name__)

# 8x8 Bayer matrix; each cell is the threshold rank of its pixel in the tile.
_BAYER_8 = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)


class DitherMode(StrEnum):
    """Image dithering algorithm for 1-bit conversion.

    ``FLOYD_STEINBERG`` produces the best visual quality for
    photographic content. ``THRESHOLD`` applies a simple threshold
    at value 128 with no dithering.
    """

    FLOYD_STEINBERG = "floyd_steinberg"
    THRESHOLD = "threshold"


class ToneMode(StrEnum):
    """How 8-bit gray becomes the head's 1-bit output.

    ``THRESHOLD`` splits at mid gray (true black and white, crisp text).
    ``ORDERED`` uses an 8x8 Bayer pattern (even tone, cheap).
    ``DIFFUSION`` uses Floyd-Steinberg error diffusion (photos).
    """

    THRESHOLD = "threshold"
    ORDERED = "ordered"
    DIFFUSION = "diffusion"


class ImageFit(StrEnum):
    """Strategy for fitting an image to the print area."""

    FIT_WIDTH = "fit_width"
    FIT_HEIGHT = "fit_height"
    FIT_PAGE = "fit_page"
    STRETCH = "stretch"
    ORIGINAL = "original"


def prepare_image(
    img: Image.Image,
    target_width: int,
    fit: ImageFit = ImageFit.FIT_WIDTH,
    dither: DitherMode = DitherMode.FLOYD_STEINBERG,
    target_height: int | None = None,
    max_height: int | None = None,
) -> Image.Image:
    """Resize and dither an image for thermal printing.

    Processes the image through the full pipeline: resize to target
    dimensions, pad or crop to exact width (multiple of 8), convert to
    grayscale, and dither to 1-bit.

    Args:
        img: Source PIL Image (any mode).
        target_width: Desired width in pixels. Rounded down to the
            nearest multiple of 8.
        fit: How to fit the image to the target dimensions.
        dither: Dithering algorithm for 1-bit conversion.
        target_height: Required for ``FIT_HEIGHT`` and ``STRETCH`` modes.
        max_height: Required for ``FIT_PAGE``: the image is scaled to fit
            within ``target_width`` x ``max_height`` preserving aspect ratio.

    Returns:
        A 1-bit (mode ``"1"``) PIL Image ready for bitmap conversion.

    Raises:
        ValueError: If ``target_height`` or ``max_height`` is required by
            the fit mode but not provided.
    """
    w, h = img.size
    target_width = (target_width // 8) * 8
    logger.debug("prepare_image: source=%dx%d fit=%s dither=%s", w, h, fit, dither)
    match fit:
        case ImageFit.FIT_WIDTH:
            scale = target_width / w
            new_size = (target_width, int(h * scale))
        case ImageFit.FIT_HEIGHT:
            if target_height is None:
                raise ValueError("target_height required for FIT_HEIGHT")
            scale = target_height / h
            new_size = (int(w * scale), target_height)
        case ImageFit.FIT_PAGE:
            if max_height is None:
                raise ValueError("max_height required for FIT_PAGE")
            scale = min(target_width / w, max_height / h)
            new_size = (max(8, int(w * scale) // 8 * 8), int(h * scale))
        case ImageFit.STRETCH:
            if target_height is None:
                raise ValueError("target_height required for STRETCH")
            new_size = (target_width, target_height)
        case ImageFit.ORIGINAL:
            new_size = (w, h)
        case _:
            raise ValueError(f"Unsupported fit mode: {fit}")

    img = img.resize(new_size, Image.Resampling.LANCZOS)
    logger.debug("prepare_image: resized to %dx%d", *new_size)

    # Pad to exact target width, centered horizontally
    if img.size[0] != target_width:
        padded = Image.new("RGB", (target_width, img.size[1]), (255, 255, 255))
        offset = max(0, (target_width - img.size[0]) // 2)
        padded.paste(img, (offset, 0))
        img = padded

    # Convert to grayscale, then dither to 1-bit
    img = img.convert("L")
    match dither:
        case DitherMode.FLOYD_STEINBERG:
            img = img.convert("1")
        case DitherMode.THRESHOLD:
            img = img.point(lambda x: 0 if x < 128 else 255, mode="1")
        case _:
            raise ValueError(f"Unsupported dither mode: {dither}")

    return img


def image_to_bitmap(img: Image.Image) -> bytes:
    """Convert a 1-bit PIL Image to packed bitmap bytes.

    Each row is packed into ``width / 8`` bytes. Black pixels (value 0)
    map to bit value 1 (ink on), white pixels (value 255) map to bit
    value 0 (no ink). MSB of each byte is the leftmost pixel.

    Args:
        img: A mode ``"1"`` PIL Image.

    Returns:
        Packed bitmap bytes, row by row.

    Raises:
        ValueError: If the image mode is not ``"1"``.
    """
    if img.mode != "1":
        raise ValueError(f"Expected mode '1', got '{img.mode}'")

    width = img.size[0]
    if width % 8 != 0:
        raise ValueError(f"Image width must be a multiple of 8, got {width}")

    # PIL mode "1": 0 = black, 255 = white
    # Printer: 1 = black (ink), 0 = white (no ink)
    # Invert so tobytes() packs black pixels as 1-bits.
    inverted = ImageChops.invert(img)
    bitmap = inverted.tobytes()
    logger.debug(
        "image_to_bitmap: %dx%d -> %d bytes", img.size[0], img.size[1], len(bitmap)
    )
    return bitmap


def _bayer_tile(width: int, height: int) -> Image.Image:
    """Threshold image tiled from the 8x8 Bayer matrix, values 2..254."""
    tile = Image.new("L", (8, 8))
    tile.putdata([int((rank + 0.5) * 4) for row in _BAYER_8 for rank in row])
    canvas = Image.new("L", (width, height))
    for y in range(0, height, 8):
        for x in range(0, width, 8):
            canvas.paste(tile, (x, y))
    return canvas


def _apply_tone(img: Image.Image, tone: ToneMode) -> Image.Image:
    """Convert a mode ``L`` image to mode ``1`` with the given tone mode."""
    match tone:
        case ToneMode.THRESHOLD:
            return img.point(lambda v: 255 if v >= 128 else 0).convert(
                "1", dither=Image.Dither.NONE
            )
        case ToneMode.ORDERED:
            above = ImageChops.subtract(img, _bayer_tile(*img.size))
            return above.point(lambda v: 255 if v > 0 else 0).convert(
                "1", dither=Image.Dither.NONE
            )
        case ToneMode.DIFFUSION:
            return img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        case _:
            raise ValueError(f"Unsupported tone mode: {tone}")


def prepare_page(
    img: Image.Image,
    profile: PrinterProfile,
    length_mm: float | None,
    tone: ToneMode,
    rotate: bool = False,
) -> Image.Image:
    """Map a client page raster onto the printable area of a sheet.

    The raster is optionally rotated a quarter turn counter-clockwise (an
    A5 portrait page printed on a sheet fed long edge first), centred on
    the head width when narrower and cropped when wider, stripped of the
    rows that fall into the unprintable top lead, and clipped to the rows
    the sheet can hold. Gray input is converted with ``tone``; 1-bit input
    keeps its pixels.

    Args:
        img: Page raster, mode ``L`` (0 = black) or mode ``1``.
        profile: Printer geometry: head width, dpi, margins.
        length_mm: Sheet length, or ``None`` for roll media (no clipping).
        tone: Conversion for gray input; ignored for 1-bit input.
        rotate: Rotate the raster 90 degrees counter-clockwise first.

    Returns:
        A mode ``1`` image ``profile.print_width_px`` wide.
    """
    if img.mode not in ("L", "1"):
        raise ValueError(f"page raster must be mode L or 1, got {img.mode}")
    if rotate:
        img = img.transpose(Image.Transpose.ROTATE_90)
    width = profile.print_width_px
    if img.width != width:
        canvas = Image.new(img.mode, (width, img.height), 255)
        canvas.paste(
            img.crop((0, 0, min(img.width, width), img.height)),
            (max(0, (width - img.width) // 2), 0),
        )
        img = canvas
    top = profile.lead_rows
    if img.height <= top:
        raise ValueError(
            f"page of {img.height} rows lies inside the {top}-row unprintable lead"
        )
    max_rows = profile.rows_for(length_mm)
    bottom = img.height if max_rows is None else min(img.height, top + max_rows)
    img = img.crop((0, top, width, bottom))
    if img.mode == "L":
        img = _apply_tone(img, tone)
    return img
