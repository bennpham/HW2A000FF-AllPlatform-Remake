from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hw2a000ff.context import ConversionContext
from hw2a000ff.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"
MINI_CAMPAIGN = FIXTURES / "mini_campaign"


@pytest.fixture
def campaign(tmp_path: Path) -> Path:
    """A writable copy of the mini campaign."""
    target = tmp_path / "campaign"
    shutil.copytree(MINI_CAMPAIGN, target)
    return target


@pytest.fixture
def settings(campaign: Path, tmp_path: Path) -> Settings:
    return Settings(
        source_path=campaign / "assets",
        levels_path=campaign / "campaign" / "levels.xml",
        output_path=tmp_path / "out",
        output_prefix="hwport/",
    )


@pytest.fixture
def ctx(settings: Settings) -> ConversionContext:
    settings.output_path.mkdir(parents=True, exist_ok=True)
    return ConversionContext(settings)
