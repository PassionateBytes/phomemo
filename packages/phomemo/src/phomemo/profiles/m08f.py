"""Built-in printer profiles for the Phomemo M08F.

Registers M08F-A4 and M08F-Letter profiles on import. Profile data is
derived from the M08F Protocol Reference document.

Third-party code can follow the same pattern: define ``PrinterProfile``
instances and pass them to ``register_profile``.
"""

from phomemo.registry import PrinterProfile

_M08F_WRITE = "00000000-0000-0000-0000-00000000ff02"
_M08F_NOTIFY = "00000000-0000-0000-0000-00000000ff01"
_M08F_STATUS = "00000000-0000-0000-0000-00000000ff03"

# A4: 297mm sheet, 10mm sensor-to-head lead, ~287mm printable at 203 dpi.
M08F_A4 = PrinterProfile(
    name="M08F-A4",
    ble_name_pattern=r"^M08F",
    print_width_px=1680,
    max_rows=2290,
    top_margin_mm=10.0,
    write_uuid=_M08F_WRITE,
    notify_uuid=_M08F_NOTIFY,
    status_uuid=_M08F_STATUS,
)

# Letter: 279.4mm sheet minus the same 10mm lead = 269mm ≈ 2150 rows.
# Derived from the A4 measurement, not measured on Letter stock.
M08F_LETTER = PrinterProfile(
    name="M08F-Letter",
    ble_name_pattern=r"^M08F",
    print_width_px=1728,
    max_rows=2150,
    top_margin_mm=10.0,
    write_uuid=_M08F_WRITE,
    notify_uuid=_M08F_NOTIFY,
    status_uuid=_M08F_STATUS,
)
