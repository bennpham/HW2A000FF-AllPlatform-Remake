"""Composite-actor skills — port of ``xml2unit/UnitSkills/*.cs``."""

from __future__ import annotations

from dataclasses import dataclass

from ..context import ConversionContext
from ..fmt import Writer, fmt_float, fmt_int
from ..paths import change_extension
from . import particle as particle_converter


@dataclass
class UnitSkill:
    do_snd: str = ""

    def write(self, ctx: ConversionContext, writer: Writer) -> None:  # pragma: no cover
        raise NotImplementedError


@dataclass
class BlinkSkill(UnitSkill):
    cooldown: int = 0
    range: float = 0.0
    distance: float = 0.0
    sound: str = ""
    fx: str = ""

    def write(self, ctx: ConversionContext, writer: Writer) -> None:
        prefix = ctx.settings.output_prefix
        writer.line("      <dict>")
        writer.line('        <string name="class">BlinkSkill</string>')
        writer.line(f'        <int name="cooldown">{self.cooldown}</int>')
        writer.line(f'        <int name="range">{fmt_int(self.range)}</int>')
        writer.line(f'        <float name="distance">{fmt_float(self.distance)}</float>')
        if self.sound:
            writer.line(
                f'        <string name="snd">{prefix}{change_extension(self.sound, "sbnk")}</string>'
            )
        if self.fx:
            produced = particle_converter.convert(ctx, self.fx)
            writer.line(f'        <string name="fx-producer">{prefix}{produced}</string>')
            writer.line(f'        <string name="fx-name">{self.fx.split(":")[-1]}</string>')
        writer.line("      </dict>")


@dataclass
class StrikeSkill(UnitSkill):
    anim: str = ""
    cooldown: int = 0
    range: float = 0.0
    damage: int = 0

    def write(self, ctx: ConversionContext, writer: Writer) -> None:
        writer.line("      <dict>")
        writer.line('        <string name="class">EnemyMeleeStrike</string>')
        writer.line()
        writer.line(f'        <string name="anim">{self.anim} 8</string>')
        if self.do_snd:
            writer.line(
                f'        <string name="snd">{ctx.settings.output_prefix}{self.do_snd}</string>'
            )
        writer.line()
        writer.line(f'        <int name="cooldown">{self.cooldown}</int>')
        writer.line(f'        <int name="range">{fmt_int(self.range)}</int>')
        writer.line('        <dict name="effect">')
        writer.line('          <string name="class">Damage</string>')
        writer.line(
            f'          <int name="dmg">{fmt_int(self.damage * ctx.settings.damage_scale)}</int>'
        )
        writer.line('          <string name="dmg-type">pierce</string>')
        writer.line("        </dict>")
        writer.line("      </dict>")


@dataclass
class SpewSkill(UnitSkill):
    anim: str = ""
    range: float = 0.0
    duration: int = 0
    cooldown: int = 0
    projectile: str = ""
    spread: float = 0.0
    rate: int = 0

    def write(self, ctx: ConversionContext, writer: Writer) -> None:
        prefix = ctx.settings.output_prefix
        writer.line("      <dict>")
        writer.line('        <string name="class">SpewSkill</string>')
        writer.line(f'        <string name="anim">{self.anim} 8</string>')
        writer.line(f'        <int name="range">{fmt_int(self.range)}</int>')
        writer.line(f'        <int name="cooldown">{self.cooldown}</int>')
        writer.line(f'        <int name="duration">{self.duration}</int>')
        writer.line(
            f'        <string name="projectile">'
            f'{prefix}{change_extension(self.projectile, "unit")}</string>'
        )
        writer.line(f'        <float name="spread">{fmt_float(self.spread)}</float>')
        # The original writes m_range into this field, so every spewing enemy
        # inherited its attack range as its fire rate.
        writer.line(f'        <int name="rate">{self.rate}</int>')
        writer.line("      </dict>")
