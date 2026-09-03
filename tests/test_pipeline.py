"""Input validation, stage selection and the reported crash."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hw2a000ff.errors import ConversionError, MissingDirectoryError
from hw2a000ff.pipeline import convert_all, convert_single_unit, preflight
from hw2a000ff.settings import Settings, SettingsError


# --------------------------------------------------------------- the crash


def test_missing_sound_directory_is_skipped_not_fatal(settings: Settings, campaign: Path):
    """`Directory.GetFiles(source + "/sound")` — FormMain.cs:387.

    A generated campaign has no sound folder. The original raises a bare
    IOException that names no path and takes the whole conversion down.
    """
    shutil.rmtree(campaign / "assets" / "sound")

    report = convert_all(settings)

    assert report.file_count > 0
    assert any("sound" in note for note in report.skipped_stages)
    assert "soundbank" not in report.counts


def test_missing_levels_directory_is_skipped_not_fatal(settings: Settings, campaign: Path):
    """`Directory.GetFiles(levelsPath + "levels\\")` — FormMain.cs:371."""
    shutil.rmtree(campaign / "campaign" / "levels")

    report = convert_all(settings)

    assert report.file_count > 0
    assert any("levels" in note for note in report.skipped_stages)
    assert "level" not in report.counts


def test_both_optional_directories_missing_still_converts(settings: Settings, campaign: Path):
    shutil.rmtree(campaign / "assets" / "sound")
    shutil.rmtree(campaign / "campaign" / "levels")

    report = convert_all(settings)

    assert report.counts["actor"] == 1
    assert len(report.skipped_stages) >= 2


def test_source_pointing_at_a_file_names_the_path(settings: Settings, campaign: Path):
    """`Directory.GetFiles(sourcePath)` — FormMain.cs:204."""
    settings.source_path = campaign / "assets" / "actors" / "gnaar.xml"

    with pytest.raises(SettingsError) as exc:
        preflight(settings)

    assert "not a directory" in str(exc.value)
    assert "gnaar.xml" in str(exc.value)


def test_missing_source_directory_names_the_path(settings: Settings, tmp_path: Path):
    settings.source_path = tmp_path / "nowhere"

    with pytest.raises(SettingsError) as exc:
        preflight(settings)

    assert "nowhere" in str(exc.value)


# ------------------------------------------------------ the Hammerwatch.exe gate


def test_missing_game_install_is_only_a_note(settings: Settings):
    """FormMain.cs:165 refuses to run without Hammerwatch.exe as a sibling."""
    notes = preflight(settings)
    assert any("Hammerwatch.exe" in note for note in notes)


def test_require_game_install_restores_the_hard_check(settings: Settings):
    settings.require_game_install = True
    with pytest.raises(ConversionError) as exc:
        preflight(settings)
    assert "Hammerwatch" in str(exc.value)


def test_game_install_present_is_detected(settings: Settings, campaign: Path):
    (campaign / "Hammerwatch.exe").write_bytes(b"MZ")
    assert settings.game_install_present()
    assert not any("Hammerwatch.exe" in n for n in preflight(settings))


# ------------------------------------------------------------------- stages


def test_only_actors_converts_just_actors(settings: Settings):
    settings.stages = {"actors"}
    report = convert_all(settings)
    assert set(report.counts) == {"actor"}


def test_skipping_levels_leaves_them_out(settings: Settings):
    settings.stages = settings.stages - {"levels"}
    report = convert_all(settings)
    assert "level" not in report.counts
    assert (settings.output_path / "actors" / "gnaar.unit").is_file()


def test_dry_run_writes_nothing(settings: Settings):
    report = convert_all(settings, dry_run=True)
    assert report.file_count == 0
    assert not settings.output_path.exists()


# ------------------------------------------------------------- levels.xml


def test_levels_xml_must_be_named_levels_xml(settings: Settings, campaign: Path):
    other = campaign / "campaign" / "index.xml"
    other.write_text("<campaign/>")
    settings.levels_path = other
    with pytest.raises(SettingsError) as exc:
        preflight(settings)
    assert "levels.xml" in str(exc.value)


def test_level_exit_resolves_level_ids(settings: Settings):
    convert_all(settings)
    level = (settings.output_path / "levels" / "lvl1.lvl").read_text()
    # levels.xml maps id 2 to levels/lvl2.xml.
    assert "levels/lvl2.lvl" in level
    assert "HWPORT.UNKNOWN.LVL" not in level


def test_unknown_script_node_is_reported_not_fatal(settings: Settings):
    report = convert_all(settings)
    assert any("SomeFutureNode" in w for w in report.warnings)
    assert "UnknownScriptLink" in (settings.output_path / "levels" / "lvl1.lvl").read_text()


# ----------------------------------------------------------------- scales


def test_scales_stay_integral_in_int_fields(settings: Settings):
    settings.damage_scale = 1.5
    settings.stages = {"actors"}
    convert_all(settings)
    unit = (settings.output_path / "actors" / "gnaar.unit").read_text()
    # 8 damage * 1.5 = 12; the original would emit a float here for odd scales.
    assert '<int name="dmg">12</int>' in unit
    assert '<int name="dmg">12.0' not in unit


def test_odd_scale_never_writes_a_fraction_into_an_int(settings: Settings):
    settings.damage_scale = 1.3
    settings.stages = {"actors"}
    convert_all(settings)
    unit = (settings.output_path / "actors" / "gnaar.unit").read_text()
    assert '<int name="dmg">10</int>' in unit
    assert "." not in unit.split('<int name="dmg">')[1].split("<")[0]


# ------------------------------------------------------------ single unit


def test_convert_single_unit(settings: Settings, campaign: Path, tmp_path: Path):
    out = tmp_path / "gnaar.unit"
    slot = convert_single_unit(settings, campaign / "assets" / "actors" / "gnaar.xml", out)
    assert slot == "actor"
    assert out.read_text().startswith('<unit netsync="position" slot="actor">')


def test_convert_single_unit_rejects_unsupported_roots(settings: Settings, tmp_path: Path):
    source = tmp_path / "thing.xml"
    source.write_text("<mystery/>")
    with pytest.raises(ConversionError) as exc:
        convert_single_unit(settings, source, tmp_path / "out.unit")
    assert "unsupported unit type" in str(exc.value)


# --------------------------------------------------------------- line endings


def test_crlf_line_endings(settings: Settings):
    settings.line_endings = "\r\n"
    settings.stages = {"actors"}
    convert_all(settings)
    raw = (settings.output_path / "actors" / "gnaar.unit").read_bytes()
    assert b"\r\n" in raw


def test_lf_is_the_default(settings: Settings):
    settings.stages = {"actors"}
    convert_all(settings)
    raw = (settings.output_path / "actors" / "gnaar.unit").read_bytes()
    assert b"\r\n" not in raw
