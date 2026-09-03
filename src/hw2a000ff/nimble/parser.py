"""Attribute parsing — port of ``xml2unit/XML/XmlHelpers.cs``.

Hammerwatch XML is read by a hand-rolled parser, not a conforming one, and the
converters depend on its quirks (unquoted values, valueless attributes, HTML
entity decoding). This reproduces it character for character.
"""

from __future__ import annotations

import html
from typing import Callable

from .reader import CharReader


class ParsedAttributes:
    __slots__ = ("attributes", "open_tag")

    def __init__(self) -> None:
        self.attributes: dict[str, str] = {}
        self.open_tag = False


def parse_attributes(fs: CharReader, warn: Callable[[str], None] | None = None) -> ParsedAttributes:
    ret = ParsedAttributes()

    key: list[str] = []
    value: list[str] = []
    reading_key = True
    reading_string = False

    def add(k: str, v: str) -> None:
        # The original calls Dictionary.Add, which throws on a repeated
        # attribute name and takes the whole conversion down. Last one wins.
        if k in ret.attributes and warn is not None:
            warn(f"duplicate XML attribute {k!r}; keeping the last value")
        ret.attributes[k] = v

    while not fs.end_of_stream:
        c = fs.read_char()

        if reading_key:
            if c == "=":
                reading_key = False
                if fs.peek_char() == '"':
                    reading_string = True
                    fs.read_char()
            elif c == " ":
                if key:
                    if fs.peek_char() == "=":
                        reading_key = False
                        fs.read_char()
                        if fs.peek_char() == '"':
                            reading_string = True
                            fs.read_char()
                    else:
                        add("".join(key), "")
                        key.clear()
            elif c in ("/", "?"):
                fs.expect(">")
                ret.open_tag = False
                break
            elif c == ">":
                ret.open_tag = True
                break
            elif c not in ("\r", "\n", "\t"):
                key.append(c)
        else:
            if c == '"' or (c == " " and not reading_string) or (c == "/" and not reading_string):
                reading_key = True
                reading_string = False
                add("".join(key), html.unescape("".join(value)))
                key.clear()
                value.clear()
            else:
                value.append(c)

    return ret
