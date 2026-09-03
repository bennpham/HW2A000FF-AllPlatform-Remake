"""Asset path helpers.

Asset references inside Hammerwatch XML are POSIX-ish strings that sometimes
carry a ``:name`` suffix selecting one entry inside a file
(``sound/enemies.xml:gnaar-die``). The original mixes ``\\`` and ``/``
throughout -- it even tests ``filename.StartsWith("language\\\\")``
(``FormMain.cs:301``), which can never match off Windows. Everything here is
normalised to ``/`` so the output is identical on all three platforms.
"""

from __future__ import annotations

import posixpath
from pathlib import Path, PurePosixPath


def normalize(reference: str) -> str:
    """Normalise an asset reference to forward slashes."""
    return reference.replace("\\", "/")


def change_extension(reference: str, extension: str) -> str:
    """``Program.ChangeExtension`` — keeps a ``:entry`` suffix intact.

    >>> change_extension("sound/enemies.xml:gnaar-die", "sbnk")
    'sound/enemies.sbnk:gnaar-die'
    """
    reference = normalize(reference)
    if ":" in reference:
        head, _, tail = reference.partition(":")
        return f"{_change_ext(head, extension)}:{tail}"
    return _change_ext(reference, extension)


def _change_ext(reference: str, extension: str) -> str:
    """``Path.ChangeExtension`` — an empty extension is not appended."""
    if not reference:
        return reference
    base = reference[: reference.rfind(".")] if "." in posixpath.basename(reference) else reference
    return f"{base}.{extension}" if extension else base


def stem(reference: str) -> str:
    """``Path.GetFileNameWithoutExtension``."""
    return PurePosixPath(normalize(reference)).stem


def dirname(reference: str) -> str:
    """``Path.GetDirectoryName``, normalised; '' for a bare filename."""
    return posixpath.dirname(normalize(reference))


def relative_key(path: Path, root: Path) -> str:
    """The asset key for ``path`` under ``root``, using forward slashes."""
    return path.relative_to(root).as_posix()
