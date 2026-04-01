"""BLE device picker modal screen."""

from __future__ import annotations

from bleak.backends.device import BLEDevice
from phomemo import discover
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
)

from phomemo_tui.printer_service import match_profile as _match_profile


class ScannerScreen(ModalScreen):
    """BLE device discovery and selection modal."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("r", "refresh", "Rescan"),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._devices: list[BLEDevice] = []

    def compose(self) -> ComposeResult:
        """Build scanner layout."""
        yield Header()
        with Vertical(id="scanner-container"):
            yield Label("", id="scan-status")
            yield LoadingIndicator(id="scan-spinner")
            yield ListView(id="device-list")
            with Center():
                yield Button("Rescan", id="btn-rescan", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        """Start scan immediately."""
        self.query_one("#scan-spinner", LoadingIndicator).display = False
        self._do_scan()

    @work(exclusive=True)
    async def _do_scan(self) -> None:
        """Run BLE scan and populate device list."""
        status = self.query_one("#scan-status", Label)
        spinner = self.query_one("#scan-spinner", LoadingIndicator)
        device_list = self.query_one("#device-list", ListView)

        status.update("Scanning…")
        spinner.display = True
        device_list.clear()
        self._devices = []

        try:
            all_devices = await discover(timeout=5.0)
            # Profile-matched first, then alphabetical
            self._devices = sorted(
                all_devices,
                key=lambda d: (not bool(_match_profile(d.name)), d.name or ""),
            )
        except Exception as exc:
            spinner.display = False
            status.update(f"Scan error: {exc}")
            return

        spinner.display = False

        if not self._devices:
            status.update("No devices found. Make sure your printer is on.")
            return

        matched = sum(1 for d in self._devices if _match_profile(d.name))
        status.update(
            f"Found {len(self._devices)} device(s)"
            + (f", {matched} likely printer(s)" if matched else "")
        )

        for dev in self._devices:
            name = dev.name or "Unknown"
            profile = _match_profile(dev.name)
            label_text = f"{name}  ({dev.address})"
            if profile:
                label_text += f"  [{profile}]"
            item = ListItem(Label(label_text))
            if not profile:
                item.add_class("dim")
            device_list.append(item)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Connect to selected device and close screen."""
        idx = event.list_view.index
        if idx is not None and idx < len(self._devices):
            device = self._devices[idx]
            profile = _match_profile(device.name)
            await self.app.printer_service.connect_to(  # type: ignore[union-attr]
                device.address,
                device.name or device.address,
                self.app.config.profile_override or profile or "M08F-A4",  # type: ignore[union-attr]
            )
            self.app.pop_screen()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-rescan":
            self._do_scan()

    def action_refresh(self) -> None:
        self._do_scan()

    def action_go_back(self) -> None:
        self.app.pop_screen()
