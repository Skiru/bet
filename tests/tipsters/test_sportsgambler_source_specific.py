import pytest
from bet.tipsters.contracts import RawDocument, ExtractorVerdict
from bet.tipsters.sportsgambler import (
    is_allowed_sportsgambler_url,
    discover_sportsgambler_detail_links,
    parse_sportsgambler_index,
    parse_sportsgambler_detail,
    extract_sportsgambler_documents,
)

def test_sportsgambler_url_allowance():
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/betting-tips/football/") is True
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/predictions/chelsea-vs-arsenal/") is True
    # Forbidden links
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/r/betclic/") is False
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/odds.php") is False
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/betting-sites/go/") is False
    assert is_allowed_sportsgambler_url("https://www.sportsgambler.com/login") is False
    assert is_allowed_sportsgambler_url("https://google.com") is False

def test_sportsgambler_discover_detail_links():
    html = """
    <html>
        <body>
            <a href="https://www.sportsgambler.com/predictions/chelsea-vs-arsenal/">Match Preview</a>
            <a href="https://www.sportsgambler.com/r/betclic/">Clickout</a>
        </body>
    </html>
    """
    links = discover_sportsgambler_detail_links(html)
    assert "https://www.sportsgambler.com/predictions/chelsea-vs-arsenal/" in links
    assert "https://www.sportsgambler.com/r/betclic/" not in links

def test_sportsgambler_analyst_false_positive_filter():
    # Verify analyst profiles are excluded from match events
    html = """
    <div class="footer-staff">
        <span> Football Analyst Rafael Hernández </span> vs <span> Senior South American Football Analyst Gabriel Oliveira </span>
    </div>
    """
    picks = parse_sportsgambler_detail(html, "https://www.sportsgambler.com/predictions/some-prediction-detail-page")
    assert len(picks) == 0

def test_sportsgambler_parse_preview_detail():
    html = """
    <div class="match-content">
        <h1> Chelsea vs Arsenal </h1>
        <p> Chelsea will face Arsenal. We predict over 2.5 goals at odds 1.85. </p>
        <p> Team news: Chelsea has injuries to Reece James and Enzo Fernandez. </p>
        <p> Lineups: starting XI includes Cole Palmer. </p>
        <p> Form: Arsenal is unbeaten in last 5 matches. </p>
    </div>
    """
    picks = parse_sportsgambler_detail(html, "https://www.sportsgambler.com/predictions/chelsea-vs-arsenal/")
    assert len(picks) == 1
    p = picks[0]
    assert p.home_team == "Chelsea"
    assert p.away_team == "Arsenal"
    assert p.market == "over 2.5 goals"
    assert p.odds_decimal == 1.85
    assert p.source_id == "sportsgambler"
    assert "team_news_injuries" in p.valuable_signals
    assert "lineups" in p.valuable_signals
    assert "form_trends" in p.valuable_signals
    assert "Reece James" in "".join(p.valuable_signals["team_news_injuries"])

def test_sportsgambler_extract_documents():
    doc = RawDocument(
        source_id="sportsgambler",
        url="https://www.sportsgambler.com/predictions/chelsea-vs-arsenal/",
        fetched_at_utc="2026-07-07T04:00:00Z",
        html="<h1>Chelsea vs Arsenal</h1> <p>We recommend over 2.5 goals @ 1.85.</p>",
        status_code=200,
        content_type="text/html"
    )
    res = extract_sportsgambler_documents([doc])
    assert res.verdict == ExtractorVerdict.OK
    assert len(res.picks) == 1
    assert res.picks[0].event == "Chelsea vs Arsenal"
