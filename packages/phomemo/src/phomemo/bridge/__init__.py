"""Bridge daemon: drives a printer over a unix socket for a printer application.

The bridge owns the device side (BLE link, raster encoding, tone
conversion, sheet handling); a printer application owns the IPP side and
talks to the bridge with a few JSON commands. See ``protocol`` for the wire
format and ``server`` for the command set.
"""
