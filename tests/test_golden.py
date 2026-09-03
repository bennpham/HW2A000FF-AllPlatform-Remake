"""Golden-file coverage for the whole conversion.

Regenerate after an intentional change with::

    HW2A000FF_REGOLD=1 python -m pytest tests/test_golden.py

The goldens lock in this port's behaviour so a refactor cannot quietly change
converted output. They were derived by reading the C# line by line -- there is
no .NET toolchain here to run the original against -- so they are a regression
guard, not a proof of byte-identical parity with a Windows run.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from hw2a000ff.pipeline import convert_all
from hw2a000ff.settings import Settings

from conftest import GOLDEN

REGOLD = os.environ.get("HW2A000FF_REGOLD") == "1"

#: Binary copies; their bytes are the input's, so only presence is checked.
BINARY_SUFFIXES = {".png", ".wav", ".ogg"}


def _converted(settings: Settings) -> dict[str, str]:
    report = convert_all(settings)
    assert report.file_count > 0
    out = settings.output_path
    assert out is not None
    return {
        path.relative_to(out).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.suffix not in BINARY_SUFFIXES
    }


def test_full_campaign_matches_golden(settings: Settings):
    produced = _converted(settings)

    if REGOLD:
        if GOLDEN.exists():
            shutil.rmtree(GOLDEN)
        for name, text in produced.items():
            target = GOLDEN / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        pytest.skip(f"regenerated {len(produced)} golden file(s)")

    expected = {
        path.relative_to(GOLDEN).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(GOLDEN.rglob("*"))
        if path.is_file()
    }
    assert expected, "no goldens on disk; run with HW2A000FF_REGOLD=1"

    assert sorted(produced) == sorted(expected), "the set of converted files changed"
    for name in sorted(expected):
        assert produced[name] == expected[name], f"converted output changed: {name}"


def test_binary_assets_are_copied_through(settings: Settings):
    convert_all(settings)
    out = settings.output_path
    assert (out / "actors/gnaar.png").is_file()
    assert (out / "sound/gnaar_die.wav").read_bytes().startswith(b"RIFF")


def test_conversion_is_repeatable_in_one_process(settings: Settings, tmp_path: Path):
    """Two runs must produce the same thing.

    The original keeps its caches and loot tables on static fields, so a second
    conversion in the same process reuses stale state and appends loot entries
    to the tables the first run already filled.
    """
    first = _converted(settings)

    second_settings = Settings(**{**settings.__dict__, "output_path": tmp_path / "out2"})
    second_settings.stages = set(settings.stages)
    second = _converted(second_settings)

    assert first == second
