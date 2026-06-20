from __future__ import annotations

import json
from pathlib import Path

BENCHMARK_DIR = Path("reports/football_data_foundation/source_admission_benchmark")


def test_inventory_completeness() -> None:
    # All known source families appear in inventory
    inventory_path = BENCHMARK_DIR / "01_existing_inventory.json"
    assert inventory_path.exists()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))["inventory"]

    families = {item["source_family"] for item in inventory}
    expected_families = {
        "espn_live_baseline",
        "sportdb",
        "football-data.org",
        "soccerdata_clubelo",
        "soccerdata_espn",
        "soccerdata_fbref",
        "soccerdata_understat",
        "soccerdata_whoscored",
        "soccerdata_sofascore",
        "soccerdata_sofifa",
        "soccerdata_matchhistory",
        "soccerdata_fivethirtyeight",
        "statsbomb_open_data",
        "statsbombpy",
        "kaggle_european_soccer",
        "openfootball",
        "fotmob_probe",
        "sofascore_rich_probe",
        "scraperfc_sofascore",
        "socceraction",
        "kloppy",
        "floodlight",
        "mplsoccer"
    }
    assert expected_families.issubset(families)


def test_existence_alone_cannot_admit() -> None:
    # Existence alone cannot admit a source
    # Every admitted source must have facts_extracted_count > 0 and meet hard gates
    scorecard_path = BENCHMARK_DIR / "05_source_value_scorecard.json"
    assert scorecard_path.exists()
    scorecards = json.loads(scorecard_path.read_text(encoding="utf-8"))["scorecards"]

    for s in scorecards:
        # If can participate in next phase, recommended role is ADMITted
        if s["can_participate_next_phase"] and s["recommended_role"] != "ACCEPTED_BASELINE":
            assert s["recommended_role"] in {"HISTORICAL_ENRICHMENT_CANDIDATE", "REFERENCE_CANDIDATE"}
            # Admitted sources must not be blocked by dependency or facts missing
            assert "dependency_missing" not in s["hard_gates_failed"]
            assert "no_facts_extracted" not in s["hard_gates_failed"]


def test_no_facts_extracted_prevents_enrichment_admission() -> None:
    # facts_extracted_count=0 prevents enrichment admission
    scorecards = json.loads((BENCHMARK_DIR / "05_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    offline_probes = json.loads((BENCHMARK_DIR / "03_offline_value_probe.json").read_text(encoding="utf-8"))["offline_probes"]

    probe_map = {p["source_family"]: p for p in offline_probes}

    for s in scorecards:
        fam = s["source_family"]
        if fam == "espn_live_baseline":
            continue
        p = probe_map[fam]
        if p["facts_extracted_count"] == 0:
            assert s["recommended_role"] not in {"HISTORICAL_ENRICHMENT_CANDIDATE"}


def test_historical_datasets_cannot_be_current_live() -> None:
    # historical datasets cannot become current live source
    scorecards = json.loads((BENCHMARK_DIR / "05_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    offline_probes = json.loads((BENCHMARK_DIR / "03_offline_value_probe.json").read_text(encoding="utf-8"))["offline_probes"]

    probe_map = {p["source_family"]: p for p in offline_probes}

    for s in scorecards:
        fam = s["source_family"]
        if fam == "espn_live_baseline":
            continue
        p = probe_map[fam]
        if p["current_or_historical"] == "historical":
            assert "historical_dataset_cannot_confirm_current_live_score" in s["hard_gates_failed"]


def test_missing_credentials_handling() -> None:
    # missing credential gives credential-blocked, not fake success
    scorecards = json.loads((BENCHMARK_DIR / "05_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]

    # football-data.org and sportdb should report credential-blocked if missing credentials
    for s in scorecards:
        fam = s["source_family"]
        if fam in {"football-data.org", "sportdb"} and not s.get("score_breakdown", {}).get("live_api_score"):
            assert "missing_credential_blocks_live_api_proof" in s["hard_gates_failed"]
            assert s["recommended_role"] in {"CURRENT_SHADOW_CANDIDATE", "METADATA_ONLY", "CREDENTIAL_BLOCKED"}


def test_missing_dependency_blocking() -> None:
    # dependency missing gives dependency-blocked
    scorecards = json.loads((BENCHMARK_DIR / "05_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    for s in scorecards:
        fam = s["source_family"]
        if fam in {"statsbombpy", "scraperfc_sofascore", "socceraction", "kloppy", "floodlight", "mplsoccer"}:
            assert "dependency_missing" in s["hard_gates_failed"]
            assert s["recommended_role"] in {"DEPENDENCY_BLOCKED", "OFFLINE_EVIDENCE_ONLY"}


def test_scorecard_hard_gates_override() -> None:
    # scorecard hard gates override numeric score
    scorecards = json.loads((BENCHMARK_DIR / "05_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    for s in scorecards:
        if len(s["hard_gates_failed"]) > 0 and s["source_family"] != "espn_live_baseline":
            assert not s["can_participate_next_phase"] or s["source_family"] in {
                "statsbomb_open_data", "kaggle_european_soccer", "openfootball"
            }


def test_no_forbidden_admissions() -> None:
    # admission decisions cannot contain SELECTABLE, CERTIFIED_SELECTABLE, PRODUCTION_READY
    decisions_path = BENCHMARK_DIR / "06_admission_decision_matrix.json"
    assert decisions_path.exists()
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"]

    forbidden = {"SELECTABLE", "CERTIFIED_SELECTABLE", "PRODUCTION_READY"}
    for d in decisions:
        dec = d["decision"]
        for f in forbidden:
            assert f not in dec


def test_next_implementation_plan_excludes_deferred_and_rejected() -> None:
    # next implementation plan excludes rejected/deferred sources
    plan_path = BENCHMARK_DIR / "07_next_implementation_plan.json"
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))["plan_steps"]

    admitted_fams = {p["source_family"] for p in plan}
    scorecards = json.loads((BENCHMARK_DIR / "05_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]

    deferred_or_rejected = {
        s["source_family"] for s in scorecards
        if s["recommended_role"] in {"DEPENDENCY_BLOCKED", "CREDENTIAL_BLOCKED", "REJECTED_LOW_VALUE"}
        or not s["can_participate_next_phase"]
    }

    for f in admitted_fams:
        assert f not in deferred_or_rejected


def test_no_secrets_serialized() -> None:
    # No secrets are serialized
    for fpath in BENCHMARK_DIR.glob("**/*.json"):
        content = fpath.read_text(encoding="utf-8")
        assert "api_key" not in content.lower() or "present" in content.lower()
        assert "password" not in content.lower()
        assert "token" not in content.lower()


def test_manifest_hash_integrity() -> None:
    # manifest hash sidecar matches manifest bytes
    manifest_path = BENCHMARK_DIR / "l2a_source_admission_manifest.json"
    sha_path = BENCHMARK_DIR / "l2a_source_admission_manifest.sha256"

    assert manifest_path.exists()
    assert sha_path.exists()

    import hashlib
    computed_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    recorded_sha = sha_path.read_text(encoding="utf-8").strip()

    assert computed_sha == recorded_sha
