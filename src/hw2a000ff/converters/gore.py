"""Gore/gib definitions → ``.sval`` — port of ``xml2unit/GoreConverter.cs``."""

from __future__ import annotations

from ..context import ConversionContext
from ..fmt import fmt_float, parse_float
from ..paths import change_extension, dirname
from . import particle as particle_converter
from . import sprite as sprite_converter

#: The sprite the original pulls out of a breakable's particle file.
BREAKABLE_GIB_SPRITE = "breakable_wood"


def convert_particle(ctx: ConversionContext, particle_effect: str) -> str | None:
    """Build a gib table from a ``<file>.xml:<sprite>`` particle reference."""
    if ":" not in particle_effect:
        return None
    particle_file, _, particle = particle_effect.partition(":")

    local = particle_effect.replace(".xml:", "_") + "_gib.sval"
    if local in ctx.converted_gore:
        return local
    ctx.converted_gore.add(local)

    source = ctx.resolve_source(particle_file)
    if source is None:
        ctx.warn(f"gore particle source '{particle_file}' not found; skipped")
        return None

    ctx.status(f"Gore particle: {local}")
    ctx.prepare(dirname(local), local)

    prefix = ctx.settings.output_prefix
    with ctx.open_output(local) as writer:
        writer.line("<dict>")
        writer.line('  <array name="death-gib">')
        writer.line("    <float>0</float>")
        for lo, hi, force, stay in ((6, 8, "0.5", "true"), (8, 12, "0.75", "false")):
            writer.line("    <dict>")
            writer.line(f'      <int name="min">{lo}</int>')
            writer.line(f'      <int name="max">{hi}</int>')
            writer.line(f'      <float name="force">{force}</float>')
            writer.line(f'      <string name="unit">{prefix}{local}.unit</string>')
            writer.line(f'      <string name="anim">{particle}</string>')
            writer.line(f'      <bool name="stay">{stay}</bool>')
            writer.line("    </dict>")
        writer.line("  </array>")
        writer.line("</dict>")

    gib_sprite = ctx.load_xml(source).root[f"sprite[name={BREAKABLE_GIB_SPRITE}]"]
    if gib_sprite is None:
        ctx.warn(
            f"'{particle_file}' has no '{BREAKABLE_GIB_SPRITE}' sprite; "
            f"'{local}.unit' will have no gib scene"
        )

    ctx.prepare(dirname(local), local + ".unit")
    with ctx.open_output(local + ".unit") as writer:
        writer.line('<unit netsync="none" save="false">')
        writer.line("  <scenes>")
        writer.line(f'    <scene name="{particle}" random-start="true">')
        if gib_sprite is not None:
            sprite_converter.convert(ctx, gib_sprite, writer, "gib")
        writer.line("    </scene>")
        writer.line("  </scenes>")
        writer.line("</unit>")

    return local


def convert(ctx: ConversionContext, script_path: str) -> str:
    """Convert a ``<gore>`` definition file referenced by an actor's ``gib``."""
    local = change_extension(script_path, "sval")
    if local in ctx.converted_gore:
        return local
    ctx.converted_gore.add(local)

    source = ctx.resolve_source(script_path)
    if source is None:
        ctx.warn(f"gore source '{script_path}' not found; '{local}' will be missing")
        return local

    root = ctx.load_xml(source).document_element
    ctx.status(f"Gore: {local}")
    ctx.prepare(dirname(local), local)

    prefix = ctx.settings.output_prefix
    force = 0.5
    anim_file = ""
    anim = "none"

    if "speed" in root.attributes:
        force *= parse_float(root.attributes["speed"], 1.0)
    if "particle" in root.attributes:
        anim_file = particle_converter.convert(ctx, root.attributes["particle"])
        anim = root.attributes["particle"].split(":")[-1]

    with ctx.open_output(local) as writer:
        writer.line("<dict>")
        writer.line('  <array name="death-gib">')
        writer.line("    <float>0</float>")
        writer.line("    <dict>")
        writer.line('      <int name="min">1</int>')
        writer.line('      <int name="max">1</int>')
        writer.line(f'      <float name="force">{fmt_float(force)}</float>')
        writer.line(f'      <string name="unit">{anim_file}</string>')
        writer.line(f'      <string name="anim">{anim}</string>')
        writer.line('      <bool name="stay">false</bool>')
        writer.line("    </dict>")

        sprites = [s for s in root.children if s.name == "sprite"]
        if root.children:
            ctx.prepare(dirname(local), local + ".unit")
            with ctx.open_output(local + ".unit") as unit_writer:
                unit_writer.line('<unit netsync="none" save="false">')
                unit_writer.line("  <scenes>")
                for n, sprite in enumerate(sprites):
                    scene = f"hwport_{n}"
                    unit_writer.line(f'    <scene name="{scene}" random-start="true">')
                    sprite_converter.convert(ctx, sprite, unit_writer, "gib")
                    unit_writer.line("    </scene>")

                    writer.line("    <dict>")
                    writer.line('      <int name="min">0</int>')
                    writer.line('      <int name="max">1</int>')
                    writer.line(f'      <float name="force">{fmt_float(force)}</float>')
                    writer.line(f'      <string name="unit">{prefix}{local}.unit</string>')
                    writer.line(f'      <string name="anim">{scene}</string>')
                    writer.line('      <bool name="stay">false</bool>')
                    writer.line("    </dict>")
                unit_writer.line("  </scenes>")
                unit_writer.line("</unit>")

        writer.line("  </array>")
        writer.line("</dict>")

    return local
