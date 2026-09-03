"""World scripts — port of ``xml2unit/LevelScriptLoader.cs``.

Hammerwatch's scripting graph maps onto A000FF's fairly directly, but node
types are renamed, a few are re-expressed (an area shape becomes a separate
``AreaTrigger``), and parameter names/units differ throughout.
"""

from __future__ import annotations

import math
from typing import Any

from ..context import ConversionContext, SoundMetadata
from ..fmt import parse_bool, parse_float, parse_int
from ..nimble import XmlTag
from ..paths import change_extension
from . import effect as effect_converter
from .level_objects import CircleShape, OldUnitID, RectangleShape, WorldScript

#: Script node types A000FF understands. Anything else loads as a plain link.
SUPPORTED_SCRIPTS = frozenset({
    "LevelStart", "LevelExitArea", "LevelExit", "ScriptLink", "SpawnObject", "RectangleShape",
    "CircleShape", "Random", "PlaySound", "ChangeDoodadState", "AnnounceText", "DestroyObject",
    "ToggleElement", "AreaTrigger", "GlobalEventTrigger", "Counter", "IncrementCounter",
    "ObjectEventTrigger", "DangerArea", "TimerTrigger", "ProjectileShooter", "PlayMusic",
    "ChangeDoodadLayer", "HideObject", "SetGlobalFlag", "CheckGlobalFlag", "PlayEffect",
    "TogglePhysics", "DifficultyFilter", "PlayAttachedEffect", "ToggleImmortality",
    "ShowSpeechBubble", "HideSpeechBubble", "StopSound", "ProjectileSpewer", "ShopArea",
    "PathNode",
})

#: Hammerwatch node type → A000FF node type.
SCRIPT_RENAMES = {
    "SpawnObject": "SpawnUnit",
    "LevelExitArea": "LevelExit",
    "Random": "RandomCount",
    "ChangeDoodadState": "SetUnitScene",
    "DestroyObject": "DestroyUnits",
    "ToggleElement": "ToggleScripts",
    "ChangeDoodadLayer": "SetUnitLayer",
    "HideObject": "HideUnit",
    "CheckGlobalFlag": "CheckFlag",
    "PlayEffect": "SpawnEffect",
    "TogglePhysics": "ToggleCollision",
}

#: Hammerwatch AreaTrigger actor-type flags → A000FF's filter flags.
_AREA_TRIGGER_FLAGS = ((1, 2), (2, 4), (4, 2), (8, 1))

#: ProjectileShooter direction index → degrees.
_SHOOTER_DIRECTIONS = {0: 270, 1: 90, 2: 180, 3: 0}


class ScriptLoaderMixin:
    """Script half of ``LevelLoader`` (a ``partial class`` in the original)."""

    def load_scripts(self, script_dict: XmlTag) -> None:
        ctx: ConversionContext = self.ctx  # type: ignore[attr-defined]
        nodes = script_dict["array[name=nodes]"]
        if nodes is None:
            ctx.warn("scripting block has no 'nodes' array")
            return

        for node in nodes.elements():
            type_tag = node["string[name=type]"]
            if type_tag is None:
                continue
            type_hw = type_tag.value
            node_type = type_hw

            if node_type not in SUPPORTED_SCRIPTS:
                ctx.warn(f"unsupported script node '{type_hw}'; loaded as a plain link")
                node_type = "UnknownScriptLink"

            node_type = SCRIPT_RENAMES.get(node_type, node_type)

            node_id = parse_int(node.qv("int[name=id]"))
            enabled = parse_bool(node.qv("bool[name=enabled]"), True)
            trigger_times = parse_int(node.qv("int[name=trigger-times]"), -1)
            pos = node.qv("vec2[name=pos]").split(" ")
            args = node.find_tag_by_attribute("name", "parameters")
            execute_on_start = False

            # A GlobalEventTrigger listening for LevelLoaded is how Hammerwatch
            # spells "run this on startup".
            if node_type == "GlobalEventTrigger":
                if args is not None and args.value == "LevelLoaded":
                    node_type = "ScriptLink"
                    execute_on_start = True
                else:
                    continue  # TODO: support the other global events
            elif node_type == "ObjectEventTrigger":
                event = args.qv("string[name=event]") if args is not None else ""
                if event == "Destroyed":
                    node_type = "UnitDestroyedTrigger"
                elif event == "Hit":
                    node_type = "UnitDamagedTrigger"
                else:
                    continue  # TODO: support the other object events
            elif node_type == "AnnounceText":
                if args is not None and args.qv("int[name=type]") == "3":
                    node_type = "ShowFloatingText"

            x = parse_float(pos[0]) if pos else 0.0
            y = parse_float(pos[1]) if len(pos) > 1 else 0.0

            # A couple of "scripts" are really collision areas.
            if node_type == "RectangleShape":
                shape = RectangleShape(id=self._next_id(), id_old=node_id, x=x, y=y)
                if args is not None:
                    shape.w = parse_float(args.qv("float[name=w]"))
                    shape.h = parse_float(args.qv("float[name=h]"))
                self.collision_areas.append(shape)  # type: ignore[attr-defined]
                continue
            if node_type == "CircleShape":
                circle = CircleShape(id=self._next_id(), id_old=node_id, x=x, y=y)
                if args is not None:
                    circle.diameter = parse_float(args.qv("float[name=diameter]"))
                self.collision_areas.append(circle)  # type: ignore[attr-defined]
                continue

            ws = WorldScript(
                id=self._next_id(),
                id_old=node_id,
                x=x,
                y=y,
                tag=node,
                type=node_type,
                enabled=enabled,
                trigger_times=trigger_times,
                execute_on_start=execute_on_start,
            )

            if args is not None:
                if args.name == "dictionary":
                    self._read_params(ws, args, type_hw)
                else:
                    # A few node types carry a single packed value instead.
                    if type_hw == "SpawnObject":
                        ws.params["UnitType"] = ctx.prefixed(change_extension(args.value, "unit"))
                    elif type_hw == "TimerTrigger":
                        ws.params["Frequency"] = parse_int(args.value)

            self.world_scripts.append(ws)  # type: ignore[attr-defined]

    # ------------------------------------------------------------- parameters

    def _read_params(self, ws: WorldScript, args: XmlTag, type_hw: str) -> None:
        ctx: ConversionContext = self.ctx  # type: ignore[attr-defined]
        prefix = ctx.settings.output_prefix
        sound_file = ""

        for param in args.elements():
            name = param.attributes.get("name")
            if name is None:
                continue
            value: Any = None

            if type_hw == "LevelStart":
                if name == "id" and param.value != "0":
                    name, value = "StartID", param.value

            elif type_hw in ("LevelExitArea", "LevelExit"):
                if name == "level":
                    name = "Level"
                    if param.value in ctx.level_keys:
                        value = ctx.level_keys[param.value]
                    else:
                        value = "HWPORT.UNKNOWN.LVL"
                        ctx.warn(
                            f"unknown level id '{param.value}' referenced by a LevelExit script"
                        )
                elif name == "start id" and param.value != "0":
                    name, value = "StartID", param.value
                elif name == "shape":
                    # A000FF scripts cannot point at a shape, so an intermediate
                    # AreaTrigger is inserted that fires this script instead.
                    array_tag = param["int-arr"]
                    if array_tag is not None:
                        trigger = WorldScript(
                            id=self._next_id(),
                            id_old=-1,
                            x=ws.x + 4,
                            y=ws.y,
                            type="AreaTrigger",
                            enabled=True,
                            trigger_times=ws.trigger_times,
                        )
                        trigger.connections.append((ws.id, 0))
                        trigger.params["Areas"] = self._old_ids(array_tag.value)
                        self.world_scripts.append(trigger)  # type: ignore[attr-defined]

            elif type_hw == "Random":
                if name == "nodes":
                    self._connections(param, ws, "ToExecute")
                elif name == "run-one" and not parse_bool(param.value):
                    # Not "run one" means a chance roll, not a count.
                    ws.type = "RandomChance"

            elif type_hw == "PlaySound":
                if name == "sound":
                    name = "Sound"
                    sound_file = change_extension(param.value, "sbnk")
                    value = prefix + sound_file
                elif name == "loop":
                    name, value = "Looping", parse_bool(param.value)
                    ctx.sound_metadata.setdefault(sound_file, SoundMetadata()).looping = value
                elif name == "play3d":
                    name, value = "PlayAs3D", parse_bool(param.value)
                    ctx.sound_metadata.setdefault(sound_file, SoundMetadata()).is_2d = not value

            elif type_hw == "ChangeDoodadState":
                if name == "state":
                    name, value = "State", param.value
                elif name == "object":
                    self._connections(param, ws, "Units")

            elif type_hw == "AnnounceText":
                if name == "text":
                    name = "Text"
                    value = (
                        "." + ctx.settings.strings_key_prefix + param.value
                        if param.value.startswith("ig.")
                        else param.value
                    )
                elif name == "time":
                    name, value = "Time", parse_int(param.value)
                elif name == "type":
                    if param.value == "0":  # title
                        name, value = "AnchorY", 0.2
                    elif param.value == "1":  # subtitle
                        name, value = "AnchorY", 0.2
                        ws.params["Font"] = "system/system_small.fnt"
                    elif param.value == "2":  # body text
                        name, value = "Font", "system/system_small.fnt"

            elif type_hw == "DestroyObject":
                if name == "static":
                    self._connections_static(param, ws, "Units")
                elif name == "dynamic":
                    self._connections_dynamic(param, ws, "Units")

            elif type_hw == "ToggleElement":
                if name == "state":
                    name, value = "State", parse_int(param.value) + 1
                elif name == "element":
                    self._connections(param, ws, "Scripts")

            elif type_hw == "AreaTrigger":
                if name == "event":
                    name, value = "Event", parse_int(param.value) + 1
                elif name == "types":
                    flags = parse_int(param.value)
                    new_flags = 0
                    for hw_flag, a000ff_flag in _AREA_TRIGGER_FLAGS:
                        if flags & hw_flag:
                            new_flags |= a000ff_flag
                    name, value = "Filter", new_flags
                elif name == "shape":
                    self._connections(param, ws, "Areas")

            elif type_hw == "Counter":
                if name == "count":
                    name, value = "Count", parse_int(param.value)
                elif name == "execute":
                    self._connections(param, ws, "ToExecute")

            elif type_hw == "ObjectEventTrigger":
                if name == "object":
                    self._connections(param, ws, "Units")

            elif type_hw == "DangerArea":
                if name == "damage":
                    name, value = "Damage", parse_int(param.value)
                elif name == "freq":
                    name, value = "Frequency", parse_int(param.value)
                elif name == "shape":
                    self._connections(param, ws, "Areas")
                # TODO: buffs ("buff")

            elif type_hw in ("ProjectileShooter", "ProjectileSpewer"):
                if name == "projectile":
                    name = "Projectile"
                    value = prefix + change_extension(param.value, "unit")
                elif name == "direction":
                    name = "Direction"
                    value = _SHOOTER_DIRECTIONS.get(parse_int(param.value))
                elif name == "spread":
                    name, value = "Spread", math.pi * parse_float(param.value) / 180.0
                elif name == "spawn-rate":
                    name, value = "Frequency", parse_int(param.value)

            elif type_hw == "PlayMusic":
                if name == "sound":
                    name = "Music"
                    value = prefix + change_extension(param.value, "sbnk")

            elif type_hw == "ChangeDoodadLayer":
                if name == "layer":
                    name, value = "Layer", parse_int(param.value)
                elif name == "objects":
                    self._connections(param, ws, "Units")

            elif type_hw == "HideObject":
                if name == "state":
                    name, value = "State", _remap_tristate(parse_int(param.value))
                elif name == "object":
                    self._connections(param, ws, "Units")

            elif type_hw == "SetGlobalFlag":
                if name == "flag":
                    name, value = "Flag", param.value
                elif name == "state":
                    name, value = "State", parse_int(param.value)

            elif type_hw == "CheckGlobalFlag":
                if name == "flag":
                    name, value = "Flag", param.value
                elif name == "on-true":
                    self._connections(param, ws, "OnTrue")
                elif name == "on-false":
                    self._connections(param, ws, "OnFalse")

            elif type_hw == "PlayEffect":
                if name == "effect":
                    name = "Effect"
                    value = prefix + effect_converter.convert(ctx, param.value)

            elif type_hw == "TogglePhysics":
                if name == "state":
                    state = parse_int(param.value)
                    name, value = "State", 0 if state == 2 else state
                elif name == "doodad":
                    self._connections(param, ws, "Units")

            elif type_hw == "DifficultyFilter":
                if name in ("easy", "medium", "hard"):
                    self._connections(param, ws, name.capitalize())

            elif type_hw == "PlayAttachedEffect":
                if name == "effect":
                    name = "Effect"
                    value = prefix + effect_converter.convert(ctx, param.value)
                elif name == "layer":
                    name, value = "Layer", parse_int(param.value)
                elif name == "objects":
                    self._connections(param, ws, "Objects")
                elif name == "y-offset":
                    name, value = "OffsetY", int(parse_float(param.value) * 16.0)

            elif type_hw == "ToggleImmortality":
                if name == "state":
                    name, value = "State", _remap_tristate(parse_int(param.value))
                elif name == "element":
                    self._connections(param, ws, "Units")

            elif type_hw == "ShowSpeechBubble":
                if name == "style":
                    name = "Style"
                    value = prefix + change_extension(param.value, "sval")
                elif name == "text":
                    name = "Text"
                    value = "." + ctx.settings.strings_key_prefix + param.value
                elif name == "objects":
                    self._connections(param, ws, "Objects")
                elif name == "x-offset":
                    name, value = "OffsetX", int(parse_float(param.value) * 16.0)
                elif name == "y-offset":
                    name, value = "OffsetY", int(parse_float(param.value) * 16.0)
                elif name in ("width", "layer", "time"):
                    name, value = name.capitalize(), parse_int(param.value)
                elif name == "execute":
                    self._connections(param, ws, "OnFinished")

            elif type_hw == "StopSound":
                if name == "sound":
                    self._connections(param, ws, "Sounds")

            elif type_hw == "ShopArea":
                if name == "cats":
                    name, value = "Categories", param.value
                elif name == "shape":
                    self._connections(param, ws, "Areas")

            elif type_hw == "PathNode":
                if name == "next":
                    self._connections(param, ws, "NextPath")
                elif name == "spread":
                    name, value = "Spread", parse_float(param.value)

            if value is not None:
                ws.params[name] = value

    # ------------------------------------------------------------ connections

    def _old_ids(self, raw: str) -> list[OldUnitID]:
        out = []
        for token in raw.split(" "):
            if not token:
                continue
            old = OldUnitID(parse_int(token))
            self.old_ids.append(old)  # type: ignore[attr-defined]
            out.append(old)
        return out

    def _connections_static(self, tag: XmlTag | None, ws: WorldScript, name: str) -> None:
        if tag is None:
            return
        ws.params[name] = self._old_ids(tag.value)

    def _connections_dynamic(self, tag: XmlTag | None, ws: WorldScript, name: str) -> None:
        if tag is None:
            return
        ids = [t for t in tag.value.split(" ") if t]
        # Pairs of (id, 0); only the first of each pair carries information.
        ws.params["#" + name] = self._old_ids(" ".join(ids[::2]))

    def _connections(self, param: XmlTag, ws: WorldScript, name: str) -> None:
        if not param.children:
            return
        self._connections_static(param["int-arr[name=static]"], ws, name)
        self._connections_dynamic(param["int-arr[name=dynamic]"], ws, name)

    def prepare_script_writing(self) -> None:
        """Resolve script-to-script connections now that every id exists."""
        by_old = {}
        for ws in self.world_scripts:  # type: ignore[attr-defined]
            by_old.setdefault(ws.id_old, ws)

        for ws in self.world_scripts:  # type: ignore[attr-defined]
            if ws.tag is None:
                continue
            conns_tag = ws.tag["int-arr[name=connections]"]
            if conns_tag is None:
                continue
            conns = [c for c in conns_tag.value.split(" ") if c]
            delays_tag = ws.tag["int-arr[name=connection-delays]"]
            delays = [d for d in delays_tag.value.split(" ") if d] if delays_tag else []

            for i, raw in enumerate(conns):
                target = by_old.get(parse_int(raw))
                if target is None:
                    continue
                delay = parse_int(delays[i]) if i < len(delays) else 0
                ws.connections.append((target.id, delay))


def _remap_tristate(state: int) -> int:
    """Hammerwatch 0/1/2 (hide/show/toggle) → A000FF 2/1/3."""
    if state == 0:
        return 2
    if state == 2:
        return 3
    return state
