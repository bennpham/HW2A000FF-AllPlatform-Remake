"""``XmlTag`` — port of ``xml2unit/XML/XmlTag.cs``."""

from __future__ import annotations

import re
from typing import Callable, Iterator

from .parser import parse_attributes
from .reader import CharReader

_QUERY_RE = re.compile(r"^([^\[]+)(\[([^=]+)=([^\]]*)\])?$")


class XmlTag:
    __slots__ = ("name", "value", "is_comment", "is_text_node", "parent", "attributes", "children")

    def __init__(self, parent: "XmlTag | None" = None) -> None:
        self.name: str = ""
        self.value: str = ""
        self.is_comment = False
        self.is_text_node = False
        self.parent = parent
        self.attributes: dict[str, str] = {}
        self.children: list[XmlTag] = []

    # ------------------------------------------------------------------ parse

    def parse(self, fs: CharReader, warn: Callable[[str], None] | None = None) -> None:
        """Parse one tag; the caller has already consumed the opening ``<``."""
        read_attributes = True
        open_tag = False

        while True:
            if fs.peek_char() == "?":
                fs.expect("?xml ")
                read_attributes = True
                break
            if fs.peek_char() == "!":
                fs.expect("!--")
                self.is_comment = True
                self.value = self._scan_comment(fs)
                return

            name, c = fs.read_until("\r", "\n", "\t", " ", ">", "/")
            self.name = name
            if c == "/" and fs.peek_char() == ">":
                read_attributes = False
                open_tag = False
                fs.expect(">")
            elif c == ">":
                read_attributes = False
                open_tag = True
            break

        if read_attributes:
            attrs = parse_attributes(fs, warn)
            self.attributes = attrs.attributes
            open_tag = attrs.open_tag

        if open_tag:
            self._parse_body(fs, warn)

    @staticmethod
    def _scan_comment(fs: CharReader) -> str:
        out: list[str] = []
        ending = "-->"
        i = 0
        while not fs.end_of_stream:
            c = fs.read_char()
            if c == ending[i]:
                i += 1
            else:
                i = 0
                out.append(c)
            if i == len(ending):
                break
        return "".join(out)

    def _parse_body(self, fs: CharReader, warn: Callable[[str], None] | None) -> None:
        value: list[str] = []
        text_buf: list[str] = []

        text_node = XmlTag(self)
        text_node.is_text_node = True

        while not fs.end_of_stream:
            c = fs.read_char()
            if c == "<":
                if text_buf:
                    content = "".join(text_buf).strip("\r\n\t")
                    if content:
                        text_node.value = content
                        text_buf.clear()
                        self.children.append(text_node)
                        text_node = XmlTag(self)
                        text_node.is_text_node = True
                if fs.peek_char() == "/":
                    fs.expect("/" + self.name + ">")
                    break
                child = XmlTag(self)
                child.parse(fs, warn)
                self.children.append(child)
            else:
                value.append(c)
                text_buf.append(c)

        self.value = "".join(value)

        if text_buf:
            content = "".join(text_buf).strip("\r\n\t")
            if content:
                # Faithful to the original: the trailing text node keeps the
                # untrimmed buffer even though the emptiness test is trimmed.
                text_node.value = "".join(text_buf)
                self.children.append(text_node)

    # ----------------------------------------------------------------- lookup

    def find_tag_by_name(self, name: str) -> "XmlTag | None":
        for tag in self.children:
            if tag.name == name:
                return tag
        for tag in self.children:
            if not tag.children:
                continue
            found = tag.find_tag_by_name(name)
            if found is not None:
                return found
        return None

    def find_tags_by_name(self, name: str) -> list["XmlTag"]:
        out = [tag for tag in self.children if tag.name == name]
        for tag in self.children:
            if not tag.children:
                continue
            out.extend(tag.find_tags_by_name(name))
        return out

    def find_tag_by_name_and_attribute(self, name: str, attr: str, value: str) -> "XmlTag | None":
        for tag in self.find_tags_by_name(name):
            if tag.attributes.get(attr) == value:
                return tag
        return None

    def find_tag_by_attribute(self, attr: str, value: str) -> "XmlTag | None":
        for tag in self.children:
            if tag.attributes.get(attr) == value:
                return tag
        for tag in self.children:
            if not tag.children:
                continue
            found = tag.find_tag_by_attribute(attr, value)
            if found is not None:
                return found
        return None

    def find_tags_by_attribute(self, attr: str, value: str) -> list["XmlTag"]:
        out = [tag for tag in self.children if tag.attributes.get(attr) == value]
        for tag in self.children:
            if not tag.children:
                continue
            out.extend(tag.find_tags_by_attribute(attr, value))
        return out

    def __getitem__(self, query: str) -> "XmlTag | None":
        """``tag["entry[name=hp]"]`` — the C# query indexer."""
        match = _QUERY_RE.match(query)
        if match is None:
            raise ValueError(f"malformed XML query: {query!r}")
        name, attr, value = match.group(1), match.group(3), match.group(4)
        if attr:
            return self.find_tag_by_name_and_attribute(name, attr, value)
        return self.find_tag_by_name(query)

    # ---------------------------------------------------------------- helpers
    # C# leans on `?.` and `??`; these keep the ported call sites readable and
    # turn what would be a NullReferenceException into a None.

    def q(self, *path: str) -> "XmlTag | None":
        """Follow a chain of queries, short-circuiting on a miss."""
        tag: XmlTag | None = self
        for step in path:
            if tag is None:
                return None
            tag = tag[step]
        return tag

    def qv(self, *path: str, default: str = "") -> str:
        """Value of ``q(*path)``, or ``default`` if any step is missing."""
        tag = self.q(*path)
        return default if tag is None else tag.value

    def first_element(self) -> "XmlTag | None":
        """The first real child element.

        The original indexes ``Children[0]`` directly. Hammerwatch's own files
        are written compactly so that lands on the element, but indentation
        between tags parses as a text node -- the parser only trims ``\r``,
        ``\n`` and ``\t``, never spaces -- so any pretty-printed input (a
        hand-edited file, or a level from a map generator) shifts the index and
        the converter reads the whitespace instead.
        """
        return next(self.elements(), None)

    def element_value(self, default: str = "") -> str:
        """Value of ``first_element()``, or ``default`` when there is none."""
        first = self.first_element()
        return default if first is None else first.value

    def elements(self) -> Iterator["XmlTag"]:
        """Children that are neither comments nor text nodes."""
        for child in self.children:
            if not child.is_comment and not child.is_text_node:
                yield child

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<XmlTag {self.name!r} attrs={self.attributes!r} children={len(self.children)}>"
