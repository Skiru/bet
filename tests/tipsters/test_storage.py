import json
import sqlite3

from bet.tipsters.extractors import dispatch_extract, make_raw
from bet.tipsters.storage import build_payload, persist_sqlite


def test_payload_exposes_pipeline_consumers_and_decision_boundary(sportsgambler_detail_url, sportsgambler_detail_html):
    result = dispatch_extract(make_raw("sportsgambler", sportsgambler_detail_url, sportsgambler_detail_html), "sportsgambler")
    payload = build_payload([result])
    assert payload["contract"] == "evidence_only_not_betting_decision"
    assert "S3 contextual cross-check" in payload["pipeline_consumers"]
    assert payload["all_picks"][0]["decision_boundary"] == "evidence_only_not_a_bet"
    assert payload["sources_with_picks"] == 1
    assert isinstance(payload["sources_with_picks"], int)
    assert payload["blocked_sources"] == []
    assert payload["skipped_sources"] == []
    for pick in payload["all_picks"]:
        assert "stake" not in pick
        assert "coupon" not in pick
        assert "final_bet" not in pick
        assert "superbet_combined" not in pick
        assert "superbet combined odds" not in [k.lower() for k in pick.keys()]
    assert "stake" not in payload
    assert "coupon" not in payload


def test_sqlite_persistence_roundtrip(tmp_path, sportsgambler_detail_url, sportsgambler_detail_html):
    result = dispatch_extract(make_raw("sportsgambler", sportsgambler_detail_url, sportsgambler_detail_html), "sportsgambler")
    db = tmp_path / "tipsters.sqlite"
    counts = persist_sqlite([result], db)
    # Four legs on the captured page, each its own separately priced selection.
    assert counts["picks"] == 4
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "select source_id, market_family, valuable_signals_json from tipster_picks_v2 "
            "where market like 'Team Corners%'"
        ).fetchone()
    assert row[0] == "sportsgambler"
    assert row[1] == "corners"
    assert isinstance(json.loads(row[2]), dict)


# --- Schema migration --------------------------------------------------------
#
# CREATE TABLE IF NOT EXISTS is a no-op against an existing table, so a database
# created by the first v2 schema would keep its old column set and every insert
# would fail on arity.

_V1_OF_V2_SCHEMA = """
CREATE TABLE tipster_picks_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL, source_name TEXT NOT NULL, sport TEXT NOT NULL,
    event TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
    market TEXT NOT NULL, market_family TEXT NOT NULL, direction TEXT NOT NULL,
    line REAL, odds_decimal REAL, confidence_label TEXT NOT NULL, reasoning TEXT,
    stats_cited_json TEXT NOT NULL, valuable_signals_json TEXT NOT NULL,
    source_url TEXT, extracted_at_utc TEXT NOT NULL, extraction_quality REAL NOT NULL,
    warnings_json TEXT NOT NULL, source_record_type TEXT NOT NULL,
    pipeline_use_json TEXT NOT NULL
);
CREATE TABLE tipster_consensus_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, sport TEXT NOT NULL,
    home_team TEXT NOT NULL, away_team TEXT NOT NULL, consensus_market TEXT NOT NULL,
    consensus_direction TEXT NOT NULL, total_tipsters INTEGER NOT NULL,
    agreement_pct REAL NOT NULL, avg_extraction_quality REAL NOT NULL,
    payload_json TEXT NOT NULL, created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def _countable_result():
    from bet.tipsters.contracts import ExtractionResult, ExtractorVerdict, TipsterPick

    pick = TipsterPick(
        source_id="zawodtyper", source_name="ZawodTyper", sport="football",
        event="Valencia vs Real Betis", home_team="Valencia", away_team="Real Betis",
        market="Poniżej 10,5 rzutów rożnych", market_family="corners", direction="UNDER",
        match_date="2026-08-25", tipster_name="AnalystA", source_ref="492297",
    )
    return ExtractionResult(
        source_id="zawodtyper", url="https://www.zawodtyper.pl/",
        verdict=ExtractorVerdict.OK, picks=[pick],
    )


def test_an_old_v2_table_is_migrated_rather_than_failing_the_insert(tmp_path):
    import sqlite3

    from bet.tipsters.storage import persist_sqlite

    db = tmp_path / "old.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(_V1_OF_V2_SCHEMA)

    assert persist_sqlite([_countable_result()], db) == {"picks": 1, "consensus": 1}

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "select claim_market, claim_line, claim_direction, claim_countable, match_date, tipster_name"
            " from tipster_picks_v2"
        ).fetchone()
    assert row == ("corners_total", 10.5, "UNDER", 1, "2026-08-25", "AnalystA")


def test_migration_is_idempotent(tmp_path):
    from bet.tipsters.storage import persist_sqlite

    db = tmp_path / "twice.sqlite"
    persist_sqlite([_countable_result()], db)
    persist_sqlite([_countable_result()], db)  # must not raise "duplicate column"


def test_the_claim_verdict_is_persisted_for_uncountable_picks_too(tmp_path):
    """A reject reason in the DB is how "the column was empty" stays auditable
    months later, without re-parsing Polish free text."""
    import sqlite3
    from dataclasses import replace

    from bet.tipsters.storage import persist_sqlite

    result = _countable_result()
    result.picks = [replace(result.picks[0], market="Winner: 1")]
    db = tmp_path / "reject.sqlite"
    persist_sqlite([result], db)

    with sqlite3.connect(db) as conn:
        countable, reason = conn.execute(
            "select claim_countable, claim_reject_reason from tipster_picks_v2"
        ).fetchone()
    assert countable == 0
    assert reason == "outcome_market_not_a_total"
