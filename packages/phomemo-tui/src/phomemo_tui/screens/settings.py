"""Print settings modal screen."""

from __future__ import annotations

import contextlib

from phomemo import list_profiles
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Label, Select

_PROFILE_AUTO = "auto"


class SettingsScreen(ModalScreen):
    """Modal screen for configuring print settings."""

    BINDINGS = [Binding("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        """Build the settings form with Select dropdowns for each setting."""
        cfg = self.app.config  # type: ignore[union-attr]
        profiles = [(_PROFILE_AUTO.title(), _PROFILE_AUTO)] + [
            (name, name) for name in list_profiles()
        ]
        current_profile = cfg.profile_override or _PROFILE_AUTO

        yield Header()
        with Vertical(id="settings-container"):
            yield Label("Settings", classes="section-title")

            yield Label("Profile:")
            yield Select(profiles, value=current_profile, id="sel-profile")

            yield Label("Dither:")
            yield Select(
                [("Floyd-Steinberg", "floyd_steinberg"), ("Threshold", "threshold")],
                value=cfg.dither,
                id="sel-dither",
            )

            yield Label("Density:")
            yield Select(
                [("Light", "light"), ("Medium", "medium"), ("Dark", "dark")],
                value=cfg.density,
                id="sel-density",
            )

            yield Label("Fit:")
            yield Select(
                [
                    ("Fit Width", "fit_width"),
                    ("Fit Height", "fit_height"),
                    ("Stretch", "stretch"),
                    ("Original", "original"),
                ],
                value=cfg.fit,
                id="sel-fit",
            )

            yield Label("Multi-page mode:")
            yield Select(
                [("Manual", "manual"), ("Auto", "auto")],
                value=cfg.multi_page_mode,
                id="sel-multipage",
            )
        yield Footer()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Persist setting change immediately.

        Args:
            event: Select change event containing the new value.
        """
        cfg = self.app.config  # type: ignore[union-attr]
        match event.select.id:
            case "sel-profile":
                cfg.profile_override = (
                    None if event.value == _PROFILE_AUTO else str(event.value)
                )
            case "sel-dither":
                cfg.dither = str(event.value)  # type: ignore[assignment]
            case "sel-density":
                cfg.density = str(event.value)  # type: ignore[assignment]
            case "sel-fit":
                cfg.fit = str(event.value)  # type: ignore[assignment]
            case "sel-multipage":
                cfg.multi_page_mode = str(event.value)  # type: ignore[assignment]
        # Refresh print button label (mode may have changed)
        from phomemo_tui.widgets.print_button import PrintButton

        with contextlib.suppress(Exception):
            self.app.query_one(PrintButton).refresh_state()

    def action_go_back(self) -> None:
        """Close this modal and return to the previous screen."""
        self.app.pop_screen()
