import json
import sqlite3
from bet.enrichment.football_data_foundation.source_bound_shadow.contracts import NormalizedMatchSnapshot, NormalizedFact
from bet.enrichment.football_data_foundation.source_bound_shadow.writer import write_shadow_json, write_shadow_sqlite

def test_writer_writes_deterministic_json_and_sqlite(tmp_path):
    allowed_dir = tmp_path / "reports" / "football_data_foundation" / "source_bound_shadow"
    allowed_dir.mkdir(parents=True, exist_ok=True)

    fact = NormalizedFact(
        source="sportdb",
        source_role="test_role",
        fact_type="score",
        key="full_time_score",
        value={"home": 3, "away": 2},
        provider_match_id="xSUJLPV8",
        body_sha256="sha",
        source_file="file",
    )
    snapshot = NormalizedMatchSnapshot(
        fixture_slug="worldcup2026-norway-senegal",
        provider_ids={"sportdb": "xSUJLPV8"},
        teams={"home": "Norway", "away": "Senegal"},
        status="FINISHED",
        score={"home": 3, "away": 2},
        kickoff_utc="2026-06-23T00:00:00Z",
        competition="FIFA World Cup",
        venue="MetLife Stadium",
        referee="Sampaio W.",
        facts=[fact],
        conflicts=[]
    )

    json_path = allowed_dir / "snapshot.json"
    write_shadow_json(snapshot, json_path)
    assert json_path.exists()
    
    content = json_path.read_text(encoding="utf-8")
    data = json.loads(content)
    assert data["fixture_slug"] == "worldcup2026-norway-senegal"
    
    sqlite_path = allowed_dir / "shadow.sqlite"
    write_shadow_sqlite(snapshot, sqlite_path, diagnostics={})
    assert sqlite_path.exists()

    con = sqlite3.connect(sqlite_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT fixture_slug, shadow_status FROM shadow_match_snapshot")
        row = cur.fetchone()
        assert row[0] == "worldcup2026-norway-senegal"
        assert row[1] == "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW"
        
        cur.execute("SELECT provider, provider_match_id FROM shadow_provider_ids")
        row2 = cur.fetchone()
        assert row2[0] == "sportdb"
        assert row2[1] == "xSUJLPV8"
    finally:
        con.close()

