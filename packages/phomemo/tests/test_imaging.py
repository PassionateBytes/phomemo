"""Tests for the image preparation pipeline."""

import pytest
from phomemo.imaging import ImageFit, prepare_image
from PIL import Image


def test_fit_page_bounds_tall_image() -> None:
    img = Image.new("L", (1000, 4000), 255)
    out = prepare_image(img, target_width=1680, fit=ImageFit.FIT_PAGE, max_height=2290)
    assert out.size == (1680, 2290)


def test_fit_page_bounds_wide_image() -> None:
    img = Image.new("L", (4000, 1000), 255)
    out = prepare_image(img, target_width=1680, fit=ImageFit.FIT_PAGE, max_height=2290)
    assert out.size[0] == 1680
    assert out.size[1] == 420


def test_fit_page_requires_max_height() -> None:
    img = Image.new("L", (100, 100), 255)
    with pytest.raises(ValueError, match="max_height"):
        prepare_image(img, target_width=1680, fit=ImageFit.FIT_PAGE)


import phomemo.profiles  # noqa: E402, F401, registers built-in profiles
from phomemo.imaging import ToneMode, prepare_page  # noqa: E402
from phomemo.registry import get_profile  # noqa: E402

A4 = get_profile("M08F-A4")


def _gray(w: int, h: int, value: int = 255) -> Image.Image:
    return Image.new("L", (w, h), value)


def test_prepare_page_drops_lead_and_clips() -> None:
    img = _gray(1680, 2374)
    img.putpixel((5, 80), 0)
    out = prepare_page(img, A4, 297.0, ToneMode.THRESHOLD)
    assert out.size == (1680, 2245)
    assert out.getpixel((5, 0)) == 0
    assert out.getpixel((5, 1)) == 255


def test_prepare_page_rotates_a5() -> None:
    img = _gray(1183, 1678)
    img.putpixel((600, 10), 0)
    out = prepare_page(img, A4, 148.0, ToneMode.THRESHOLD, rotate=True)
    assert out.size == (1680, 1054)
    # Counter-clockwise: source (x, y) lands at (y, width - 1 - x), then the
    # 1678-wide result is centred (offset 1) and the 80 lead rows dropped.
    assert out.getpixel((1 + 10, 1183 - 1 - 600 - A4.lead_rows)) == 0


def test_prepare_page_centres_narrow_raster() -> None:
    img = _gray(1000, 500)
    for y in range(500):
        img.putpixel((0, y), 0)
    out = prepare_page(img, A4, None, ToneMode.THRESHOLD)
    assert out.size == (1680, 500 - 80)
    assert out.getpixel((340, 0)) == 0
    assert out.getpixel((339, 0)) == 255


def test_prepare_page_threshold_is_binary_split() -> None:
    img = _gray(8, 100)
    for y in range(100):
        for x in range(8):
            img.putpixel((x, y), 127 if y >= 90 else 128)
    out = prepare_page(img, A4, None, ToneMode.THRESHOLD)
    x0 = (1680 - 8) // 2
    assert out.getpixel((x0, 0)) == 255
    assert out.getpixel((x0, out.height - 1)) == 0


def test_prepare_page_ordered_has_texture() -> None:
    out = prepare_page(_gray(64, 144, 128), A4, None, ToneMode.ORDERED)
    px = out.load()
    x0 = (1680 - 64) // 2
    for ty in range(0, 64, 8):
        for tx in range(0, 64, 8):
            vals = {px[x0 + tx + i, ty + j] for i in range(8) for j in range(8)}
            assert vals == {0, 255}


def test_prepare_page_diffusion_mean_preserved() -> None:
    out = prepare_page(_gray(200, 280, 128), A4, None, ToneMode.DIFFUSION)
    x0 = (1680 - 200) // 2
    region = out.crop((x0, 0, x0 + 200, 200))
    black = region.histogram()[0] / (200 * 200)
    assert 0.45 <= black <= 0.55


def test_prepare_page_roll_has_no_clip() -> None:
    out = prepare_page(_gray(1680, 5000), A4, None, ToneMode.THRESHOLD)
    assert out.size == (1680, 5000 - 80)


def test_prepare_page_mode_1_passthrough() -> None:
    img = Image.new("1", (1680, 300), 255)
    img.putpixel((7, 90), 0)
    out = prepare_page(img, A4, None, ToneMode.DIFFUSION)
    assert out.mode == "1"
    assert out.size == (1680, 220)
    assert out.getpixel((7, 10)) == 0
    assert out.getpixel((8, 10)) == 255
