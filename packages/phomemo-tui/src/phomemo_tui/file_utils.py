"""Image and PDF loading utilities for the print pipeline."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp", ".pdf"}
)

_IMAGE_EXTENSIONS: frozenset[str] = SUPPORTED_EXTENSIONS - {".pdf"}


def get_page_count(path: Path) -> int:
    """Return the number of printable pages in a file.

    Images always return 1. PDFs return the document page count.

    Args:
        path: Path to an image or PDF file.

    Returns:
        Number of pages (always >= 1).

    Raises:
        ValueError: If the file extension is not supported.
    """
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext!r}")
    if ext == ".pdf":
        import fitz  # pymupdf

        doc = fitz.open(str(path))
        count = len(doc)
        doc.close()
        return count
    return 1


def load_page_as_pil(path: Path, page: int) -> Image.Image:
    """Load a single page from an image or PDF as a PIL Image.

    Args:
        path: Path to an image or PDF file.
        page: 1-based page number.

    Returns:
        RGB PIL Image of the requested page.

    Raises:
        ValueError: If the extension is unsupported or page is out of range.
    """
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext!r}")

    if ext == ".pdf":
        import fitz  # pymupdf

        doc = fitz.open(str(path))
        total = len(doc)
        if page < 1 or page > total:
            raise ValueError(
                f"page {page} out of range for {path.name} ({total} pages)"
            )
        fitz_page = doc[page - 1]
        mat = fitz.Matrix(2.0, 2.0)  # 2x scale for reasonable preview/print quality
        pix = fitz_page.get_pixmap(matrix=mat)
        doc.close()
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    # Regular image
    total = get_page_count(path)
    if page != 1:
        raise ValueError(
            f"page {page} out of range for {path.name} ({total} pages)"
        )
    return Image.open(path).convert("RGB")
