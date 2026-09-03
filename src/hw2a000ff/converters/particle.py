"""Particle files → ``.unit`` — port of ``xml2unit/ParticleConverter.cs``."""

from __future__ import annotations

from ..context import ConversionContext
from ..paths import change_extension, dirname
from . import sprite as sprite_converter


def convert(ctx: ConversionContext, script_path: str) -> str:
    file_ref, _, _entry = script_path.partition(":")
    local = change_extension(file_ref, "unit")

    if local in ctx.converted_particles:
        return local
    ctx.converted_particles.add(local)

    # The original reads from the source path only; a scenario that inherits its
    # particles from the base game would crash here.
    source = ctx.resolve_source(file_ref)
    if source is None:
        ctx.warn(f"particle source '{file_ref}' not found; '{local}' will be missing")
        return local

    ctx.status(f"Particles: {local}")
    ctx.prepare(dirname(local), local)

    root = ctx.load_xml(source).document_element
    with ctx.open_output(local) as writer:
        writer.line('<unit slot="doodad" netsync="none">')
        writer.line("  <scenes>")
        for sprite in root.children:
            if sprite.name != "sprite":
                continue
            name = sprite.attributes.get("name")
            if name is None:
                continue
            writer.line(f'    <scene name="{name}" random-start="true">')
            sprite_converter.convert(ctx, sprite, writer, "gib")
            writer.line("    </scene>")
        writer.line("  </scenes>")
        writer.line("</unit>")

    return local
