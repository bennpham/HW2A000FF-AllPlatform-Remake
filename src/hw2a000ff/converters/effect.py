"""Particle sprites → ``.effect`` — port of ``xml2unit/EffectConverter.cs``."""

from __future__ import annotations

from ..context import ConversionContext
from ..paths import dirname, stem
from . import sprite as sprite_converter


def convert(ctx: ConversionContext, script_path: str) -> str:
    """Convert one named sprite out of a particle file; returns the asset key.

    ``script_path`` is ``"<file>.xml:<sprite name>"``.
    """
    file_ref, _, entry = script_path.partition(":")
    directory = dirname(file_ref)
    base = f"{stem(file_ref)}_{entry}.effect"
    local = f"{directory}/{base}" if directory else base

    if local in ctx.converted_effects:
        return local
    ctx.converted_effects.add(local)

    source = ctx.resolve_source(file_ref)
    if source is None:
        ctx.warn(f"effect source '{file_ref}' not found; '{local}' will be missing")
        return local

    ctx.status(f"Effect: {local}")
    root = ctx.load_xml(source).document_element

    for child in root.children:
        if child.name != "sprite":
            continue
        if entry != "" and child.attributes.get("name") != entry:
            continue
        ctx.prepare(dirname(local), local)
        with ctx.open_output(local) as writer:
            writer.line("<effect>")
            sprite_converter.convert(ctx, child, writer, "effect", looping=False)
            writer.line("</effect>")
        break
    else:
        ctx.warn(f"no sprite named '{entry}' in '{file_ref}'")

    return local
