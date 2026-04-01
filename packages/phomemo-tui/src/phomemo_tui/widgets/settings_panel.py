"""Settings summary panel (read-only; click opens SettingsScreen)."""

from __future__ import annotations

from textual.widgets import Static


class SettingsPanel(Static, can_focus=True):
    """Displays current print settings. Activating opens SettingsScreen."""

    def on_mount(self) -> None:
        self.refresh_state()

    def refresh_state(self) -> None:
        """Rebuild content from current config."""
        from phomemo_tui.app import PhomemoApp

        app = self.app
        if not isinstance(app, PhomemoApp):
            return

        cfg = app.config

        if cfg.profile_override is None:
            # Auto mode — try to match profile from last known device name
            from phomemo_tui.printer_service import match_profile

            matched = match_profile(cfg.last_device_name)
            if matched:
                profile_line = f"{matched} (auto)"
            else:
                profile_line = "Auto"
        else:
            profile_line = cfg.profile_override

        dither = cfg.dither.replace("_", " ").title()
        density = cfg.density.title()
        fit = cfg.fit.replace("_", " ").title()
        mode = cfg.multi_page_mode.title()

        self.update(
            "[dim]SETTINGS[/dim]\n\n"
            f" {profile_line}\n"
            f" Dither: {dither}\n"
            f" Density: {density}\n"
            f" Fit: {fit}\n"
            f" Multi-page: {mode}"
        )

    def on_click(self) -> None:
        self._open_settings()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._open_settings()
            event.prevent_default()

    def _open_settings(self) -> None:
        from phomemo_tui.screens.settings import SettingsScreen

        self.app.push_screen(SettingsScreen(), callback=self._on_settings_closed)

    def _on_settings_closed(self, _: object) -> None:
        self.refresh_state()
