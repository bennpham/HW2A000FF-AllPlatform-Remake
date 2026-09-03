"""Number formatting must match .NET, and never depend on the locale."""

from __future__ import annotations

import pytest

from hw2a000ff.fmt import (
    fmt_bool, fmt_float, fmt_int, parse_bool, parse_float, parse_int, to_single,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (24.0, "24"),        # .NET drops a bare .0; Python's str() would not
        (1.0, "1"),
        (0.5, "0.5"),
        (-0.0, "0"),
        (2.7, "2.7"),
        (76.8, "76.8"),
        (0.1 * 3, "0.3"),    # G7 hides double-precision noise
        (1e-5, "1E-05"),
        (7, "7"),            # ints pass through untouched
    ],
)
def test_fmt_float_matches_dotnet_g7(value, expected):
    assert fmt_float(value) == expected


def test_fmt_float_rejects_bools():
    with pytest.raises(TypeError):
        fmt_float(True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(24.0, "24"), (20.8, "20"), (112.5, "112"), (-3.7, "-3"), (5, "5")],
)
def test_fmt_int_truncates_toward_zero(value, expected):
    # The original writes raw floats into <int> fields whenever a scale slider
    # is off 100%, producing values the game cannot parse.
    assert fmt_int(value) == expected


def test_fmt_bool_is_lowercase():
    assert (fmt_bool(True), fmt_bool(False)) == ("true", "false")


def test_parse_helpers_never_raise():
    assert parse_float("nonsense") == 0.0
    assert parse_float("nonsense", 2.5) == 2.5
    assert parse_int("nonsense", 7) == 7
    assert parse_int("12.9") == 12
    assert parse_bool("t") is True
    assert parse_bool("f") is False
    assert parse_bool("", True) is True


def test_parse_float_is_locale_independent():
    # A comma decimal separator is not a number here, whatever the OS locale.
    assert parse_float("0,5") == 0.0
    assert parse_float("0.5") == 0.5


def test_to_single_rounds_to_float32():
    assert to_single(0.1) == pytest.approx(0.1, abs=1e-7)
    assert to_single(1 / 3) != 1 / 3
