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
    result = dispatch_extract(make_raw("sportsgambler", "https://www.sportsgambler.com/predictions/today/", html), "sportsgambler")
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
    html = """<article><h2>Poland vs Germany</h2><p>Prediction for 03/07/2026: under 2.5 goals. Last 10 matches were low tempo.</p></article>"""
    result = dispatch_extract(make_raw("sportsgambler", "https://www.sportsgambler.com/predictions/poland-vs-germany/", html), "sportsgambler")
    assert result.pick_count == 1
    assert result.picks[0].line == 2.5
    assert result.picks[0].direction == "UNDER"


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


def test_sportsgambler_extracts_valuable_evidence_buckets():
    html = """
    <article>
      <h1>Halmstad vs Vasteras Prediction</h1>
      <p>Best bet: BTTS Yes @ 1.62.</p>
      <p>Our football analysis uses xG, xGA and PPDA. Halmstad have scored in the last 8 matches.</p>
      <p>Team news: Vasteras have one suspended defender and the predicted lineup is unchanged.</p>
    </article>
    """
    result = dispatch_extract(make_raw("sportsgambler", "https://www.sportsgambler.com/predictions/halmstad-vs-vasteras/", html), "sportsgambler")
    assert result.pick_count == 1
    pick = result.picks[0]
    assert pick.market_family == "btts"
    assert pick.direction == "BTTS_YES"
    assert "advanced_metrics" in pick.valuable_signals
    assert "team_news_injuries" in pick.valuable_signals
    assert "lineups" in pick.valuable_signals
    assert "s3_context_cross_check" in pick.pipeline_use


def test_forebet_preserves_probabilities_avg_goals_and_score_model():
    html = """
    <table><tr><td>Australia Egypt 03/07/2026 20:00 32 34 35 2 0-1 0 - 1 1.33</td></tr></table>
    """
    result = dispatch_extract(make_raw("forebet", "https://www.forebet.com/en/football-tips-and-predictions-for-today", html), "forebet")
    pick = result.picks[0]
    assert "prob_1=32%" in pick.stats_cited[0]
    assert "model_probabilities" in pick.valuable_signals
    assert "s3_probability_cross_check" in pick.pipeline_use


def test_windrawwin_score_inference_and_pipeline_usage():
    html = """<section><p>Halmstad v Vasteras 15:00 correct score 1-1 BTTS Yes Over 2.5 odds context</p></section>"""
    result = dispatch_extract(make_raw("windrawwin", "https://www.windrawwin.com/predictions/today/", html), "windrawwin")
    assert result.pick_count == 1
    pick = result.picks[0]
    assert "correct_score=1-1" in pick.stats_cited
    assert "score_model" in pick.valuable_signals
    assert pick.source_record_type == "score_inferred_prediction"


def test_feedinco_rejects_affiliate_noise_even_with_fixture():
    html = """<article><h2>Arsenal vs Chelsea</h2><p>Best bet: over 2.5 goals. Sign up for casino bonus and free bet bookmaker code.</p></article>"""
    result = dispatch_extract(make_raw("feedinco", "https://www.feedinco.com/tips/", html), "feedinco")
    assert result.pick_count == 0
    assert result.verdict == ExtractorVerdict.EMPTY


def test_clean_team_name_does_not_strip_internal_x_character():
    from bet.tipsters.normalization import clean_team_name
    assert clean_team_name("Xerez Deportivo") == "Xerez Deportivo"
    assert clean_team_name("Real Betis X2") == "Real Betis"


def test_discover_public_detail_links_blocks_commercial_paths():
    from bet.tipsters.extractors import discover_public_detail_links
    html = """
    <a href="/betting-tips/football/team-a-v-team-b/">Team A v Team B preview</a>
    <a href="/go/bookmaker-x/">Best Odds</a>
    <a href="/login/">Login</a>
    <a href="https://external.example/prediction">External Prediction</a>
    """
    doc = make_raw("sportsgambler", "https://www.sportsgambler.com/betting-tips/football/", html)
    links = discover_public_detail_links(doc, "sportsgambler")
    assert links == ["https://www.sportsgambler.com/betting-tips/football/team-a-v-team-b/"]


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
