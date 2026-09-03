"""Image helpers.

The original leans on ``System.Drawing`` (GDI+, Windows-only) for two things:
reading a light texture's dimensions and re-saving PNGs so they are always
32bpp. Dimensions come straight out of the PNG header here -- no dependency at
all -- and the re-save uses Pillow when it is installed, falling back to a plain
copy with a warning when it is not.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class ImageError(ValueError):
    pass


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from a PNG's IHDR chunk."""
    with path.open("rb") as fh:
        header = fh.read(24)
    if len(header) < 24 or not header.startswith(_PNG_MAGIC):
        raise ImageError(f"not a PNG file: {path}")
    if header[12:16] != b"IHDR":
        raise ImageError(f"PNG is missing its IHDR chunk: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def png_is_32bpp(path: Path) -> bool:
    """True when the PNG is already 8-bit RGBA, i.e. nothing to re-encode."""
    try:
        with path.open("rb") as fh:
            header = fh.read(26)
        if len(header) < 26 or not header.startswith(_PNG_MAGIC):
            return False
        bit_depth, color_type = header[24], header[25]
        return bit_depth == 8 and color_type == 6
    except OSError:
        return False


def copy_png_as_32bpp(src: Path, dst: Path) -> str | None:
    """Copy ``src`` to ``dst`` as a 32bpp RGBA PNG.

    Returns ``None`` on success, or a warning message when the image had to be
    copied verbatim instead of re-encoded.
    """
    if png_is_32bpp(src):
        shutil.copyfile(src, dst)
        return None
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        shutil.copyfile(src, dst)
        return (
            f"copied {src.name} without converting it to 32bpp "
            "(install the 'png' extra: pip install 'hw2a000ff[png]')"
        )
    with Image.open(src) as img:
        img.convert("RGBA").save(dst, format="PNG")
    return None
