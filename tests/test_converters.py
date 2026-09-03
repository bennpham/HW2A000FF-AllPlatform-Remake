"""Behaviour-level checks on individual converters."""

from __future__ import annotations

import io

import pytest

from hw2a000ff.context import ConversionContext
from hw2a000ff.fmt import Writer
from hw2a000ff.nimble import XmlFile
from hw2a000ff.converters import loot, sprite, unit
from hw2a000ff.converters.level import make_multiple
from hw2a000ff.converters.level_objects import Light, to_pixels
from hw2a000ff.converters.level_scripts import SCRIPT_RENAMES, _remap_tristate
from hw2a000ff.converters.skills import SpewSkill


def render(ctx: ConversionContext, xml_text: str, slot: str, name: str) -> str:
    buf = io.StringIO()
    unit.convert(ctx, XmlFile.from_text(xml_text), Writer(buf), slot, name, f"{name}.unit")
    return buf.getvalue()


# ----------------------------------------------------------------- sprite names


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("east", "idle-0"), ("southeast", "idle-1"), ("south", "idle-2"),
        ("southwest", "idle-3"), ("west", "idle-4"), ("northwest", "idle-5"),
        ("north", "idle-6"), ("northeast", "idle-7"),
        ("east-attack", "attack-0"), ("north-walk", "walk-6"),
        ("default", "default"),
    ],
)
def test_resolve_actor_name(name, expected):
    assert unit.resolve_actor_name(name) == expected


@pytest.mark.parametrize(
    ("count", "name", "expected"),
    [
        (16, "0", "idle-8"), (16, "8", "idle-0"), (16, "15", "idle-7"),
        (8, "0", "idle-4"), (8, "4", "idle-0"),
        (4, "0", "idle-2"), (4, "2", "idle-0"),
        (1, "0", "idle-0"),
    ],
)
def test_resolve_projectile_name(count, name, expected):
    assert unit.resolve_projectile_name(name, count)[0] == expected


def test_unusual_sprite_count_warns_rather_than_guessing():
    resolved, warning = unit.resolve_projectile_name("0", 5)
    assert resolved == "0"
    assert warning is not None


# --------------------------------------------------------------------- slots


@pytest.mark.parametrize(
    ("root", "expected"),
    [
        ('<actor/>', "actor"),
        ('<projectile/>', "projectile"),
        ('<doodad/>', "doodad"),
        ('<item behavior="money"/>', "item"),
        ('<item behavior="potion"/>', "item"),
        ('<item behavior="breakable"/>', "doodad"),
        ('<item behavior="door"/>', "doodad"),
        ('<item behavior="mystery"/>', None),
        ('<item/>', None),
        ('<tileset/>', None),
    ],
)
def test_slot_for_root(ctx, root, expected):
    assert unit.slot_for_root(ctx, XmlFile.from_text(root).document_element) == expected


# ------------------------------------------------------------------ behaviors


def test_melee_actor_gets_a_composite_behavior(ctx):
    out = render(ctx, '<actor behavior="melee"><behavior><dictionary>'
                      '<entry name="hp"><int>50</int></entry>'
                      "</dictionary></behavior></actor>", "actor", "gnaar")
    assert '<behavior class="CompositeActorBehavior">' in out
    assert '<string name="class">MeleeMovement</string>' in out
    assert '<string name="class">EnemyMeleeStrike</string>' in out


def test_money_item_becomes_a_pickup_with_a_sensor_collider(ctx):
    out = render(ctx, '<item behavior="money"><behavior><dictionary>'
                      '<entry name="amount"><int>25</int></entry></dictionary></behavior>'
                      '<polygon collision="true"><point>0 0</point></polygon></item>',
                 "item", "coin")
    assert '<behavior class="Pickup">' in out
    assert '<string name="class">GiveGold</string>' in out
    assert '<int name="amount">25</int>' in out
    assert 'sensor="true"' in out


def test_small_projectile_uses_a_ray(ctx):
    small = render(ctx, '<projectile speed="1" damage="4" collision="2">'
                        "<sprite name=\"0\"><texture>a.png</texture><frame>0 0 8 8</frame></sprite>"
                        "</projectile>", "projectile", "bolt")
    assert '<behavior class="RayProjectile">' in small

    large = render(ctx, '<projectile speed="1" damage="4" collision="2">'
                        "<sprite name=\"0\"><texture>a.png</texture><frame>0 0 32 32</frame></sprite>"
                        "</projectile>", "projectile", "boulder")
    assert '<behavior class="Projectile">' in large


def test_projectile_hit_effect_sprites_are_skipped(ctx):
    out = render(ctx, '<projectile speed="1" damage="1" collision="2">'
                      '<sprite name="0"><texture>a.png</texture><frame>0 0 8 8</frame></sprite>'
                      '<sprite name="d0"><texture>a.png</texture><frame>0 0 8 8</frame></sprite>'
                      "</projectile>", "projectile", "bolt")
    assert out.count("<scene name=") == 2  # hwport_shared + one rotation
    assert '<string name="anim">idle 1</string>' in out


def test_missing_east_attack_sprite_warns_instead_of_crashing(ctx):
    # UnitConverter.cs:1214 dereferences this without a null check.
    out = render(ctx, '<actor behavior="ranged"><behavior><dictionary>'
                      '<entry name="range"><float>5</float></entry>'
                      "</dictionary></behavior></actor>", "actor", "archer")
    assert '<int name="castpoint">0</int>' in out
    assert any("east-attack" in w for w in ctx.warnings)


def test_layer_is_relative_to_the_a000ff_default(ctx):
    out = render(ctx, '<doodad defaultlayer="23"/>', "doodad", "torch")
    assert 'layer="3"' in out
    assert '<unit slot="doodad">' in render(ctx, "<doodad/>", "doodad", "torch")


# ---------------------------------------------------------------------- loot


def test_flat_loot_array(ctx):
    render(ctx, '<actor behavior="melee"><behavior><dictionary><entry name="loot">'
                "<int>50</int><string>items/coin.xml</string>"
                "<int>25</int><string>items/gem.xml</string>"
                "</entry></dictionary></behavior></actor>", "actor", "gnaar")
    buf = io.StringIO()
    loot.convert(ctx, "actor", Writer(buf))
    out = buf.getvalue()
    assert "<int>50</int><string>hwport/items/coin.unit</string>" in out
    assert "<int>25</int><string>hwport/items/gem.unit</string>" in out


def test_dictionary_loot_carries_origin_and_spread(ctx):
    render(ctx, '<item behavior="breakable"><behavior><dictionary>'
                '<dictionary name="loot">'
                '<string name="origin">0 -1</string><float name="spread">0.5</float>'
                '<array name="loot"><array><int>75</int><string>items/coin.xml</string></array></array>'
                "</dictionary></dictionary></behavior></item>", "doodad", "crate")
    buf = io.StringIO()
    loot.convert(ctx, "doodad", Writer(buf))
    out = buf.getvalue()
    assert "<vec2>0 16</vec2> <!-- Offset -->" in out
    assert "<vec2>8 8</vec2> <!-- Spread -->" in out


def test_odd_loot_list_warns(ctx):
    render(ctx, '<actor behavior="melee"><behavior><dictionary><entry name="loot">'
                "<int>50</int><string>items/coin.xml</string><int>25</int>"
                "</entry></dictionary></behavior></actor>", "actor", "gnaar")
    assert any("odd number" in w for w in ctx.warnings)


# -------------------------------------------------------------------- levels


def test_to_pixels_matches_the_original_offset():
    assert to_pixels(10) == 0.0
    assert to_pixels(0) == -160.0
    assert to_pixels(20) == 160.0


@pytest.mark.parametrize(
    ("n", "multiple", "floor", "expected"),
    [(-37, 20, True, -40), (37, 20, False, 40), (37, 20, True, 20), (0, 20, False, 0)],
)
def test_make_multiple(n, multiple, floor, expected):
    assert make_multiple(n, multiple, floor) == expected


def test_light_color_transform_is_srgb():
    assert Light.transform(0) == 0.0
    assert 0.2 < Light.transform(255) < 0.22


def test_script_renames_cover_the_documented_set():
    assert SCRIPT_RENAMES["SpawnObject"] == "SpawnUnit"
    assert SCRIPT_RENAMES["ChangeDoodadState"] == "SetUnitScene"
    assert SCRIPT_RENAMES["TogglePhysics"] == "ToggleCollision"


@pytest.mark.parametrize(("hw", "a000ff"), [(0, 2), (1, 1), (2, 3)])
def test_hide_state_remap(hw, a000ff):
    assert _remap_tristate(hw) == a000ff


# -------------------------------------------------------------------- sprites


@pytest.mark.parametrize(
    ("name", "behavior", "slot", "expected"),
    [
        ("anything", "money", "item", "item-money"),
        ("anything", "breakable", "doodad", "proj-prop"),
        ("wall_h_mid", "", "doodad", "proj-wall"),
        ("wall_v_mid", "", "doodad", "wall"),
        ("wall_v_cap_dn", "", "doodad", "proj-wall"),
        ("deco_barrel", "", "doodad", "proj-prop"),
        ("trap_spikes", "", "doodad", "floor"),
        ("plain_thing", "", "actor", "actor"),
    ],
)
def test_get_material(name, behavior, slot, expected):
    assert sprite.get_material(name, behavior, slot) == expected


def test_wall_y_offset_only_applies_when_enabled(ctx):
    assert sprite.unit_y_offset(ctx, "wall_v_mid") == 0
    ctx.settings.modify_wall_collision = True
    assert sprite.unit_y_offset(ctx, "wall_v_mid") == 16
    assert sprite.unit_y_offset(ctx, "wall_v_cap_dn") == 0


# --------------------------------------------------------------------- skills


def test_spew_skill_writes_its_own_rate(ctx):
    # The original writes m_range into this field.
    buf = io.StringIO()
    SpewSkill(anim="spew", range=64.0, duration=500, cooldown=2000,
              projectile="p.xml", spread=0.4, rate=7).write(ctx, Writer(buf))
    out = buf.getvalue()
    assert '<int name="rate">7</int>' in out
    assert '<int name="range">64</int>' in out
