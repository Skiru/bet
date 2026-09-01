from bet.tipsters.extractors import dispatch_extract, make_raw
from bet.tipsters.pipeline_adapter import consensus_from_picks, to_legacy_pick


def _pick(source_id, html, url="https://example.test"):
    return dispatch_extract(make_raw(source_id, url, html), source_id).picks[0]


def _sportsgambler_pick(url, html, market_prefix):
    """One captured leg, chosen by market, rather than an invented sentence."""
    picks = dispatch_extract(make_raw("sportsgambler", url, html), "sportsgambler").picks
    return next(p for p in picks if p.market.startswith(market_prefix))


def test_consensus_groups_sources_for_same_event(sportsgambler_detail_url, sportsgambler_detail_html):
    p1 = _sportsgambler_pick(sportsgambler_detail_url, sportsgambler_detail_html, "Total Goals")
    p2 = _pick("predictz", "<h2>Parma v Cremonese</h2><p>Prediction: under 2.5 goals. Recent form and average goals support this.</p>")
    rows = consensus_from_picks([p1, p2])
    assert len(rows) == 1
    assert rows[0]["total_tipsters"] == 2
    assert rows[0]["agreement_pct"] == 100.0


def test_legacy_shape_preserves_no_decision_boundary(sportsgambler_detail_url, sportsgambler_detail_html):
    p = _sportsgambler_pick(sportsgambler_detail_url, sportsgambler_detail_html, "Team Corners")
    legacy = to_legacy_pick(p)
    assert "stake" not in legacy
    assert "coupon" not in legacy
    assert legacy["market_type"] == "statistical"
