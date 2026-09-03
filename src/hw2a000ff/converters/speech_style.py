"""Speech styles → ``.sval`` — port of ``xml2unit/SpeechStyleConverter.cs``."""

from __future__ import annotations

from ..context import ConversionContext
from ..fmt import Writer, fmt_float, parse_float, parse_int
from ..nimble import XmlFile
from ..paths import change_extension


def convert(ctx: ConversionContext, xml: XmlFile, writer: Writer) -> None:
    root = xml.document_element
    prefix = ctx.settings.output_prefix

    font = root.attributes.get("font", "")
    raw_color = root.attributes.get("text-color", "255 255 255").split(" ")
    while len(raw_color) < 3:
        raw_color.append("255")
    color = " ".join(fmt_float(parse_float(c) / 255.0) for c in raw_color[:3])

    writer.line("<dict>")
    writer.line(f'  <string name="font">{prefix}{change_extension(font, "fnt")}</string>')
    writer.line(f'  <vec3 name="color">{color}</vec3>')
    writer.line()
    writer.line('  <dict name="sprites">')
    for child in root.children:
        if child.name != "sprite":
            continue
        name = child.attributes.get("name")
        if name is None:
            ctx.warn("speech style <sprite> without a name attribute; skipped")
            continue
        texture_tag = child.find_tag_by_name("texture")
        if texture_tag is None:
            ctx.warn(f"speech style sprite '{name}' has no <texture>; skipped")
            continue

        writer.line(f'    <array name="{name}">')
        writer.line(f"      <string>{prefix}{texture_tag.value}</string>")
        ctx.copy_asset(texture_tag.value)
        for frame in child.children:
            if frame.name != "frame":
                continue
            length = parse_int(frame.attributes["time"]) if "time" in frame.attributes else 100
            writer.line(f"      <int>{length}</int><vec4>{frame.value}</vec4>")
        writer.line("    </array>")
    writer.line("  </dict>")
    writer.line("</dict>")
