"""Main dashboard screen with 4-panel layout."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


# Grid navigation: widget-id → {direction: target-id}
_GRID: dict[str, dict[str, str]] = {
    "panel-status":   {"right": "panel-preview",  "down": "panel-settings"},
    "panel-settings": {"right": "panel-print",    "up":   "panel-status"},
    "panel-preview":  {"left":  "panel-status",   "down": "panel-print"},
    "panel-print":    {"left":  "panel-settings", "up":   "panel-preview"},
}


class Panel(Static, can_focus=True):
    """A focusable dashboard tile."""


class MainMenuScreen(Screen):
    """4-panel dashboard: status, settings, preview, print button."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Build the 2x2 grid layout."""
        yield Header()
        with Horizontal(id="dashboard"):
            with Vertical(id="left-column"):
                yield Panel(id="panel-status", classes="panel")
                yield Panel(id="panel-settings", classes="panel")
            with Vertical(id="right-column"):
                yield Panel(id="panel-preview", classes="panel")
                yield Panel(id="panel-print", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the print button on startup."""
        self.query_one("#panel-print").focus()

    def on_key(self, event) -> None:
        """Arrow-key grid navigation + Enter to activate panels."""
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
        """Open the sub-screen or action for a panel.

        Args:
            panel_id: The CSS id of the activated panel.
        """
        # Panels will be wired to real screens/actions in later tasks
        pass

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
