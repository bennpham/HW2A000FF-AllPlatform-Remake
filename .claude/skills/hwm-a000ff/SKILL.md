---
name: hwm-a000ff
description: Reference for converting Hammerwatch 1 (HWM) XML assets to the A000FF/SSBD format used by Heroes of Hammerwatch, Hammerwatch II and the Anniversary Edition. Covers the file-extension map, coordinate and scale constants, behavior-to-class mappings, sprite and scene naming, world-script renames, lighting maths, and the known gaps. Use when working on this converter, adding support for an unconverted Hammerwatch behavior or script node, debugging converted output that the game rejects, or answering questions about how a Hammerwatch asset maps onto A000FF.
---

# Hammerwatch (HWM) → A000FF conversion

Everything here was derived by reading the original C# tool at
[bennpham/hw2a000ff](https://github.com/bennpham/hw2a000ff) line by line. Line
references point into that repository.

## The two formats

**Hammerwatch (HWM)** ships its assets as XML: `<actor>`, `<projectile>`,
`<doodad>`, `<item>`, `<tileset>`, `<font>`, `<speech>`, `<soundbank>`,
`<dictionary>` (strings) and level files. Gameplay data hangs off a
`<behavior><dictionary>` block of `<entry name="...">` elements.

**A000FF** (the engine shared by Heroes of Hammerwatch, Hammerwatch II and the
Anniversary Edition; internally SSBD) uses a family of typed files where
behavior is a named class with typed properties, and animation is a set of
*scenes*.

### Extension map

| Hammerwatch | A000FF | Produced by |
|---|---|---|
| `<actor>`, `<projectile>`, `<doodad>`, `<item>` `.xml` | `.unit` | `UnitConverter` |
| `<tileset>` `.xml` | `.tileset` | `TilesetConverter` |
| `language/*.xml` `<dictionary>` | `.lang` | `StringConverter` |
| `<speech>` `.xml` | `.sval` | `SpeechStyleConverter` |
| `<font>` `.xml` | `.fnt` (AngelCode text, not XML) | `BitmapFontConverter` |
| `<soundbank>` `.xml` | `.sbnk` | `SoundbankConverter` |
| campaign `levels/*.xml` | `.lvl` | `LevelConverter` |
| a named sprite in a particle file | `.effect` | `EffectConverter` |
| `<gore>` `.xml` | `.sval` + a companion `.sval.unit` | `GoreConverter` |
| particle file | `.unit` | `ParticleConverter` |
| per-unit inline loot | `loot/<slot>.sval` | `LootConverter` |
| a level's `lighting` block | `env/<level>.env` | `LevelLoader.LoadLights` |

An asset reference may carry a `:entry` suffix selecting one item inside a file
(`sound/enemies.xml:gnaar-die`). Changing the extension must preserve it:
`sound/enemies.sbnk:gnaar-die`.

## Scale and coordinate constants

| Constant | Value | Where |
|---|---|---|
| World unit → pixels | `16` | everywhere |
| Level position | `u * 16 - 160` | `LevelConverter.ToPixels` |
| Unit layer | `defaultlayer - 20` | `UnitConverter.cs:41-51` |
| Tileset layer | `-1100 + level` | `TilesetConverter.cs` |
| Tile cell size | `16` px, forced | `TilesetConverter.cs` |
| Tilemap chunk | `20 × 20` tiles | `LevelLoader.cs:69` |
| A000FF tile cell | `512` px | `LevelConverter.cs` |
| Actor speed | `× 3.0` (`SPEED_ACTOR_MULT`) | `UnitConverter.cs:22` |
| Projectile speed | `× 4.0` (`SPEED_PROJECTILE_MULT`), except `behavior="spray"` | `UnitConverter.cs:23,796` |
| Light size | `range * 16 * 0.8` | `LevelObjects.cs:75` |

## Behavior → A000FF class

Read from the root element's `behavior` attribute; the values live in
`<behavior><dictionary>`. `neutral` and `spray` are ignored — some projectiles
use them and they carry no gameplay data.

| HWM behavior | A000FF class | Notes |
|---|---|---|
| `bomb` on `<item>` | `BombBehavior` | emits an `Explode` action |
| `bomb` on `<actor>` | `BombActorBehavior` | `EmptyMovement`; pulse scenes numbered |
| `checkpoint` | `HwCheckpoint` | forces sensor colliders on its polygons |
| `melee` | `CompositeActorBehavior` + `EnemyMeleeStrike` | melee reach hardcoded to 20 |
| `ranged`, `caster` | `CompositeActorBehavior` + `CompositeActorSkill` | fires `HwShootProjectile` |
| `spawner` | `CompositeActorBehavior` + `HwSpawnUnit` | `PassiveMovement`, `impenetrable` |
| `composite` | `CompositeActorBehavior` | skills come from `skills`/`pskills` |
| `tower-flower` | `TowerFlowerSkill` | also writes `actors/spikes/<name>_spike.unit` |
| `tower-nova` | `NovaSkill` | `proj-count` from `nova-parts` |
| `breakable` | `Breakable` | gore from `destroy-particle` |
| `food` `money` `key` `collectable` `mana` `life` `potion` `present` `upgrade` | `Pickup` | sensor colliders; `key` keeps its bounce |
| `door` | `Door` | |

`<item>` elements are slotted by behavior: the pickup list above becomes slot
`item`; `breakable`, `door`, `bomb` and `checkpoint` become slot `doodad`.

### Composite property remapping

Properties are copied through as `<type name="prop">value</type>` unless
special-cased (`UnitConverter.cs:254-473`):

- `*-snd` → soundbank reference (`.xml` → `.sbnk`, output prefix applied)
- `aggro-range`, `max-range` → `× 16 × range-scale`, **float in HWM, int in A000FF**
- `speed` → `× 3.0 × speed-scale`, moves into the `movement` dict
- `range` → `× 16 × range-scale`, moves into the skills array
- `hit-effect` → `hit-fx`, value converted by `EffectConverter`
- `gib` → `gore`, value converted by `GoreConverter`
- `loot` → `loot/<slot>.sval:<unit key>`, contents moved to the loot table
- `editor-range-marker`, `hp-bar` → dropped
- `dmg`, `corpse`, `frequency`, `spawns`, `spawn-range`, `projectile`, `seeker`,
  `movement`, `blink`, `skills`, `pskills`, `nova-parts`, `attack-*`, `dmg-*` →
  consumed into the movement/skills blocks rather than written directly

## Sprite and scene naming

A000FF names 8-way animations `<action>-<index>`. Hammerwatch names them
`<compass>-<action>`, so `east-attack` → `attack-0` and a bare `south` →
`idle-2`:

| east | southeast | south | southwest | west | northwest | north | northeast |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |

Projectiles number their sprites `0..n-1` and are rotated half a turn:
`idle-((i + n/2) mod n)` for n = 16, 8 or 4; a single sprite is always `idle-0`.
Projectile sprites whose name starts with `d` are hit effects and are skipped.

Every unit gets a shared scene `hwport_shared` holding collision, shadows and
lights, referenced by each animation scene via `<scene src="hwport_shared" />`.
The exception is `attack-effect`, which deliberately omits it. Units named
`editor_*` wrap their sprites in `%if EDITOR` / `%endif`.

Starting scene selection (`UnitConverter.cs:860-926`): the `states` element's
`default` attribute, else every `random-start="true"` sprite joined by spaces,
else a sprite literally named `default`, else `idle-0 … idle-7` for actors, else
`hwport_def`.

### Materials

`SpriteConverter.GetMaterial` picks a material from substrings of the unit name
— Hammerwatch's tile-piece naming convention. `_h_` → `proj-wall`; `_v_` →
`wall` unless `_v_cap_dn`; `_x_t_` → `wall` unless `_x_t_dn`; `deco_`, `_ivy_`,
`_chains_`, `vendor_` → `proj-prop`; `trap_spikes`, `trap_turret`, `marker`,
`floor` → `floor`. Behavior wins over name: `money` → `item-money`, `breakable`
→ `proj-prop`. Anything unmatched falls back to the slot name.

## World scripts

Node type comes from `<string name="type">`. Unsupported types load as
`UnknownScriptLink`.

| Hammerwatch | A000FF |
|---|---|
| `SpawnObject` | `SpawnUnit` |
| `LevelExitArea` | `LevelExit` |
| `Random` | `RandomCount` (`RandomChance` when `run-one` is false) |
| `ChangeDoodadState` | `SetUnitScene` |
| `DestroyObject` | `DestroyUnits` |
| `ToggleElement` | `ToggleScripts` |
| `ChangeDoodadLayer` | `SetUnitLayer` |
| `HideObject` | `HideUnit` |
| `CheckGlobalFlag` | `CheckFlag` |
| `PlayEffect` | `SpawnEffect` |
| `TogglePhysics` | `ToggleCollision` |

Re-expressed rather than renamed:

- `GlobalEventTrigger` with `LevelLoaded` → `ScriptLink` with execute-on-start.
  Every other global event is dropped.
- `ObjectEventTrigger` → `UnitDestroyedTrigger` (`Destroyed`) or
  `UnitDamagedTrigger` (`Hit`). Other events are dropped.
- `AnnounceText` with `type == 3` → `ShowFloatingText`. Types 0/1 set
  `AnchorY 0.2`; types 1/2 set the small system font.
- `RectangleShape` / `CircleShape` are not scripts at all — they become
  `:Physics_Rectangle` / `:Physics_Circle` collision units.
- A `LevelExit` with a `shape` parameter gets a generated `AreaTrigger`
  positioned 4 units to its right, wired to fire the exit.

`AreaTrigger` actor-type flags are remapped: HWM `1` Player → `2` PlayerActor,
`2` Enemy → `4` EnemyActor, `4` Allied → `2` PlayerActor, `8` Neutral → `1`
NeutralActor. `HideObject` and `ToggleImmortality` remap state `0 → 2` (show)
and `2 → 3` (toggle). `ProjectileShooter` directions `0,1,2,3` become
`270, 90, 180, 0` degrees, and `spread` converts degrees to radians.

Object ids are rewritten: Hammerwatch ids are collected as `OldUnitID`
placeholders and resolved to freshly allocated sequential A000FF ids in a pass
after everything is loaded (`LevelLoader.PrepareWriting`). Dynamic unit feeds
are prefixed `#` and emit a `LastSpawned` string after each entry.

## Lighting

`srgb_to_linear(f) = f/12.92 if f <= 0.04045 else ((f + 0.055)/1.055) ** 2.4`

Three different boosts are applied before the conversion, then the result is
scaled to 0-255 and clamped:

| Where | Boost |
|---|---|
| Unit lights (`UnitConverter.cs:1088`) | `× 1.45` |
| Level ambient (`LevelLoader.cs:219`) | `× 1.55` |
| Level point lights (`LevelObjects.cs:82`) | `× 0.5` |

Each Hammerwatch `<light>` emits **two** A000FF lights — the first `color1`/
`range` pair with alpha 0, the second with alpha 25. The colour attribute is
written as `r g b alpha g`; the repeated green is in the original's format
string and is preserved.

A level's environment file uses a directional light when `shadow-color` is not
`255 255 255 255`, and a flat ambient otherwise.

## Levels

The tilemap is repacked from Hammerwatch's 20×20 chunks into A000FF's
512-pixel cells (32×32 tiles at 16px). Tile indices are written as a flat
lowercase hex string, two characters per tile, `00` for empty.

Prefabs are imported after the main level is prepared: each placement re-loads
the prefab with its own loader, continues the id counter, and offsets every
unit, script and collision area by the placement position.

## Known gaps

Carried over from the original, all still unimplemented:

- `summon` and `nova` composite skills are skipped.
- Buffs are referenced but there is no buff converter; projectile buffs get a
  `<buff>` path that may not resolve.
- Particles convert, but nothing wires them to a `HwParticle` behavior with a
  ttl, or to a `HwProjectile` that emits for its lifetime — so `spew` skills
  have no visual trail.
- `checkpoint` items are slotted as doodads and want a behavior of their own.
- Melee and ranged attack sounds are hardcoded to `sound/enemies.sbnk:gnaar-melee`
  and `sound/enemies.sbnk:spider-melee`.
- `GoreConverter.ConvertParticle` only looks for a sprite literally named
  `breakable_wood`.
- Animation `transition` states are approximated; A000FF has no equivalent.
- In `GoreConverter.Convert` the first gib entry writes its `unit` path without
  the output prefix while later entries include it. This inconsistency is
  reproduced as-is, because there is no way to test which the game wants
  without the real assets. It only matters when a prefix is configured.

## Bugs found in the C# original

Fixed in this port; each is covered by a test.

| C# location | Problem |
|---|---|
| `FormMain.cs:204, 371, 387` | Three unguarded `Directory.GetFiles` calls. A missing `sound/` or `levels/` directory raises `IOException: The directory name is invalid` naming no path. |
| `FormMain.cs:165` | Refuses to run unless `Hammerwatch.exe` sits beside the assets folder, blocking generated campaigns. |
| `FormMain.cs:199` | The worker thread does not inherit the `InvariantCulture` set on the UI thread, so a comma-decimal locale corrupts every float. |
| `FormMain.cs:298` | Batch item conversion passes `""` as the unit name where single-unit conversion passes the real stem, so items alone lose material selection, wall offsets and the editor guard. |
| `UnitConverter.cs:131, 179, 520, 576, 821, 826` and the scaled `hp`/`dmg` fields | Raw floats written into `<int>` elements; any scale slider off 100% emits `<int name="dmg">112.5</int>`. |
| `UnitConverter.cs:1069` | Reads a light texture's size from the *output* copy, which does not exist when the asset was missing. |
| `UnitConverter.cs:1214` | `FindAttackLength` dereferences an absent `east-attack` sprite. |
| `LevelLoader.cs:211-217` | `ambient-color` is fetched with `?.` then indexed unconditionally. |
| `LevelLoader.cs:69` | `Debug.Assert(side == 20)` is stripped from release builds, so a malformed chunk silently corrupts the tilemap. |
| `LevelConverter.cs:110-112` | A bare `catch {}` silently drops tiles that fall outside the grid. |
| `SpewSkill.cs` | Writes `m_range` into the `rate` field. |
| `BitmapFontConverter.cs` | Mutates `page.Attributes["file"]` on a cached `XmlFile`, double-prefixing on a second run. |
| `XmlHelpers.cs` | `Dictionary.Add` throws on a repeated attribute name. |
| `XmlHelpers.cs` | `Debug.Assert(fs.Expect('>'))` is compiled out in release builds, so the closing `>` of a self-closing tag is never consumed and leaks into text nodes. |
| Static state across `XmlFile`, `LootConverter`, `EffectConverter`, `GoreConverter`, `ParticleConverter`, `SoundbankConverter`, `Program`, `TilesetConverter` | Leaks between runs; a second conversion in one process reuses stale caches and appends to already-filled loot tables. |
| Throughout | Warnings go to `Console.WriteLine`, invisible from a WinForms app — so "couldn't locate asset" was never seen. |

### The parser is not a standards-compliant XML parser

`Nimble.XML` is hand-rolled and the converters depend on its behaviour. Two
consequences worth remembering:

- Text nodes are trimmed of `\r`, `\n` and `\t` but **not spaces**, so indented
  XML produces whitespace text nodes. Anywhere the original indexes
  `Children[0]` it can land on whitespace instead of the element — which breaks
  on pretty-printed input such as a generated map. This port uses
  `first_element()` throughout.
- Attribute values are HTML-decoded; element text is not.

Do not swap in `xml.etree`: it would change how values concatenate, how
duplicate attributes behave, and what `.Value` contains for mixed content.
