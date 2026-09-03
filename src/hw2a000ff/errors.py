"""Exception types that carry enough context to fix the problem."""

from __future__ import annotations

from pathlib import Path


class ConversionError(Exception):
    """A failure that stops the conversion, with the offending file named."""

    def __init__(self, message: str, path: Path | None = None, hint: str | None = None) -> None:
        self.message = message
        self.path = path
        self.hint = hint
        super().__init__(message)

    def __str__(self) -> str:
        out = self.message
        if self.path is not None:
            out = f"{out}\n  file: {self.path}"
        if self.hint:
            out = f"{out}\n  hint: {self.hint}"
        return out


class MissingDirectoryError(ConversionError):
    """A directory the conversion needs is absent or is not a directory.

    This is the failure behind the reported crash. ``FormMain.cs`` calls
    ``Directory.GetFiles`` on three roots -- the source path (:204), the
    ``levels/`` folder beside ``levels.xml`` (:371) and ``<source>/sound``
    (:387) -- and only the first is ever shown to the user. When one of the
    other two is absent, .NET raises a bare ``IOException: The directory name
    is invalid`` that names no path at all.
    """
