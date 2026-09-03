"""Levels → ``.lvl`` — port of ``xml2unit/LevelConverter.cs``.

Hammerwatch stores its tilemap as fixed 20x20 chunks; A000FF wants 512-pixel
cells. The bulk of this module is repacking one grid into the other.
"""

from __future__ import annotations

import math

from ..context import ConversionContext
from ..fmt import Writer, fmt_float, parse_float
from ..nimble import XmlFile, XmlTag
from ..paths import stem
from .level_loader import CHUNK_SIDE, LevelLoader
from .level_objects import CircleShape, RectangleShape, Tile, UnitType
from ..paths import change_extension

#: A000FF tile cells are 512 pixels on a side.
CELL_PIXELS = 512


def make_multiple(n: int, multiple: int, floor: bool) -> int:
    if n > 0 and not floor:
        return int(math.ceil(n / multiple) * multiple)
    return int(math.floor(n / multiple) * multiple)


def convert(ctx: ConversionContext, xml: XmlFile, writer: Writer, local_filename: str) -> None:
    root = xml.document_element
    level_name = stem(local_filename)
    loader = LevelLoader(ctx, level_name)
    prefix = ctx.settings.output_prefix

    writer.line("<dict>")
    writer.line('  <dict name="game-mode">')
    writer.line('    <string name="Class">HwCampaign</string>')
    writer.line("  </dict>")
    writer.line('  <dict name="lighting">')
    writer.line(f'    <string name="environment">{prefix}env/{level_name}.env</string>')
    writer.line("  </dict>")

    tilemap = root["dictionary[name=tilemap]"]
    if tilemap is not None:
        chunks = tilemap.first_element()
        if chunks is not None:
            for chunk in chunks.elements():
                if chunk.name != "dictionary":
                    continue
                loader.load_tile_data(chunk)

    writer.line('  <array name="tiles">')
    for tileset in loader.tilesets.values():
        _write_tileset(ctx, writer, tileset)
    writer.line("  </array>")

    for query, load in (
        ("dictionary[name=doodads]", loader.load_doodads),
        ("dictionary[name=actors]", loader.load_actors),
        ("dictionary[name=items]", loader.load_items),
        ("dictionary[name=lighting]", loader.load_lights),
        ("dictionary[name=scripting]", loader.load_scripts),
    ):
        tag = root[query]
        if tag is not None:
            load(tag)

    # Must happen before prefabs are imported.
    loader.prepare_writing()

    prefabs = root["dictionary[name=prefabs]"]
    if prefabs is not None:
        _import_prefabs(ctx, loader, prefabs)

    writer.line('  <dict name="units">')
    for type_name, unit_type in loader.unit_types.items():
        key = change_extension(type_name, "unit") if unit_type.mutate_filename else type_name
        writer.line(f'    <array name="{prefix}{key}">')
        for unit in unit_type.units:
            unit.write(writer)
        writer.line("    </array>")

    rectangles = [c for c in loader.collision_areas if isinstance(c, RectangleShape)]
    if rectangles:
        writer.line('    <array name=":Physics_Rectangle">')
        for shape in rectangles:
            shape.write(writer)
        writer.line("    </array>")

    circles = [c for c in loader.collision_areas if isinstance(c, CircleShape)]
    if circles:
        writer.line('    <array name=":Physics_Circle">')
        for shape in circles:
            shape.write(writer)
        writer.line("    </array>")

    writer.line("  </dict>")

    if loader.world_scripts:
        writer.line('  <array name="scripts">')
        for ws in loader.world_scripts:
            ws.write(writer)
        writer.line("  </array>")

    writer.line('  <int name="version">1</int>')
    writer.line("</dict>")


def _write_tileset(ctx: ConversionContext, writer: Writer, tileset) -> None:
    """Repack one tileset's 20x20 chunks into 512-pixel cells."""
    if not tileset.tiles:
        return

    min_unit_x = min(t.origin_x + t.x for t in tileset.tiles)
    min_unit_y = min(t.origin_y + t.y for t in tileset.tiles)
    min_x = min(t.world_x for t in tileset.tiles)
    min_y = min(t.world_y for t in tileset.tiles)
    max_x = max(t.world_x for t in tileset.tiles)
    max_y = max(t.world_y for t in tileset.tiles)

    new_side = CELL_PIXELS // tileset.size

    min_unit_x = make_multiple(min_unit_x, new_side, True)
    min_unit_y = make_multiple(min_unit_y, new_side, True)
    min_x = make_multiple(min_x, CELL_PIXELS, True)
    min_y = make_multiple(min_y, CELL_PIXELS, True)
    max_x = make_multiple(max_x, CELL_PIXELS, False)
    max_y = make_multiple(max_y, CELL_PIXELS, False)

    side_offset = new_side - CHUNK_SIDE
    cells_w = int(math.ceil((-min_x + max_x + side_offset * tileset.size) / CELL_PIXELS))
    cells_h = int(math.ceil((-min_y + max_y + side_offset * tileset.size) / CELL_PIXELS))
    cell_count = max(cells_w * cells_h, 0)
    if cell_count == 0 or cells_w == 0:
        ctx.warn(f"tileset '{tileset.set_name}' produced no cells; skipped")
        return

    cells: list[list[list[Tile | None]]] = [
        [[None] * new_side for _ in range(new_side)] for _ in range(cell_count)
    ]

    dropped = 0
    for tile in tileset.tiles:
        x = -min_unit_x + tile.origin_x + tile.x + side_offset // 2
        y = -min_unit_y + tile.origin_y + tile.y + side_offset // 2
        cell = (y // new_side) * cells_w + (x // new_side)
        x %= new_side
        y %= new_side
        if 0 <= cell < cell_count:
            cells[cell][y][x] = tile
        else:
            # The original swallows this with a bare `catch {}`, so tiles could
            # vanish from a converted level with nothing said about it.
            dropped += 1
    if dropped:
        ctx.warn(
            f"tileset '{tileset.set_name}': {dropped} tile(s) fell outside the "
            "converted grid and were dropped"
        )

    prefix = ctx.settings.output_prefix
    for i in range(cell_count):
        cell_y, cell_x = divmod(i, cells_w)
        data = "".join(
            f"{cells[i][y][x].index:02x}" if cells[i][y][x] is not None else "00"
            for y in range(new_side)
            for x in range(new_side)
        )
        center_x = cell_x * new_side + min_unit_x
        center_y = cell_y * new_side + min_unit_y

        writer.line("    <dict>")
        writer.line('      <array name="datasets">')
        writer.line("        <dict>")
        writer.line(f'          <bytes name="data">{data}</bytes>')
        writer.line(f'          <string name="tileset">{prefix}{tileset.set_name}</string>')
        writer.line("        </dict>")
        writer.line("      </array>")
        writer.line(
            f'      <vec2 name="pos">{center_x * tileset.size} {center_y * tileset.size}</vec2>'
        )
        writer.line("    </dict>")


def _import_prefabs(ctx: ConversionContext, loader: LevelLoader, prefabs: XmlTag) -> None:
    """Merge prefab contents into the level at each placement offset."""
    for prefab_array in prefabs.elements():
        if prefab_array.name != "array":
            continue
        reference = prefab_array.attributes.get("name")
        if reference is None:
            continue

        source = ctx.resolve_source(reference)
        if source is None:
            ctx.warn(f"prefab '{reference}' not found; its contents are missing from the level")
            continue

        for placement in prefab_array.elements():
            if placement.name != "vec2":
                continue
            parts = placement.value.split(" ")
            offset_x = parse_float(parts[0]) if parts else 0.0
            offset_y = parse_float(parts[1]) if len(parts) > 1 else 0.0

            prefab_xml = ctx.load_xml(source)
            root = prefab_xml.document_element  # <prefab>
            prefab_root = root.first_element()  # <dictionary>
            if prefab_root is None:
                ctx.warn(f"prefab '{reference}' is empty")
                continue

            sub = LevelLoader(ctx, "prefab")
            sub.unit_id_counter = loader.unit_id_counter

            for query, load in (
                ("dictionary[name=doodads]", sub.load_doodads),
                ("dictionary[name=actors]", sub.load_actors),
                ("dictionary[name=items]", sub.load_items),
                ("dictionary[name=scripting]", sub.load_scripts),
            ):
                tag = prefab_root[query]
                if tag is not None:
                    load(tag)

            sub.prepare_writing()
            loader.unit_id_counter = sub.unit_id_counter

            for type_name, unit_type in sub.unit_types.items():
                target = loader.unit_types.get(type_name)
                if target is None:
                    target = UnitType(mutate_filename=unit_type.mutate_filename)
                    loader.unit_types[type_name] = target
                for unit in unit_type.units:
                    unit.x += offset_x
                    unit.y += offset_y
                    target.units.append(unit)

            for script in sub.world_scripts:
                script.x += offset_x
                script.y += offset_y
                loader.world_scripts.append(script)

            for coll in sub.collision_areas:
                coll.x += offset_x
                coll.y += offset_y
                loader.collision_areas.append(coll)


__all__ = ["convert", "make_multiple", "fmt_float"]
