"""Loot tables → ``loot/<slot>.sval`` — port of ``xml2unit/LootConverter.cs``.

Hammerwatch defines loot inline on each unit; A000FF wants one file per slot
with a named array per unit, referenced as ``loot/<slot>.sval:<unit key>``.
Entries accumulate across the whole run and are flushed at the end.
"""

from __future__ import annotations

from ..context import ConversionContext, LootEntry
from ..fmt import Writer, fmt_int


def add(ctx: ConversionContext, chance: int, unit: str) -> None:
    ctx.loot_current.append((chance, unit))


def end_set(ctx: ConversionContext, slot: str, name: str) -> None:
    """Close the current drop list and attach it to ``slot``/``name``."""
    entry = ctx.loot.setdefault(slot, {}).setdefault(name, LootEntry())
    entry.sets.append(ctx.loot_current)
    ctx.loot_current = []


def end(ctx: ConversionContext, slot: str, name: str, spread: float, origin: tuple[int, int]) -> None:
    entry = ctx.loot.setdefault(slot, {}).setdefault(name, LootEntry())
    entry.spread = spread
    entry.origin = origin


def slots(ctx: ConversionContext) -> list[str]:
    return list(ctx.loot)


def convert(ctx: ConversionContext, slot: str, writer: Writer) -> None:
    prefix = ctx.settings.output_prefix
    writer.line("<dict>")
    for name, entry in ctx.loot[slot].items():
        writer.line(f'  <array name="{prefix}{name}">')
        writer.line(
            f"    <vec2>{fmt_int(entry.origin[0] * 16.0)} "
            f"{fmt_int(-entry.origin[1] * 16.0)}</vec2> <!-- Offset -->"
        )
        spread = fmt_int(entry.spread * 16.0)
        writer.line(f"    <vec2>{spread} {spread}</vec2> <!-- Spread -->")
        for drop_set in entry.sets:
            writer.line("    <array>")
            for chance, unit in drop_set:
                writer.line(f"      <int>{chance}</int><string>{prefix}{unit}</string>")
            writer.line("    </array>")
        writer.line("  </array>")
    writer.line("</dict>")
