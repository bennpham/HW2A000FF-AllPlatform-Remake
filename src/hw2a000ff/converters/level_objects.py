"""Level entities — port of ``xml2unit/LevelObjects.cs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..fmt import Writer, fmt_bool, fmt_float

#: Hammerwatch level coordinates are in tiles, offset by half a 20-tile chunk.
TILE_PIXELS = 16.0
LEVEL_ORIGIN_OFFSET = 160.0


def to_pixels(u: float) -> float:
    return u * TILE_PIXELS - LEVEL_ORIGIN_OFFSET


def srgb_to_linear(f: float) -> float:
    if f <= 0.04045:
        return f / 12.92
    return ((f + 0.055) / 1.055) ** 2.4


@dataclass
class TileSet:
    set_name: str = ""
    size: int = 16
    tiles: list["Tile"] = field(default_factory=list)


@dataclass
class Tile:
    origin_x: int = 0
    origin_y: int = 0
    x: int = 0
    y: int = 0
    index: int = 0
    tile_set: TileSet | None = None

    @property
    def world_x(self) -> int:
        assert self.tile_set is not None
        return (self.origin_x + self.x) * self.tile_set.size

    @property
    def world_y(self) -> int:
        assert self.tile_set is not None
        return (self.origin_y + self.y) * self.tile_set.size


@dataclass
class Unit:
    id: int = 0
    id_old: int = 0
    x: float = 0.0
    y: float = 0.0
    layer: int | None = None

    def write(self, writer: Writer) -> None:
        px, py = fmt_float(to_pixels(self.x)), fmt_float(to_pixels(self.y))
        if self.layer is None:
            writer.line(f"      <vec3>{px} {py} 0</vec3>")
            writer.line(f"      <int>{self.id}</int>")
        else:
            writer.line("      <array>")
            writer.line(f"          <vec3>{px} {py} 0</vec3>")
            writer.line(f"          <int>{self.id}</int>")
            writer.line(f'          <dict><int name="layer">{self.layer}</int></dict>')
            writer.line("      </array>")


@dataclass
class Light(Unit):
    r: int = 0
    g: int = 0
    b: int = 0
    size: float = 0.0

    @staticmethod
    def transform(color: int) -> float:
        return srgb_to_linear(color / 255.0 * 0.5)

    def write(self, writer: Writer) -> None:
        writer.line("      <array>")
        writer.line(
            f"        <vec3>{fmt_float(to_pixels(self.x))} {fmt_float(to_pixels(self.y))} 0</vec3>"
        )
        writer.line(f"        <int>{self.id}</int>")
        writer.line("        <dict>")
        writer.line('          <bool name="cast-shadows">f</bool>')
        writer.line(
            f'          <vec4 name="color">{fmt_float(self.transform(self.r))} '
            f"{fmt_float(self.transform(self.g))} {fmt_float(self.transform(self.b))} 0</vec4>"
        )
        writer.line(f'          <float name="size">{fmt_float(self.size * 16.0 * 0.8)}</float>')
        writer.line("        </dict>")
        writer.line("      </array>")


class OldUnitID:
    """A Hammerwatch object id, resolved to its A000FF id in a later pass."""

    __slots__ = ("old_id", "new_id")

    def __init__(self, old_id: int) -> None:
        self.old_id = old_id
        self.new_id = -1

    def __str__(self) -> str:
        return str(self.new_id)


@dataclass
class WorldScript(Unit):
    tag: Any = None
    type: str = ""
    enabled: bool = True
    trigger_times: int = -1
    execute_on_start: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    connections: list[tuple[int, int]] = field(default_factory=list)

    def write(self, writer: Writer) -> None:
        writer.line("    <array>")
        writer.line(f"      <string>{self.type}</string>")
        writer.line(f"      <int>{self.id}</int>")
        writer.line(
            f"      <vec3>{fmt_float(to_pixels(self.x))} {fmt_float(to_pixels(self.y))} 0</vec3>"
        )
        writer.line(f'      <bool>{"t" if self.enabled else "f"}</bool>')
        writer.line(f"      <int>{self.trigger_times}</int>")
        writer.line(f'      <bool>{"t" if self.execute_on_start else "f"}</bool>')

        if self.params:
            writer.line("      <dict>")
            for name, value in self.params.items():
                if isinstance(value, (list, tuple)):
                    writer.line(f'        <array name="{name}">')
                    for item in value:
                        kind, text = _param_repr(item)
                        writer.line(f"          <{kind}>{text}</{kind}>")
                        # Only two dynamic unit feeds exist in Hammerwatch, so
                        # naming the last spawned unit is enough.
                        if name.startswith("#"):
                            writer.line("          <string>LastSpawned</string>")
                    writer.line("        </array>")
                else:
                    kind, text = _param_repr(value)
                    writer.line(f'        <{kind} name="{name}">{text}</{kind}>')
            writer.line("      </dict>")

        if self.connections:
            writer.line("      <array>")
            for target, delay in self.connections:
                writer.line(f"        <int>{target}</int><int>{delay}</int>")
            writer.line("      </array>")

        writer.line("    </array>")


def _param_repr(value: Any) -> tuple[str, str]:
    """Element name and text for a world-script parameter."""
    if isinstance(value, bool):
        return "bool", "t" if value else "f"
    if isinstance(value, OldUnitID):
        return "int", str(value)
    if isinstance(value, int):
        return "int", str(value)
    if isinstance(value, float):
        return "float", fmt_float(value)
    return "string", str(value)


@dataclass
class CollisionArea(Unit):
    pass


@dataclass
class RectangleShape(CollisionArea):
    w: float = 0.0
    h: float = 0.0

    def write(self, writer: Writer) -> None:
        writer.line("      <array>")
        writer.line(
            f"        <vec3>{fmt_float(to_pixels(self.x))} {fmt_float(to_pixels(self.y))} 0</vec3>"
        )
        writer.line(f"        <int>{self.id}</int>")
        writer.line("        <dict>")
        writer.line('          <bool name="sensor">t</bool>')
        writer.line('          <bool name="shoot-through">t</bool>')
        writer.line(
            f'          <vec2 name="size">{fmt_float(self.w * 16.0)} '
            f"{fmt_float(self.h * 16.0)}</vec2>"
        )
        writer.line("        </dict>")
        writer.line("      </array>")


@dataclass
class CircleShape(CollisionArea):
    diameter: float = 0.0

    def write(self, writer: Writer) -> None:
        writer.line("      <array>")
        writer.line(
            f"        <vec3>{fmt_float(to_pixels(self.x))} {fmt_float(to_pixels(self.y))} 0</vec3>"
        )
        writer.line(f"        <int>{self.id}</int>")
        writer.line("        <dict>")
        writer.line('          <bool name="sensor">t</bool>')
        writer.line('          <bool name="shoot-through">t</bool>')
        writer.line(f'          <float name="radius">{fmt_float(self.diameter / 2.0 * 16.0)}</float>')
        writer.line("        </dict>")
        writer.line("      </array>")


@dataclass
class UnitType:
    mutate_filename: bool = True
    units: list[Unit] = field(default_factory=list)


__all__ = [
    "Tile", "TileSet", "Unit", "Light", "WorldScript", "CollisionArea",
    "RectangleShape", "CircleShape", "OldUnitID", "UnitType",
    "to_pixels", "srgb_to_linear", "fmt_bool",
]
