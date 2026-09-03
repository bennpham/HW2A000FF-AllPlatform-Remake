"""Level loading — port of ``xml2unit/LevelLoader.cs``."""

from __future__ import annotations

import math

from ..context import ConversionContext
from ..errors import ConversionError
from ..fmt import fmt_int, parse_float, parse_int
from ..nimble import XmlTag
from ..paths import change_extension
from .level_objects import (
    CollisionArea,
    Light,
    OldUnitID,
    Tile,
    TileSet,
    Unit,
    UnitType,
    WorldScript,
    srgb_to_linear,
)
from .level_scripts import ScriptLoaderMixin

#: Hammerwatch stores its tilemap in fixed 20x20 chunks.
CHUNK_SIDE = 20
#: Ambient light is boosted before conversion to linear space.
AMBIENT_BOOST = 1.55
#: The stock light texture used for every point light in a level.
LIGHT_TEXTURE = "system/light_L.png"


class LevelLoader(ScriptLoaderMixin):
    def __init__(self, ctx: ConversionContext, level_name: str) -> None:
        self.ctx = ctx
        self.level_name = level_name

        self.tilesets: dict[str, TileSet] = {}
        self.unit_id_counter = 1
        self.unit_types: dict[str, UnitType] = {}
        self.world_scripts: list[WorldScript] = []
        self.collision_areas: list[CollisionArea] = []
        self.old_ids: list[OldUnitID] = []

    def _next_id(self) -> int:
        value = self.unit_id_counter
        self.unit_id_counter += 1
        return value

    def _unit_type(self, type_name: str, mutate_filename: bool = True) -> UnitType:
        existing = self.unit_types.get(type_name)
        if existing is None:
            existing = UnitType(mutate_filename=mutate_filename)
            self.unit_types[type_name] = existing
        return existing

    # ------------------------------------------------------------------ tiles

    def load_tile_data(self, tile_dict: XmlTag) -> None:
        pos_x = parse_int(tile_dict.qv("int[name=x]"))
        pos_y = parse_int(tile_dict.qv("int[name=y]"))

        sets = tile_dict["array[name=datasets]"]
        if sets is None:
            return

        for dataset in sets.elements():
            if dataset.name != "dictionary":
                continue
            filename_tag = dataset["string[name=tileset]"]
            if filename_tag is None:
                continue
            filename = change_extension(filename_tag.value, "tileset")

            tileset = self.tilesets.get(filename)
            if tileset is None:
                tileset = TileSet(set_name=filename, size=16)
                self.tilesets[filename] = tileset

            data = dataset["int-arr[name=data-t]"]
            if data is None:
                continue
            values = [v for v in data.value.split(" ") if v]
            side = int(math.sqrt(len(values)))
            if side != CHUNK_SIDE or side * side != len(values):
                # The original asserts this, which a release build strips out --
                # so a malformed chunk silently produced a corrupt tilemap.
                raise ConversionError(
                    f"level '{self.level_name}' has a {len(values)}-entry tile chunk; "
                    f"Hammerwatch chunks are always {CHUNK_SIDE}x{CHUNK_SIDE}"
                )

            half = side // 2
            for y in range(side):
                for x in range(side):
                    tileset.tiles.append(
                        Tile(
                            tile_set=tileset,
                            origin_x=pos_x,
                            origin_y=pos_y,
                            x=x - half,
                            y=y - half,
                            index=parse_int(values[y * side + x]) & 0xFF,
                        )
                    )

    # ------------------------------------------------------------------ units

    def load_doodads(self, doodads_dict: XmlTag) -> None:
        doodads = doodads_dict["array[name=doodads]"]
        if doodads is None:
            return
        for doodad in doodads.elements():
            if doodad.name != "dictionary":
                continue
            type_tag = doodad["string[name=type]"]
            if type_tag is None:
                continue
            pos = doodad.qv("vec2[name=pos]").split(" ")
            layer = doodad["int[name=layer]"]

            unit = Unit(
                id=self._next_id(),
                id_old=parse_int(doodad.qv("int[name=id]")),
                x=parse_float(pos[0]) if pos else 0.0,
                y=parse_float(pos[1]) if len(pos) > 1 else 0.0,
                layer=parse_int(layer.value) if layer is not None else None,
            )
            self._unit_type(type_tag.value).units.append(unit)

    def _load_id_pos_arrays(self, container: XmlTag) -> None:
        """Actors and items share an ``<array name=type><array>id,pos``shape."""
        for group in container.elements():
            if group.name != "array":
                continue
            type_name = group.attributes.get("name")
            if type_name is None:
                continue
            for entry in group.elements():
                if entry.name != "array":
                    continue
                fields = list(entry.elements())
                if len(fields) < 2:
                    continue
                pos = fields[1].value.split(" ")
                self._unit_type(type_name).units.append(
                    Unit(
                        id=self._next_id(),
                        id_old=parse_int(fields[0].value),
                        x=parse_float(pos[0]) if pos else 0.0,
                        y=parse_float(pos[1]) if len(pos) > 1 else 0.0,
                    )
                )

    def load_actors(self, actors_dict: XmlTag) -> None:
        self._load_id_pos_arrays(actors_dict)

    def load_items(self, items_dict: XmlTag) -> None:
        self._load_id_pos_arrays(items_dict)

    # ----------------------------------------------------------------- lights

    def load_lights(self, lights_dict: XmlTag) -> None:
        ctx = self.ctx
        lights = lights_dict["array[name=lights]"]
        if lights is not None:
            for light in lights.elements():
                if light.name != "dictionary":
                    continue
                pos = light.qv("vec2[name=pos]").split(" ")
                color = light.qv("int-arr[name=mulColor1]").split(" ")
                while len(color) < 3:
                    color.append("0")
                self._unit_type(LIGHT_TEXTURE, mutate_filename=False).units.append(
                    Light(
                        id=self._next_id(),
                        id_old=parse_int(light.qv("int[name=id]")),
                        x=parse_float(pos[0]) if pos else 0.0,
                        y=parse_float(pos[1]) if len(pos) > 1 else 0.0,
                        r=parse_int(color[0]),
                        g=parse_int(color[1]),
                        b=parse_int(color[2]),
                        size=parse_float(light.qv("float[name=mulRange]")),
                    )
                )

        ambient_tag = lights_dict["int-arr[name=ambient-color]"]
        shadow_tag = lights_dict["int-arr[name=shadow-color]"]

        if ambient_tag is None:
            # The original reads this with `?.` and then indexes it regardless,
            # so a level without an ambient colour takes the tool down.
            ctx.warn(f"level '{self.level_name}' has no ambient-color; defaulting to black")
            ambient = ["0", "0", "0"]
        else:
            ambient = ambient_tag.value.split(" ")
            while len(ambient) < 3:
                ambient.append("0")

        channels = [
            min(255, int(srgb_to_linear(parse_int(c) / 255.0 * AMBIENT_BOOST) * 255.0))
            for c in ambient[:3]
        ]

        env_name = f"env/{self.level_name}.env"
        ctx.prepare("env", env_name)
        with ctx.open_output(env_name) as writer:
            writer.line("<environment>")
            if shadow_tag is not None and shadow_tag.value != "255 255 255 255":
                writer.line('  <ambient value="0 0 0 0" />')
                writer.line("  <lights>")
                writer.line(
                    f'    <light color="{channels[0]} {channels[1]} {channels[2]} 0" '
                    f'dir="1.5 -2.5" shadow-length="50" />'
                )
                writer.line("  </lights>")
            else:
                writer.line(
                    f'  <ambient value="{channels[0]} {channels[1]} {channels[2]} 0" />'
                )
            writer.line("</environment>")

    # ---------------------------------------------------------------- linking

    def prepare_writing(self) -> None:
        """Resolve every Hammerwatch object id to its new A000FF id."""
        lookup: dict[int, int] = {}
        for coll in self.collision_areas:
            lookup.setdefault(coll.id_old, coll.id)
        for ws in self.world_scripts:
            lookup.setdefault(ws.id_old, ws.id)
        for unit_type in self.unit_types.values():
            for unit in unit_type.units:
                lookup.setdefault(unit.id_old, unit.id)

        unresolved = 0
        for old in self.old_ids:
            resolved = lookup.get(old.old_id)
            if resolved is None:
                unresolved += 1
            else:
                old.new_id = resolved
        if unresolved:
            self.ctx.warn(
                f"level '{self.level_name}': {unresolved} script reference(s) "
                "point at objects that do not exist"
            )

        self.prepare_script_writing()


__all__ = ["LevelLoader", "CHUNK_SIDE", "fmt_int"]
