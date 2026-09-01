"""Sportsgambler, tested against the markup the site actually serves.

These tests used to feed the parser invented prose -- "We predict over 2.5 goals
at odds 1.85" inside a bare <h1> -- and they passed while the source returned
zero picks on every live run for weeks. The site publishes nothing of the sort:
its listing carries fixture, kickoff and a button, and each fixture's picks live
on a detail page in a `div.bb_list` whose rows each carry their own market,
selection and price.

So the fixtures here are trimmed captures of the real pages, kept structurally
verbatim. A parser that passes these is a parser that would have worked in
production, which is the only property worth asserting.
"""
from pathlib import Path

from bet.tipsters.contracts import ExtractorVerdict, RawDocument
from bet.tipsters.sportsgambler import (
    discover_sportsgambler_detail_links,
    extract_sportsgambler_documents,
    is_allowed_sportsgambler_url,
    parse_sportsgambler_detail,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tipsters"
LISTING = (FIXTURES / "sportsgambler_listing.html").read_text(encoding="utf-8")
DETAIL = (FIXTURES / "sportsgambler_detail.html").read_text(encoding="utf-8")
DETAIL_URL = (
    "https://www.sportsgambler.com/betting-tips/football/"
    "parma-vs-cremonese-prediction-lineups-odds-2026-09-01/"
)


def test_sportsgambler_url_allowance():
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/betting-tips/football/") is True
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/predictions/chelsea-vs-arsenal/") is True
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/r/betclic/") is False
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/odds.php") is False
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/betting-sites/go/") is False
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/login") is False
    assert is_allowed_sportsgambler_url("https://google.com") is False


def test_detail_links_are_the_fixture_anchors_only():
    links = discover_sportsgambler_detail_links(LISTING, max_links=10)
    assert links == [
        DETAIL_URL,
        "https://www.sportsgambler.com/betting-tips/football/wolfsberger-vs-lask-prediction-lineups-odds-2026-09-01/",
    ]


def test_commercial_and_auth_anchors_are_refused_even_with_the_fixture_class():
    """The class narrows the scan; the URL gate is what actually refuses."""
    links = discover_sportsgambler_detail_links(LISTING, max_links=10)
    assert not any("/betting-sites/go/" in url or "/login" in url for url in links)


def test_a_listing_page_yields_no_picks():
    """It states no tip, so inventing one from its fixture names is a bug."""
    assert parse_sportsgambler_detail(LISTING, "https://www.sportsgambler.com/betting-tips/football/") == []


def test_each_bet_builder_leg_becomes_its_own_pick():
    picks = parse_sportsgambler_detail(DETAIL, DETAIL_URL)
    assert [p.market for p in picks] == [
        "Full-Time Result Parma",
        "Total Goals Under 2.5",
        "Team Corners Cremonese Over 3.5",
        "Shots On Target John McAtee Over 0.5",
    ]
    assert [p.odds_decimal for p in picks] == [2.16, 1.62, 1.74, 2.40]
    assert all(p.home_team == "Parma" and p.away_team == "Cremonese" for p in picks)
    assert all(p.match_date == "2026-09-01" for p in picks)
    # Separately named and separately priced, so not a parlay.
    assert not any(p.is_combo for p in picks)


def test_the_headline_pick_is_not_emitted_twice():
    """"Parma To Win @ 2.16" is the same selection as the Full-Time Result leg.

    Same bet, same price, prose instead of a row. Emitting both counted one
    opinion twice and would have doubled this source's entries in public_lean.
    """
    picks = parse_sportsgambler_detail(DETAIL, DETAIL_URL)
    assert sum(1 for p in picks if "2.16" == str(p.odds_decimal)) == 1
    assert not any(p.market == "Parma To Win" for p in picks)


def test_extract_documents_merges_and_reports_ok():
    doc = RawDocument(
        source_id="sportsgambler", url=DETAIL_URL, fetched_at_utc="2026-09-01T10:00:00Z",
        html=DETAIL, status_code=200, content_type="text/html",
    )
    res = extract_sportsgambler_documents([doc])
    assert res.verdict == ExtractorVerdict.OK
    assert len(res.picks) == 4
    assert res.picks[0].event == "Parma vs Cremonese"


def test_analyst_profiles_are_not_read_as_a_fixture():
    html = """
    <div class="footer-staff">
        <span>Football Analyst Rafael Hernández</span> vs <span>Analyst Gabriel Oliveira</span>
    </div>
    """
    assert parse_sportsgambler_detail(html, "https://www.sportsgambler.com/predictions/some-page/") == []
