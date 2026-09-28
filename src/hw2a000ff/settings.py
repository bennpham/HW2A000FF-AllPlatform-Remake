"""Conversion settings — port of ``Settings.cs`` plus the WinForms controls.

Every option maps to a control on the original's tabbed window. The four scale
values were sliders reading ``Value / 100.0f`` (``FormMain.cs:188-191``), so
they are plain multipliers here: ``1.0`` is the original 100%.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

#: Converter stages, in the order the original's checkbox list presents them.
STAGES: tuple[str, ...] = (
    "actors",
    "projectiles",
    "doodads",
    "tilesets",
    "items",
    "strings",
    "speech_styles",
    "fonts",
    "loot",
    "levels",
    "sounds",
)

#: Accepted on the command line; hyphens read better than underscores there.
STAGE_ALIASES = {s.replace("_", "-"): s for s in STAGES}


class SettingsError(ValueError):
    """Raised for a configuration the converter cannot run with."""


@dataclass
class Settings:
    # --- paths -------------------------------------------------------------
    source_path: Path | None = None
    source_fallback_path: Path | None = None
    levels_path: Path | None = None
    output_path: Path | None = None
    output_prefix: str = ""
    #: Materials file every sprite and tileset points at. Empty means the
    #: original's ``<prefix>system/hammerwatch.mats``, which Heroes of
    #: Hammerwatch ships; the Anniversary Edition has only
    #: ``system/default.mats`` (with the same material names). Used verbatim.
    materials_path: str = ""

    # --- stages ------------------------------------------------------------
    stages: set[str] = field(default_factory=lambda: set(STAGES))

    # --- balance scales (1.0 == the original's 100% slider) ----------------
    health_scale: float = 1.0
    range_scale: float = 1.0
    damage_scale: float = 1.0
    speed_scale: float = 1.0

    # --- sprites -----------------------------------------------------------
    modify_wall_collision: bool = False

    # --- strings -----------------------------------------------------------
    strings_key_prefix: str = "hwport."

    # --- behaviour not present in the original -----------------------------
    #: The original refuses to start unless ``Hammerwatch.exe`` sits in the
    #: parent of the source or fallback path (``FormMain.cs:165``). That check
    #: blocks perfectly valid input -- a generated campaign, an extracted asset
    #: dump -- so it is a warning here unless explicitly demanded.
    require_game_install: bool = False
    #: ``\r\n`` reproduces the byte-for-byte output of a Windows run.
    line_endings: str = "\n"

    # ------------------------------------------------------------------ misc

    def enabled(self, stage: str) -> bool:
        return stage in self.stages

    def material(self, name: str) -> str:
        """Reference to material ``name`` in the configured materials file."""
        mats = self.materials_path or f"{self.output_prefix}system/hammerwatch.mats"
        return f"{mats}:{name}"

    def validate(self, require_output: bool = True) -> None:
        if self.source_path is None:
            raise SettingsError("no source path given (--source)")
        if require_output and self.output_path is None:
            raise SettingsError("no output path given (--output)")
        if not self.source_path.exists():
            raise SettingsError(f"source path does not exist: {self.source_path}")
        if not self.source_path.is_dir():
            raise SettingsError(
                f"source path is not a directory: {self.source_path}\n"
                "  --source must be the assets folder itself, not a file inside it."
            )
        if self.source_fallback_path is not None:
            if not self.source_fallback_path.is_dir():
                raise SettingsError(
                    f"fallback path is not a directory: {self.source_fallback_path}"
                )
        if self.levels_path is not None:
            if self.levels_path.name != "levels.xml":
                raise SettingsError(
                    f"--levels-xml must point at a file named levels.xml, got: {self.levels_path}"
                )
            if not self.levels_path.is_file():
                raise SettingsError(f"levels.xml does not exist: {self.levels_path}")
        for name in ("health_scale", "range_scale", "damage_scale", "speed_scale"):
            if getattr(self, name) <= 0:
                raise SettingsError(f"{name.replace('_', '-')} must be greater than zero")
        if self.line_endings not in ("\n", "\r\n"):
            raise SettingsError("line_endings must be 'lf' or 'crlf'")

    def game_install_present(self) -> bool:
        """Does ``Hammerwatch.exe`` sit beside the assets folder?"""
        base = self.source_fallback_path or self.source_path
        if base is None:
            return False
        return (base.parent / "Hammerwatch.exe").is_file()

    # ------------------------------------------------------------- from file

    @classmethod
    def from_toml(cls, path: Path) -> "Settings":
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        return cls.from_mapping(data, base_dir=path.parent)

    @classmethod
    def from_mapping(cls, data: dict, base_dir: Path | None = None) -> "Settings":
        """Build settings from a parsed config file.

        Relative paths resolve against the config file's own directory, so a
        config checked in next to a campaign keeps working wherever it is run.
        """
        known = {f.name for f in fields(cls)}
        settings = cls()

        def resolve(value: str) -> Path:
            p = Path(value).expanduser()
            if not p.is_absolute() and base_dir is not None:
                p = (base_dir / p).resolve()
            return p

        paths = data.get("paths", {})
        for key, attr in (
            ("source", "source_path"),
            ("fallback", "source_fallback_path"),
            ("levels_xml", "levels_path"),
            ("output", "output_path"),
        ):
            if key in paths:
                setattr(settings, attr, resolve(str(paths[key])))
        if "prefix" in paths:
            settings.output_prefix = str(paths["prefix"])
        if "materials" in paths:
            settings.materials_path = str(paths["materials"])

        if "convert" in data:
            convert = data["convert"]
            enabled = set()
            for stage in STAGES:
                if convert.get(stage, True):
                    enabled.add(stage)
            settings.stages = enabled

        scales = data.get("scales", {})
        for key in ("health", "range", "damage", "speed"):
            if key in scales:
                setattr(settings, f"{key}_scale", float(scales[key]))

        sprites = data.get("sprites", {})
        if "modify_wall_collision" in sprites:
            settings.modify_wall_collision = bool(sprites["modify_wall_collision"])

        strings = data.get("strings", {})
        if "key_prefix" in strings:
            settings.strings_key_prefix = str(strings["key_prefix"])

        options = data.get("options", {})
        if "require_game_install" in options:
            settings.require_game_install = bool(options["require_game_install"])
        if "line_endings" in options:
            value = str(options["line_endings"]).lower()
            settings.line_endings = "\r\n" if value == "crlf" else "\n"

        unknown = set(data) - {"paths", "convert", "scales", "sprites", "strings", "options"}
        if unknown:
            raise SettingsError(
                f"unknown config section(s): {', '.join(sorted(unknown))}; "
                f"expected any of paths, convert, scales, sprites, strings, options"
            )
        assert known  # keeps the dataclass field list honest against renames
        return settings
