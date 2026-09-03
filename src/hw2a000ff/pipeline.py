"""The batch conversion — port of ``FormMain.buttonConvert_Click``.

The original runs this on a worker thread behind a modal progress window and
reports failures by dumping a .NET stack trace into a message box. Here the
inputs are checked before any work starts, each stage names the directory it
needs, and the run finishes with a report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from .context import ConversionContext
from .errors import ConversionError, MissingDirectoryError
from .nimble import XmlFile
from .paths import change_extension, dirname, stem
from .converters import bitmap_font, level, loot, soundbank, speech_style, strings, tileset, unit
from .settings import Settings


@dataclass
class Report:
    """What a conversion produced."""

    file_count: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing_assets: list[str] = field(default_factory=list)
    skipped_stages: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Converted {self.file_count} file(s) in {self.seconds:.3f} seconds.",
        ]
        if self.counts:
            lines.append("")
            for kind, count in sorted(self.counts.items()):
                lines.append(f"  {kind:<14} {count}")
        if self.skipped_stages:
            lines.append("")
            for note in self.skipped_stages:
                lines.append(f"  skipped: {note}")
        if self.missing_assets:
            lines.append("")
            lines.append(f"  {len(self.missing_assets)} referenced asset(s) could not be found")
        if self.warnings:
            lines.append(f"  {len(self.warnings)} warning(s)")
        return "\n".join(lines)


def _require_directory(path: Path, what: str, hint: str) -> None:
    if path.is_dir():
        return
    if path.exists():
        raise MissingDirectoryError(f"{what} is not a directory", path=path, hint=hint)
    raise MissingDirectoryError(f"{what} does not exist", path=path, hint=hint)


def preflight(settings: Settings, *, require_output: bool = True) -> list[str]:
    """Check everything the conversion will need. Returns advisory notes.

    Anything that would abort the run raises; anything that merely disables a
    stage comes back as a note. This is what the ``doctor`` command runs, and
    what the crash in the original tool needed.
    """
    settings.validate(require_output=require_output)
    notes: list[str] = []
    assert settings.source_path is not None

    _require_directory(
        settings.source_path,
        "source path",
        "point --source at the assets folder containing the .xml files to convert",
    )

    if not settings.game_install_present():
        base = settings.source_fallback_path or settings.source_path
        message = (
            f"Hammerwatch.exe was not found in {base.parent}. "
            "That is expected for a generated campaign or an extracted asset dump."
        )
        if settings.require_game_install:
            raise ConversionError(
                "no Hammerwatch install found next to the assets folder",
                path=base.parent,
                hint="drop --require-game-install to convert anyway",
            )
        notes.append(message)

    if settings.enabled("sounds"):
        sound_dir = settings.source_path / "sound"
        if not sound_dir.is_dir():
            notes.append(
                f"no 'sound' directory under {settings.source_path}; skipping soundbanks"
            )

    if settings.enabled("levels"):
        if settings.levels_path is None:
            notes.append("no --levels-xml given; skipping levels")
        else:
            levels_dir = settings.levels_path.parent / "levels"
            if not levels_dir.is_dir():
                notes.append(
                    f"no 'levels' directory beside {settings.levels_path.name}; skipping levels"
                )

    return notes


def convert_all(
    settings: Settings,
    *,
    on_status=None,
    on_warning=None,
    dry_run: bool = False,
) -> Report:
    notes = preflight(settings)
    ctx = ConversionContext(settings, on_status=on_status, on_warning=on_warning)
    report = Report(skipped_stages=list(notes))

    if dry_run:
        return report

    assert settings.source_path is not None and settings.output_path is not None
    settings.output_path.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    _convert_assets(ctx)
    _convert_loot(ctx)
    _convert_levels(ctx, report)
    _convert_sounds(ctx, report)
    report.seconds = time.monotonic() - started

    report.file_count = ctx.file_count
    report.counts = dict(ctx.counts)
    report.warnings = list(ctx.warnings)
    report.missing_assets = sorted(ctx.missing_assets)
    return report


# --------------------------------------------------------------------- stages


def _source_xml_files(ctx: ConversionContext) -> list[tuple[Path, str]]:
    root = ctx.settings.source_path
    assert root is not None
    return sorted(
        (path, path.relative_to(root).as_posix())
        for path in root.rglob("*.xml")
        if path.is_file()
    )


def _convert_assets(ctx: ConversionContext) -> None:
    settings = ctx.settings

    for path, relative in _source_xml_files(ctx):
        try:
            xml = ctx.load_xml(path)
            root = xml.document_element
        except (ConversionError, ValueError) as exc:
            ctx.warn(f"{relative}: {exc}; skipped")
            continue

        directory = dirname(relative)

        if settings.enabled("actors") and root.name == "actor":
            _write_unit(ctx, xml, relative, directory, "actor", "Actor")

        elif settings.enabled("projectiles") and root.name == "projectile":
            _write_unit(ctx, xml, relative, directory, "projectile", "Projectile")

        elif settings.enabled("doodads") and root.name == "doodad":
            _write_unit(ctx, xml, relative, directory, "doodad", "Doodad")

        elif settings.enabled("tilesets") and root.name == "tileset":
            target = change_extension(relative, "tileset")
            ctx.status(f"Tileset: {target}")
            ctx.count("tileset")
            ctx.prepare(directory, target)
            with ctx.open_output(target) as writer:
                tileset.convert(ctx, xml, writer)

        elif settings.enabled("items") and root.name == "item":
            slot = unit.slot_for_root(ctx, root)
            if slot is None:
                continue
            _write_unit(ctx, xml, relative, directory, slot, "Item")

        elif (
            settings.enabled("strings")
            and relative.startswith("language/")
            and root.name == "dictionary"
        ):
            target = change_extension(relative, "lang")
            ctx.status(f"Strings: {target}")
            ctx.count("lang")
            ctx.prepare(directory, target)
            with ctx.open_output(target) as writer:
                strings.convert(ctx, xml, writer)

        elif settings.enabled("speech_styles") and root.name == "speech":
            target = change_extension(relative, "sval")
            ctx.status(f"Speech style: {target}")
            ctx.count("speech style")
            ctx.prepare(directory, target)
            with ctx.open_output(target) as writer:
                speech_style.convert(ctx, xml, writer)

        elif settings.enabled("fonts") and root.name == "font":
            target = change_extension(relative, "fnt")
            ctx.status(f"Font: {target}")
            ctx.count("font")
            ctx.prepare(directory, target)
            with ctx.open_output(target) as writer:
                bitmap_font.convert(ctx, xml, writer)


def _write_unit(
    ctx: ConversionContext,
    xml: XmlFile,
    relative: str,
    directory: str,
    slot: str,
    label: str,
) -> None:
    target = change_extension(relative, "unit")
    ctx.status(f"{label}: {target}")
    ctx.count(label.lower())
    ctx.prepare(directory, target)
    # The original passes "" as the unit name for items, so items alone missed
    # out on material selection, wall offsets and the editor-only guard.
    with ctx.open_output(target) as writer:
        unit.convert(ctx, xml, writer, slot, stem(target), target)


def _convert_loot(ctx: ConversionContext) -> None:
    if not ctx.settings.enabled("loot"):
        return
    if ctx.file_count == 0:
        ctx.warn("no units were converted, so there is no loot to convert")
        return
    for slot in loot.slots(ctx):
        target = f"loot/{slot}.sval"
        ctx.status(f"Loot: {target}")
        ctx.count("loot table")
        ctx.prepare("loot", target)
        with ctx.open_output(target) as writer:
            loot.convert(ctx, slot, writer)


def _convert_levels(ctx: ConversionContext, report: Report) -> None:
    settings = ctx.settings
    if not settings.enabled("levels") or settings.levels_path is None:
        return

    levels_root = settings.levels_path.parent
    levels_dir = levels_root / "levels"
    if not levels_dir.is_dir():
        # This is one of the three unguarded Directory.GetFiles calls that make
        # the original die with "The directory name is invalid".
        return

    levels_xml = ctx.load_xml(settings.levels_path)
    for entry in levels_xml.root.find_tags_by_name("level"):
        level_id = entry.attributes.get("id")
        res = entry.attributes.get("res")
        if level_id is None or res is None:
            ctx.warn("a <level> entry in levels.xml has no id/res; ignored")
            continue
        ctx.level_keys[level_id] = change_extension(res, "lvl")

    for path in sorted(levels_dir.rglob("*.xml")):
        if not path.is_file():
            continue
        relative = change_extension(path.relative_to(levels_dir).as_posix(), "lvl")
        target = f"levels/{relative}"
        ctx.status(f"Level: {relative}")
        ctx.count("level")
        ctx.prepare(f"levels/{dirname(relative)}", target)
        try:
            with ctx.open_output(target) as writer:
                level.convert(ctx, ctx.load_xml(path), writer, relative)
        except ConversionError as exc:
            ctx.warn(f"level '{relative}' could not be converted: {exc}")


def _convert_sounds(ctx: ConversionContext, report: Report) -> None:
    settings = ctx.settings
    if not settings.enabled("sounds"):
        return
    assert settings.source_path is not None

    sound_dir = settings.source_path / "sound"
    if not sound_dir.is_dir():
        # The second of the three unguarded Directory.GetFiles calls.
        return

    for path in sorted(sound_dir.rglob("*.xml")):
        if not path.is_file():
            continue
        xml = ctx.load_xml(path)
        try:
            root = xml.document_element
        except ValueError:
            continue
        if root.name != "soundbank":
            continue

        relative = path.relative_to(settings.source_path).as_posix()
        target = change_extension(relative, "sbnk")
        ctx.status(f"Soundbank: {target}")
        ctx.count("soundbank")
        ctx.prepare(dirname(target), target)
        with ctx.open_output(target) as writer:
            soundbank.convert(ctx, xml, writer, stem(target))


# ------------------------------------------------------------- single unit


def convert_single_unit(
    settings: Settings, source: Path, destination: Path, *, on_warning=None
) -> str:
    """Convert one unit file — the original's "Convert single unit" button."""
    # Converting one file needs no project layout: default the asset roots to
    # the input and output files' own directories so referenced effects, gore
    # and spike units still land somewhere sensible.
    if settings.source_path is None:
        settings = replace(settings, source_path=source.parent)
    if settings.output_path is None:
        settings = replace(settings, output_path=destination.parent)

    ctx = ConversionContext(settings, on_warning=on_warning)
    xml = XmlFile.from_file(source, warn=lambda m: ctx.warn(f"{source}: {m}"))
    try:
        root = xml.document_element
    except ValueError as exc:
        raise ConversionError("the file has no root element", path=source) from exc

    slot = unit.slot_for_root(ctx, root)
    if slot is None:
        raise ConversionError(
            f"unsupported unit type '{root.name}'",
            path=source,
            hint="supported roots are actor, projectile, doodad and item",
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        from .fmt import Writer

        unit.convert(
            ctx, xml, Writer(handle, settings.line_endings), slot, destination.stem, destination.name
        )
    for warning in ctx.warnings:
        if on_warning:
            on_warning(warning)
    return slot
