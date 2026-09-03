"""Soundbanks → ``.sbnk`` — port of ``xml2unit/SoundbankConverter.cs``.

The format is effectively unchanged; the conversion exists so the referenced
audio files get copied into the output, and so 2D/looping metadata learned from
``PlaySound`` script nodes can be folded in.
"""

from __future__ import annotations

from ..context import ConversionContext
from ..fmt import Writer, fmt_bool, fmt_float, parse_float
from ..nimble import XmlFile


def convert(ctx: ConversionContext, xml: XmlFile, writer: Writer, sbnk_name: str) -> None:
    root = xml.root["soundbank"]
    if root is None:
        ctx.warn(f"'{sbnk_name}' has no <soundbank> element; skipped")
        return

    prefix = ctx.settings.output_prefix
    writer.line("<soundbank>")

    for sound in root.find_tags_by_name("sound"):
        name = sound.attributes.get("name")
        if name is None:
            ctx.warn(f"{sbnk_name}: <sound> without a name attribute; skipped")
            continue
        volume = parse_float(sound.attributes.get("volume", ""), 1.0)
        pitch_var = parse_float(sound.attributes.get("pitch-var", ""), 0.0)

        meta = ctx.sound_metadata.get(f"sound/{sbnk_name}.sbnk:{name}")
        is_3d = not meta.is_2d if meta else True
        looping = meta.looping if meta else False

        writer.line(
            f'  <sound category="sfx" name="{name}" volume="{fmt_float(volume)}" '
            f'pitch-var="{fmt_float(pitch_var)}" is3d="{fmt_bool(is_3d)}" '
            f'looping="{fmt_bool(looping)}">'
        )
        for source in sound.find_tags_by_name("source"):
            res = source.attributes.get("res")
            if res is not None:
                ctx.copy_asset(res)
                writer.line(f'    <source res="{prefix}{res}" />')
            else:
                writer.line("    <source />")
        writer.line("  </sound>")

    for music in root.find_tags_by_name("music"):
        name = music.attributes.get("name")
        if name is None:
            ctx.warn(f"{sbnk_name}: <music> without a name attribute; skipped")
            continue
        volume = parse_float(music.attributes.get("volume", ""), 1.0)
        writer.line(
            f'  <sound category="music" name="{name}" volume="{fmt_float(volume)}" '
            f'is3d="false" looping="true">'
        )
        for source in music.find_tags_by_name("source"):
            res = source.attributes.get("res")
            if res is None:
                ctx.warn(f"{sbnk_name}: music '{name}' has a <source> without res")
                continue
            ctx.copy_asset(res)
            writer.line(f'    <source res="{prefix}{res}" />')
        writer.line("  </sound>")

    writer.line("</soundbank>")
