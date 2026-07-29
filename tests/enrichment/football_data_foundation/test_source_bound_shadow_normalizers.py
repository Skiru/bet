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
        "events": [{"homeScore": "3", "awayScore": "2", "type": "goal", "elapsed": 45, "playerName": "Haaland", "teamName": "home"}]
    })
    write("sportdb", "match_stats.json", [{"type": "Shots on Goal", "value": "5"}])
    write("sportdb", "match_lineups.json", [{"teamName": "Norway", "formation": "4-3-3", "players": [{"name": "Haaland"}]}])
    write("sportdb", "match_odds.json", [{"bookmakerName": "Midnite", "odds": [{"name": "1X2"}]}])

    # Highlightly files
    write("highlightly", "match_detail.json", {
        "id": 1267481035, "homeTeam": {"name": "Norway"}, "awayTeam": {"name": "Senegal"},
        "state": {"score": {"current": "3-2"}},
        "venue": {"name": "MetLife Stadium"}
    })
    write("highlightly", "statistics.json", {"Expected Goals": 1.5})
    write("highlightly", "lineups.json", [{"name": "Norway", "system": "4-3-3", "lineup": [{"name": "Haaland"}]}])
    write("highlightly", "events.json", [{"type": "Goal", "time": {"elapsed": 45}, "team": {"name": "Norway"}, "player": {"name": "Haaland"}}])

    # API-Football
    write("api-football", "fixture.json", {
        "response": [{
            "fixture": {"id": 1489401, "status": {"long": "Finished"}},
            "teams": {"home": {"name": "Norway"}, "away": {"name": "Senegal"}},
            "goals": {"home": 3, "away": 2},
            "events": [{"type": "Goal", "time": {"elapsed": 45}, "team": {"name": "Norway"}, "player": {"name": "Haaland"}}],
            "lineups": [{"team": {"name": "Norway"}, "formation": "4-3-3", "startXI": [{"player": {"name": "Haaland"}}]}],
            "statistics": [{"team": {"name": "Norway"}, "statistics": [{"type": "Shots on Goal", "value": "10"}]}]
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

    # REQ-TEST-002: normalizers emit summary fact types, not raw match_event/lineup/match_statistic payload facts
    for f in facts:
        assert f.fact_type not in {"match_event", "lineup", "match_statistic"}

    # REQ-TEST-003: event summary strips raw nested payload keys while preserving useful counts/goals
    event_summaries = [f for f in facts if f.fact_type == "match_event_summary" and f.key == "event_summary"]
    assert len(event_summaries) >= 3
    for f in event_summaries:
        val = f.value
        assert "event_count" in val
        assert "goals" in val
        assert "cards_count" in val
        assert "substitutions_count" in val
        assert "provider_event_categories" in val
        for g in val["goals"]:
            assert "minute" in g
            assert "team" in g
            assert "player" in g

    # REQ-TEST-004: lineup summary strips raw player payloads while preserving formations/counts
    lineup_summaries = [f for f in facts if f.fact_type == "lineup_summary" and f.key == "lineup_summary"]
    assert len(lineup_summaries) >= 3
    for f in lineup_summaries:
        val = f.value
        assert "teams_with_lineups" in val
        assert "formations" in val
        assert "listed_player_count" in val
        assert "unavailable_suspension_injury_counts" in val
        # Ensure no raw players list is exposed
        assert "players" not in val
        assert "startXI" not in val

    # REQ-TEST-005: statistics summary strips raw stats payload while preserving groups/scalars
    stat_summaries = [f for f in facts if f.fact_type == "statistics_summary" and f.key == "statistics_summary"]
    assert len(stat_summaries) >= 3
    for f in stat_summaries:
        val = f.value
        assert "stat_group_count" in val
        assert "stat_groups" in val
        assert "selected_numeric_stats" in val
        # Ensure no raw stats array is exposed
        assert "stats" not in val

    # REQ-TEST-006: odds are odds_reference only
    odds_facts = [f for f in facts if f.fact_type == "odds_reference"]
    assert len(odds_facts) >= 1
    for f in odds_facts:
        if f.key == "odds_reference_available":
            assert f.value["odds_reference_available"] is True
            assert f.value["decision_use"] == "forbidden_reference_only"

    # REQ-TEST-007: ESPN story/article/media is excluded
    espn_facts = [f for f in facts if f.source == "espn-baseline"]
    for f in espn_facts:
        val_str = str(f.value).lower()
        assert "story" not in val_str
        assert "media" not in val_str
        assert "article" not in val_str
