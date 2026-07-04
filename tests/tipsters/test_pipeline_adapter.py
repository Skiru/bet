from bet.tipsters.extractors import dispatch_extract, make_raw
from bet.tipsters.pipeline_adapter import consensus_from_picks, to_legacy_pick


def _pick(source_id, html):
    return dispatch_extract(make_raw(source_id, "https://example.test", html), source_id).picks[0]


def test_consensus_groups_sources_for_same_event():
    p1 = _pick("sportsgambler", "<h2>Arsenal vs Chelsea</h2><p>Pick: over 2.5 goals. Arsenal scored in last 10 matches.</p>")
    p2 = _pick("predictz", "<h2>Arsenal v Chelsea</h2><p>Prediction: over 2.5 goals. Recent form and average goals support this.</p>")
    rows = consensus_from_picks([p1, p2])
    assert len(rows) == 1
    assert rows[0]["total_tipsters"] == 2
    assert rows[0]["agreement_pct"] == 100.0


def test_legacy_shape_preserves_no_decision_boundary():
    p = _pick("sportsgambler", "<h2>Arsenal vs Chelsea</h2><p>Best bet: over 9.5 corners. Average corners are high.</p>")
    legacy = to_legacy_pick(p)
    assert "stake" not in legacy
    assert "coupon" not in legacy
    assert legacy["market_type"] == "statistical"
