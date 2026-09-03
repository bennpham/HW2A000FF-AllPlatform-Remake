"""``XmlFile`` — port of ``xml2unit/XML/XmlFile.cs``."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .reader import CharReader
from .tag import XmlTag


class XmlFile:
    __slots__ = ("declaration", "root", "path")

    def __init__(self, path: Path | None = None) -> None:
        self.declaration = XmlTag()
        self.root = XmlTag()
        self.path = path

    @classmethod
    def from_text(
        cls, text: str, path: Path | None = None, warn: Callable[[str], None] | None = None
    ) -> "XmlFile":
        xml = cls(path)
        xml._load(text, warn)
        return xml

    @classmethod
    def from_file(cls, path: Path, warn: Callable[[str], None] | None = None) -> "XmlFile":
        if not path.is_file():
            raise FileNotFoundError(f"XML file not found: {path}")
        # utf-8-sig strips a BOM the way StreamReader's encoding detection does.
        # Hammerwatch ships a few files with stray bytes; never abort on those.
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return cls.from_text(text, path, warn)

    def _load(self, text: str, warn: Callable[[str], None] | None) -> None:
        reader = CharReader(text)
        while not reader.end_of_stream:
            if reader.read_char() != "<":
                continue
            if reader.peek_char() == "?":
                self.declaration.parse(reader, warn)
            else:
                tag = XmlTag(self.root)
                tag.parse(reader, warn)
                self.root.children.append(tag)

    @property
    def document_element(self) -> XmlTag:
        """``xml.Root.Children[0]`` — the outermost tag of the document."""
        first = self.root.first_element()
        if first is None:
            raise ValueError(f"XML document has no root element: {self.path}")
        return first

    def __getitem__(self, query: str) -> XmlTag | None:
        return self.root[query]
