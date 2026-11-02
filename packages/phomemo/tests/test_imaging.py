"""Tests for the image preparation pipeline."""

import pytest
from phomemo.imaging import ImageFit, prepare_image
from PIL import Image


def test_fit_page_bounds_tall_image() -> None:
    img = Image.new("L", (1000, 4000), 255)
    out = prepare_image(img, target_width=1680, fit=ImageFit.FIT_PAGE, max_height=2285)
    assert out.size == (1680, 2285)


def test_fit_page_bounds_wide_image() -> None:
    img = Image.new("L", (4000, 1000), 255)
    out = prepare_image(img, target_width=1680, fit=ImageFit.FIT_PAGE, max_height=2285)
    assert out.size[0] == 1680
    assert out.size[1] == 420


def test_fit_page_requires_max_height() -> None:
    img = Image.new("L", (100, 100), 255)
    with pytest.raises(ValueError, match="max_height"):
        prepare_image(img, target_width=1680, fit=ImageFit.FIT_PAGE)
