"""Settings, the config file, and the command line."""

from __future__ import annotations

from pathlib import Path

import pytest

from hw2a000ff.cli import main
from hw2a000ff.settings import STAGES, Settings, SettingsError


def test_defaults_match_the_original_form(tmp_path: Path):
    s = Settings()
    assert s.stages == set(STAGES)          # every checkbox ticked
    assert s.strings_key_prefix == "hwport."
    assert (s.health_scale, s.range_scale, s.damage_scale, s.speed_scale) == (1.0,) * 4
    assert s.modify_wall_collision is False


def test_toml_round_trip(tmp_path: Path, campaign: Path):
    config = tmp_path / "hw.toml"
    config.write_text(
        # as_posix: a Windows path's backslashes are escape sequences in TOML strings.
        f'[paths]\nsource = "{(campaign / "assets").as_posix()}"\noutput = "{(tmp_path / "out").as_posix()}"\n'
        'prefix = "hwport/"\nmaterials = "system/default.mats"\n\n'
        "[convert]\nlevels = false\nsounds = false\n\n"
        "[scales]\ndamage = 2.0\n\n"
        '[strings]\nkey_prefix = "mymod."\n\n'
        '[options]\nline_endings = "crlf"\n'
    )
    s = Settings.from_toml(config)
    assert s.output_prefix == "hwport/"
    assert s.materials_path == "system/default.mats"
    assert "levels" not in s.stages and "sounds" not in s.stages
    assert "actors" in s.stages
    assert s.damage_scale == 2.0
    assert s.strings_key_prefix == "mymod."
    assert s.line_endings == "\r\n"


def test_relative_config_paths_resolve_against_the_config(tmp_path: Path):
    (tmp_path / "assets").mkdir()
    config = tmp_path / "hw.toml"
    config.write_text('[paths]\nsource = "assets"\noutput = "out"\n')
    s = Settings.from_toml(config)
    assert s.source_path == (tmp_path / "assets").resolve()


def test_unknown_config_section_is_rejected(tmp_path: Path):
    config = tmp_path / "hw.toml"
    config.write_text('[nonsense]\nkey = 1\n')
    with pytest.raises(SettingsError) as exc:
        Settings.from_toml(config)
    assert "nonsense" in str(exc.value)


def test_non_positive_scale_is_rejected(campaign: Path, tmp_path: Path):
    s = Settings(source_path=campaign / "assets", output_path=tmp_path / "out", damage_scale=0)
    with pytest.raises(SettingsError):
        s.validate()


# ------------------------------------------------------------------------ CLI


def test_cli_convert(campaign: Path, tmp_path: Path, capsys):
    code = main([
        "convert",
        "--source", str(campaign / "assets"),
        "--levels-xml", str(campaign / "campaign" / "levels.xml"),
        "--output", str(tmp_path / "out"),
        "--prefix", "hwport/",
    ])
    assert code == 0
    assert (tmp_path / "out" / "actors" / "gnaar.unit").is_file()
    assert "Converted" in capsys.readouterr().out


def test_cli_only_and_skip_are_mutually_exclusive(campaign: Path, tmp_path: Path, capsys):
    code = main([
        "convert", "--source", str(campaign / "assets"),
        "--output", str(tmp_path / "out"), "--only", "actors", "--skip", "levels",
    ])
    assert code == 1
    assert "cannot be used together" in capsys.readouterr().err


def test_cli_rejects_an_unknown_stage(campaign: Path, tmp_path: Path, capsys):
    code = main([
        "convert", "--source", str(campaign / "assets"),
        "--output", str(tmp_path / "out"), "--only", "wizards",
    ])
    assert code == 1
    assert "unknown stage" in capsys.readouterr().err


def test_cli_doctor_reports_the_skipped_stages(campaign: Path, capsys):
    import shutil

    shutil.rmtree(campaign / "assets" / "sound")
    code = main([
        "doctor",
        "--source", str(campaign / "assets"),
        "--levels-xml", str(campaign / "campaign" / "levels.xml"),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "sound" in out
    assert "Hammerwatch.exe" in out


def test_cli_doctor_names_a_bad_source(tmp_path: Path, capsys):
    code = main(["doctor", "--source", str(tmp_path / "missing"), "--output", str(tmp_path)])
    assert code == 1
    assert "missing" in capsys.readouterr().err


def test_cli_convert_unit(campaign: Path, tmp_path: Path, capsys):
    out = tmp_path / "gnaar.unit"
    code = main(["convert-unit", str(campaign / "assets" / "actors" / "gnaar.xml"), str(out)])
    assert code == 0
    assert out.is_file()
    assert "slot: actor" in capsys.readouterr().out


def test_cli_init_config_is_valid_toml(capsys, tmp_path: Path):
    assert main(["init-config"]) == 0
    config = tmp_path / "hw.toml"
    config.write_text(capsys.readouterr().out)
    settings = Settings.from_toml(config)
    assert settings.stages == set(STAGES)


def test_cli_dry_run_writes_nothing(campaign: Path, tmp_path: Path, capsys):
    code = main([
        "convert", "--source", str(campaign / "assets"),
        "--output", str(tmp_path / "out"), "--dry-run",
    ])
    assert code == 0
    assert not (tmp_path / "out").exists()
    assert "Dry run" in capsys.readouterr().out
