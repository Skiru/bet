import json
import sqlite3

from bet.tipsters.extractors import dispatch_extract, make_raw
from bet.tipsters.storage import build_payload, persist_sqlite


def test_payload_exposes_pipeline_consumers_and_decision_boundary():
    result = dispatch_extract(make_raw("sportsgambler", "https://example.test", "<h2>Arsenal vs Chelsea</h2><p>Best bet: over 9.5 corners. Average corners are high in the last 10 matches.</p>"), "sportsgambler")
    payload = build_payload([result])
    assert payload["contract"] == "evidence_only_not_betting_decision"
    assert "S3 contextual cross-check" in payload["pipeline_consumers"]
    assert payload["all_picks"][0]["decision_boundary"] == "evidence_only_not_a_bet"
    assert payload["sources_with_picks"] == 1
    assert isinstance(payload["sources_with_picks"], int)
    assert payload["blocked_sources"] == []
    assert payload["skipped_sources"] == []
    assert "stake" not in json.dumps(payload)
    assert "coupon" not in json.dumps(payload)
    assert "final bet" not in json.dumps(payload).lower()
    assert "superbet combined odds" not in json.dumps(payload).lower()


def test_sqlite_persistence_roundtrip(tmp_path):
    result = dispatch_extract(make_raw("sportsgambler", "https://example.test", "<h2>Arsenal vs Chelsea</h2><p>Best bet: over 9.5 corners. Average corners are high in the last 10 matches.</p>"), "sportsgambler")
    db = tmp_path / "tipsters.sqlite"
    counts = persist_sqlite([result], db)
    assert counts["picks"] == 1
    with sqlite3.connect(db) as conn:
        row = conn.execute("select source_id, market_family, valuable_signals_json from tipster_picks_v2").fetchone()
    assert row[0] == "sportsgambler"
    assert row[1] == "corners"
    assert isinstance(json.loads(row[2]), dict)
