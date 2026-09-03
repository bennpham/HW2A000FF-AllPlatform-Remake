from __future__ import annotations

import pytest

from hw2a000ff.paths import change_extension, dirname, normalize, stem


@pytest.mark.parametrize(
    ("reference", "extension", "expected"),
    [
        ("units/gnaar.xml", "unit", "units/gnaar.unit"),
        # A ":entry" suffix selects one item inside a file and must survive.
        ("sound/enemies.xml:gnaar-die", "sbnk", "sound/enemies.sbnk:gnaar-die"),
        ("levels\\lvl1.xml", "lvl", "levels/lvl1.lvl"),
        ("noext", "unit", "noext.unit"),
        ("dir.with.dots/file.xml", "unit", "dir.with.dots/file.unit"),
    ],
)
def test_change_extension(reference, extension, expected):
    assert change_extension(reference, extension) == expected


def test_normalize_and_stem_and_dirname():
    assert normalize("a\\b\\c.xml") == "a/b/c.xml"
    assert stem("units/gnaar.xml") == "gnaar"
    assert dirname("units/a/gnaar.xml") == "units/a"
    assert dirname("gnaar.xml") == ""
