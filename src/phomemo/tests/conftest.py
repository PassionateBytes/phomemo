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

"""Shared fixtures: no test scans for real Bluetooth devices."""

import json
import shutil
from pathlib import Path

import phomemo.bridge.server as server_module
import phomemo.registry as registry_module
import pytest
from bleak.backends.device import BLEDevice
from phomemo.registry import PrinterProfile, load_manifest

IN_RANGE_ADDRESS = "AA:BB:CC:DD:EE:FF"
MODELS = Path(__file__).parents[2] / "models"
VARIANT_CODE = "Q999"
VARIANT_SERIAL = "TESTQ999SERIAL0"
PLAIN_SERIAL = "TESTSERIAL00000"


@pytest.fixture
def variant_models_dir(tmp_path: Path) -> Path:
    """A manifest directory with the M08F and a variant of it keyed by a serial code.

    ``m08f-test`` shares the M08F's advertised name and claims printers whose
    serial contains ``Q999``.
    """
    root = tmp_path / "models"
    shutil.copytree(MODELS / "m08f", root / "m08f")
    variant = root / "m08f-test"
    shutil.copytree(MODELS / "m08f", variant)
    data = json.loads((variant / "model.json").read_text())
    data["id"] = "m08f-test"
    data["name"] = "M08F test variant"
    data["serial_codes"] = [VARIANT_CODE]
    (variant / "model.json").write_text(json.dumps(data))
    return root


@pytest.fixture
def variant_registered(
    variant_models_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> PrinterProfile:
    """Register the ``m08f-test`` variant for one test (via ``PHOMEMO_MODELS_DIR``)."""
    monkeypatch.setenv("PHOMEMO_MODELS_DIR", str(variant_models_dir))
    monkeypatch.setattr(registry_module, "_REGISTRY", dict(registry_module._REGISTRY))
    profile = load_manifest(variant_models_dir / "m08f-test")
    registry_module.register_profile(profile)
    return profile


@pytest.fixture(autouse=True)
def one_m08f_in_range(monkeypatch: pytest.MonkeyPatch) -> list[BLEDevice]:
    """Make the bridge's scans find one M08F; tests may change the list."""
    in_range = [BLEDevice(address=IN_RANGE_ADDRESS, name="M08F", details=None)]

    async def fake_discover(name_pattern: str, timeout: float) -> list[BLEDevice]:
        return list(in_range)

    monkeypatch.setattr(server_module, "discover", fake_discover)
    return in_range
