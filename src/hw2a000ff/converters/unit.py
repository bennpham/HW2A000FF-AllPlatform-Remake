"""Units → ``.unit`` — port of ``xml2unit/UnitConverter.cs``.

This is the heart of the converter: a Hammerwatch ``<actor>``/``<projectile>``/
``<doodad>``/``<item>`` becomes an A000FF ``<unit>`` with a behavior block and a
set of animation scenes.
"""

from __future__ import annotations

from ..context import ConversionContext
from ..fmt import Writer, fmt_bool, fmt_float, fmt_int, parse_bool, parse_float, parse_int
from ..nimble import XmlFile, XmlTag
from ..paths import change_extension, dirname
from . import effect as effect_converter
from . import gore as gore_converter
from . import loot as loot_converter
from . import sprite as sprite_converter
from .skills import BlinkSkill, SpewSkill, StrikeSkill, UnitSkill

SPEED_ACTOR_MULT = 3.0
SPEED_PROJECTILE_MULT = 4.0

#: Hammerwatch world units are 16 pixels.
UNITS_TO_PIXELS = 16.0

#: A000FF's default layer; Hammerwatch's `defaultlayer` is relative to it.
DEFAULT_LAYER = 20

#: `<item behavior="...">` values and the A000FF slot each maps onto.
ITEM_BEHAVIOR_SLOTS = {
    "food": "item",
    "money": "item",
    "key": "item",
    "collectable": "item",
    "mana": "item",
    "life": "item",
    "potion": "item",
    "present": "item",
    "upgrade": "item",
    "breakable": "doodad",
    "door": "doodad",
    "bomb": "doodad",
    "checkpoint": "doodad",  # TODO: this needs a behavior of its own
}

PICKUP_BEHAVIORS = (
    "food", "money", "key", "collectable", "mana", "life", "potion", "present", "upgrade",
)

COMPOSITE_BEHAVIORS = (
    "spawner", "melee", "ranged", "caster", "composite", "tower-flower", "tower-nova",
)

#: Compass direction → animation index, as A000FF numbers its 8-way sprites.
DIRECTION_INDEX = {
    "east": "0",
    "southeast": "1",
    "south": "2",
    "southwest": "3",
    "west": "4",
    "northwest": "5",
    "north": "6",
    "northeast": "7",
}

#: Projectile sprite rotations are offset by half a turn per sprite count.
_PROJECTILE_ROTATIONS = {16: 8, 8: 4, 4: 2, 1: 0}


def slot_for_root(ctx: ConversionContext, root: XmlTag) -> str | None:
    """The A000FF slot a Hammerwatch root element belongs in, or None."""
    if root.name in ("actor", "projectile", "doodad"):
        return root.name
    if root.name == "item":
        behavior = root.attributes.get("behavior")
        if behavior is None:
            ctx.warn("item has no behavior attribute; skipped")
            return None
        slot = ITEM_BEHAVIOR_SLOTS.get(behavior)
        if slot is None:
            ctx.warn(f"unknown item behavior '{behavior}'; skipped")
        return slot
    return None


def srgb_to_linear(f: float) -> float:
    if f <= 0.04045:
        return f / 12.92
    return ((f + 0.055) / 1.055) ** 2.4


def resolve_actor_name(name: str) -> str:
    """``east-attack`` → ``attack-0``, ``south`` → ``idle-2``, and so on."""
    real_name = "idle"
    if "-" in name:
        name, _, real_name = name.partition("-")
    index = DIRECTION_INDEX.get(name)
    return f"{real_name}-{index}" if index is not None else name


def resolve_projectile_name(name: str, sprite_count: int) -> tuple[str, str | None]:
    """Map a projectile's numbered sprite onto an ``idle-N`` scene."""
    rotation = _PROJECTILE_ROTATIONS.get(sprite_count)
    if rotation is None:
        return name, f"unknown how to handle {sprite_count} sprite count"
    try:
        index = int(name)
    except ValueError:
        return name, None
    if not 0 <= index < sprite_count:
        return name, None
    return f"idle-{(index + rotation) % sprite_count}", None


def convert_collision_point(ctx: ConversionContext, unit_name: str, point: str) -> str:
    """Flatten the lower edge of wall pieces so players cannot stand in them."""
    if not ctx.settings.modify_wall_collision:
        return point
    markers = ("_h_", "_v_", "_crn_", "_x_", "_special_pillar", "_special_deteriorate")
    if any(m in unit_name for m in markers):
        parts = point.split(" ")
        if len(parts) >= 2 and parts[1].startswith("-"):
            return f"{parts[0]} 0"
    return point


def find_attack_length(ctx: ConversionContext, unit: XmlTag) -> int:
    """Total duration of the east-facing attack animation, used as castpoint."""
    sprite = unit.find_tag_by_attribute("name", "east-attack")
    if sprite is None:
        # The original dereferences this straight away and throws.
        ctx.warn("no 'east-attack' sprite; using a castpoint of 0")
        return 0
    time = 0
    for frame in sprite.children:
        if frame.name != "frame":
            continue
        time += parse_int(frame.attributes["time"]) if "time" in frame.attributes else 100
    return time


def _add_loot_pairs(ctx: ConversionContext, pairs: list[XmlTag]) -> None:
    """Read a flat ``<int>chance</int><string>unit</string>`` sequence."""
    if len(pairs) % 2:
        ctx.warn("loot table has an odd number of entries; the last one is ignored")
    for i in range(0, len(pairs) - 1, 2):
        loot_converter.add(
            ctx, parse_int(pairs[i].value), change_extension(pairs[i + 1].value, "unit")
        )


def create_loot(ctx: ConversionContext, slot: str, full_unit_name: str, entry: XmlTag) -> None:
    """Move a unit's inline loot into the run-wide loot table."""
    spread = 0.0
    origin = (0, 0)

    if entry.name == "dictionary":
        # Some units define loot as a dictionary carrying offset information.
        origin_tag = entry["string[name=origin]"]
        if origin_tag is not None:
            parts = origin_tag.value.split(" ")
            if len(parts) >= 2:
                origin = (parse_int(parts[0]), parse_int(parts[1]))
        spread = parse_float(entry.qv("float[name=spread]"))

        use_array = entry["array[name=loot]"]
        if use_array is not None:
            for child in use_array.elements():
                _add_loot_pairs(ctx, list(child.elements()))
                loot_converter.end_set(ctx, slot, full_unit_name)
    else:
        # Otherwise it is a flat <chance, unit> pair list. Some units wrap it in
        # a single <array>; both shapes appear in Hammerwatch's own assets.
        pairs = list(entry.elements())
        if len(pairs) == 1 and pairs[0].name == "array":
            pairs = list(pairs[0].elements())
        _add_loot_pairs(ctx, pairs)
        loot_converter.end_set(ctx, slot, full_unit_name)

    loot_converter.end(ctx, slot, full_unit_name, spread, origin)


class _State:
    """Values the behavior block computes that the scene block also needs."""

    def __init__(self) -> None:
        self.sensor_colliders = False
        self.static_coll = True
        self.coll_radius = 16.0
        self.actor_resolve = True
        self.behavior = ""


def convert(
    ctx: ConversionContext,
    xml: XmlFile,
    writer: Writer,
    slot: str,
    unit_name: str,
    full_unit_name: str,
) -> None:
    root = xml.document_element
    settings = ctx.settings
    prefix = settings.output_prefix

    is_actor = slot == "actor"
    is_projectile = slot == "projectile"
    is_item = slot == "item"
    is_editor = unit_name.startswith("editor_")

    netsync = ""
    if is_projectile:
        netsync = ' netsync="none"'
    elif is_actor:
        netsync = ' netsync="position"'

    layer = parse_int(root.attributes.get("defaultlayer", str(DEFAULT_LAYER)), DEFAULT_LAYER)

    if layer != DEFAULT_LAYER:
        if is_projectile or is_item:
            writer.line(f'<unit{netsync} layer="{layer - DEFAULT_LAYER}">')
        else:
            writer.line(f'<unit{netsync} slot="{slot}" layer="{layer - DEFAULT_LAYER}">')
    else:
        if is_projectile:
            writer.line(f"<unit{netsync}>")
        else:
            writer.line(f'<unit{netsync} slot="{slot}">')
    writer.line()

    state = _State()

    tag_states = root.find_tag_by_name("states")
    sprites = root.find_tags_by_name("sprite")
    sprite_count, most_pixels, most_width, most_height = sprite_converter.frame_extents(
        sprites, skip_hit_effects=is_projectile
    )

    # `neutral` and `spray` are projectile behaviours we deliberately ignore.
    raw_behavior = root.attributes.get("behavior")
    has_behavior = raw_behavior is not None and raw_behavior not in ("neutral", "spray")

    if has_behavior:
        state.behavior = raw_behavior or ""
        behavior_dict = root.q("behavior", "dictionary")
        if behavior_dict is None:
            ctx.warn(f"'{full_unit_name}' declares behavior '{state.behavior}' but has no dictionary")
        else:
            _write_behavior(
                ctx, writer, root, behavior_dict, state, slot, unit_name, full_unit_name,
                most_width, most_height,
            )

    elif is_projectile:
        _write_projectile_behavior(ctx, writer, root, state, unit_name, sprite_count, most_pixels)

    elif tag_states is not None:
        writer.line('  <behavior class="StateAnimations">')
        if "default" in tag_states.attributes:
            writer.line(f'    <string name="default">{tag_states.attributes["default"]}</string>')
        writer.line('    <array name="transitions">')
        for transition in tag_states.children:
            if transition.name != "transition":
                continue
            writer.line("      <dict>")
            writer.line(f'        <string name="from">{transition.attributes.get("from", "")}</string>')
            writer.line(f'        <string name="to">{transition.attributes.get("to", "")}</string>')
            writer.line("      </dict>")
        writer.line("    </array>")
        writer.line("  </behavior>")

    start_scene = _find_start_scene(ctx, root, tag_states, is_actor, is_projectile, sprite_count)

    _write_scenes(
        ctx, writer, root, sprites, state, slot, unit_name, is_actor, is_projectile, is_editor,
        start_scene, sprite_count,
    )

    writer.line()
    writer.line("</unit>")


# --------------------------------------------------------------------- behavior


def _write_behavior(
    ctx: ConversionContext,
    writer: Writer,
    root: XmlTag,
    dct: XmlTag,
    state: _State,
    slot: str,
    unit_name: str,
    full_unit_name: str,
    most_width: int,
    most_height: int,
) -> None:
    settings = ctx.settings
    prefix = settings.output_prefix
    behavior = state.behavior

    if behavior == "bomb":
        if root.name == "item":
            _write_bomb_item(ctx, writer, dct)
        elif root.name == "actor":
            _write_bomb_actor(ctx, writer, dct, most_width, most_height)

    elif behavior == "checkpoint":
        writer.line('  <behavior class="HwCheckpoint">')
        snd = dct.qv("entry[name=snd]", "string")
        writer.line(f'    <string name="sound">{prefix}{change_extension(snd, "sbnk")}</string>')
        writer.line('    <string name="anim-active">active</string>')
        writer.line("  </behavior>")
        writer.line()

    elif behavior in COMPOSITE_BEHAVIORS:
        _write_composite(
            ctx, writer, root, dct, state, slot, unit_name, full_unit_name, most_width, most_height
        )

    elif behavior == "breakable":
        writer.line('  <behavior class="Breakable">')
        destroy_snd = dct.q("entry[name=destroy-snd]")
        if destroy_snd is not None:
            fnm = change_extension(destroy_snd.element_value(), "sbnk")
            writer.line(f'    <string name="break-sound">{prefix}{fnm}</string>')
        destroy_particle = dct.q("entry[name=destroy-particle]")
        if destroy_particle is not None:
            gore_name = gore_converter.convert_particle(ctx, destroy_particle.element_value())
            if gore_name:
                writer.line(f'    <string name="gore">{prefix}{gore_name}</string>')
        tag_loot = dct.find_tag_by_attribute("name", "loot")
        if tag_loot is not None:
            create_loot(ctx, slot, full_unit_name, tag_loot)
            writer.line(
                f'    <string name="loot">{prefix}loot/{slot}.sval:{full_unit_name}</string>'
            )
        writer.line("  </behavior>")
        writer.line()

    elif behavior in PICKUP_BEHAVIORS:
        _write_pickup(ctx, writer, dct, state, behavior)

    elif behavior == "door":
        tag_type = dct.q("entry[name=type]")
        if tag_type is not None:
            writer.line('  <behavior class="Door">')
            writer.line(f'    <int name="type">{tag_type.element_value()}</int>')
            for key, field in (("open-snd", "open-snd"), ("no-key-snd", "no-key-snd")):
                tag = dct.q(f"entry[name={key}]")
                if tag is not None:
                    fnm = change_extension(tag.element_value(), "sbnk")
                    writer.line(f'    <string name="{field}">{prefix}{fnm}</string>')
            writer.line("  </behavior>")
            writer.line()


def _write_bomb_item(ctx: ConversionContext, writer: Writer, dct: XmlTag) -> None:
    prefix = ctx.settings.output_prefix
    writer.line('  <behavior class="BombBehavior">')

    death_sound = dct.qv("entry[name=death-snd]", "string") or dct.qv(
        "entry[name=explode-snd]", "string"
    )
    if death_sound:
        writer.line(
            f'    <string name="explode-sound">'
            f'{prefix}{change_extension(death_sound, "sbnk")}</string>'
        )
    writer.line(f'    <int name="delay">{parse_int(dct.qv("entry[name=explode-delay]", "int"))}</int>')
    writer.line()
    writer.line('    <dict name="action">')
    writer.line('      <string name="class">Explode</string>')

    explode_fx = dct.qv("entry[name=explode-particle]", "string")
    if explode_fx:
        writer.line(
            f'      <string name="fx">{prefix}{effect_converter.convert(ctx, explode_fx)}</string>'
        )

    raw_radius = dct.qv("entry[name=splash]", "float") or dct.qv("entry[name=dmg-range]", "float")
    radius = parse_float(raw_radius) * UNITS_TO_PIXELS
    writer.line(f'      <int name="radius">{fmt_int(radius)}</int>')

    dmg_all = parse_bool(dct.qv("entry[name=dmg-all]", "bool"))
    writer.line(f'      <float name="team-dmg">{"1" if dmg_all else "0"}</float>')
    writer.line('      <array name="effects">')
    writer.line("        <dict>")
    writer.line('          <string name="class">Damage</string>')
    writer.line('          <int name="dmg">10</int>')
    writer.line('          <string name="dmg-type">pierce</string>')
    writer.line("        </dict>")

    buff = dct.qv("entry[name=buff]", "string")
    if buff:
        writer.line("        <dict>")
        writer.line('          <string name="class">ApplyBuff</string>')
        writer.line(f'          <string name="buff">{prefix}{change_extension(buff, "sval")}</string>')
        writer.line("        </dict>")
    writer.line("      </array>")
    writer.line("    </dict>")
    writer.line("  </behavior>")
    writer.line()


def _write_bomb_actor(
    ctx: ConversionContext, writer: Writer, dct: XmlTag, most_width: int, most_height: int
) -> None:
    settings = ctx.settings
    prefix = settings.output_prefix

    writer.line('  <behavior class="BombActorBehavior">')
    hp = parse_int(dct.qv("entry[name=hp]", "int")) * settings.health_scale
    writer.line(f'    <int name="hp">{fmt_int(hp)}</int>')
    writer.line(
        f'    <int name="explode-delay">{parse_int(dct.qv("entry[name=explode-delay]", "int"))}</int>'
    )
    for field in ("min-range", "max-range", "dmg-range"):
        value = parse_float(dct.qv(f"entry[name={field}]", "float")) * UNITS_TO_PIXELS
        writer.line(f'    <int name="{field}">{fmt_int(value)}</int>')
    writer.line(
        f'    <int name="pulse-states">{parse_int(dct.qv("entry[name=pulse-states]", "int"))}</int>'
    )

    death_sound = dct.qv("entry[name=death-snd]", "string")
    if death_sound:
        writer.line(
            f'    <string name="death-snd">{prefix}{change_extension(death_sound, "sbnk")}</string>'
        )
    writer.line()
    writer.line('    <array name="skills">')

    spawn_on_death = dct.qv("entry[name=spawn-on-death]", "string")
    if spawn_on_death:
        writer.line("      <dict>")
        writer.line('        <string name="class">CompositeActorTriggeredSkill</string>')
        writer.line('        <string name="trigger">OnDeath</string>')
        writer.line('        <array name="actions">')
        count = parse_int(dct.qv("entry[name=spawn-on-death-count]", "int", default="1"), 1)
        for _ in range(count):
            writer.line("          <dict>")
            writer.line('            <string name="class">SpawnUnit</string>')
            writer.line(
                f'            <string name="unit">{change_extension(spawn_on_death, "unit")}</string>'
            )
            writer.line('            <bool name="safe-spawn">true</bool>')
            writer.line(
                f'            <int name="spawn-dist">{fmt_int((most_width + most_height) / 5.0)}</int>'
            )
            writer.line("          </dict>")
        writer.line("        </array>")
        writer.line("      </dict>")

    corpse = dct.qv("entry[name=corpse]", "string")
    if corpse:
        writer.line("      <dict>")
        writer.line('        <string name="class">CompositeActorTriggeredSkill</string>')
        writer.line('        <string name="trigger">OnDeath</string>')
        writer.line('        <array name="actions">')
        writer.line("          <dict>")
        writer.line('            <string name="class">SpawnUnit</string>')
        writer.line(
            f'            <string name="unit">{prefix}{change_extension(corpse, "unit")}</string>'
        )
        writer.line("          </dict>")
        writer.line("        </array>")
        writer.line("      </dict>")

    writer.line("    </array>")
    writer.line()
    writer.line('    <dict name="movement">')
    writer.line('      <string name="class">EmptyMovement</string>')
    writer.line("    </dict>")
    writer.line("  </behavior>")
    writer.line()


def _write_pickup(
    ctx: ConversionContext, writer: Writer, dct: XmlTag, state: _State, behavior: str
) -> None:
    prefix = ctx.settings.output_prefix
    state.sensor_colliders = True

    writer.line('  <behavior class="Pickup">')
    if behavior != "key":
        writer.line('    <bool name="bounce">false</bool>')

    sound = dct.q("entry[name=pickup-snd]")
    if sound is not None:
        fnm = change_extension(sound.element_value(), "sbnk")
        writer.line(f'    <string name="sound">{prefix}{fnm}</string>')

    writer.line('    <bool name="global">true</bool>')
    writer.line('    <array name="effects">')

    hp = dct.q("entry[name=hp]")
    if behavior == "food" and hp is not None:
        writer.line("      <dict>")
        writer.line('        <string name="class">Heal</string>')
        writer.line(f'        <int name="heal">{hp.element_value()}</int>')
        writer.line('        <bool name="pickup">true</bool>')
        writer.line("      </dict>")

    key_type = dct.q("entry[name=type]")
    if behavior == "key" and key_type is not None:
        writer.line("      <dict>")
        writer.line('        <string name="class">GiveKey</string>')
        writer.line(f'        <int name="type">{key_type.element_value()}</int>')
        writer.line("      </dict>")

    if behavior == "money":
        amount = dct.q("entry[name=amount]")
        if amount is None:
            ctx.warn("money pickup has no 'amount'; defaulting to 0")
            value = 0
        else:
            value = parse_int(amount.element_value())
        writer.line("      <dict>")
        writer.line('        <string name="class">GiveGold</string>')
        writer.line(f'        <int name="amount">{value}</int>')
        writer.line("      </dict>")

    pickup_text = dct.q("entry[name=pickup-text]")
    if pickup_text is not None:
        writer.line("      <dict>")
        writer.line('        <string name="class">ShowFloatingText</string>')
        writer.line(
            f'        <string name="text">.{ctx.settings.strings_key_prefix}'
            f'{pickup_text.element_value()}</string>'
        )
        writer.line('        <vec2 name="offset">0 -18</vec2>')
        writer.line("      </dict>")

    writer.line("    </array>")
    writer.line("  </behavior>")
    writer.line()


# ------------------------------------------------------------------- composite


def _write_composite(
    ctx: ConversionContext,
    writer: Writer,
    root: XmlTag,
    dct: XmlTag,
    state: _State,
    slot: str,
    unit_name: str,
    full_unit_name: str,
    most_width: int,
    most_height: int,
) -> None:
    settings = ctx.settings
    prefix = settings.output_prefix
    behavior = state.behavior

    movement = ""
    speed = 0.0
    dist = 0.0
    attack_range = 0.0
    damage = 0
    projectile = ""
    seeking = False
    seek_turnspeed = -1.0
    corpse = ""
    frequency = 2000
    spawn_unit_types: list[tuple[int, str]] = []
    composite_skills: list[UnitSkill] = []
    aggro_range = 0
    attack_delay = 0
    attack_sound = ""
    nova_parts = 0
    do_snd = ""
    spike_damage_delay = 0
    spike_damage_range = 0

    is_spawner = behavior == "spawner"

    if "collision" in root.attributes:
        state.coll_radius = parse_float(root.attributes["collision"], state.coll_radius)
    if not is_spawner:
        state.static_coll = False

    writer.line('  <behavior class="CompositeActorBehavior">')

    for entry in dct.children:
        if entry.is_comment or entry.is_text_node or not entry.children:
            continue
        value_tag = entry.first_element()
        if value_tag is None:
            continue
        prop_type = value_tag.name
        prop_name = entry.attributes.get("name")
        prop_value = value_tag.value
        if prop_name is None:
            continue

        # Things A000FF has no use for.
        if prop_name in ("editor-range-marker", "hp-bar"):
            continue

        if prop_type == "dictionary":
            prop_type = "dict"

        # Sound references become soundbank references.
        if prop_name.endswith("-snd"):
            prop_value = prefix + change_extension(prop_value, "sbnk")

        if prop_name in ("aggro-range", "max-range"):
            scaled = int(parse_float(prop_value) * UNITS_TO_PIXELS * settings.range_scale)
            if prop_name == "aggro-range":
                aggro_range = scaled
            # A float in Hammerwatch, an int in A000FF.
            prop_type = "int"
            prop_value = str(scaled)

        elif prop_name == "dmg-delay":
            spike_damage_delay = parse_int(prop_value)
            continue
        elif prop_name == "dmg-range":
            spike_damage_range = int(parse_float(prop_value) * UNITS_TO_PIXELS)
            continue
        elif prop_name == "nova-parts":
            nova_parts = parse_int(prop_value)
            continue
        elif prop_name == "sound" and behavior == "composite":
            do_snd = prop_value
            continue
        elif prop_name == "attack-snd":
            attack_sound = prop_value
            continue
        elif prop_name == "attack-delay":
            attack_delay = parse_int(prop_value)
            continue
        elif prop_name == "speed":
            speed = parse_float(prop_value) * SPEED_ACTOR_MULT * settings.speed_scale
            continue
        elif prop_name == "projectile":
            projectile = prop_value
            continue
        elif prop_name == "seeker":
            seeking = True
            seeker_proj = entry.q("entry[name=projectile]")
            projectile = seeker_proj.element_value() if seeker_proj is not None else ""
            ang = entry.q("entry[name=ang-speed]")
            seek_turnspeed = (
                parse_float(ang.element_value(), -1.0) if ang is not None else -1.0
            )
            continue
        elif prop_name == "range":
            attack_range = parse_float(prop_value) * UNITS_TO_PIXELS * settings.range_scale
            continue
        elif prop_name == "movement":
            kind = entry.qv("string[name=type]")
            if kind == "melee":
                movement = "MeleeMovement"
                speed = parse_float(entry.qv("float[name=speed]")) * SPEED_ACTOR_MULT
            elif kind == "ranged":
                movement = "RangedMovement"
                speed = parse_float(entry.qv("float[name=speed]")) * SPEED_ACTOR_MULT
                dist = parse_float(entry.qv("float[name=range]")) * UNITS_TO_PIXELS * settings.range_scale
            else:
                ctx.warn(f"unknown movement type '{kind}'")
            continue
        elif prop_name == "blink":
            composite_skills.append(
                BlinkSkill(
                    do_snd=do_snd,
                    cooldown=parse_int(_child_value(entry, "entry[name=timer]")),
                    range=parse_float(_child_value(entry, "entry[name=range]")) * UNITS_TO_PIXELS,
                    distance=parse_float(_child_value(entry, "entry[name=dist]")) * UNITS_TO_PIXELS,
                )
            )
            continue
        elif prop_name in ("skills", "pskills"):
            _read_skills(ctx, entry, composite_skills, do_snd)
            continue
        elif prop_name == "loot":
            create_loot(ctx, slot, full_unit_name, entry)
            prop_type = "string"
            prop_name = "loot"
            prop_value = f"{prefix}loot/{slot}.sval:{full_unit_name}"
        elif prop_name == "dmg":
            damage = parse_int(prop_value)
            continue
        elif prop_name == "corpse":
            corpse = prop_value
            continue
        elif prop_name == "frequency":
            frequency = parse_int(prop_value)
            continue
        elif prop_name == "spawn-range":
            attack_range = parse_float(prop_value) * UNITS_TO_PIXELS
            continue
        elif prop_name == "spawns":
            kids = list(entry.elements())
            if len(kids) == 1 and kids[0].name == "array":
                kids = list(kids[0].elements())
            for i in range(0, len(kids) - 1, 2):
                spawn_unit_types.append((parse_int(kids[i].value), kids[i + 1].value))
            continue
        elif prop_name == "hit-effect":
            prop_name = "hit-fx"
            prop_value = prefix + effect_converter.convert(ctx, prop_value)
        elif prop_name == "gib":
            prop_name = "gore"
            prop_value = prefix + gore_converter.convert(ctx, prop_value)
        elif prop_name == "summon":
            ctx.warn(f"'{full_unit_name}': summon skills are not converted yet")
            continue
        elif prop_name == "nova":
            ctx.warn(f"'{full_unit_name}': nova skills are not converted yet")
            continue

        writer.line(f'    <{prop_type} name="{prop_name}">{prop_value}</{prop_type}>')

    if is_spawner:
        writer.line('    <bool name="impenetrable">true</bool>')
    if behavior == "tower-flower":
        writer.line('    <bool name="must-see-target">false</bool>')

    # Movement
    writer.line()
    writer.line('    <dict name="movement">')
    if is_spawner or behavior.startswith("tower-"):
        writer.line('      <string name="class">PassiveMovement</string>')
        writer.line('      <string name="anim-idle">default</string>')
    else:
        writer.line(f'      <string name="class">{movement or "MeleeMovement"}</string>')
        writer.line('      <string name="anim-idle">idle 8</string>')
        writer.line('      <string name="anim-walk">walk 8</string>')
        writer.line()
        writer.line(f'      <float name="speed">{fmt_float(speed)}</float>')
        if dist > 0:
            writer.line(f'      <int name="dist">{fmt_int(dist)}</int>')
        elif behavior == "ranged":
            writer.line(f'      <int name="dist">{fmt_int(attack_range)}</int>')
    writer.line("    </dict>")

    # Skills
    writer.line()
    writer.line('    <array name="skills">')

    if behavior in ("ranged", "caster"):
        attack_len = find_attack_length(ctx, root)
        writer.line("      <dict>")
        writer.line('        <string name="class">CompositeActorSkill</string>')
        writer.line()
        writer.line('        <string name="anim">attack 8</string>')
        writer.line()
        writer.line('        <int name="cooldown">0</int>')
        writer.line(f'        <int name="range">{fmt_int(attack_range)}</int>')
        writer.line(f'        <int name="castpoint">{attack_len}</int>')
        writer.line('        <string name="snd">sound/enemies.sbnk:spider-melee</string>')
        writer.line('        <array name="actions">')
        if projectile:
            writer.line("          <dict>")
            writer.line('            <string name="class">HwShootProjectile</string>')
            writer.line(
                f'            <string name="projectile">'
                f'{prefix}{change_extension(projectile, "unit")}</string>'
            )
            if seeking:
                writer.line('            <bool name="seeking">true</bool>')
                if seek_turnspeed >= 0:
                    writer.line(
                        f'            <float name="seek-turnspeed">{fmt_float(seek_turnspeed)}</float>'
                    )
            writer.line("          </dict>")
        writer.line("        </array>")
        writer.line("      </dict>")

    elif behavior == "melee":
        attack_len = find_attack_length(ctx, root)
        writer.line("      <dict>")
        writer.line('        <string name="class">EnemyMeleeStrike</string>')
        writer.line()
        writer.line('        <string name="anim">attack 8</string>')
        writer.line('        <string name="snd">sound/enemies.sbnk:gnaar-melee</string>')
        writer.line()
        writer.line('        <int name="cooldown">0</int>')
        # `range` is 0 for non-ranged enemies, so a melee reach is hardcoded.
        writer.line('        <int name="range">20</int>')
        writer.line(f'        <int name="castpoint">{attack_len}</int>')
        writer.line('        <int name="arc">90</int>')
        writer.line('        <dict name="effect">')
        writer.line('          <string name="class">Damage</string>')
        writer.line(f'          <int name="dmg">{fmt_int(damage * settings.damage_scale)}</int>')
        writer.line('          <string name="dmg-type">pierce</string>')
        writer.line("        </dict>")
        writer.line("      </dict>")

    elif behavior == "spawner":
        writer.line("      <dict>")
        writer.line('        <string name="class">CompositeActorSkill</string>')
        writer.line('        <bool name="must-see">true</bool>')
        writer.line(f'        <int name="cooldown">{frequency}</int>')
        writer.line(f'        <int name="range">{fmt_int(attack_range)}</int>')
        writer.line('        <string name="anim">default</string>')
        if spawn_unit_types:
            writer.line('        <array name="actions">')
            writer.line("          <dict>")
            writer.line('            <string name="class">HwSpawnUnit</string>')
            writer.line('            <array name="units">')
            for chance, unit in spawn_unit_types:
                writer.line(
                    f"              <int>{chance}</int>"
                    f'<string>{prefix}{change_extension(unit, "unit")}</string>'
                )
            writer.line("            </array>")
            writer.line('            <bool name="safe-spawn">true</bool>')
            writer.line(
                f'            <int name="spawn-dist">{fmt_int((most_width + most_height) / 4.0)}</int>'
            )
            writer.line("          </dict>")
            writer.line("        </array>")
        else:
            ctx.warn(f"'{full_unit_name}' is a spawner with no spawn definitions")
        writer.line("      </dict>")

    elif behavior == "tower-flower":
        _write_spike_unit(ctx, unit_name, spike_damage_delay, spike_damage_range, damage)
        writer.line("      <dict>")
        writer.line('        <string name="class">TowerFlowerSkill</string>')
        writer.line('        <string name="anim">attack</string>')
        writer.line('        <int name="castpoint">50</int>')
        writer.line(f'        <int name="radius">{aggro_range}</int>')
        writer.line(f'        <int name="interval">{attack_delay}</int>')
        writer.line('        <int name="interval-random">0</int>')
        writer.line(
            f'        <string name="spike">{prefix}actors/spikes/{unit_name}_spike.unit</string>'
        )
        writer.line('        <string name="spike-effect">attack-effect</string>')
        writer.line(f'        <string name="cast-snd">{prefix}{attack_sound}</string>')
        writer.line("      </dict>")
        state.actor_resolve = False

    elif behavior == "tower-nova":
        writer.line("      <dict>")
        writer.line('        <string name="class">NovaSkill</string>')
        writer.line('        <string name="anim">attack</string>')
        writer.line(f'        <int name="cooldown">{frequency}</int>')
        writer.line('        <int name="min-range">0</int>')
        writer.line(f'        <int name="range">{aggro_range}</int>')
        writer.line(
            f'        <string name="projectile">'
            f'{prefix}{change_extension(projectile, "unit")}</string>'
        )
        writer.line(f'        <string name="fire-snd">{prefix}{attack_sound}</string>')
        writer.line(f'        <int name="proj-count">{nova_parts}</int>')
        writer.line("      </dict>")

    if corpse:
        writer.line("      <dict>")
        writer.line('        <string name="class">CompositeActorTriggeredSkill</string>')
        writer.line('        <string name="trigger">OnDeath</string>')
        writer.line('        <array name="actions">')
        writer.line("          <dict>")
        writer.line('            <string name="class">SpawnUnit</string>')
        writer.line(
            f'            <string name="unit">{prefix}{change_extension(corpse, "unit")}</string>'
        )
        writer.line("          </dict>")
        writer.line("        </array>")
        writer.line("      </dict>")

    for skill in composite_skills:
        skill.write(ctx, writer)

    writer.line("    </array>")
    writer.line("  </behavior>")
    writer.line()


def _child_value(entry: XmlTag, query: str) -> str:
    tag = entry.q(query)
    return tag.element_value() if tag is not None else ""


def _read_skills(
    ctx: ConversionContext, entry: XmlTag, skills: list[UnitSkill], do_snd: str
) -> None:
    for skill in entry.children:
        if skill.is_text_node or skill.is_comment:
            continue
        kind_tag = skill.q("string[name=type]")
        if kind_tag is None:
            continue
        kind = kind_tag.value

        if kind == "blink":
            skills.append(
                BlinkSkill(
                    do_snd=do_snd,
                    cooldown=parse_int(skill.qv("int[name=cooldown]")),
                    range=parse_float(skill.qv("float[name=range]")) * UNITS_TO_PIXELS,
                    distance=parse_float(skill.qv("float[name=dist]")) * UNITS_TO_PIXELS,
                    sound=skill.qv("string[name=sound]"),
                    fx=skill.qv("string[name=effect]"),
                )
            )
        elif kind == "hit":
            skills.append(
                StrikeSkill(
                    do_snd=do_snd,
                    anim=skill.qv("string[name=anim-set]"),
                    cooldown=parse_int(skill.qv("int[name=cooldown]")),
                    range=parse_float(skill.qv("float[name=range]")) * UNITS_TO_PIXELS,
                    damage=parse_int(skill.qv("int[name=dmg]")),
                )
            )
        elif kind == "spew":
            # TODO: particles. ParticleConverter works, but wiring it up needs a
            # HwParticle behavior with a ttl, plus an HwProjectile that can emit
            # for the projectile's lifetime (spawn-time-limit).
            anim = skill.qv("string[name=chnl-anim-set]") or skill.qv("string[name=anim-set]")
            skills.append(
                SpewSkill(
                    do_snd=do_snd,
                    anim=anim,
                    range=parse_float(skill.qv("float[name=range]")) * UNITS_TO_PIXELS,
                    duration=parse_int(skill.qv("int[name=duration]")),
                    cooldown=parse_int(skill.qv("int[name=cooldown]")),
                    projectile=skill.qv("string[name=proj]"),
                    spread=parse_float(skill.qv("float[name=spread]")),
                    rate=parse_int(skill.qv("int[name=rate]")),
                )
            )
        else:
            ctx.warn(f"unsupported composite skill type '{kind}'")


def _write_spike_unit(
    ctx: ConversionContext, unit_name: str, delay: int, radius: int, damage: int
) -> None:
    """Tower flowers need a companion projectile unit for their spikes."""
    local = f"actors/spikes/{unit_name}_spike.unit"
    ctx.prepare("actors/spikes", local)
    with ctx.open_output(local) as writer:
        writer.line('<unit slot="projectile">')
        writer.line('  <behavior class="TowerFlowerSpike">')
        writer.line('    <string name="anim"></string>')
        writer.line(f'    <int name="hurt-delay">{delay}</int>')
        writer.line(f'    <int name="hurt-delay-max">{delay + 100}</int>')
        writer.line(f'    <int name="radius">{radius}</int>')
        writer.line('    <dict name="effect">')
        writer.line('      <string name="class">Damage</string>')
        writer.line(
            f'      <int name="dmg">{fmt_int(damage * ctx.settings.damage_scale)}</int>'
        )
        writer.line('      <string name="dmg-type">pierce</string>')
        writer.line("    </dict>")
        writer.line("  </behavior>")
        writer.line("  <scenes>")
        writer.line("    <scene>")
        writer.line("    </scene>")
        writer.line("  </scenes>")
        writer.line("</unit>")


# ------------------------------------------------------------------ projectile


def _write_projectile_behavior(
    ctx: ConversionContext,
    writer: Writer,
    root: XmlTag,
    state: _State,
    unit_name: str,
    sprite_count: int,
    most_pixels: int,
) -> None:
    """Projectiles carry their stats on the root element, not in a behavior."""
    settings = ctx.settings
    prefix = settings.output_prefix

    speed = parse_float(root.attributes.get("speed", "0")) * settings.speed_scale
    damage = parse_float(root.attributes.get("damage", "0"))
    state.static_coll = False
    if "collision" in root.attributes:
        state.coll_radius = parse_float(root.attributes["collision"], state.coll_radius)
    else:
        ctx.warn(f"projectile '{unit_name}' has no collision radius; using 16")

    if root.attributes.get("behavior") != "spray":
        speed *= SPEED_PROJECTILE_MULT

    # ...except that sometimes they do have a behavior after all.
    ttl = ""
    buff = ""
    attack_range = 0.0
    behavior_dict = root.q("behavior", "dictionary")
    if behavior_dict is not None:
        buff = behavior_dict.qv("string[name=buff]")
        ttl = behavior_dict.qv("int[name=ttl]")
        raw_range = behavior_dict.qv("float[name=range]")
        if raw_range:
            attack_range = parse_float(raw_range) * UNITS_TO_PIXELS * settings.range_scale

    kind = "RayProjectile" if most_pixels <= 64 else "Projectile"
    writer.line(f'  <behavior class="{kind}">')
    writer.line(f'    <string name="anim">idle {sprite_count}</string>')
    writer.line(f'    <float name="speed">{fmt_float(speed)}</float>')
    if ttl:
        writer.line(f'    <int name="ttl">{ttl}</int>')
    elif attack_range > 0:
        writer.line(f'    <int name="range">{fmt_int(attack_range)}</int>')
    writer.line('    <array name="effects">')
    writer.line("      <dict>")
    writer.line('        <string name="class">Damage</string>')
    writer.line(f'        <int name="dmg">{fmt_int(int(damage) * settings.damage_scale)}</int>')
    writer.line('        <string name="dmg-type">pierce</string>')
    writer.line("      </dict>")
    if buff:
        writer.line("      <dict>")
        writer.line('        <string name="class">ApplyBuff</string>')
        # TODO: a real BuffConverter.
        writer.line(
            f'        <string name="buff">{prefix}{change_extension(buff, "sval")}'
            f":{unit_name}</string>"
        )
        writer.line("      </dict>")
    writer.line("    </array>")
    writer.line("  </behavior>")
    writer.line()


# ---------------------------------------------------------------------- scenes


def _find_start_scene(
    ctx: ConversionContext,
    root: XmlTag,
    tag_states: XmlTag | None,
    is_actor: bool,
    is_projectile: bool,
    sprite_count: int,
) -> str:
    """Work out which scene the unit should start on."""
    start_scene = ""

    if tag_states is not None:
        # `transitions` are not an A000FF feature; the sprite `loopback` flag
        # covers some of the same ground, so only the default state is used.
        start_scene = tag_states.attributes.get("default", "")
    else:
        random_start = root.find_tags_by_attribute("random-start", "true")
        for sprite in random_start:
            name = sprite.attributes.get("name", "hwport_def")
            if is_actor:
                name = resolve_actor_name(name)
            start_scene += name + " "

        if not random_start:
            if root.find_tag_by_name_and_attribute("sprite", "name", "default") is not None:
                start_scene = "default"
            elif is_actor:
                # Actors usually have idle-0 through idle-7.
                start_scene = "".join(f"idle-{i} " for i in range(8))

    if not start_scene:
        if is_projectile:
            start_scene, warning = resolve_projectile_name("0", sprite_count)
            if warning:
                ctx.warn(warning)
        else:
            start_scene = "hwport_def"

    return start_scene


def _write_scenes(
    ctx: ConversionContext,
    writer: Writer,
    root: XmlTag,
    sprites: list[XmlTag],
    state: _State,
    slot: str,
    unit_name: str,
    is_actor: bool,
    is_projectile: bool,
    is_editor: bool,
    start_scene: str,
    sprite_count: int,
) -> None:
    writer.line(f'  <scenes start="{start_scene.rstrip()}">')

    # A shared scene holds collision, shadows and lights for every animation.
    writer.line('    <scene name="hwport_shared">')
    _write_collision(ctx, writer, root, state, unit_name, is_actor, is_projectile)
    _write_shadows(ctx, writer, root, unit_name)
    _write_lights(ctx, writer, root)
    writer.line("    </scene>")
    writer.line()

    pulse_count = 0
    for sprite in sprites:
        should_have_shared = True
        looping = True

        name = sprite.attributes.get("name")
        if name is not None:
            if name == "attack-effect":
                should_have_shared = False
            if is_actor and name.startswith("attack"):
                looping = False
            if is_actor and state.actor_resolve:
                name = resolve_actor_name(name)
            if is_projectile:
                # TODO: use the projectile's hit-effect sprites for something.
                if name.startswith("d"):
                    continue
                name, warning = resolve_projectile_name(name, sprite_count)
                if warning:
                    ctx.warn(warning)
            if name == "pulse" and root.name == "actor" and state.behavior == "bomb":
                name = f"pulse-{pulse_count}"
                pulse_count += 1
            writer.line(f'    <scene name="{name}">')
        else:
            writer.line('    <scene name="hwport_def">')

        if should_have_shared:
            writer.line('\t  <scene src="hwport_shared" />')
        if is_editor:
            writer.line("%if EDITOR")

        sprite_converter.convert(
            ctx,
            sprite,
            writer,
            sprite_converter.get_material(unit_name, state.behavior, slot),
            looping,
            unit_name,
        )

        if is_editor:
            writer.line("%endif")

        writer.line("    </scene>")
        writer.line()

    writer.line("  </scenes>")


def _write_collision(
    ctx: ConversionContext,
    writer: Writer,
    root: XmlTag,
    state: _State,
    unit_name: str,
    is_actor: bool,
    is_projectile: bool,
) -> None:
    started = False
    collision = root.find_tag_by_name("collision")

    if collision is not None:
        shoot_through = parse_bool(collision.attributes.get("shoot-through", "false"))
        static_coll = parse_bool(collision.attributes.get("static", "true"), True)

        for circle in collision.find_tags_by_name("circle"):
            if not started:
                writer.line(f'      <collision static="{fmt_bool(static_coll)}">')
                started = True
            sensor = ' sensor="true"' if state.sensor_colliders else ""
            through = ' shoot-through="true"' if shoot_through else ""
            offset = circle.attributes.get("offset", "0 0")
            radius = circle.attributes.get("radius", "0")
            writer.line(
                f'        <circle offset="{offset}" radius="{radius}"{sensor}{through} />'
            )

    # Polygons may sit outside a <collision> tag, for backwards compatibility.
    for poly in root.find_tags_by_name("polygon"):
        shoot_through = False
        if "collision" not in poly.attributes:
            if poly.parent is not None and poly.parent.name == "collision":
                if parse_bool(poly.parent.attributes.get("shoot-through", "false")):
                    shoot_through = True
            else:
                continue
        elif not parse_bool(poly.attributes["collision"]):
            continue

        # Checkpoints are polygons with no sensor type, so force one here.
        if state.behavior == "checkpoint":
            state.sensor_colliders = True

        if not started:
            writer.line(f'      <collision static="{fmt_bool(state.static_coll)}">')
            started = True

        sensor = ' sensor="true"' if state.sensor_colliders else ""
        through = ' shoot-through="true"' if shoot_through else ""
        writer.line(f"        <polygon{sensor}{through}>")
        for point in poly.find_tags_by_name("point"):
            writer.line(f"          <point>{convert_collision_point(ctx, unit_name, point.value)}</point>")
        writer.line("        </polygon>")

    # Some unit types define no collision at all, so supply one.
    if is_actor and not started:
        radius = fmt_float(state.coll_radius)
        writer.line(f'      <collision static="{fmt_bool(state.static_coll)}">')
        writer.line(f'        <circle offset="0 0" aim-through="true" radius="{radius}" />')
        writer.line(
            f'        <circle offset="0 {fmt_float(-state.coll_radius * 1.5)}" sensor="true" '
            f'shoot-through="false" aim-through="true" radius="{radius}" />'
        )
        started = True
    elif is_projectile and not started:
        writer.line(f'      <collision static="{fmt_bool(state.static_coll)}">')
        writer.line(
            f'        <circle offset="0 0" radius="{fmt_float(state.coll_radius)}" '
            f'projectile="true" />'
        )
        started = True

    if started:
        writer.line("      </collision>")


def _write_shadows(ctx: ConversionContext, writer: Writer, root: XmlTag, unit_name: str) -> None:
    for shadow in root.find_tags_by_name("polygon"):
        if not parse_bool(shadow.attributes.get("shadow", "false")):
            continue
        writer.line('      <shadow darkness="1.0">')
        writer.line("        <polygon>")
        y_offset = sprite_converter.unit_y_offset(ctx, unit_name)
        for point in shadow.find_tags_by_name("point"):
            if y_offset == 0:
                writer.line(f"          <point>{point.value}</point>")
            else:
                parts = point.value.split(" ")
                if len(parts) >= 2:
                    writer.line(f"          <point>{parts[0]} {parse_int(parts[1]) - y_offset}</point>")
                else:
                    writer.line(f"          <point>{point.value}</point>")
        writer.line("        </polygon>")
        writer.line("      </shadow>")


#: Hammerwatch light colours are brighter than A000FF's, hence the boost.
LIGHT_COLOR_BOOST = 1.45


def _write_lights(ctx: ConversionContext, writer: Writer, root: XmlTag) -> None:
    prefix = ctx.settings.output_prefix

    for light in root.find_tags_by_name("light"):
        origin_tag = light.find_tag_by_name("origin")
        origin = origin_tag.value if origin_tag is not None else "0 0"

        texture = "system/light_L.png"
        frame = "0 0 128 128"

        texture_tag = light.find_tag_by_name("texture")
        if texture_tag is not None:
            texture = texture_tag.value
            ctx.copy_asset(texture)
            # The original measures the *output* copy, which does not exist when
            # the asset could not be found. Measure the resolved source instead.
            source = ctx.resolve_source(texture)
            if source is None:
                ctx.warn(f"light texture '{texture}' not found; assuming {frame}")
            else:
                try:
                    from ..imaging import png_size

                    width, height = png_size(source)
                    frame = f"0 0 {width} {height}"
                except Exception as exc:  # noqa: BLE001 - never fail a conversion on this
                    ctx.warn(f"could not read the size of '{texture}': {exc}")
            texture = prefix + texture

        # Two lights are emitted per definition: color1 from mul, color1 from add.
        ranges = light.find_tags_by_name("range")
        colors = light.find_tags_by_name("color1")
        if len(ranges) < 2 or len(colors) < 2:
            ctx.warn("light needs two <range> and two <color1> entries; skipped")
            continue

        for i in range(2):
            parts = colors[i].value.split(" ")
            while len(parts) < 3:
                parts.append("0")
            channels = [
                min(255, int(srgb_to_linear(parse_int(p) / 255.0 * LIGHT_COLOR_BOOST) * 255.0))
                for p in parts[:3]
            ]
            writer.line(f'      <light pos="{origin}">')
            writer.line(f'        <sprite texture="{texture}">')
            writer.line(f"          <frame>{frame}</frame>")
            writer.line("        </sprite>")
            writer.line('        <length value="50" />')
            writer.line('        <looping value="true" />')
            writer.line('        <cast-shadows value="false" />')
            writer.line('        <shadow-cast-pos value="0 0" />')
            writer.line('        <shadow-cast-pos-jitter value="0 0 0 0" />')
            writer.line("        <sizes>")
            writer.line(f'          <size value="{ranges[i].value}" />')
            writer.line("        </sizes>")
            writer.line("        <colors>")
            writer.line(
                f'          <color value="{channels[0]} {channels[1]} {channels[2]} '
                f'{0 if i == 0 else 25} {channels[1]}" />'
            )
            writer.line("        </colors>")
            writer.line("      </light>")
