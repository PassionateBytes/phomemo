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

from enum import StrEnum

from PIL import Image, ImageChops


class DitherMode(StrEnum):
    """Image dithering algorithm for 1-bit conversion."""

    FLOYD_STEINBERG = "floyd_steinberg"
    THRESHOLD = "threshold"
    NONE = "none"


class ImageFit(StrEnum):
    """Strategy for fitting an image to the print area."""

    FIT_WIDTH = "fit_width"
    FIT_HEIGHT = "fit_height"
    STRETCH = "stretch"
    ORIGINAL = "original"


def prepare_image(
    img: Image.Image,
    target_width: int,
    fit: ImageFit = ImageFit.FIT_WIDTH,
    dither: DitherMode = DitherMode.FLOYD_STEINBERG,
    target_height: int | None = None,
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

    Returns:
        A 1-bit (mode ``"1"``) PIL Image ready for bitmap conversion.

    Raises:
        ValueError: If ``target_height`` is required but not provided.
    """
    target_width = (target_width // 8) * 8

    w, h = img.size
    match fit:
        case ImageFit.FIT_WIDTH:
            scale = target_width / w
            new_size = (target_width, int(h * scale))
        case ImageFit.FIT_HEIGHT:
            if target_height is None:
                raise ValueError("target_height required for FIT_HEIGHT")
            scale = target_height / h
            new_size = (int(w * scale), target_height)
        case ImageFit.STRETCH:
            if target_height is None:
                raise ValueError("target_height required for STRETCH")
            new_size = (target_width, target_height)
        case ImageFit.ORIGINAL:
            new_size = (w, h)
        case _:
            raise ValueError(f"Unsupported fit mode: {fit}")

    img = img.resize(new_size, Image.Resampling.LANCZOS)

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
        case DitherMode.NONE:
            img = img.convert("1", dither=Image.Dither.NONE)
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
    return inverted.tobytes()
