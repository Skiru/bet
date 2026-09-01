"""Shared access to the captured Sportsgambler markup.

Several tests here need a Sportsgambler pick but are not about Sportsgambler --
they exercise storage, the pipeline adapter or the extractor dispatch. They used
to build one from invented prose, which is how they stayed green while the real
parser returned nothing. They now read the same captured pages the source-
specific tests use, so a parser that breaks in production breaks here too.
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tipsters"

SPORTSGAMBLER_DETAIL_URL = (
    "https://www.sportsgambler.com/betting-tips/football/"
    "parma-vs-cremonese-prediction-lineups-odds-2026-09-01/"
)


@pytest.fixture
def sportsgambler_detail_url() -> str:
    return SPORTSGAMBLER_DETAIL_URL


@pytest.fixture
def sportsgambler_detail_html() -> str:
    return (FIXTURES / "sportsgambler_detail.html").read_text(encoding="utf-8")


@pytest.fixture
def sportsgambler_listing_html() -> str:
    return (FIXTURES / "sportsgambler_listing.html").read_text(encoding="utf-8")
