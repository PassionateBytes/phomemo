"""Tests for image and PDF loading utilities."""

from pathlib import Path

import pytest
from PIL import Image

from phomemo_tui.file_utils import (
    SUPPORTED_EXTENSIONS,
    get_page_count,
    load_page_as_pil,
)


def _make_png(tmp_path: Path) -> Path:
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    p = tmp_path / "test.png"
    img.save(p)
    return p


def test_supported_extensions_contains_pdf() -> None:
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".png" in SUPPORTED_EXTENSIONS
    assert ".jpg" in SUPPORTED_EXTENSIONS


def test_get_page_count_image(tmp_path: Path) -> None:
    p = _make_png(tmp_path)
    assert get_page_count(p) == 1


def test_load_page_as_pil_image(tmp_path: Path) -> None:
    p = _make_png(tmp_path)
    img = load_page_as_pil(p, page=1)
    assert isinstance(img, Image.Image)
    assert img.size == (100, 100)


def test_load_page_as_pil_page_out_of_range(tmp_path: Path) -> None:
    p = _make_png(tmp_path)
    with pytest.raises(ValueError, match="page"):
        load_page_as_pil(p, page=2)


def test_unsupported_extension(tmp_path: Path) -> None:
    p = tmp_path / "file.xyz"
    p.write_bytes(b"data")
    with pytest.raises(ValueError, match="Unsupported"):
        load_page_as_pil(p, page=1)
