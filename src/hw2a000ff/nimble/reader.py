"""Character reader mirroring the C# ``StreamReader`` extension methods.

Port of ``xml2unit/Extensions/StreamReader.cs``. The original walks a
``StreamReader`` one ``char`` at a time; we walk a decoded ``str`` with an index,
which gives identical semantics without the I/O overhead.
"""

from __future__ import annotations

# (char)(-1) in C#. Returned by ReadChar/PeekChar past end of stream.
EOF_CHAR = "￿"


class CharReader:
    __slots__ = ("_s", "_i")

    def __init__(self, text: str) -> None:
        self._s = text
        self._i = 0

    @property
    def end_of_stream(self) -> bool:
        return self._i >= len(self._s)

    def read_char(self) -> str:
        if self._i >= len(self._s):
            return EOF_CHAR
        c = self._s[self._i]
        self._i += 1
        return c

    def peek_char(self) -> str:
        if self._i >= len(self._s):
            return EOF_CHAR
        return self._s[self._i]

    def read_string(self, length: int) -> str:
        """``ReadString`` — C# fills a char[] and may leave '\\0' padding at EOF."""
        chunk = self._s[self._i : self._i + length]
        self._i = min(self._i + length, len(self._s))
        if len(chunk) < length:
            chunk += "\0" * (length - len(chunk))
        return chunk

    def read_until(self, *stops: str) -> tuple[str, str]:
        """Read until one of ``stops``.

        Returns ``(text, terminator)``; the terminator is consumed, and is
        ``'\\0'`` if the stream ended first (C# returns the default char).
        """
        out: list[str] = []
        term = "\0"
        while not self.end_of_stream:
            c = self.read_char()
            if c in stops:
                term = c
                break
            out.append(c)
        return "".join(out), term

    def expect(self, expected: str) -> bool:
        return self.read_string(len(expected)) == expected
