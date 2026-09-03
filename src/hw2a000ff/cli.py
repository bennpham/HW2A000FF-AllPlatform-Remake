"""Command line interface.

Every control on the original's tabbed WinForms window has a flag here, and the
same settings can live in a TOML file so a campaign can carry its own recipe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import ConversionError
from .pipeline import convert_all, convert_single_unit, preflight
from .settings import STAGE_ALIASES, STAGES, Settings, SettingsError

EXAMPLE_CONFIG = """\
# hw2a000ff configuration.
# Relative paths resolve against this file's directory.

[paths]
# Assets to convert. For a scenario this is the scenario's own assets folder.
source = "Hammerwatch/assets"
# Base game assets, used to fill in anything the scenario does not override.
# Leave unset when converting the base game itself.
# fallback = "Hammerwatch/assets"
# Campaign levels index. Levels are read from the "levels" folder beside it.
# levels_xml = "Hammerwatch/assets_campaign/campaign/levels.xml"
output = "out"
# Prepended to every asset reference written into the output.
prefix = ""

[convert]
actors = true
projectiles = true
doodads = true
tilesets = true
items = true
strings = true
speech_styles = true
fonts = true
loot = true
levels = true
sounds = true

[scales]
# 1.0 is the original tool's 100% slider position.
health = 1.0
range = 1.0
damage = 1.0
speed = 1.0

[sprites]
modify_wall_collision = false

[strings]
key_prefix = "hwport."

[options]
# Refuse to run unless Hammerwatch.exe sits beside the assets folder.
require_game_install = false
# "lf" or "crlf"; crlf reproduces the original Windows tool's output bytes.
line_endings = "lf"
"""


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, metavar="FILE", help="read settings from a TOML file")
    parser.add_argument("--source", type=Path, metavar="DIR", help="assets folder to convert")
    parser.add_argument(
        "--fallback", type=Path, metavar="DIR", help="base game assets to fall back on"
    )
    parser.add_argument(
        "--levels-xml", type=Path, metavar="PATH", help="campaign levels.xml to convert levels from"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hw2a000ff",
        description="Convert Hammerwatch (HWM) assets to the A000FF format used by "
        "Heroes of Hammerwatch, Hammerwatch II and the Anniversary Edition.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser("convert", help="convert a whole assets tree")
    _add_common(convert)
    convert.add_argument("--output", type=Path, metavar="DIR", help="where to write the result")
    convert.add_argument(
        "--prefix", metavar="STR", help="prepended to every asset reference in the output"
    )
    convert.add_argument(
        "--strings-prefix", metavar="STR", help="key prefix for converted strings (default hwport.)"
    )
    convert.add_argument(
        "--only",
        metavar="LIST",
        help=f"convert only these stages: {', '.join(STAGE_ALIASES)}",
    )
    convert.add_argument("--skip", metavar="LIST", help="convert everything except these stages")
    for name in ("health", "range", "damage", "speed"):
        convert.add_argument(
            f"--{name}-scale", type=float, metavar="N", help=f"{name} multiplier (default 1.0)"
        )
    convert.add_argument(
        "--modify-wall-collision", action="store_true", default=None,
        help="flatten the lower edge of wall pieces",
    )
    convert.add_argument(
        "--require-game-install", action="store_true", default=None,
        help="refuse to run unless Hammerwatch.exe sits beside the assets folder",
    )
    convert.add_argument(
        "--line-endings", choices=("lf", "crlf"), help="line endings for converted files"
    )
    convert.add_argument(
        "--dry-run", action="store_true", help="check the inputs and report, without writing"
    )
    convert.add_argument("-v", "--verbose", action="store_true", help="print each file as it converts")
    convert.add_argument("-q", "--quiet", action="store_true", help="only report errors")

    single = subparsers.add_parser("convert-unit", help="convert a single unit .xml to a .unit")
    single.add_argument("input", type=Path)
    single.add_argument("output", type=Path)
    single.add_argument("--prefix", metavar="STR", default="")
    single.add_argument("--config", type=Path, metavar="FILE")

    doctor = subparsers.add_parser(
        "doctor", help="check paths and report what would be converted or skipped"
    )
    _add_common(doctor)
    doctor.add_argument("--output", type=Path, metavar="DIR")

    subparsers.add_parser("init-config", help="print a commented starter config to stdout")

    return parser


def _settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings.from_toml(args.config) if getattr(args, "config", None) else Settings()

    for attr, field in (
        ("source", "source_path"),
        ("fallback", "source_fallback_path"),
        ("levels_xml", "levels_path"),
        ("output", "output_path"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(settings, field, Path(value).expanduser().resolve())

    if getattr(args, "prefix", None) is not None:
        settings.output_prefix = args.prefix
    if getattr(args, "strings_prefix", None) is not None:
        settings.strings_key_prefix = args.strings_prefix
    for name in ("health", "range", "damage", "speed"):
        value = getattr(args, f"{name}_scale", None)
        if value is not None:
            setattr(settings, f"{name}_scale", value)
    if getattr(args, "modify_wall_collision", None):
        settings.modify_wall_collision = True
    if getattr(args, "require_game_install", None):
        settings.require_game_install = True
    if getattr(args, "line_endings", None):
        settings.line_endings = "\r\n" if args.line_endings == "crlf" else "\n"

    only = getattr(args, "only", None)
    skip = getattr(args, "skip", None)
    if only and skip:
        raise SettingsError("--only and --skip cannot be used together")
    if only:
        settings.stages = _parse_stages(only)
    elif skip:
        settings.stages = settings.stages - _parse_stages(skip)

    return settings


def _parse_stages(raw: str) -> set[str]:
    out = set()
    for token in raw.replace(",", " ").split():
        stage = STAGE_ALIASES.get(token.strip().lower().replace("_", "-"))
        if stage is None:
            raise SettingsError(
                f"unknown stage '{token}'; expected any of {', '.join(STAGE_ALIASES)}"
            )
        out.add(stage)
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init-config":
        sys.stdout.write(EXAMPLE_CONFIG)
        return 0

    try:
        if args.command == "convert-unit":
            settings = _settings_from_args(args)
            settings.output_prefix = args.prefix
            slot = convert_single_unit(
                settings,
                args.input,
                args.output,
                on_warning=lambda m: print(f"warning: {m}", file=sys.stderr),
            )
            print(f"Converted {args.input} to {args.output} (slot: {slot})")
            return 0

        settings = _settings_from_args(args)

        if args.command == "doctor":
            notes = preflight(settings, require_output=False)
            print(f"source:   {settings.source_path}")
            print(f"fallback: {settings.source_fallback_path or '(none)'}")
            print(f"levels:   {settings.levels_path or '(none)'}")
            print(f"output:   {settings.output_path or '(none)'}")
            print(f"stages:   {', '.join(sorted(settings.stages))}")
            if notes:
                print()
                for note in notes:
                    print(f"  note: {note}")
            else:
                print("\n  Everything checks out.")
            return 0

        quiet = getattr(args, "quiet", False)
        verbose = getattr(args, "verbose", False)
        report = convert_all(
            settings,
            on_status=(lambda m: print(m)) if verbose else None,
            on_warning=(lambda m: print(f"warning: {m}", file=sys.stderr)) if not quiet else None,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print("Dry run — nothing was written.")
            for note in report.skipped_stages:
                print(f"  note: {note}")
            return 0
        if not quiet:
            for note in report.skipped_stages:
                print(f"note: {note}")
            print(report.summary())
        return 0

    except (ConversionError, SettingsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
