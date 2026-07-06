from __future__ import annotations

import pytest
from pathlib import Path
from bet.tipsters.source_registry import CERTIFIED_SHADOW_SOURCE_IDS
from scripts.pipeline_steps.s2_tipsters_v2_live_dry_run import (
    _review_gate_details,
    review_allows_source,
    resolve_target_entrypoints,
)


def test_review_gate_details_validates_attestation():
    # 1. Valid review data
    valid_review = {
        "source_reviews": {
            "zawodtyper": {
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "reviewed_by": "Marek Koziol",
                "reviewed_at_utc": "2026-07-06T09:23:16Z",
                "status": "allow_live_dry_run",
                "allow_public_xhr_capture": True,
                "notes": "NP_ajax.php public XHR review",
                "cookie_policy": "no_cookie",
                "allowed_cookie_names": [],
            }
        }
    }
    details = _review_gate_details(valid_review, "zawodtyper")
    assert details["allowed"] is True
    assert details["reason"] == "review_allows_live_dry_run"

    # 2. Missing terms review flag
    invalid_review_1 = {
        "source_reviews": {
            "zawodtyper": {
                "terms_reviewed": False,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "reviewed_by": "Marek Koziol",
                "reviewed_at_utc": "2026-07-06T09:23:16Z",
                "status": "allow_live_dry_run",
            }
        }
    }
    details = _review_gate_details(invalid_review_1, "zawodtyper")
    assert details["allowed"] is False
    assert "missing_required_review_flags:terms_reviewed" in details["reason"]

    # 3. Placeholder attestation
    invalid_review_2 = {
        "source_reviews": {
            "zawodtyper": {
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "reviewed_by": "REPLACE_WITH_OPERATOR",
                "reviewed_at_utc": "REPLACE_WITH_UTC_TIMESTAMP",
                "status": "allow_live_dry_run",
            }
        }
    }
    details = _review_gate_details(invalid_review_2, "zawodtyper")
    assert details["allowed"] is False
    assert details["reason"] == "INVALID_REVIEW_ATTESTATION"


def test_resolve_target_entrypoints_for_zawodtyper():
    # standard source (no date dependence)
    entrypoints, fallback = resolve_target_entrypoints("sportsgambler", "2026-07-06")
    assert "sportsgambler" in entrypoints[0]
    assert fallback is None

    # zawodtyper date dependence
    entrypoints, fallback = resolve_target_entrypoints("zawodtyper", "2026-07-06")
    assert "typy-dnia-6-lipca-poniedzialek" in entrypoints[0]
    assert fallback == "https://www.zawodtyper.pl/"


def test_certified_shadow_ids_contain_zawodtyper():
    assert "zawodtyper" in CERTIFIED_SHADOW_SOURCE_IDS
