"""Sprite conversion — port of ``xml2unit/SpriteConverter.cs``."""

from __future__ import annotations

from ..context import ConversionContext
from ..fmt import Writer, fmt_bool, fmt_int, parse_int
from ..nimble import XmlTag


def get_material(unit_name: str, behavior: str, slot: str) -> str:
    """Pick the A000FF material for a unit, by name and behaviour.

    A pile of substring tests inherited verbatim from the original -- this is
    how Hammerwatch's tile-piece naming convention (``_h_``, ``_v_``, ``_crn_``,
    ``_x_t_``) is mapped onto materials that shoot/walk correctly.
    """
    if behavior == "money":
        return "item-money"
    if behavior == "breakable":
        return "proj-prop"

    if "round_crn" in unit_name:
        return slot
    if "pillar_off_up" in unit_name:
        return slot
    if "stone_up" in unit_name:
        return slot

    if "_overhang" in unit_name:
        return "wall"
    if "_h_" in unit_name:
        return "proj-wall"

    if "_v_" in unit_name:
        return "proj-wall" if "_v_cap_dn" in unit_name else "wall"

    if "_crn_l_dn" in unit_name:
        return "proj-wall"
    if "_crn_r_dn" in unit_name:
        return "proj-wall"

    if "_x_t_" in unit_name:
        return "proj-wall" if "_x_t_dn" in unit_name else "wall"

    if "_exit_h_" in unit_name:
        return "proj-wall"

    if "_special_" in unit_name:
        if "_special_pillar" in unit_name:
            return "proj-wall"
        if "_special_eyes" in unit_name:
            return "proj-wall"
        if "_special_deteriorate" in unit_name:
            return "proj-wall"

    if "_floorsign_" in unit_name:
        return "proj-prop"
    if "_ivy_" in unit_name:
        return "proj-prop"
    if "_chains_" in unit_name:
        return "proj-prop"
    if "trap_shooter_" in unit_name:
        return "proj-prop"
    if "trap_spikes" in unit_name:
        return "floor"
    if "trap_turret" in unit_name:
        return "floor"
    if "maggot_slime" in unit_name:
        return "floor"

    if "deco_" in unit_name:
        return "proj-prop"
    if "marker" in unit_name:
        return "floor"
    if "vendor_speech" in unit_name:
        return slot
    if "vendor_" in unit_name:
        return "proj-prop"
    if "floor" in unit_name:
        return "floor"

    return slot


def unit_y_offset(ctx: ConversionContext, unit_name: str) -> int:
    """Vertical nudge applied to wall pieces when wall collision is modified."""
    if not ctx.settings.modify_wall_collision or not unit_name:
        return 0
    if (
        ("_crn_" in unit_name and "_up" in unit_name)
        or ("_x_" in unit_name and "_x_t_dn" not in unit_name)
        or ("_v_" in unit_name and "_v_cap_dn" not in unit_name)
    ):
        return 16
    return 0


def get_origin(ctx: ConversionContext, unit_name: str, tag: XmlTag | None) -> str:
    if tag is None:
        return "0 0"
    offset = unit_y_offset(ctx, unit_name)
    if offset != 0:
        parts = tag.value.split(" ")
        if len(parts) >= 2:
            return f"{parts[0]} {parse_int(parts[1]) + offset}"
    return tag.value


def _write_frames(writer: Writer, container: XmlTag) -> None:
    for frame in container.children:
        if frame.name != "frame":
            continue
        time = frame.attributes.get("time")
        if time is not None:
            writer.line(f'        <frame time="{time}">{frame.value}</frame>')
        else:
            writer.line(f"        <frame>{frame.value}</frame>")


def convert(
    ctx: ConversionContext,
    sprite: XmlTag,
    writer: Writer,
    material: str,
    looping: bool = True,
    unit_name: str = "",
) -> None:
    texture_tag = sprite.find_tag_by_name("texture")
    if texture_tag is None:
        ctx.warn(f"sprite '{sprite.attributes.get('name', '?')}' has no <texture>; skipped")
        return
    texture = texture_tag.value
    ctx.copy_asset(texture)

    origin_tag = sprite.find_tag_by_name("origin")
    prefix = ctx.settings.output_prefix

    writer.line(
        f'      <sprite origin="{get_origin(ctx, unit_name, origin_tag)}" '
        f'looping="{fmt_bool(looping)}" texture="{prefix}{texture}" '
        f'material="{prefix}system/hammerwatch.mats:{material}">'
    )
    _write_frames(writer, sprite)
    writer.line("      </sprite>")

    glow = sprite.find_tag_by_name("glow")
    if glow is not None:
        # The original dereferences <origin> again here without a null check.
        glow_origin = origin_tag.value if origin_tag is not None else "0 0"
        writer.line(
            f'      <sprite origin="{glow_origin}" looping="{fmt_bool(looping)}" '
            f'texture="{prefix}{texture}" material="{prefix}system/hammerwatch.mats:glow">'
        )
        _write_frames(writer, glow)
        writer.line("      </sprite>")


def frame_extents(sprites: list[XmlTag], skip_hit_effects: bool) -> tuple[int, int, int, int]:
    """Count sprites and measure the largest frame across them.

    Returns ``(count, most_pixels, most_width, most_height)``. Projectiles skip
    their ``d*`` hit-effect sprites, matching ``UnitConverter.cs:79``.
    """
    count = most_pixels = most_width = most_height = 0
    for sprite in sprites:
        name = sprite.attributes.get("name")
        if skip_hit_effects and name is not None and name.startswith("d"):
            continue
        for frame in sprite.find_tags_by_name("frame"):
            parts = frame.value.split(" ")
            if len(parts) != 4:
                continue
            w, h = parse_int(parts[2]), parse_int(parts[3])
            most_pixels = max(most_pixels, w * h)
            most_width = max(most_width, w)
            most_height = max(most_height, h)
        count += 1
    return count, most_pixels, most_width, most_height


__all__ = [
    "convert",
    "get_material",
    "get_origin",
    "unit_y_offset",
    "frame_extents",
    "fmt_int",
]
