"""Bitmap fonts → ``.fnt`` — port of ``xml2unit/BitmapFontConverter.cs``.

Output is the AngelCode text format, not XML, so tags are laid out by hand.
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..fmt import Writer
from ..nimble import XmlFile, XmlTag

_NUMERIC = re.compile(r"^[0-9,\-]+$")


def _layout(tag: XmlTag, writer: Writer, overrides: dict[str, str] | None = None) -> None:
    parts = [tag.name]
    for key, value in tag.attributes.items():
        if overrides and key in overrides:
            value = overrides[key]
        if _NUMERIC.match(value):
            parts.append(f" {key}={value}")
        else:
            parts.append(f' {key}="{value}"')
    writer.line("".join(parts))


def convert(ctx: ConversionContext, xml: XmlFile, writer: Writer) -> None:
    root = xml.document_element

    for section in ("info", "common"):
        tag = root.find_tag_by_name(section)
        if tag is None:
            ctx.warn(f"font is missing its <{section}> block")
            continue
        _layout(tag, writer)

    for page in root.find_tags_by_name("page"):
        file_ref = page.attributes.get("file")
        if file_ref is None:
            ctx.warn("font <page> without a file attribute; skipped")
            continue
        ctx.copy_asset(file_ref)
        # The original assigns the prefixed name back onto the tag. That tag
        # lives in a cached XmlFile, so converting the same font twice in one
        # run prefixes it twice. Pass the new value through instead.
        _layout(page, writer, overrides={"file": ctx.settings.output_prefix + file_ref})

    chars = root.find_tag_by_name("chars")
    if chars is None:
        ctx.warn("font has no <chars> block")
        return
    _layout(chars, writer)
    for char in chars.children:
        if char.name != "char":
            continue
        _layout(char, writer)
