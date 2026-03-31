"""Status panel widget showing connection and device state indicators."""

from __future__ import annotations

from phomemo.events import LidState, PaperState
from textual.widgets import Static

from phomemo_tui.messages import DeviceConnected, DeviceStateUpdated


def _dot(color: str) -> str:
    return f"[{color}]●[/{color}]"


class StatusPanel(Static, can_focus=True):
    """Displays BLE connection and device sensor state indicators.

    Shows four labeled indicator rows: connection, battery, lid, paper.
    Colors: green=ok, yellow=warning, dim=unknown/scanning.
    """

    def __init__(self) -> None:
        super().__init__()
        self._connected = False
        self._scanning = False
        self._device_name: str | None = None
        self._battery: int | None = None
        self._lid: LidState | None = None
        self._paper: PaperState | None = None

    def on_mount(self) -> None:
        self._render()

    def handle_device_scan_started(self) -> None:
        """Called by app when scanning begins."""
        self._scanning = True
        self._connected = False
        self._render()

    def handle_device_connected(self, msg: DeviceConnected) -> None:
        """Called by app on successful connection."""
        self._connected = True
        self._scanning = False
        self._device_name = msg.name
        self._render()

    def handle_device_disconnected(self) -> None:
        """Called by app on disconnection."""
        self._connected = False
        self._scanning = False
        self._battery = None
        self._lid = None
        self._paper = None
        self._render()

    def handle_state_updated(self, msg: DeviceStateUpdated) -> None:
        """Called by app when device sensor state changes."""
        self._battery = msg.battery
        self._lid = msg.lid
        self._paper = msg.paper
        self._render()

    def _render(self) -> None:
        """Rebuild the widget markup from current state."""
        if self._scanning:
            conn_line = " [dim]◌[/dim] Scanning…"
        elif self._connected:
            name = self._device_name or "Unknown"
            conn_line = f" {_dot('green')} {name}"
        else:
            conn_line = f" {_dot('dim')} Disconnected"

        # Battery
        if self._battery is None:
            bat_line = f" {_dot('dim')} Battery: —"
        elif self._battery >= 60:
            bat_line = f" {_dot('green')} Battery: {self._battery}%"
        elif self._battery >= 25:
            bat_line = f" {_dot('yellow')} Battery: {self._battery}%"
        else:
            bat_line = f" {_dot('red')} Battery: {self._battery}%"

        # Lid
        if self._lid is None:
            lid_line = f" {_dot('dim')} Lid: —"
        elif self._lid == LidState.CLOSED:
            lid_line = f" {_dot('green')} Lid: Closed"
        else:
            lid_line = f" {_dot('yellow')} Lid: Open"

        # Paper
        if self._paper is None:
            paper_line = f" {_dot('dim')} Paper: —"
        elif self._paper == PaperState.PRESENT:
            paper_line = f" {_dot('green')} Paper: Ready"
        else:
            paper_line = f" {_dot('yellow')} Paper: Empty"

        self.update(
            f"[dim]STATUS[/dim]\n\n{conn_line}\n{bat_line}\n{lid_line}\n{paper_line}"
        )
