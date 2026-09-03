"""A faithful port of the ``Nimble.XML`` reader bundled with the C# converter.

This is deliberately *not* a standards-compliant XML parser. The converters
depend on its exact behaviour, so it reproduces the original quirk for quirk.
"""

from .file import XmlFile
from .reader import CharReader
from .tag import XmlTag

__all__ = ["XmlFile", "XmlTag", "CharReader"]
