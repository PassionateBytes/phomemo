"""Printer hardware profiles.

Each profile captures the physical and protocol characteristics of a
specific Phomemo printer model: print width, BLE UUIDs, timing
constraints, and supported features. The profile system is extensible —
add new models by registering a ``PrinterProfile`` instance.

Profile data is derived from the M08F Protocol Reference document.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PrinterProfile:
    """Hardware and protocol parameters for a Phomemo printer model.

    Attributes:
        name: Human-readable model identifier (e.g. ``"M08F-A4"``).
        ble_name_pattern: Regex pattern matched against BLE advertisement
            names during device discovery.
        print_width_px: Print head width in dots/pixels.
        dpi: Print resolution in dots per inch.
        max_chunk_bytes: Maximum BLE write payload in bytes. Determined by
            the negotiated ATT MTU minus 3 bytes of ATT overhead.
        chunk_delay_s: Minimum delay between BLE writes in seconds. 0.02s
            is reliable for full-page jobs on the M08F.
        band_height: Maximum rows per GS v 0 raster command.
        service_uuid: BLE GATT service UUID for the print data service.
        write_uuid: BLE characteristic UUID for writing commands/data.
        notify_uuid: BLE characteristic UUID for device events (``ff01``).
        status_uuid: BLE characteristic UUID for status echo (``ff03``).
        supports_density: Whether ESC N 04 concentration is functional.
        supports_escpos_queries: Whether standard ESC/POS queries return
            meaningful data (False for M08F — use Phomemo queries instead).
    """

    name: str
    ble_name_pattern: str
    print_width_px: int
    dpi: int = 203
    max_chunk_bytes: int = 244
    chunk_delay_s: float = 0.02
    band_height: int = 256
    service_uuid: str = "0000ff00-0000-1000-8000-00805f9b34fb"
    write_uuid: str = "0000ff02-0000-1000-8000-00805f9b34fb"
    notify_uuid: str = "0000ff01-0000-1000-8000-00805f9b34fb"
    status_uuid: str = "0000ff03-0000-1000-8000-00805f9b34fb"
    supports_density: bool = True
    supports_escpos_queries: bool = False

    @property
    def width_bytes(self) -> int:
        """Print width in bytes (8 pixels per byte, MSB-first)."""
        return self.print_width_px // 8


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, PrinterProfile] = {}


def _register(profile: PrinterProfile) -> PrinterProfile:
    """Add a profile to the global registry.

    Args:
        profile: The printer profile to register.

    Returns:
        The same profile instance (allows inline use).
    """
    _REGISTRY[profile.name] = profile
    return profile


# M08F profiles — derived from the protocol reference document.
_M08F_WRITE = "0000ff02-0000-1000-8000-00805f9b34fb"
_M08F_NOTIFY = "0000ff01-0000-1000-8000-00805f9b34fb"
_M08F_STATUS = "0000ff03-0000-1000-8000-00805f9b34fb"

_register(
    PrinterProfile(
        name="M08F-A4",
        ble_name_pattern=r"^M08F",
        print_width_px=1680,
        write_uuid=_M08F_WRITE,
        notify_uuid=_M08F_NOTIFY,
        status_uuid=_M08F_STATUS,
    )
)

_register(
    PrinterProfile(
        name="M08F-Letter",
        ble_name_pattern=r"^M08F",
        print_width_px=1728,
        write_uuid=_M08F_WRITE,
        notify_uuid=_M08F_NOTIFY,
        status_uuid=_M08F_STATUS,
    )
)


def get_profile(name: str) -> PrinterProfile:
    """Look up a registered printer profile by name.

    Args:
        name: Profile key (e.g. ``"M08F-A4"``).

    Returns:
        The matching ``PrinterProfile``.

    Raises:
        KeyError: If no profile is registered under that name.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown profile {name!r}. Available: {available}") from None


def list_profiles() -> list[str]:
    """Return the names of all registered printer profiles.

    Returns:
        Sorted list of profile name strings.
    """
    return sorted(_REGISTRY)


def register_profile(profile: PrinterProfile) -> None:
    """Register a custom printer profile.

    Allows third-party code to add profiles for printer models not
    shipped with this library.

    Args:
        profile: The profile to register. Overwrites any existing
            profile with the same name.
    """
    _REGISTRY[profile.name] = profile
