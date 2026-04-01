"""Contextual Print / Cancel button tile."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from phomemo_tui.file_utils import get_page_count
from phomemo_tui.messages import CancelPrintRequested, PrintRequested
from phomemo_tui.printer_service import ServiceState

_PRINTING_STATES: frozenset[ServiceState] = frozenset(
    {
        ServiceState.WAITING_FOR_READY,
        ServiceState.PRINTING,
        ServiceState.WAITING_FOR_PAPER,
    }
)


class PrintButton(Static, can_focus=True):
    """Full-width tile that acts as Print or Cancel depending on state.

    States:
      - disabled (gray): not connected or no file loaded
      - ready (green): PRINT / PRINT PAGE N / PRINT ALL PAGES
      - cancel (amber): active print job or waiting state
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._locked = False

    def on_mount(self) -> None:
        self.refresh_state()

    def refresh_state(self) -> None:
        """Recompute label and CSS classes from current app state."""
        from phomemo_tui.app import PhomemoApp  # avoid circular at module level

        app = self.app
        if not isinstance(app, PhomemoApp):
            return

        service_state = app.printer_service.state
        connected = service_state not in (
            ServiceState.DISCONNECTED,
            ServiceState.SCANNING,
            ServiceState.CONNECTING,
        )
        file_path = app.current_file

        self.remove_class("ready", "cancel", "disabled")

        if self._locked or service_state in _PRINTING_STATES:
            self.update("[bold]CANCEL[/bold]")
            self.add_class("cancel")
            return

        if not connected or file_path is None:
            self.update("[dim]PRINT[/dim]")
            self.add_class("disabled")
            return

        # Ready — build contextual label
        label = _build_print_label(
            file_path, app.current_page, app.config.multi_page_mode
        )
        self.update(f"[bold]{label}[/bold]")
        self.add_class("ready")

    def on_click(self) -> None:
        self._activate()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._activate()
            event.prevent_default()

    def _activate(self) -> None:
        """Dispatch print or cancel action."""
        from phomemo_tui.app import PhomemoApp

        app = self.app
        if not isinstance(app, PhomemoApp):
            return

        service_state = app.printer_service.state

        if self._locked or service_state in _PRINTING_STATES:
            self.post_message(CancelPrintRequested())
            return

        connected = service_state not in (
            ServiceState.DISCONNECTED,
            ServiceState.SCANNING,
            ServiceState.CONNECTING,
        )
        if not connected or app.current_file is None:
            return  # disabled

        self.post_message(
            PrintRequested(source=app.current_file, start_page=app.current_page)
        )


def _build_print_label(path: Path, current_page: int, multi_page_mode: str) -> str:
    """Return contextual print button label.

    Args:
        path: Currently loaded file path.
        current_page: 1-based page number.
        multi_page_mode: 'manual' or 'auto'.

    Returns:
        Label string without markup.
    """
    try:
        total = get_page_count(path)
    except Exception:
        return "PRINT"

    if total <= 1:
        return "PRINT"
    if multi_page_mode == "manual":
        return f"PRINT PAGE {current_page}"
    return "PRINT ALL PAGES"
