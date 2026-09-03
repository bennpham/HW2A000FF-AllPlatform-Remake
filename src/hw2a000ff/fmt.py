"""Number formatting and output writing that match the C# original.

.NET renders ``24.0f`` as ``"24"`` and uses 7 significant digits for a
``float``; Python's ``str()`` would emit ``"24.0"`` and full double precision.
Every number written to a converted asset goes through here.

This module is also where the original's locale bug is closed for good. The C#
tool sets ``InvariantCulture`` on the UI thread (``FormMain.cs:18``) but runs the
conversion on a fresh ``Thread`` (``FormMain.cs:199``), which does not inherit
it -- so on a machine with a comma decimal separator the converter writes
``"0,5"`` into every float field. Formatting here is locale-independent.
"""

from __future__ import annotations

import struct
from typing import IO


def to_single(x: float) -> float:
    """Round a Python double to IEEE-754 single precision, as C# ``float`` is."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def fmt_float(x: float | int) -> str:
    """Format like .NET's default ``float.ToString()`` (``G7``)."""
    if isinstance(x, bool):  # bool is an int subclass; never format one as a number
        raise TypeError("use fmt_bool for booleans")
    if isinstance(x, int):
        return str(x)
    f = to_single(x)
    if f != f:
        return "NaN"
    if f == float("inf"):
        return "Infinity"
    if f == float("-inf"):
        return "-Infinity"
    s = f"{f:.7G}"
    if "E" in s:
        mantissa, exponent = s.split("E")
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        sign = exponent[0]
        digits = exponent[1:].lstrip("0") or "0"
        return f"{mantissa}E{sign}{digits.rjust(2, '0')}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def fmt_int(x: float | int) -> str:
    """Format a value destined for an ``<int>`` element.

    The original writes raw floats into ``<int>`` fields in a dozen places --
    ``<int name="radius">`` in ``UnitConverter.cs:131``, ``spawn-dist`` at
    :179 and :576, ``range`` at :520 and :821, and every ``dmg``/``hp`` field
    scaled by a slider. With the sliders at their default 100% the products are
    whole numbers and it goes unnoticed; at any other setting the tool emits
    ``<int name="dmg">112.5</int>``, which the game cannot parse. Truncating
    toward zero matches the explicit ``(int)`` casts used elsewhere in the same
    file.
    """
    if isinstance(x, bool):
        raise TypeError("use fmt_bool for booleans")
    return str(int(to_single(x) if isinstance(x, float) else x))


def fmt_bool(b: bool) -> str:
    """C# ``bool.ToString().ToLower()``."""
    return "true" if b else "false"


def parse_float(s: str, default: float = 0.0) -> float:
    """``float.TryParse`` — invariant culture, never raises."""
    try:
        return to_single(float(s.strip()))
    except (ValueError, AttributeError):
        return default


def parse_int(s: str, default: int = 0) -> int:
    """``int.TryParse`` — never raises."""
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        try:
            return int(float(s.strip()))
        except (ValueError, AttributeError):
            return default


def parse_bool(s: str, default: bool = False) -> bool:
    """``bool.Parse``, tolerating the ``t``/``f`` spellings HW also uses."""
    if s is None:
        return default
    v = s.strip().lower()
    if v in ("true", "t", "1"):
        return True
    if v in ("false", "f", "0"):
        return False
    return default


class Writer:
    """Line writer standing in for ``StreamWriter.WriteLine``."""

    __slots__ = ("_out", "_newline")

    def __init__(self, stream: IO[str], newline: str = "\n") -> None:
        self._out = stream
        self._newline = newline

    def line(self, text: str = "") -> None:
        self._out.write(text)
        self._out.write(self._newline)

    def raw(self, text: str) -> None:
        self._out.write(text)
