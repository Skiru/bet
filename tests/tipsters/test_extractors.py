from bet.tipsters.extractors import dispatch_extract, make_raw
from bet.tipsters.contracts import ExtractorVerdict


def test_generic_extracts_statistical_market_and_reasoning():
    html = """
    <article>
      <h2>Arsenal vs Chelsea</h2>
      <p>Best bet: over 9.5 corners @ 1.82.</p>
      <p>Arsenal average 6.2 corners at home and Chelsea conceded 5.8 corners in last 10 matches.</p>
    </article>
    """
    # Routed through a generic source on purpose: this asserts the generic
    # prose extractor, and Sportsgambler no longer uses it -- its picks are read
    # structurally from the site's own bet-builder rows.
    result = dispatch_extract(make_raw("olbg", "https://www.olbg.com/predictions/today/", html), "olbg")
    assert result.verdict == ExtractorVerdict.OK
    assert result.picks[0].home_team == "Arsenal"
    assert result.picks[0].away_team == "Chelsea"
    assert result.picks[0].market_family == "corners"
    assert result.picks[0].direction == "OVER"
    assert result.picks[0].line == 9.5
    assert result.picks[0].odds_decimal == 1.82
    assert result.picks[0].extraction_quality >= 0.6


def test_rejects_navigation_false_positive():
    html = """
    <nav>Predictions vs Betting Tips</nav>
    <div>Free bet - sign up - bonus code</div>
    """
    result = dispatch_extract(make_raw("predictz", "https://www.predictz.com/predictions/", html), "predictz")
    assert result.pick_count == 0
    assert result.verdict == ExtractorVerdict.EMPTY


def test_forebet_table_extractor():
    html = """
    <table><tr><td>Australia Egypt 03/07/2026 20:00 32 34 35 2 0-1 0 - 1 1.33</td></tr></table>
    """
    result = dispatch_extract(make_raw("forebet", "https://www.forebet.com/en/football-tips-and-predictions-for-today", html), "forebet")
    assert result.pick_count == 1
    pick = result.picks[0]
    assert pick.market_family == "winner"
    assert pick.direction == "AWAY"
    assert "correct score" in pick.market


def test_parse_line_does_not_capture_date_or_year_noise():
    """A date in the sentence is not the betting line.

    This used to assert the claim through the old Sportsgambler prose parser,
    which no longer exists -- that source is read structurally now. The property
    belongs to ``parse_line`` and is asserted there directly, which is also
    where a regression would actually live.
    """
    from bet.tipsters.market_parser import direction, parse_line

    text = "Prediction for 03/07/2026: under 2.5 goals. Last 10 matches were low tempo."
    assert parse_line(text) == 2.5
    assert direction(text) == "UNDER"
    assert parse_line("Kick-off 03/07/2026, no line stated") is None
    assert parse_line("Season 2026 preview") is None


def test_predictz_table_extractor_keeps_fixture_score_signal():
    html = """
    <section>Argentina W W W W W Home 4-0 Cape Verde Islands W W D D D Argentina v Cape Verde Islands 1 X 2 1.14 8.00 21.00</section>
    """
    result = dispatch_extract(make_raw("predictz", "https://www.predictz.com/predictions/", html), "predictz")
    assert result.pick_count == 1
    assert result.picks[0].home_team == "Argentina"
    assert result.picks[0].away_team == "Cape Verde Islands"
    assert result.picks[0].market_family == "winner"
    assert "predicted_score=4-0" in result.picks[0].stats_cited


def test_bettingclosed_index_page_does_not_fabricate_picks():
    html = """<main><h1>Predictions football</h1><p>Loading ...</p><a>Login</a><a>Vip</a><a>Predictions World Cup 2026 (6 predictions)</a></main>"""
    result = dispatch_extract(make_raw("bettingclosed", "https://www.bettingclosed.com/predictions/", html), "bettingclosed")
    assert result.pick_count == 0
    assert result.verdict == ExtractorVerdict.EMPTY
    assert "index_or_js_loading_page_no_detail_pick_extraction" in result.warnings


def test_sportsgambler_extracts_valuable_evidence_buckets(
    sportsgambler_detail_url, sportsgambler_detail_html
):
    """The narrative this source is registered for, read from the real page."""
    result = dispatch_extract(
        make_raw("sportsgambler", sportsgambler_detail_url, sportsgambler_detail_html),
        "sportsgambler",
    )
    assert result.pick_count == 4
    pick = result.picks[0]
    assert "advanced_metrics" in pick.valuable_signals
    assert "team_news_injuries" in pick.valuable_signals
    assert "lineups" in pick.valuable_signals


def test_discover_public_detail_links_blocks_commercial_paths(sportsgambler_listing_html):
    """The captured listing puts the fixture class on commercial anchors too."""
    from bet.tipsters.extractors import discover_public_detail_links

    doc = make_raw("sportsgambler", "https://www.sportsgambler.com/betting-tips/football/", sportsgambler_listing_html)
    links = discover_public_detail_links(doc, "sportsgambler")
    assert links == [
        "https://www.sportsgambler.com/betting-tips/football/parma-vs-cremonese-prediction-lineups-odds-2026-09-01/",
        "https://www.sportsgambler.com/betting-tips/football/wolfsberger-vs-lask-prediction-lineups-odds-2026-09-01/",
    ]
    assert not any("/betting-sites/go/" in url or "/login" in url for url in links)


def test_live_review_gate_requires_all_operator_attestations(tmp_path):
    from bet.tipsters import live as mod
    data = {"source_reviews": {"forebet": {"status": "allow_live_dry_run", "terms_reviewed": True}}}
    allowed, reason = mod.review_allows_source(data, "forebet")
    assert not allowed
    assert "robots_reviewed" in reason
    data["source_reviews"]["forebet"].update({
        "robots_reviewed": True,
        "public_html_only": True,
        "no_auth_no_premium_no_bypass": True,
    })
    allowed, reason = mod.review_allows_source(data, "forebet")
    assert not allowed
    assert reason == "INVALID_REVIEW_ATTESTATION"
    data["source_reviews"]["forebet"].update({
        "reviewed_by": "operator@example",
        "reviewed_at_utc": "2026-07-04T11:20:00Z",
    })
    allowed, reason = mod.review_allows_source(data, "forebet")
    assert allowed
    assert reason == "review_allows_live_dry_run"
