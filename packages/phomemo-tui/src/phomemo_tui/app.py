"""Phomemo TUI application.

The main Textual application for interacting with Phomemo printers.
Provides screens for scanning, connecting, monitoring, and printing.
"""

from phomemo import (
    BatteryEvent,
    DeviceEvent,
    MotorStopEvent,
    Printer,
    SensorEvent,
    discover,
)
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

# ------------------------------------------------------------------
# Scan screen
# ------------------------------------------------------------------


class ScanScreen(Screen):
    """BLE device scanner screen.

    Scans for nearby Phomemo printers and lets the user select one
    to connect to.
    """

    BINDINGS = [
        Binding("r", "scan", "Re-scan"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def compose(self) -> ComposeResult:
        """Build the scan screen layout."""
        yield Header()
        yield Label("Scanning for printers...", id="scan-status")
        yield ListView(id="device-list")
        yield Footer()

    async def on_mount(self) -> None:
        """Start scanning when the screen mounts."""
        await self.action_scan()

    async def action_scan(self) -> None:
        """Perform a BLE scan and populate the device list."""
        status = self.query_one("#scan-status", Label)
        device_list = self.query_one("#device-list", ListView)
        status.update("Scanning...")
        device_list.clear()

        devices = await discover(timeout=5.0)
        if not devices:
            status.update("No devices found. Press [bold]r[/] to re-scan.")
            return

        for dev in devices:
            name = dev.name or "Unknown"
            device_list.append(
                ListItem(Label(f"{name}  ({dev.address})"), name=dev.address)
            )
        status.update(f"Found {len(devices)} device(s). Select one to connect.")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle device selection from the list."""
        address = event.item.name
        if address:
            app = self.app
            if isinstance(app, PhomemoApp):
                await app.connect_to_printer(address)


# ------------------------------------------------------------------
# Main screen
# ------------------------------------------------------------------


class MainScreen(Screen):
    """Main printer control screen.

    Shows device status and provides controls for printing and
    paper management.
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "disconnect", "Disconnect"),
        Binding("i", "query_info", "Device Info"),
        Binding("f", "feed", "Feed Paper"),
        Binding("e", "eject", "Eject Paper"),
    ]

    def compose(self) -> ComposeResult:
        """Build the main screen layout."""
        yield Header()
        with Vertical():
            yield Label("Connected", id="connection-status")
            yield Static("", id="device-info")
            yield Static("", id="event-log")
            with Horizontal():
                yield Button("Device Info", id="btn-info", variant="default")
                yield Button("Feed", id="btn-feed", variant="default")
                yield Button("Eject", id="btn-eject", variant="warning")
                yield Button("Disconnect", id="btn-disconnect", variant="error")
        yield Footer()

    async def on_mount(self) -> None:
        """Query device info on mount."""
        await self.action_query_info()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Route button presses to actions."""
        match event.button.id:
            case "btn-info":
                await self.action_query_info()
            case "btn-feed":
                await self.action_feed()
            case "btn-eject":
                await self.action_eject()
            case "btn-disconnect":
                await self.action_disconnect()

    async def action_query_info(self) -> None:
        """Query and display device information."""
        app = self.app
        if not isinstance(app, PhomemoApp) or app.printer is None:
            return

        info_widget = self.query_one("#device-info", Static)
        info_widget.update("Querying...")

        try:
            info = await app.printer.query_device_info(timeout=1.0)
            bat = f"{info.battery}%" if info.battery is not None else "--"
            lid = info.lid.value if info.lid else "--"
            paper = info.paper.value if info.paper else "--"
            aoff = info.auto_off_minutes
            timer = f"{aoff}min" if aoff is not None else "--"
            lines = [
                f"Battery:   {bat}",
                f"Firmware:  {info.firmware or '--'}",
                f"Serial:    {info.serial or '--'}",
                f"Lid:       {lid}",
                f"Paper:     {paper}",
                f"Auto-off:  {timer}",
            ]
            info_widget.update("\n".join(lines))
        except Exception as exc:
            info_widget.update(f"Error: {exc}")

    async def action_feed(self) -> None:
        """Feed paper a small amount."""
        app = self.app
        if isinstance(app, PhomemoApp) and app.printer is not None:
            await app.printer.feed(20)

    async def action_eject(self) -> None:
        """Eject the current sheet."""
        app = self.app
        if isinstance(app, PhomemoApp) and app.printer is not None:
            await app.printer.eject_paper()

    async def action_disconnect(self) -> None:
        """Disconnect and return to the scan screen."""
        app = self.app
        if isinstance(app, PhomemoApp):
            await app.disconnect_printer()

    def add_event(self, event: DeviceEvent) -> None:
        """Append a device event to the event log display.

        Args:
            event: The parsed device event.
        """
        log = self.query_one("#event-log", Static)
        text = _format_event(event)
        current = str(log.renderable)
        # Keep last 10 lines
        lines = current.split("\n") if current else []
        lines.append(text)
        log.update("\n".join(lines[-10:]))


def _format_event(event: DeviceEvent) -> str:
    """Format a device event for display.

    Args:
        event: The parsed device event.

    Returns:
        A human-readable string representation.
    """
    match event:
        case SensorEvent(lid=lid) if lid is not None:
            return f"Lid: {lid.value}"
        case SensorEvent(paper=paper) if paper is not None:
            return f"Paper: {paper.value}"
        case BatteryEvent(percent=pct):
            return f"Battery: {pct}%"
        case MotorStopEvent():
            return "Print complete (motor stopped)"
        case _:
            return f"Event: {event.raw.hex()}" if hasattr(event, "raw") else str(event)


# ------------------------------------------------------------------
# Application
# ------------------------------------------------------------------


class PhomemoApp(App):
    """Textual application for Phomemo thermal printers.

    Manages the printer connection lifecycle and screen navigation.
    """

    TITLE = "Phomemo"
    CSS = """
    #device-info {
        margin: 1 2;
        padding: 1 2;
        background: $surface;
    }
    #event-log {
        margin: 1 2;
        padding: 1 2;
        background: $surface;
        min-height: 5;
    }
    #scan-status {
        margin: 1 2;
    }
    Horizontal {
        margin: 1 2;
        height: auto;
    }
    Button {
        margin: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.printer: Printer | None = None
        self._main_screen: MainScreen | None = None

    def on_mount(self) -> None:
        """Show the scan screen on startup."""
        self.push_screen(ScanScreen())

    async def connect_to_printer(self, address: str) -> None:
        """Connect to a printer and switch to the main screen.

        Args:
            address: BLE MAC address of the printer.
        """
        self.printer = Printer("M08F-A4")

        # Register event handler for the main screen
        self._main_screen = MainScreen()

        def on_event(event: DeviceEvent) -> None:
            if self._main_screen is not None:
                self.call_from_thread(self._main_screen.add_event, event)

        self.printer.on_event(on_event)

        try:
            await self.printer.connect(address)
            self.switch_screen(self._main_screen)
        except Exception as exc:
            self.notify(f"Connection failed: {exc}", severity="error")

    async def disconnect_printer(self) -> None:
        """Disconnect the printer and return to the scan screen."""
        if self.printer is not None:
            await self.printer.disconnect()
            self.printer = None
        self._main_screen = None
        self.switch_screen(ScanScreen())


def main() -> None:
    """Entry point for the phomemo-tui command."""
    app = PhomemoApp()
    app.run()


if __name__ == "__main__":
    main()
