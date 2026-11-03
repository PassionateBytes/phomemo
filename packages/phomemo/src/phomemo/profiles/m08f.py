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

# The sensor sits 10mm ahead of the head, so the first 10mm of a sheet cannot be
# printed. The bottom margin keeps the raster off the sheet end; a page longer
# than that is clipped.
_TOP_MARGIN_MM = 10.0
_BOTTOM_MARGIN_MM = 5.0

M08F_A4 = PrinterProfile(
    name="M08F-A4",
    ble_name_pattern=r"^M08F",
    print_width_px=1680,
    sheet_length_mm=297.0,
    top_margin_mm=_TOP_MARGIN_MM,
    bottom_margin_mm=_BOTTOM_MARGIN_MM,
    write_uuid=_M08F_WRITE,
    notify_uuid=_M08F_NOTIFY,
    status_uuid=_M08F_STATUS,
)

# Letter margins copied from A4, not measured on Letter stock.
M08F_LETTER = PrinterProfile(
    name="M08F-Letter",
    ble_name_pattern=r"^M08F",
    print_width_px=1728,
    sheet_length_mm=279.4,
    top_margin_mm=_TOP_MARGIN_MM,
    bottom_margin_mm=_BOTTOM_MARGIN_MM,
    write_uuid=_M08F_WRITE,
    notify_uuid=_M08F_NOTIFY,
    status_uuid=_M08F_STATUS,
)
