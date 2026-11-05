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

"""Tests for model manifests and the profiles built from them."""

import json
import shutil
from pathlib import Path

import phomemo.profiles  # noqa: F401, registers the built-in profiles
import pytest
from phomemo.profiles import models_dir
from phomemo.registry import get_profile, load_manifest, profile_for_name

MODELS = Path(__file__).parents[2] / "models"


def test_m08f_manifest_gives_the_m08f_profile() -> None:
    profile = load_manifest(MODELS / "m08f")
    assert profile.name == "m08f"
    assert profile.make == "Phomemo"
    assert profile.model_name == "M08F"
    assert profile.ble_name_pattern == "^M08F"
    assert (profile.print_width_px, profile.dpi, profile.band_height) == (
        1680,
        203,
        256,
    )
    assert profile.sheet_length_mm == 297.0
    assert (profile.top_margin_mm, profile.bottom_margin_mm) == (10.0, 5.0)
    assert [m.pwg for m in profile.media] == [
        "iso_a4_210x297mm",
        "iso_a5_148x210mm",
        "na_letter_8.5x11in",
    ]
    assert [m.tested for m in profile.media] == [True, True, False]
    assert profile.default_media == "iso_a4_210x297mm"
    assert profile.max_chunk_bytes == 244
    assert profile.negotiate_mtu and profile.write_with_response
    assert profile.chunk_delay_s == 0.0
    assert profile.service_uuid == "0000ff00-0000-1000-8000-00805f9b34fb"
    assert profile.write_uuid == "00000000-0000-0000-0000-00000000ff02"
    assert profile.notify_uuid == "00000000-0000-0000-0000-00000000ff01"
    assert profile.status_uuid == "00000000-0000-0000-0000-00000000ff03"
    assert profile.density_levels == (1, 5, 6)
    assert not profile.supports_escpos_queries
    assert profile.max_rows == 2253


def test_m08f_is_registered_under_its_id() -> None:
    assert get_profile("m08f") == load_manifest(MODELS / "m08f")


def test_m08f_manifest_has_the_three_icons() -> None:
    for size in (48, 128, 512):
        assert (MODELS / "m08f" / f"icon-{size}.png").is_file()


@pytest.mark.parametrize("ble_name", ["M08F", "M08F-0B4D", "M08F_XYZ"])
def test_profile_for_name_matches_m08f_names(ble_name: str) -> None:
    assert profile_for_name(ble_name) == get_profile("m08f")


@pytest.mark.parametrize("ble_name", ["", "Q30", "XM08F", None])
def test_profile_for_name_without_a_match(ble_name: str | None) -> None:
    assert profile_for_name(ble_name) is None


def _copy_model(tmp_path: Path) -> tuple[Path, dict]:
    target = tmp_path / "m08f"
    shutil.copytree(MODELS / "m08f", target)
    return target, json.loads((target / "model.json").read_text())


def _write(target: Path, data: dict) -> None:
    (target / "model.json").write_text(json.dumps(data))


@pytest.mark.parametrize("field", ["make", "name", "print_width_px", "media"])
def test_manifest_without_a_required_field_is_rejected(
    tmp_path: Path, field: str
) -> None:
    target, data = _copy_model(tmp_path)
    del data[field]
    _write(target, data)
    with pytest.raises(ValueError, match=rf"model\.json: {field}: missing"):
        load_manifest(target)


def test_manifest_with_a_wrong_type_is_rejected(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    data["dpi"] = "203"
    _write(target, data)
    with pytest.raises(ValueError, match=r"model\.json: dpi: expected"):
        load_manifest(target)


def test_manifest_id_must_match_its_directory(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    data["id"] = "m09"
    _write(target, data)
    with pytest.raises(ValueError, match=r"id: 'm09' differs from the directory"):
        load_manifest(target)


def test_manifest_needs_one_default_medium(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    data["media"] = [{"pwg": "iso_a4_210x297mm"}, {"pwg": "iso_a5_148x210mm"}]
    _write(target, data)
    with pytest.raises(ValueError, match=r"media: exactly one default"):
        load_manifest(target)


def test_models_dir_prefers_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PHOMEMO_MODELS_DIR", str(tmp_path))
    assert models_dir() == tmp_path


def test_models_dir_finds_the_manifests_in_a_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PHOMEMO_MODELS_DIR", raising=False)
    assert (models_dir() / "m08f" / "model.json").is_file()


def test_manifest_without_density_has_no_density_control(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    del data["density"]
    _write(target, data)
    assert load_manifest(target).density_levels is None


def test_manifest_density_needs_all_three_levels(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    data["density"] = {"low": 1, "high": 6}
    _write(target, data)
    with pytest.raises(ValueError, match=r"density: medium: missing"):
        load_manifest(target)


def test_manifest_media_needs_a_pwg_name_with_dimensions(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    data["media"] = [{"pwg": "letter", "default": True}]
    _write(target, data)
    with pytest.raises(ValueError, match=r"media: 'letter' is not a PWG"):
        load_manifest(target)


def test_manifest_media_tested_must_be_a_boolean(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    data["media"] = [{"pwg": "iso_a4_210x297mm", "default": True, "tested": "no"}]
    _write(target, data)
    with pytest.raises(ValueError, match=r"media: tested: expected bool"):
        load_manifest(target)


def test_manifest_media_without_tested_counts_as_tested(tmp_path: Path) -> None:
    target, data = _copy_model(tmp_path)
    data["media"] = [{"pwg": "iso_a4_210x297mm", "default": True}]
    _write(target, data)
    (medium,) = load_manifest(target).media
    assert medium.tested
