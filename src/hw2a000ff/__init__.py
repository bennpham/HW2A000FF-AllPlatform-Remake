"""Cross-platform converter from Hammerwatch (HWM) assets to A000FF.

A port of the Windows-only C# tool at https://github.com/bennpham/hw2a000ff.

Typical use from another program -- a map generator, say::

    from hw2a000ff import Settings, convert_all

    report = convert_all(Settings(
        source_path=Path("generated/assets"),
        output_path=Path("out"),
    ))
    print(report.summary())
"""

__version__ = "1.0.0"

from .context import ConversionContext
from .errors import ConversionError, MissingDirectoryError
from .pipeline import Report, convert_all, convert_single_unit, preflight
from .settings import STAGES, Settings, SettingsError

__all__ = [
    "ConversionContext",
    "ConversionError",
    "MissingDirectoryError",
    "Report",
    "STAGES",
    "Settings",
    "SettingsError",
    "convert_all",
    "convert_single_unit",
    "preflight",
    "__version__",
]
