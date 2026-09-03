"""Tilesets → ``.tileset`` — port of ``xml2unit/TilesetConverter.cs``."""

from __future__ import annotations

from ..context import ConversionContext
from ..fmt import Writer, parse_int
from ..nimble import XmlFile

#: A000FF layers are small numbers; Hammerwatch's are in the thousands.
LAYER_BASE = -1100
#: Hammerwatch tiles are always rendered at 16px regardless of frame size.
TILE_SIZE = 16


def _proper_size(value: str, size: int) -> tuple[str, str]:
    """Force a tile frame to the tileset's cell size, noting the original."""
    parts = value.split(" ")
    if len(parts) != 4:
        return value, ""
    w, h = parse_int(parts[2]), parse_int(parts[3])
    if w == size and h == size:
        return value, ""
    return f"{parts[0]} {parts[1]} {size} {size}", f" <!-- {w} {h} -->"


def convert(ctx: ConversionContext, xml: XmlFile, writer: Writer) -> None:
    root = xml.document_element
    if root.name != "tileset":
        return

    texture = ""
    size = 0
    for sprite in root.find_tags_by_name("sprite"):
        texture_tag = sprite.find_tag_by_name("texture")
        if texture_tag is not None:
            if texture == "":
                texture = texture_tag.value
            elif texture != texture_tag.value:
                # Never happens in stock Hammerwatch, but report it anyway.
                ctx.warn(f"tileset uses multiple textures: {texture} and {texture_tag.value}")
        if sprite.find_tag_by_name("frame") is not None:
            size = TILE_SIZE

    layer = LAYER_BASE + parse_int(root.attributes.get("level", "0"))

    if not texture:
        ctx.warn("tileset has no texture; skipped")
        return
    ctx.copy_asset(texture)

    prefix = ctx.settings.output_prefix
    writer.line(
        f'<tileset texture="{prefix}{texture}" layer="{layer}" size="{size}" '
        f'material="{prefix}system/hammerwatch.mats:floor">'
    )

    for tag in root.children:
        if tag.name == "sprite":
            frame = tag.find_tag_by_name("frame")
            if frame is None:
                continue
            value, comment = _proper_size(frame.value, size)
            writer.line(f"  <tile>{value}</tile>{comment}")

        elif tag.name == "borders":
            writer.line("  <borders>")
            for border in tag.children:
                if border.name != "sprite":
                    continue
                name = border.attributes.get("name")
                frame = border.find_tag_by_name("frame")
                if name is None or frame is None:
                    continue
                value, comment = _proper_size(frame.value, size)
                writer.line(f'    <tile name="{name}">{value}</tile>{comment}')
            writer.line("  </borders>")

    writer.line("</tileset>")
