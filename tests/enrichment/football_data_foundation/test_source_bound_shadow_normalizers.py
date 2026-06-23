import json
from pathlib import Path
from bet.enrichment.football_data_foundation.source_bound_shadow.loader import load_provider_envelopes
from bet.enrichment.football_data_foundation.source_bound_shadow.normalizers import normalize_envelope

def test_normalizers_extract_all_provider_ids_and_details(tmp_path):
    run = tmp_path / "run"
    providers = ["sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"]
    for p in providers:
        (run / p).mkdir(parents=True, exist_ok=True)
        
    def write(provider: str, name: str, body: object, sha: str = "abc") -> None:
        env = {
            "provider": provider,
            "status": "SUCCESS",
            "source_url": f"https://example.test/{provider}/{name}",
            "body": body,
            "body_sha256": sha + provider + name,
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        }
        (run / provider / name).write_text(json.dumps(env, sort_keys=True), encoding="utf-8")

    # SportDB files
    write("sportdb", "match_details.json", {
        "eventId": "xSUJLPV8", "homeName": "Norway", "awayName": "Senegal",
        "referee": "Sampaio W.", "venue": "MetLife Stadium",
        "events": [{"homeScore": "3", "awayScore": "2"}]
    })
    write("sportdb", "match_stats.json", [{"stats": []}])
    write("sportdb", "match_lineups.json", {"lineups": []})
    write("sportdb", "match_odds.json", [{"bookmakerName": "Midnite"}])
    
    # Highlightly files
    write("highlightly", "match_detail.json", {
        "id": 1267481035, "homeTeam": {"name": "Norway"}, "awayTeam": {"name": "Senegal"},
        "state": {"score": {"current": "3-2"}}
    })
    write("highlightly", "statistics.json", {"stats": []})
    write("highlightly", "lineups.json", {"lineups": []})
    write("highlightly", "events.json", {"events": []})

    # API-Football
    write("api-football", "fixture.json", {
        "response": [{
            "fixture": {"id": 1489401, "status": {"long": "Finished"}},
            "teams": {"home": {"name": "Norway"}, "away": {"name": "Senegal"}},
            "goals": {"home": 3, "away": 2},
            "events": [{"type": "Goal"}],
            "lineups": [{"formation": "4-3-3"}]
        }]
    })

    # football-data-org
    write("football-data-org", "match.json", {
        "id": 537394, "status": "FINISHED",
        "homeTeam": {"name": "Norway"}, "awayTeam": {"name": "Senegal"},
        "score": {"fullTime": {"home": 3, "away": 2}},
        "competition": {"name": "FIFA World Cup"}
    })

    # ESPN baseline
    write("espn-baseline", "summary.json", {
        "header": {
            "competitions": [{
                "id": "760454", "date": "2026-06-23T00:00:00Z",
                "competitors": [
                    {"homeAway": "home", "team": {"name": "Norway"}, "score": "3"},
                    {"homeAway": "away", "team": {"name": "Senegal"}, "score": "2"}
                ]
            }]
        },
        "article": {
            "story": "Norway wins 3-2. This is raw article text with story and media",
            "media": "some media payload"
        }
    })

    envelopes = load_provider_envelopes([run])
    facts = []
    for env in envelopes:
        facts.extend(normalize_envelope(env))

    # Assert provider IDs extraction (REQ-TEST-002)
    assert any(f.source == "sportdb" and f.provider_match_id == "xSUJLPV8" for f in facts)
    assert any(f.source == "highlightly" and f.provider_match_id == "1267481035" for f in facts)
    assert any(f.source == "api-football" and f.provider_match_id == "1489401" for f in facts)
    assert any(f.source == "football-data-org" and f.provider_match_id == "537394" for f in facts)
    assert any(f.source == "espn-baseline" and f.provider_match_id == "760454" for f in facts)

    # Assert scores extraction (REQ-TEST-003)
    score_facts = [f for f in facts if f.fact_type == "score" and f.key == "full_time_score"]
    assert len(score_facts) >= 4
    for f in score_facts:
        assert f.value == {"home": 3, "away": 2}

    # REQ-TEST-004 SportDB extracts events/stats/lineups/odds_reference
    sdb_facts = [f for f in facts if f.source == "sportdb"]
    assert any(f.fact_type == "match_event" for f in sdb_facts)
    assert any(f.fact_type == "match_statistic" for f in sdb_facts)
    assert any(f.fact_type == "lineup" for f in sdb_facts)
    assert any(f.fact_type == "odds_reference" and f.key == "odds_reference_available" for f in sdb_facts)

    # REQ-TEST-005 Highlightly extracts statistics/lineups/events
    hl_facts = [f for f in facts if f.source == "highlightly"]
    assert any(f.fact_type == "match_statistic" for f in hl_facts)
    assert any(f.fact_type == "lineup" for f in hl_facts)
    assert any(f.fact_type == "match_event" for f in hl_facts)

    # REQ-TEST-006 API-Football extracts detailed facts
    af_facts = [f for f in facts if f.source == "api-football"]
    assert any(f.fact_type == "match_event" for f in af_facts)
    assert any(f.fact_type == "lineup" for f in af_facts)

    # REQ-TEST-007 football-data.org extracts reference/status/score facts
    fdo_facts = [f for f in facts if f.source == "football-data-org"]
    assert any(f.fact_type == "competition" for f in fdo_facts)
    assert any(f.fact_type == "match_status" for f in fdo_facts)
    assert any(f.fact_type == "score" for f in fdo_facts)

    # REQ-TEST-008 ESPN excludes story/media/article text
    espn_facts = [f for f in facts if f.source == "espn-baseline"]
    for f in espn_facts:
        val_str = str(f.value).lower()
        assert "story" not in val_str
        assert "media" not in val_str
        assert "article" not in val_str
