# ruff: noqa: E501, I001

from __future__ import annotations

import hashlib
import json
import os
import socket
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

import pytest
import requests

from bet.api_clients.highlightly import HighlightlyClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration import telemetry_wrapper
from bet.integration.evidence import build_replay_transport
from bet.integration.source_result import SourceResultStatus


def to_canonical_json(obj) -> str:
    def simplify(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value):
            return simplify(asdict(value))
        if isinstance(value, dict):
            return {key: simplify(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [simplify(item) for item in value]
        return value

    return json.dumps(simplify(obj), sort_keys=True, separators=(",", ":"))


def _block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Unexpected outbound network access during replay")

    monkeypatch.setattr(socket, "create_connection", blocked)

    def blocked_connect(self, address):
        raise AssertionError(f"Unexpected socket connection during replay: {address}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect, raising=True)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Unexpected requests.get during replay")
        ),
    )
    try:
        import urllib3.util.connection

        monkeypatch.setattr(urllib3.util.connection, "create_connection", blocked)
    except Exception:
        pass


def _resolve_highlightly_key() -> tuple[str | None, str]:
    if os.getenv("HIGHLIGHTLY_API_KEY"):
        return os.environ["HIGHLIGHTLY_API_KEY"], "HIGHLIGHTLY_API_KEY"
    if os.getenv("RAPIDAPI_KEY"):
        return os.environ["RAPIDAPI_KEY"], "RAPIDAPI_KEY"
    return None, "HIGHLIGHTLY_API_KEY"


def _evidence_sha256(evidence_root: Path, result) -> str:
    ref = result.evidence_refs[0]
    raw_path = evidence_root / "objects" / ref.object_sha256[:2] / ref.object_sha256
    return hashlib.sha256(raw_path.read_bytes()).hexdigest()


def _proof_entry(
    *,
    evidence_root: Path,
    result,
    provider: str,
    operation: str,
    capability: str,
    competition_scope: str,
    season_scope: str,
    mode: str,
    request_path_without_secret: str,
    request_params: dict,
    key_alias_used: str,
) -> dict:
    value = result.value or {}
    normalized_payload_sha256 = hashlib.sha256(
        to_canonical_json(value).encode("utf-8")
    ).hexdigest()
    return {
        "provider": provider,
        "operation": operation,
        "capability": capability,
        "competition_scope": competition_scope,
        "season_scope": season_scope,
        "mode": mode,
        "request_path_without_secret": request_path_without_secret,
        "request_params": request_params,
        "response_status": result.http_status,
        "raw_response_sha256": _evidence_sha256(evidence_root, result),
        "normalized_payload_sha256": normalized_payload_sha256,
        "accepted_count": result.parser_diagnostics.get("accepted_count", 0),
        "rejected_count": result.parser_diagnostics.get("rejected_count", 0),
        "evidence_bundle_id": result.bundle_id,
        "parser_version": result.parser_version,
        "key_alias_used": key_alias_used,
        "rate_limit_headers": result.quota_metadata,
    }


def test_highlightly_live_and_replay(tmp_path, monkeypatch):
    from dotenv import load_dotenv

    load_dotenv()
    key, key_alias = _resolve_highlightly_key()
    if not key:
        pytest.skip("Highlightly key not found in environment or .env")

    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(evidence_root))

    league_id = "33973"
    match_id = "1028343227"
    home_team_id = "30569"
    away_team_id = "39930"

    client = HighlightlyClient(rate_limiter=RateLimiter())
    client.api_key = key

    league_res = client.discover_league_result("Premier League", "England", 2025)
    assert league_res.status is SourceResultStatus.SUCCESS
    assert league_res.value is not None
    assert any(
        row["provider_league_id"] == league_id for row in league_res.value["rows"]
    )

    match_res = client.discover_matches_result(league_id, 2025, limit=20)
    assert match_res.status is SourceResultStatus.SUCCESS
    assert match_res.value is not None
    assert match_res.value["accepted_count"] > 0

    home_form_res = client.get_last_five_games_result(home_team_id)
    assert home_form_res.status is SourceResultStatus.SUCCESS
    assert home_form_res.value is not None
    assert home_form_res.value["accepted_count"] == 5

    away_form_res = client.get_last_five_games_result(away_team_id)
    assert away_form_res.status is SourceResultStatus.SUCCESS
    assert away_form_res.value is not None
    assert away_form_res.value["accepted_count"] == 5

    h2h_res = client.get_head_to_head_result(home_team_id, away_team_id)
    assert h2h_res.status in {
        SourceResultStatus.SUCCESS,
        SourceResultStatus.VALID_EMPTY,
    }
    assert h2h_res.value is not None

    statistics_res = client.get_statistics_result(
        match_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )
    assert statistics_res.status is SourceResultStatus.SUCCESS
    assert statistics_res.value is not None
    assert statistics_res.value["raw_stat_field_names"] == [
        "Expected Goals",
        "Big Chances Created",
        "Free Kicks",
        "Throw-Ins",
        "Goal Kicks",
        "Shots accuracy",
        "Shots on target",
        "Shots off target",
        "Blocked shots",
        "Shots within penalty area",
        "Shots outside penalty area",
        "Fouls",
        "Corners",
        "Offsides",
        "Possession",
        "Yellow cards",
        "Goalkeeper saves",
        "Total passes",
        "Successful passes",
        "Failed passes",
    ]
    assert statistics_res.value["missing_target_metrics"] == ["Red cards"]

    live_proofs = [
        _proof_entry(
            evidence_root=evidence_root,
            result=league_res,
            provider="highlightly",
            operation="league_discovery",
            capability="current_discovery",
            competition_scope="football:eng.1",
            season_scope="current-season-completed",
            mode="shadow",
            request_path_without_secret="/leagues",
            request_params={
                "leagueName": "Premier League",
                "countryName": "England",
                "season": 2025,
            },
            key_alias_used=key_alias,
        ),
        _proof_entry(
            evidence_root=evidence_root,
            result=match_res,
            provider="highlightly",
            operation="match_discovery",
            capability="current_discovery",
            competition_scope="football:eng.1",
            season_scope="current-season-completed",
            mode="shadow",
            request_path_without_secret="/matches",
            request_params={"leagueId": league_id, "season": 2025, "limit": 20},
            key_alias_used=key_alias,
        ),
        _proof_entry(
            evidence_root=evidence_root,
            result=home_form_res,
            provider="highlightly",
            operation="home_form",
            capability="current_form",
            competition_scope="football:eng.1",
            season_scope="current-season-completed",
            mode="shadow",
            request_path_without_secret="/last-five-games",
            request_params={"teamId": home_team_id},
            key_alias_used=key_alias,
        ),
        _proof_entry(
            evidence_root=evidence_root,
            result=away_form_res,
            provider="highlightly",
            operation="away_form",
            capability="current_form",
            competition_scope="football:eng.1",
            season_scope="current-season-completed",
            mode="shadow",
            request_path_without_secret="/last-five-games",
            request_params={"teamId": away_team_id},
            key_alias_used=key_alias,
        ),
        _proof_entry(
            evidence_root=evidence_root,
            result=h2h_res,
            provider="highlightly",
            operation="head_to_head",
            capability="historical_form_h2h",
            competition_scope="football:eng.1",
            season_scope="current-season-completed",
            mode="shadow",
            request_path_without_secret="/head-2-head",
            request_params={"teamIdOne": home_team_id, "teamIdTwo": away_team_id},
            key_alias_used=key_alias,
        ),
        _proof_entry(
            evidence_root=evidence_root,
            result=statistics_res,
            provider="highlightly",
            operation="statistics",
            capability="detailed_metrics",
            competition_scope="football:eng.1",
            season_scope="current-season-completed",
            mode="shadow",
            request_path_without_secret=f"/statistics/{match_id}",
            request_params={},
            key_alias_used=key_alias,
        ),
    ]

    bundle_ids = [proof["evidence_bundle_id"] for proof in live_proofs]
    replay_transports = [
        build_replay_transport(bundle_id, evidence_root) for bundle_id in bundle_ids
    ]

    def replay_wrap_request(**kwargs):
        last_error = None
        for transport in replay_transports:
            try:
                return transport(**kwargs)
            except AssertionError as exc:
                last_error = exc
        raise last_error or AssertionError("No replay transport matched the request")

    monkeypatch.setattr(telemetry_wrapper, "wrap_request", replay_wrap_request)
    _block_network(monkeypatch)

    replay_client = HighlightlyClient(rate_limiter=RateLimiter())
    replay_client.api_key = key

    replay_results = [
        replay_client.discover_league_result("Premier League", "England", 2025),
        replay_client.discover_matches_result(league_id, 2025, limit=20),
        replay_client.get_last_five_games_result(home_team_id),
        replay_client.get_last_five_games_result(away_team_id),
        replay_client.get_head_to_head_result(home_team_id, away_team_id),
        replay_client.get_statistics_result(
            match_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        ),
    ]

    for live_result, replay_result, live_proof in zip(
        [league_res, match_res, home_form_res, away_form_res, h2h_res, statistics_res],
        replay_results,
        live_proofs,
        strict=True,
    ):
        assert replay_result.status is live_result.status
        assert (
            _evidence_sha256(evidence_root, replay_result)
            == live_proof["raw_response_sha256"]
        )
        assert (
            hashlib.sha256(
                to_canonical_json(replay_result.value).encode("utf-8")
            ).hexdigest()
            == live_proof["normalized_payload_sha256"]
        )
        assert (
            replay_result.parser_diagnostics.get("accepted_count", 0)
            == live_proof["accepted_count"]
        )
        assert (
            replay_result.parser_diagnostics.get("rejected_count", 0)
            == live_proof["rejected_count"]
        )

    assert replay_results[2].value["matches"] == home_form_res.value["matches"]
    assert replay_results[3].value["matches"] == away_form_res.value["matches"]
    assert replay_results[4].value["matches"] == h2h_res.value["matches"]
    assert (
        replay_results[5].value["raw_stat_field_names"]
        == statistics_res.value["raw_stat_field_names"]
    )
    assert (
        replay_results[5].value["normalized_metric_names"]
        == statistics_res.value["normalized_metric_names"]
    )
    assert replay_results[5].value["missing_target_metrics"] == ["Red cards"]

    replay_proof_id = hashlib.sha256(
        to_canonical_json(
            {
                "bundle_ids": bundle_ids,
                "operations": live_proofs,
                "replay_hashes": [
                    hashlib.sha256(
                        to_canonical_json(result.value).encode("utf-8")
                    ).hexdigest()
                    for result in replay_results
                ],
            }
        ).encode("utf-8")
    ).hexdigest()

    summary = {
        "proof_id": replay_proof_id,
        "provider": "highlightly",
        "scope": "football:eng.1/current-season-completed/shadow",
        "evidence_bundle_ids": bundle_ids,
        "raw_stat_field_names": statistics_res.value["raw_stat_field_names"],
        "missing_target_metrics": statistics_res.value["missing_target_metrics"],
        "operations": live_proofs,
        "replay_verification": "PASS",
        "key_alias_used": key_alias,
        "secret_safe": True,
    }

    artifact_dir = Path(".kilo/artifacts/football_truthful_live")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "highlightly_proof_summary.json"
    artifact_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    summary_text = artifact_path.read_text(encoding="utf-8")
    assert key not in summary_text
    assert "HIGHLIGHTY_API_KEY" not in summary_text
