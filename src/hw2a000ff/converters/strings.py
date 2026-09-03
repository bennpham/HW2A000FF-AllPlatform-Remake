"""Language dictionary → ``.lang`` — port of ``xml2unit/StringConverter.cs``."""

from __future__ import annotations

from ..context import ConversionContext
from ..fmt import Writer
from ..nimble import XmlFile


def convert(ctx: ConversionContext, xml: XmlFile, writer: Writer) -> None:
    root = xml.document_element
    prefix = ctx.settings.strings_key_prefix

    writer.line("<lang>")
    for child in root.children:
        if child.name != "string":
            continue
        name = child.attributes.get("name")
        if name is None:
            ctx.warn("<string> without a name attribute; skipped")
            continue
        writer.line(f'  <string name="{prefix}{name}">{child.value}</string>')
    writer.line("</lang>")
