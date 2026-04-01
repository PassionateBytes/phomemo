"""Tests for PreviewPanel utilities."""

from PIL import Image

from phomemo_tui.widgets.preview_panel import _render_preview


def test_render_preview_returns_string() -> None:
    """_render_preview should return a non-empty string for a valid 1-bit image."""
    # Create a simple 4x4 1-bit image with mixed black/white
    img = Image.new("1", (4, 4), color=0)  # black
    result = _render_preview(img, width=4)
    assert isinstance(result, str)
    assert len(result) > 0


def test_render_preview_uses_half_blocks() -> None:
    """Block characters should appear in output."""
    img = Image.new("1", (4, 4), color=0)
    result = _render_preview(img, width=4)
    assert "█" in result
