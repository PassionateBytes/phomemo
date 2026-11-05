# This file is part of phomemo.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with phomemo.  If not, see <https://www.gnu.org/licenses/>.

"""Printer profile registry.

Each profile captures the physical and protocol characteristics of a
specific Phomemo printer model: print width, BLE UUIDs, timing
constraints, and supported features. The profile system is extensible —
add new models by registering a ``PrinterProfile`` instance via
``register_profile``.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from phomemo.protocol import Density

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
# PWG 5101.1 self-describing media size name: class, name, width x length, unit.
_PWG_SIZE_RE = re.compile(
    r"^[a-z]+_[a-z0-9.-]+_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(mm|in)$"
)


@dataclass(frozen=True, slots=True)
class MediaSize:
    """A sheet size a printer model takes.

    Attributes:
        pwg: The PWG self-describing name (``"iso_a4_210x297mm"``).
        width_mm: Width of the sheet as the name states it.
        length_mm: Length of the sheet as the name states it.
        tested: Whether the size has been printed on real hardware; an
            untested size ships with its geometry taken from documentation.
    """

    pwg: str
    width_mm: float
    length_mm: float
    tested: bool = True

    @classmethod
    def from_pwg(cls, pwg: str, tested: bool = True) -> Self:
        """Read the dimensions out of a PWG self-describing name.

        Args:
            pwg: A name such as ``"iso_a4_210x297mm"`` or
                ``"na_letter_8.5x11in"``.
            tested: Whether the size has been printed on real hardware.

        Returns:
            The size with its dimensions in millimetres.

        Raises:
            ValueError: If the name does not carry dimensions and a unit.
        """
        match = _PWG_SIZE_RE.match(pwg)
        if not match:
            raise ValueError(f"{pwg!r} is not a PWG media size name")
        factor = 25.4 if match.group(3) == "in" else 1.0
        return cls(
            pwg,
            float(match.group(1)) * factor,
            float(match.group(2)) * factor,
            tested,
        )


@dataclass(frozen=True, slots=True)
class PrinterProfile:
    """Hardware and protocol parameters for a Phomemo printer model.

    Attributes:
        name: Lower-case model identifier (e.g. ``"m08f"``), also the name of
            the model's manifest directory.
        ble_name_pattern: Regex pattern matched against BLE advertisement
            names during device discovery.
        print_width_px: Print head width in dots/pixels.
        dpi: Print resolution in dots per inch.
        max_chunk_bytes: Maximum BLE write payload in bytes. Determined by
            the negotiated ATT MTU minus 3 bytes of ATT overhead.
        negotiate_mtu: If ``True`` (default), the transport will attempt to read the
            negotiated BLE MTU at connect time and derive the effective chunk
            size from it (MTU minus 3 bytes ATT overhead). Falls back to
            ``max_chunk_bytes`` if the MTU cannot be determined.
        write_with_response: Use ATT Write Request (``True``, default) rather
            than Write Command for every write. The printer delays its
            response while its receive buffer is full, so the stream is paced
            by the print head and never overflows. Unacknowledged writes need
            ``chunk_delay_s`` and still overflow on long jobs.
        chunk_delay_s: Minimum delay between BLE writes in seconds. ``0.0``
            (default) with ``write_with_response``; only unacknowledged
            writes need a delay.
        band_height: Maximum rows per GS v 0 raster command.
        sheet_length_mm: Length of one sheet in the feed direction, or
            ``None`` for continuous roll media.
        top_margin_mm: Unprintable lead from the paper edge to the first
            printed row, set by the distance between the paper sensor and
            the print head.
        bottom_margin_mm: Rows kept free at the sheet end so the raster plus
            trailing feed never runs the sheet out of the sensor mid-job; an
            overrun leaves the printer in an error state.
        service_uuid: BLE GATT service UUID for the print data service.
        write_uuid: BLE characteristic UUID for writing commands/data.
        notify_uuid: BLE characteristic UUID for device events (``ff01``).
            All meaningful notifications arrive here: sensor state changes,
            query responses, and print completion signals.
        status_uuid: BLE characteristic UUID for the status echo channel
            (``ff03``). Echoes ``01 01`` for most writes and sends a fixed
            connect greeting on startup. Does not carry query responses or
            actionable device state; useful only for low-level debugging.
        density_levels: ``ESC N 04`` concentration values for the low,
            medium and high ``Density`` levels, or ``None`` when the model
            has no density control.
        supports_escpos_queries: Whether standard ESC/POS queries return
            meaningful data (False for M08F — use Phomemo queries instead).
        make: Manufacturer as shown to users.
        model_name: Model as the vendor writes it (``"M08F"``); ``name`` is
            the lower-case identifier.
        media: The sheet sizes the model takes.
        default_media: PWG name of the medium jobs get when they name none.
    """

    name: str
    ble_name_pattern: str
    print_width_px: int
    dpi: int = 203
    max_chunk_bytes: int = 244
    negotiate_mtu: bool = True
    write_with_response: bool = True
    chunk_delay_s: float = 0.0
    band_height: int = 256
    sheet_length_mm: float | None = None
    top_margin_mm: float = 0.0
    bottom_margin_mm: float = 0.0
    service_uuid: str = "0000ff00-0000-1000-8000-00805f9b34fb"
    write_uuid: str = "0000ff02-0000-1000-8000-00805f9b34fb"
    notify_uuid: str = "0000ff01-0000-1000-8000-00805f9b34fb"
    status_uuid: str = "0000ff03-0000-1000-8000-00805f9b34fb"
    density_levels: tuple[int, int, int] | None = None
    supports_escpos_queries: bool = False
    make: str = "Phomemo"
    model_name: str = ""
    media: tuple[MediaSize, ...] = ()
    default_media: str | None = None

    def __post_init__(self) -> None:
        """Validate profile fields on construction.

        Raises:
            ValueError: If ``print_width_px`` is not a multiple of 8, if
                ``sheet_length_mm`` is not positive, if the margins leave no
                printable length, or if any UUID field does not match the
                standard UUID format.
        """
        if self.print_width_px % 8 != 0:
            raise ValueError(
                f"print_width_px must be a multiple of 8, got {self.print_width_px}"
            )
        if self.sheet_length_mm is not None:
            if self.sheet_length_mm <= 0:
                raise ValueError(
                    "sheet_length_mm must be positive or None, "
                    f"got {self.sheet_length_mm}"
                )
            if self.top_margin_mm + self.bottom_margin_mm >= self.sheet_length_mm:
                raise ValueError("top and bottom margin leave no printable length")
        for field_name in ("service_uuid", "write_uuid", "notify_uuid", "status_uuid"):
            value = getattr(self, field_name)
            if not _UUID_RE.match(value):
                raise ValueError(f"{field_name} is not a valid UUID: {value!r}")

    def medium(self, pwg: str) -> MediaSize:
        """The model's sheet size with this PWG name.

        Args:
            pwg: PWG self-describing name.

        Returns:
            The matching entry of ``media``.

        Raises:
            KeyError: If the model does not take that size.
        """
        for size in self.media:
            if size.pwg == pwg:
                return size
        raise KeyError(f"{self.name} does not take {pwg!r}")

    @property
    def head_width_mm(self) -> float:
        """Width of the print head in millimetres."""
        return self.print_width_px / self.dpi * 25.4

    def rotates(self, size: MediaSize) -> bool:
        """Whether a sheet of this size is fed with its length across the head.

        The dimension closer to the head width lies across the head; when
        that is the sheet's length, a portrait page is printed rotated (A5
        on an A4 printer).

        Args:
            size: One of the model's sheet sizes.

        Returns:
            ``True`` when the sheet's length lies across the head.
        """
        head = self.head_width_mm
        return abs(size.width_mm - head) > abs(size.length_mm - head)

    def sheet_length_for(self, size: MediaSize) -> float:
        """Length of a sheet of this size along the feed direction.

        Args:
            size: One of the model's sheet sizes.

        Returns:
            The dimension that does not lie across the head: 297 mm for A4,
            148 mm for A5, 279.4 mm for Letter.
        """
        return size.width_mm if self.rotates(size) else size.length_mm

    def rows_for(self, length_mm: float | None) -> int | None:
        """Dot rows that fit between the margins of a sheet of the given length.

        Args:
            length_mm: Sheet length in the feed direction, or ``None`` for
                roll media.

        Returns:
            Printable rows, or ``None`` for roll media.

        Raises:
            ValueError: If the margins leave no printable length.
        """
        if length_mm is None:
            return None
        printable_mm = length_mm - self.top_margin_mm - self.bottom_margin_mm
        if printable_mm <= 0:
            raise ValueError(
                f"sheet of {length_mm}mm leaves nothing printable after the margins"
            )
        return int(printable_mm / 25.4 * self.dpi)

    @property
    def max_rows(self) -> int | None:
        """Printable rows of the default sheet, ``None`` for roll media."""
        return self.rows_for(self.sheet_length_mm)

    @property
    def lead_rows(self) -> int:
        """Rows covered by the top margin: the sheet lead the head cannot reach."""
        return round(self.top_margin_mm / 25.4 * self.dpi)

    @property
    def width_bytes(self) -> int:
        """Print width in bytes (8 pixels per byte, MSB-first)."""
        return self.print_width_px // 8

    def density_value(self, level: Density) -> int | None:
        """The model's concentration value for a density level.

        Args:
            level: The requested density.

        Returns:
            The ``ESC N 04`` value, or ``None`` without density control.
        """
        if self.density_levels is None:
            return None
        return self.density_levels[list(Density).index(level)]


_REGISTRY: dict[str, PrinterProfile] = {}


def get_profile(name: str) -> PrinterProfile:
    """Look up a registered printer profile by name.

    Args:
        name: Profile key (e.g. ``"m08f"``).

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


def profile_for_name(ble_name: str | None) -> PrinterProfile | None:
    """The registered profile whose name pattern matches an advertised name.

    Args:
        ble_name: Name the printer advertises over Bluetooth.

    Returns:
        The first matching profile in identifier order, or ``None``.
    """
    if not ble_name:
        return None
    for key in sorted(_REGISTRY):
        if re.search(_REGISTRY[key].ble_name_pattern, ble_name):
            return _REGISTRY[key]
    return None


Kind = type | tuple[type, ...]

_FIELDS: dict[str, Kind] = {
    "id": str,
    "make": str,
    "name": str,
    "ble_name_pattern": str,
    "print_width_px": int,
    "dpi": int,
    "band_height": int,
    "sheet_length_mm": (int, float),
    "top_margin_mm": (int, float),
    "bottom_margin_mm": (int, float),
    "media": list,
    "ble": dict,
}
_BLE_FIELDS: dict[str, Kind] = {
    "max_chunk_bytes": int,
    "negotiate_mtu": bool,
    "write_with_response": bool,
    "chunk_delay_s": (int, float),
    "service_uuid": str,
    "write_uuid": str,
    "notify_uuid": str,
    "status_uuid": str,
}


def _field(where: str, data: dict[str, Any], key: str, kind: Kind) -> Any:
    if key not in data:
        raise ValueError(f"{where}: {key}: missing")
    value = data[key]
    kinds = kind if isinstance(kind, tuple) else (kind,)
    if (isinstance(value, bool) and bool not in kinds) or not isinstance(value, kinds):
        expected = " or ".join(k.__name__ for k in kinds)
        raise ValueError(f"{where}: {key}: expected {expected}, got {value!r}")
    return value


def _media(where: str, entries: list[Any]) -> tuple[tuple[MediaSize, ...], str]:
    sizes: list[MediaSize] = []
    defaults: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("pwg"), str):
            raise ValueError(f"{where}: media: expected objects with a pwg name")
        tested = True
        if "tested" in entry:
            tested = _field(f"{where}: media", entry, "tested", bool)
        try:
            sizes.append(MediaSize.from_pwg(entry["pwg"], tested))
        except ValueError as exc:
            raise ValueError(f"{where}: media: {exc}") from None
        if entry.get("default") is True:
            defaults.append(entry["pwg"])
    if len(defaults) != 1:
        raise ValueError(f"{where}: media: exactly one default medium needed")
    return tuple(sizes), defaults[0]


def load_manifest(model_dir: Path) -> PrinterProfile:
    """Build a profile from a model manifest directory.

    The directory holds ``model.json`` and the model's icons; its name is the
    model identifier.

    Args:
        model_dir: The model's manifest directory.

    Returns:
        The profile the manifest defines.

    Raises:
        ValueError: If ``model.json`` does not parse, or a field is missing,
            of the wrong type or inconsistent; the message names file and
            field.
        OSError: If ``model.json`` cannot be read.
    """
    path = model_dir / "model.json"
    where = str(path)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{where}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{where}: expected an object")
    values = {key: _field(where, data, key, kind) for key, kind in _FIELDS.items()}
    if values["id"] != model_dir.name:
        raise ValueError(
            f"{where}: id: {values['id']!r} differs from the directory "
            f"{model_dir.name!r}"
        )
    ble = {
        key: _field(f"{where}: ble", values["ble"], key, kind)
        for key, kind in _BLE_FIELDS.items()
    }
    features = data.get("features", {})
    if not isinstance(features, dict):
        raise ValueError(f"{where}: features: expected an object")
    media, default_media = _media(where, values["media"])
    density_levels = None
    if "density" in data:
        density = _field(where, data, "density", dict)
        density_levels = tuple(
            _field(f"{where}: density", density, level.value, int) for level in Density
        )
    return PrinterProfile(
        name=values["id"],
        ble_name_pattern=values["ble_name_pattern"],
        print_width_px=values["print_width_px"],
        dpi=values["dpi"],
        band_height=values["band_height"],
        sheet_length_mm=float(values["sheet_length_mm"]),
        top_margin_mm=float(values["top_margin_mm"]),
        bottom_margin_mm=float(values["bottom_margin_mm"]),
        max_chunk_bytes=ble["max_chunk_bytes"],
        negotiate_mtu=ble["negotiate_mtu"],
        write_with_response=ble["write_with_response"],
        chunk_delay_s=float(ble["chunk_delay_s"]),
        service_uuid=ble["service_uuid"],
        write_uuid=ble["write_uuid"],
        notify_uuid=ble["notify_uuid"],
        status_uuid=ble["status_uuid"],
        density_levels=density_levels,
        supports_escpos_queries=bool(features.get("escpos_queries", False)),
        make=values["make"],
        model_name=values["name"],
        media=media,
        default_media=default_media,
    )
