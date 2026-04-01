"""Phomemo TUI application."""

from __future__ import annotations

import contextlib
from pathlib import Path

from textual.app import App

from phomemo_tui.config import AppConfig, load_config
from phomemo_tui.messages import (
    CancelPrintRequested,
    DeviceConnected,
    DeviceDisconnected,
    DeviceScanStarted,
    DeviceStateUpdated,
    FileSelected,
    PrintCancelled,
    PrintComplete,
    PrintError,
    PrintPageComplete,
    PrintProgress,
    PrintRequested,
    PrintWaitingForPaper,
    PrintWaitingForReady,
)
from phomemo_tui.printer_service import PrinterService, ServiceState
from phomemo_tui.screens.main_menu import MainMenuScreen
from phomemo_tui.widgets.preview_panel import PreviewPanel
from phomemo_tui.widgets.print_button import PrintButton
from phomemo_tui.widgets.settings_panel import SettingsPanel
from phomemo_tui.widgets.status_panel import StatusPanel


class PhomemoApp(App):
    """Textual application for Phomemo thermal printers."""

    TITLE = "Phomemo"
    CSS_PATH = "styles/app.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.config: AppConfig = load_config()
        self.printer_service = PrinterService(
            post_message=self.post_message,
            config=self.config,
        )
        # Session state (not persisted)
        self.current_file: Path | None = None
        self.current_page: int = 1

    def on_mount(self) -> None:
        """Push main menu and start the printer service."""
        self.push_screen(MainMenuScreen())
        self.run_worker(
            self.printer_service.start(),
            exclusive=True,
            group="connection",
            name="printer-service",
        )

    # ------------------------------------------------------------------
    # Service → UI message routing
    # ------------------------------------------------------------------

    def on_device_scan_started(self, _: DeviceScanStarted) -> None:
        self._update_status_panel()

    def on_device_connected(self, msg: DeviceConnected) -> None:
        with contextlib.suppress(Exception):
            self.query_one(StatusPanel).handle_device_connected(msg)
        self._update_print_button()

    def on_device_disconnected(self, _: DeviceDisconnected) -> None:
        with contextlib.suppress(Exception):
            self.query_one(StatusPanel).handle_device_disconnected()
        self._update_print_button()

    def on_device_state_updated(self, msg: DeviceStateUpdated) -> None:
        with contextlib.suppress(Exception):
            self.query_one(StatusPanel).handle_state_updated(msg)

    def on_print_waiting_for_ready(self, msg: PrintWaitingForReady) -> None:
        self._update_preview_footer(msg)
        self._update_print_button()

    def on_print_progress(self, msg: PrintProgress) -> None:
        self._update_preview_footer(msg)

    def on_print_page_complete(self, msg: PrintPageComplete) -> None:
        self.current_page = min(msg.page + 1, msg.total_pages)
        self._update_preview_panel()

    def on_print_waiting_for_paper(self, msg: PrintWaitingForPaper) -> None:
        self._update_preview_footer(msg)

    def on_print_complete(self, _: PrintComplete) -> None:
        self._update_preview_panel()
        self._update_print_button()
        self._set_panels_locked(False)

    def on_print_error(self, msg: PrintError) -> None:
        self.notify(msg.message, severity="error")
        self._update_print_button()
        self._set_panels_locked(False)

    def on_print_cancelled(self, _: PrintCancelled) -> None:
        self._update_print_button()
        self._set_panels_locked(False)

    # ------------------------------------------------------------------
    # UI → Service message routing
    # ------------------------------------------------------------------

    def on_print_requested(self, msg: PrintRequested) -> None:
        self._set_panels_locked(True)
        self.run_worker(
            self.printer_service.print_job(msg.source, msg.start_page),
            exclusive=True,
            group="print",
            name="print-job",
        )

    def on_cancel_print_requested(self, _: CancelPrintRequested) -> None:
        self.printer_service.request_cancel()

    def on_file_selected(self, msg: FileSelected) -> None:
        self.current_file = msg.path
        self.current_page = 1
        self.config.add_recent_file(str(msg.path))
        with contextlib.suppress(Exception):
            self.query_one(PreviewPanel).set_file(msg.path)
        self._update_print_button()

    # ------------------------------------------------------------------
    # Widget refresh helpers (stubs — widgets added in later tasks)
    # ------------------------------------------------------------------

    def _update_status_panel(self) -> None:
        try:
            panel = self.query_one(StatusPanel)
        except Exception:
            return

        state = self.printer_service.state
        if state == ServiceState.SCANNING:
            panel.handle_device_scan_started()
        elif state == ServiceState.DISCONNECTED:
            panel.handle_device_disconnected()

    def _update_preview_panel(self) -> None:
        with contextlib.suppress(Exception):
            panel = self.query_one(PreviewPanel)
            if self.current_file:
                panel.set_file(self.current_file, self.current_page)
            panel.clear_footer()

    def _update_preview_footer(self, msg: object) -> None:
        with contextlib.suppress(Exception):
            panel = self.query_one(PreviewPanel)
            if isinstance(msg, PrintProgress):
                panel.show_progress(msg)
            elif isinstance(msg, PrintWaitingForReady):
                panel.show_waiting_ready(msg)
            elif isinstance(msg, PrintWaitingForPaper):
                panel.show_waiting_paper(msg)

    def _update_print_button(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one(PrintButton).refresh_state()
        with contextlib.suppress(Exception):
            self.query_one(SettingsPanel).refresh_state()

    def _set_panels_locked(self, locked: bool) -> None:
        with contextlib.suppress(Exception):
            self.query_one(PreviewPanel).set_locked(locked)
        with contextlib.suppress(Exception):
            btn = self.query_one(PrintButton)
            btn._locked = locked
            btn.refresh_state()
        # Toggle locked CSS class on status/settings panels
        for panel_id in ("#panel-status", "#panel-settings"):
            with contextlib.suppress(Exception):
                p = self.query_one(panel_id)
                if locked:
                    p.add_class("locked")
                else:
                    p.remove_class("locked")
