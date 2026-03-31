"""Main dashboard screen with 4-panel layout."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from phomemo_tui.widgets.preview_panel import PreviewPanel
from phomemo_tui.widgets.status_panel import StatusPanel

_GRID: dict[str, dict[str, str]] = {
    "panel-status": {"right": "panel-preview", "down": "panel-settings"},
    "panel-settings": {"right": "panel-print", "up": "panel-status"},
    "panel-preview": {"left": "panel-status", "down": "panel-print"},
    "panel-print": {"left": "panel-settings", "up": "panel-preview"},
}


class Panel(Static, can_focus=True):
    """A focusable dashboard tile (used for settings, preview, print)."""


class MainMenuScreen(Screen):
    """4-panel dashboard: status, settings, preview, print button."""

    BINDINGS = [Binding("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="dashboard"):
            with Vertical(id="left-column"):
                yield StatusPanel(id="panel-status").add_class("panel")
                yield Panel(id="panel-settings", classes="panel")
            with Vertical(id="right-column"):
                yield PreviewPanel(id="panel-preview").add_class("panel")
                yield Panel(id="panel-print", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#panel-print").focus()

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        if focused is None or focused.id not in _GRID:
            return
        if event.key == "enter":
            self._activate_panel(focused.id)
            event.prevent_default()
            event.stop()
            return
        target_id = _GRID.get(focused.id, {}).get(event.key)
        if target_id:
            self.query_one(f"#{target_id}").focus()
            event.prevent_default()
            event.stop()

    def _activate_panel(self, panel_id: str) -> None:
        from phomemo_tui.screens.scanner import ScannerScreen

        locked = self.app.printer_service.state.value.startswith(  # type: ignore[union-attr]
            ("waiting", "printing")
        )
        match panel_id:
            case "panel-status" if not locked:
                self.app.push_screen(ScannerScreen())
            case "panel-settings" if not locked:
                pass  # wired in Task 10
            case "panel-preview" if not locked:
                self.query_one(PreviewPanel).on_click()

    def action_quit(self) -> None:
        self.app.exit()
