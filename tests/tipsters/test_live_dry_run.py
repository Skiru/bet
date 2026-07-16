import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from bet.tipsters.contracts import ExtractionResult, ExtractorVerdict
from bet.tipsters.extractors import dispatch_extract, make_raw
from bet.tipsters.storage import build_payload


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py"


def _load_live_module():
    spec = importlib.util.spec_from_file_location("s2_live", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_placeholder_reviewed_by_is_rejected():
    mod = _load_live_module()
    data = {
        "source_reviews": {
            "forebet": {
                "status": "allow_live_dry_run",
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "reviewed_by": "REPLACE_WITH_OPERATOR",
                "reviewed_at_utc": "2026-07-04T11:20:00Z",
            }
        }
    }
    allowed, reason = mod.review_allows_source(data, "forebet")
    assert not allowed
    assert reason == "INVALID_REVIEW_ATTESTATION"


def test_placeholder_reviewed_at_is_rejected():
    mod = _load_live_module()
    data = {
        "source_reviews": {
            "forebet": {
                "status": "allow_live_dry_run",
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "reviewed_by": "operator@example",
                "reviewed_at_utc": "REPLACE_WITH_UTC_TIMESTAMP",
            }
        }
    }
    allowed, reason = mod.review_allows_source(data, "forebet")
    assert not allowed
    assert reason == "INVALID_REVIEW_ATTESTATION"


def test_missing_review_flags_returns_specific_skip_reason():
    mod = _load_live_module()
    data = {"source_reviews": {"sportsgambler": {"status": "manual_review_required", "terms_reviewed": False, "robots_reviewed": False}}}
    results = mod.fetch_extract_source("sportsgambler", review_data=data, max_pages=1, timeout=1.0, max_bytes=1024)
    assert len(results) == 1
    result = results[0]
    assert result.skip_reason == "missing_required_review_flags:terms_reviewed,robots_reviewed,public_html_only,no_auth_no_premium_no_bypass"
    assert result.required_flags_missing == ["terms_reviewed", "robots_reviewed", "public_html_only", "no_auth_no_premium_no_bypass"]


def test_block_robots_populates_block_fields_and_blocked_sources():
    payload = build_payload([
        ExtractionResult(
            source_id="forebet",
            url="https://www.forebet.com/en/football-tips-and-predictions-for-today",
            verdict=ExtractorVerdict.EMPTY,
            picks=[],
            warnings=["fetch_block:compliance_block:ComplianceVerdict.BLOCK_ROBOTS:robots.txt disallows target"],
            block_reason="BLOCK_ROBOTS:robots.txt disallows target",
            robots_blocked_live=True,
            live_fetch_allowed=False,
            fallback="fixture_snapshot_only",
        )
    ])
    source = payload["sources"][0]
    assert source["block_reason"] == "BLOCK_ROBOTS:robots.txt disallows target"
    assert source["robots_blocked_live"] is True
    assert source["live_fetch_allowed"] is False
    assert source["fallback"] == "fixture_snapshot_only"
    assert payload["blocked_sources"] == [{
        "source_id": "forebet",
        "reason": "BLOCK_ROBOTS:robots.txt disallows target",
        "url": "https://www.forebet.com/en/football-tips-and-predictions-for-today",
        "fallback": "fixture_snapshot_only",
        "live_fetch_allowed": False,
    }]
    assert payload["fail_closed"] is True


def test_require_at_least_one_pick_returns_non_zero(tmp_path, monkeypatch):
    mod = _load_live_module()
    out = tmp_path / "live.json"
    db = tmp_path / "live.sqlite"
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"source_reviews": {"forebet": {}}}), encoding="utf-8")

    monkeypatch.setattr(mod, "fetch_extract_source", lambda *args, **kwargs: [
        ExtractionResult(
            source_id="forebet",
            url="https://example.test",
            verdict=ExtractorVerdict.EMPTY,
            picks=[],
            warnings=["missing_required_review_flags:terms_reviewed,robots_reviewed"],
            live_fetch_allowed=False,
            fallback="manual_review",
            skip_reason="missing_required_review_flags:terms_reviewed,robots_reviewed",
            required_flags_missing=["terms_reviewed", "robots_reviewed"],
        )
    ])

    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT),
        "--date", "2026-07-04",
        "--terms-reviewed-json", str(review),
        "--source", "forebet",
        "--out", str(out),
        "--sqlite-db", str(db),
        "--require-at-least-one-pick",
    ])
    assert mod.main() != 0


def test_fixture_snapshot_parser_still_works_when_live_fetch_is_blocked():
    fixture = dispatch_extract(
        make_raw("forebet", "https://www.forebet.com/en/football-tips-and-predictions-for-today", "<table><tr><td>Australia Egypt 03/07/2026 20:00 32 34 35 2 0-1 0 - 1 1.33</td></tr></table>"),
        "forebet",
    )
    blocked = ExtractionResult(
        source_id="forebet",
        url="https://www.forebet.com/en/football-tips-and-predictions-for-today",
        verdict=ExtractorVerdict.EMPTY,
        picks=[],
        warnings=["fetch_block:compliance_block:ComplianceVerdict.BLOCK_ROBOTS:robots.txt disallows target"],
        block_reason="BLOCK_ROBOTS:robots.txt disallows target",
        robots_blocked_live=True,
        live_fetch_allowed=False,
        fallback="fixture_snapshot_only",
    )
    payload = build_payload([blocked])
    assert fixture.pick_count == 1
    assert payload["total_picks"] == 0
    assert payload["all_picks"] == []
    assert payload["blocked_sources"][0]["source_id"] == "forebet"


def test_review_gate_accepts_explicit_cookie_policy_fields():
    mod = _load_live_module()
    data = {
        "source_reviews": {
            "zawodtyper": {
                "status": "allow_live_dry_run",
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "allow_public_xhr_capture": True,
                "cookie_policy": "no_cookie",
                "allowed_cookie_names": ["SRV"],
                "reviewed_by": "Mateusz Kozioł",
                "reviewed_at_utc": "2026-07-05T22:00:00Z",
                "notes": "Public XHR review for NP_ajax.php completed.",
            }
        }
    }
    allowed, reason = mod.review_allows_source(data, "zawodtyper")
    assert allowed is True
    assert reason == "review_allows_live_dry_run"


@pytest.mark.skipif(shutil.which("fish") is None, reason="fish shell is not installed")
def test_tipster_live_summary_supports_db_alias(tmp_path):
    payload = {
        "schema_version": "tipster_consensus_v2.3",
        "total_picks": 1,
        "sources_with_picks": 1,
        "blocked_sources": [],
        "skipped_sources": [],
        "sources": [{
            "source_id": "zawodtyper",
            "expected_visible_count": None,
            "extracted_count": 1,
            "coverage_ratio": None,
            "coverage_status": "FULL_OR_ACCEPTABLE",
            "warnings": ["public_xhr_transport:selected_cookie_policy=no_cookie"],
        }],
        "all_picks": [{
            "sport": "football",
            "event": "Polska vs Niemcy",
            "market": "Powyżej 2.5",
            "odds": 1.8,
            "extraction_quality": 0.8,
            "pipeline_use": ["s2_tipster_evidence"],
        }],
    }
    json_path = tmp_path / "artifact.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "artifact.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table tipster_picks_v2 (id integer primary key)")
        conn.execute("create table tipster_consensus_v2 (id integer primary key)")
        conn.commit()
    script = Path(__file__).resolve().parents[2] / "scripts/pipeline_steps/tipster_live_summary.fish"
    result = subprocess.run(
        ["fish", str(script), f"--json={json_path}", f"--db={db_path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "total_picks=1" in result.stdout
    assert "source::zawodtyper::warning::public_xhr_transport:selected_cookie_policy=no_cookie" in result.stdout
