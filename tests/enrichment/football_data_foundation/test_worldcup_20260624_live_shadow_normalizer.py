import tempfile
import json
from pathlib import Path
from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.normalizer import normalize_fixture_snapshot

def write_valid_fetched_envelope(cache_dir: Path, provider: str, slug: str, body: dict) -> None:
    envelope = {
        "fixture_slug": slug,
        "provider": provider,
        "request_purpose": f"{provider}_fixture_detail_capture",
        "source_url": "https://v3.football.api-sports.io/fixtures?id=12345",
        "status": "FETCHED",
        "status_code": 200,
        "body": body,
        "body_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "captured_at_utc": "2026-06-24T12:00:00Z",
        "sanitized": True,
        "raw_headers_stored": False,
        "secrets_stored": False,
        "network_used": True,
        "provider_fixture_id": "12345"
    }
    prov_dir = cache_dir / "cache" / provider
    prov_dir.mkdir(parents=True, exist_ok=True)
    (prov_dir / f"{slug}.json").write_text(json.dumps(envelope))


def test_normalizer_produces_summary_facts() -> None:
    # TEST-007: normalizer produces summary facts, not raw payloads.
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        apif_body = {
            "response": [
                {
                    "goals": {"home": 2, "away": 1},
                    "fixture": {
                        "date": "2026-06-24T21:00:00Z",
                        "status": {"long": "Match Finished"},
                        "venue": {"name": "MetLife Stadium"}
                    },
                    "teams": {
                        "home": {"name": "Switzerland"},
                        "away": {"name": "Canada"}
                    }
                }
            ]
        }
        write_valid_fetched_envelope(cache_dir, "api-football", "worldcup2026-switzerland-canada", apif_body)
        
        snapshot = normalize_fixture_snapshot(
            fixture_slug="worldcup2026-switzerland-canada",
            home_team="Switzerland",
            away_team="Canada",
            group="B",
            kickoff_utc="2026-06-24T21:00:00Z",
            cache_dir=cache_dir,
            run_id="run_123"
        )
        
        assert snapshot["fixture_slug"] == "worldcup2026-switzerland-canada"
        assert "raw_payload" not in snapshot
        assert "raw_headers" not in snapshot
        assert "cookie" not in snapshot
        
        # Check that summary facts are generated
        fact_types = {fact["fact_type"] for fact in snapshot["facts"]}
        assert "provider_mapping" in fact_types
        assert "fixture_identity" in fact_types
        assert "score" in fact_types
        assert "match_status" in fact_types


def test_odds_are_reference_only() -> None:
    # TEST-008: odds are odds_reference only.
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        apif_body = {
            "response": [
                {
                    "goals": {"home": 2, "away": 1},
                    "fixture": {
                        "date": "2026-06-24T21:00:00Z",
                        "status": {"long": "Match Finished"},
                        "venue": {"name": "MetLife Stadium"}
                    },
                    "teams": {
                        "home": {"name": "Switzerland"},
                        "away": {"name": "Canada"}
                    }
                }
            ]
        }
        write_valid_fetched_envelope(cache_dir, "api-football", "worldcup2026-switzerland-canada", apif_body)
        
        snapshot = normalize_fixture_snapshot(
            fixture_slug="worldcup2026-switzerland-canada",
            home_team="Switzerland",
            away_team="Canada",
            group="B",
            kickoff_utc="2026-06-24T21:00:00Z",
            cache_dir=cache_dir,
            run_id="run_123"
        )
        
        odds_facts = [f for f in snapshot["facts"] if f["fact_type"] == "odds_reference"]
        assert len(odds_facts) > 0
        for fact in odds_facts:
            assert fact["key"] == "odds_reference_available"
            assert isinstance(fact["value"], dict)
            assert fact["value"]["odds_reference_available"] is True
            assert "price" not in str(fact["value"]).lower()
            assert "edge" not in str(fact["value"]).lower()
