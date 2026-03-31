from phomemo.protocol import QueryCommand


def test_query_command_is_bytes():
    assert isinstance(QueryCommand.BATTERY, bytes)
    assert QueryCommand.BATTERY == b"\x1f\x11\x08"


def test_query_command_members():
    names = [m.name for m in QueryCommand]
    assert "BATTERY" in names
    assert "FIRMWARE" in names
    assert "OTA_REBOOT" not in names
