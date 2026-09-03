"""Per-run conversion state.

The C# original keeps every one of these on a ``static`` field --
``XmlFile.m_fileCache``, ``LootConverter.m_definitions``/``m_currList``,
``{Effect,Gore,Particle}Converter.m_converted``,
``SoundbankConverter.s_dicSoundMetadata``, ``Program.LevelKeys``,
``TilesetConverter.m_size`` and the whole of ``Settings``. Converting twice in
one process therefore reuses stale caches and appends to loot tables that were
never cleared. Holding it all on a context object fixes that, and is what makes
this package safe to import from another program (a map generator, a test) and
call more than once.
"""

from __future__ import annotations

import shutil
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Callable, Iterator

from .errors import ConversionError
from .fmt import Writer
from .imaging import copy_png_as_32bpp
from .nimble import XmlFile
from .settings import Settings


@dataclass
class SoundMetadata:
    """``SoundbankConverter.SoundMetadata`` — learned from PlaySound scripts."""

    is_2d: bool = False
    looping: bool = False


class ConversionContext:
    def __init__(
        self,
        settings: Settings,
        *,
        on_status: Callable[[str], None] | None = None,
        on_warning: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self._on_status = on_status
        self._on_warning = on_warning

        # Caches that were static in the original.
        self._xml_cache: dict[Path, XmlFile] = {}
        self.converted_effects: set[str] = set()
        self.converted_gore: set[str] = set()
        self.converted_particles: set[str] = set()
        self.sound_metadata: dict[str, SoundMetadata] = {}
        self.level_keys: dict[str, str] = {}

        # Loot accumulates across every unit and is flushed at the end of a run.
        self.loot: dict[str, dict[str, "LootEntry"]] = {}
        self.loot_current: list[tuple[int, str]] = []

        # Reporting.
        self.warnings: list[str] = []
        self.counts: Counter[str] = Counter()
        self.missing_assets: set[str] = set()
        self.file_count = 0

    # ----------------------------------------------------------- diagnostics

    def status(self, message: str) -> None:
        self._on_status(message) if self._on_status else None

    def warn(self, message: str) -> None:
        """Record a warning.

        The original writes these to ``Console.WriteLine``, which a WinForms
        application never shows -- so every "couldn't locate asset" and
        "unsupported behavior" went straight to a console nobody was watching.
        """
        self.warnings.append(message)
        if self._on_warning:
            self._on_warning(message)

    def count(self, kind: str) -> None:
        self.counts[kind] += 1
        self.file_count += 1

    # -------------------------------------------------------------- XML I/O

    def load_xml(self, path: Path) -> XmlFile:
        """``XmlFile.FromFile`` with its cache scoped to this run."""
        path = Path(path)
        cached = self._xml_cache.get(path)
        if cached is not None:
            return cached
        try:
            xml = XmlFile.from_file(path, warn=lambda m: self.warn(f"{path}: {m}"))
        except FileNotFoundError as exc:
            raise ConversionError("XML file not found", path=path) from exc
        self._xml_cache[path] = xml
        return xml

    # ------------------------------------------------------------ resolution

    def resolve_source(self, relative: str) -> Path | None:
        """Find an asset under the source path, then the fallback path.

        Mirrors the lookup in ``Program.CopyAsset``: the scenario's own assets
        win, and the base game assets fill the gaps.
        """
        relative = relative.replace("\\", "/").lstrip("/")
        if self.settings.source_path is not None:
            candidate = self.settings.source_path / relative
            if candidate.is_file():
                return candidate
        if self.settings.source_fallback_path is not None:
            candidate = self.settings.source_fallback_path / relative
            if candidate.is_file():
                return candidate
        return None

    def output_file(self, relative: str) -> Path:
        if self.settings.output_path is None:
            raise ConversionError("no output path is configured")
        return self.settings.output_path / relative.replace("\\", "/").lstrip("/")

    # --------------------------------------------------------------- writing

    def prepare(self, directory: str | None, filename: str) -> None:
        """``Program.Prepare`` — make the output directory, drop a stale file."""
        if self.settings.output_path is None:
            raise ConversionError("no output path is configured")
        if directory:
            (self.settings.output_path / directory.replace("\\", "/")).mkdir(
                parents=True, exist_ok=True
            )
        target = self.output_file(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()

    @contextmanager
    def open_output(self, relative: str) -> Iterator[Writer]:
        """Open a converted asset for writing and hand back a ``Writer``."""
        target = self.output_file(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle: IO[str] = target.open("w", encoding="utf-8", newline="")
        try:
            yield Writer(handle, self.settings.line_endings)
        finally:
            handle.close()

    def copy_asset(self, relative: str) -> None:
        """``Program.CopyAsset`` — copy a referenced asset into the output."""
        if not relative:
            return
        relative = relative.replace("\\", "/").lstrip("/")
        destination = self.output_file(relative)
        if destination.exists():
            return

        source = self.resolve_source(relative)
        if source is None:
            if relative not in self.missing_assets:
                self.missing_assets.add(relative)
                self.warn(f"couldn't locate asset '{relative}'")
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".png":
            note = copy_png_as_32bpp(source, destination)
            if note:
                self.warn(note)
        else:
            shutil.copyfile(source, destination)

    # ------------------------------------------------------------------ misc

    def prefixed(self, relative: str) -> str:
        return self.settings.output_prefix + relative


@dataclass
class LootEntry:
    """One unit's loot table — ``LootConverter.LootDefPart``."""

    sets: list[list[tuple[int, str]]] = field(default_factory=list)
    spread: float = 0.0
    origin: tuple[int, int] = (0, 0)
