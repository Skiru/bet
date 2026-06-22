from __future__ import annotations

import json
import pytest
from pathlib import Path
from bet.enrichment.football_data_foundation.fixture_context.loader import (
    load_fixture_context_fixture,
)


def test_fixture_context_loader_wc_and_club() -> None:
    wc_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/pass3/worldcup_2026_argentina_austria_shadow.json"
    )
    club_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/pass3/generic_club_match_shadow.json"
    )

    wc_claims = load_fixture_context_fixture(wc_path)
    club_claims = load_fixture_context_fixture(club_path)

    assert len(wc_claims) == 3
    assert len(club_claims) == 3

    assert wc_claims[0].identity.provider_fixture_id == "wc-2026-arg-aus"
    assert club_claims[0].identity.provider_fixture_id == "club-match-1"


def test_fixture_context_loader_rejects_selectable_for_production(
    tmp_path: Path,
) -> None:
    bad_data = {
        "claims": [
            {
                "source": {
                    "source_key": "sportdb",
                    "display_name": "SportDB Live Client",
                    "role": "CURRENT_LIVE",
                    "allowed_proof_levels": ["REAL_LIVE_API_PROOF"],
                },
                "proof_level": "REAL_LIVE_API_PROOF",
                "fact_type": "FIXTURE_IDENTITY",
                "identity": {"source_key": "sportdb", "provider_fixture_id": "test"},
                "freshness": {"observed_at": "2026-06-22T10:00:00Z"},
                "payload_policy": {
                    "payload_hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
                },
                "claim_value": {},
                "selectable_for_production": True,
            }
        ]
    }

    bad_path = tmp_path / "bad_selectable.json"
    bad_path.write_text(json.dumps(bad_data))

    with pytest.raises(
        ValueError, match="selectable_for_production=True is strictly forbidden"
    ):
        load_fixture_context_fixture(bad_path)


def test_fixture_context_loader_rejects_raw_payload_keys(tmp_path: Path) -> None:
    bad_data = {
        "claims": [
            {
                "source": {
                    "source_key": "sportdb",
                    "display_name": "SportDB Live Client",
                    "role": "CURRENT_LIVE",
                    "allowed_proof_levels": ["REAL_LIVE_API_PROOF"],
                },
                "proof_level": "REAL_LIVE_API_PROOF",
                "fact_type": "FIXTURE_IDENTITY",
                "identity": {"source_key": "sportdb", "provider_fixture_id": "test"},
                "freshness": {"observed_at": "2026-06-22T10:00:00Z"},
                "payload_policy": {
                    "payload_hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
                },
                "claim_value": {"response_body": "some raw html response"},
            }
        ]
    }

    bad_path = tmp_path / "bad_raw.json"
    bad_path.write_text(json.dumps(bad_data))

    with pytest.raises(
        ValueError, match="Forbidden raw payload key found: response_body"
    ):
        load_fixture_context_fixture(bad_path)
