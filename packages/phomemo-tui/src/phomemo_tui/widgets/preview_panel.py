"""Preview panel: file info, block-character image preview, print progress."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from phomemo import get_profile, prepare_image
from phomemo.imaging import DitherMode, ImageFit
from textual import work
from textual.app import ComposeResult
from textual.widgets import Label, Static

from phomemo_tui.file_utils import get_page_count, load_page_as_pil
from phomemo_tui.messages import (
    FileSelected,
    PrintProgress,
    PrintWaitingForPaper,
    PrintWaitingForReady,
)


def _render_preview(img: Image.Image, width: int) -> str:
    """Render a 1-bit image as Unicode half-block characters.

    Args:
        img: 1-bit PIL Image.
        width: Target character columns.

    Returns:
        Multi-line string of block characters.
    """
    scale = width / img.size[0]
    h = int(img.size[1] * scale)
    small = img.resize((width, h), Image.Resampling.NEAREST)
    pixels = small.load()
    lines = []
    for y in range(0, h - 1, 2):
        row = []
        for x in range(width):
            top = pixels[x, y] == 0
            bot = pixels[x, y + 1] == 0 if y + 1 < h else False
            if top and bot:
                row.append("█")
            elif top:
                row.append("▀")
            elif bot:
                row.append("▄")
            else:
                row.append(" ")
        lines.append("".join(row))
    return "\n".join(lines)


class PreviewPanel(Static, can_focus=True):
    """File preview with header, body image, and print progress footer.

    Clicking or pressing Enter when idle opens the file picker.
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="preview-header")
        yield Static("", id="preview-body")
        yield Static("", id="preview-footer")

    def on_mount(self) -> None:
        self._file: Path | None = None
        self._page: int = 1
        self._total_pages: int = 1
        self._locked: bool = False
        self._render_empty()

    # ------------------------------------------------------------------
    # Public API called by app.py
    # ------------------------------------------------------------------

    def set_file(self, path: Path, page: int = 1) -> None:
        """Load and display a new file.

        Args:
            path: Path to the image or PDF.
            page: 1-based page to display.
        """
        self._file = path
        self._total_pages = get_page_count(path)
        self._page = max(1, min(page, self._total_pages))
        self._render_file()

    def set_page(self, page: int) -> None:
        """Navigate to a different page.

        Args:
            page: 1-based page number.
        """
        if self._file is None:
            return
        self._page = max(1, min(page, self._total_pages))
        self._render_file()

    def set_locked(self, locked: bool) -> None:
        """Lock/unlock the panel during a print job.

        Args:
            locked: True to suppress file-picker interaction.
        """
        self._locked = locked

    def show_progress(self, msg: PrintProgress) -> None:
        """Update progress bar in footer.

        Args:
            msg: PrintProgress message with chunk counts.
        """
        footer = self.query_one("#preview-footer", Static)
        pct = int((msg.chunks_sent / max(msg.total_chunks, 1)) * 100)
        bar_width = 30
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        footer.update(f"[{bar}] {pct}%")

    def show_waiting_ready(self, msg: PrintWaitingForReady) -> None:
        """Show instruction when printer isn't ready.

        Args:
            msg: PrintWaitingForReady message.
        """
        footer = self.query_one("#preview-footer", Static)
        match msg.reason:
            case "lid":
                footer.update("[yellow]Please close the lid[/yellow]")
            case "paper":
                footer.update("[yellow]Please feed a sheet of paper[/yellow]")
            case _:
                footer.update("[yellow]Please close the lid and feed paper[/yellow]")

    def show_waiting_paper(self, msg: PrintWaitingForPaper) -> None:
        """Show instruction when waiting for next page in auto mode.

        Args:
            msg: PrintWaitingForPaper message.
        """
        footer = self.query_one("#preview-footer", Static)
        footer.update(
            f"[dim]⠿[/dim] Feed next sheet to print page "
            f"{msg.next_page}/{msg.total_pages}"
        )

    def clear_footer(self) -> None:
        """Remove print progress from footer."""
        self.query_one("#preview-footer", Static).update("")

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def on_click(self) -> None:
        if not self._locked:
            self._open_file_picker()

    def on_key(self, event) -> None:
        if event.key == "enter" and not self._locked:
            self._open_file_picker()
            event.prevent_default()
        elif event.key in ("left", "[") and self._file and not self._locked:
            self.set_page(self._page - 1)
            event.prevent_default()
        elif event.key in ("right", "]") and self._file and not self._locked:
            self.set_page(self._page + 1)
            event.prevent_default()

    @work
    async def _open_file_picker(self) -> None:
        """Open file picker and post FileSelected if user picks a file."""
        from textual_fspicker import FileOpen, Filters

        from phomemo_tui.file_utils import SUPPORTED_EXTENSIONS

        exts = SUPPORTED_EXTENSIONS
        start = self.app.config.last_directory or "."  # type: ignore[union-attr]

        path = await self.app.push_screen_wait(
            FileOpen(
                location=start,
                filters=Filters(
                    (
                        "Images & PDFs",
                        lambda p: p.suffix.lower() in exts,
                    ),
                    ("All files", lambda _: True),
                ),
            )
        )
        if path is not None:
            self.app.config.last_directory = str(path.parent)  # type: ignore[union-attr]
            self.post_message(FileSelected(path=path))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_empty(self) -> None:
        self.query_one("#preview-header", Label).update("")
        self.query_one("#preview-body", Static).update(
            "\n\n  [dim]Select a file to print[/dim]\n\n  Press Enter or click to browse"
        )
        self.query_one("#preview-footer", Static).update("")

    @work
    async def _render_file(self) -> None:
        """Render header and block-char preview in a background thread."""
        import asyncio

        if self._file is None:
            self._render_empty()
            return

        header = self.query_one("#preview-header", Label)
        body = self.query_one("#preview-body", Static)

        name = self._file.name
        if self._total_pages > 1:
            header.update(
                f"[bold]{name}[/bold] – Page {self._page}/{self._total_pages}"
            )
        else:
            header.update(f"[bold]{name}[/bold]")

        body.update("[dim]Loading preview…[/dim]")

        try:
            profile_name = self.app.config.profile_override  # type: ignore[union-attr]
            if profile_name is None:
                from phomemo import list_profiles

                profiles = list_profiles()
                profile_name = profiles[0] if profiles else "M08F-A4"
            profile = get_profile(profile_name)
            width = profile.print_width_px

            def _process() -> str:
                img = load_page_as_pil(self._file, self._page)  # type: ignore[arg-type]
                processed = prepare_image(
                    img,
                    target_width=width,
                    fit=ImageFit.FIT_WIDTH,
                    dither=DitherMode.FLOYD_STEINBERG,
                )
                panel_w = max(20, self.size.width - 4)
                return _render_preview(processed, panel_w)

            preview_text = await asyncio.to_thread(_process)
            body.update(preview_text)
        except Exception as exc:
            body.update(f"[red]Preview error: {exc}[/red]")
