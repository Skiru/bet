from __future__ import annotations

import json
from pathlib import Path

BENCHMARK_DIR = Path("tests/fixtures/football_data_foundation/source_admission_benchmark")


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


L2B_DIR = Path("tests/fixtures/football_data_foundation/source_admission_benchmark_l2b")


def test_l2b_public_raw_reviewability_audit_exists() -> None:
    # Check that public raw reviewability audit files exist and follow the schema
    audit_json_path = L2B_DIR / "00_l2a_public_raw_reviewability_audit.json"
    audit_md_path = L2B_DIR / "00_l2a_public_raw_reviewability_audit.md"

    assert audit_json_path.exists()
    assert audit_md_path.exists()

    audit_data = json.loads(audit_json_path.read_text(encoding="utf-8"))
    assert audit_data["schema_version"] == "2.0"
    assert "audit_status" in audit_data
    assert "files_audited" in audit_data

    for f in audit_data["files_audited"]:
        assert "file_path" in f
        assert f["exact_start_sha_raw_url"].startswith("https://raw.githubusercontent.com/")
        assert f["public_raw_lf_count"] > 0
        assert f["local_lf_count"] > 0
        assert f["public_raw_reviewable"] is True
        assert f["contradiction_between_local_and_public"] is False


def test_l2b_source_files_not_collapsed() -> None:
    # Source files are not one-line collapsed or tiny
    src_files = [
        "src/bet/enrichment/football_data_foundation/source_admission_benchmark.py",
        "src/bet/enrichment/football_data_foundation/source_probe_runner.py",
        "src/bet/enrichment/football_data_foundation/source_probe_contracts.py"
    ]
    for s in src_files:
        p = Path(s)
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert len(lines) >= 30
        for line in lines:
            assert len(line) <= 140


def test_l2b_json_reports_pretty_printed() -> None:
    # All JSON files in L2B must be pretty printed and under 240 chars line length
    for p in L2B_DIR.glob("**/*.json"):
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert len(lines) > 2
        for line in lines:
            assert len(line) <= 240


def test_l2b_synthetic_fixtures_do_not_increase_real_value() -> None:
    # Synthetic fixtures must not increase real value score
    scorecard_path = L2B_DIR / "05_corrected_source_value_scorecard.json"
    assert scorecard_path.exists()
    scorecards = json.loads(scorecard_path.read_text(encoding="utf-8"))["scorecards"]

    for s in scorecards:
        if s["proof_level"] == "SYNTHETIC_CONTRACT_PROOF":
            assert s["real_value_facts_count"] == 0
            assert s["contract_facts_count"] > 0


def test_l2b_docs_capability_only_cannot_admit_measured_value() -> None:
    # docs capability only does not admit source as measured value
    scorecard_path = L2B_DIR / "05_corrected_source_value_scorecard.json"
    scorecards = json.loads(scorecard_path.read_text(encoding="utf-8"))["scorecards"]

    for s in scorecards:
        if s["proof_level"] == "DOCS_CAPABILITY_ONLY":
            assert s["real_value_facts_count"] == 0
            assert s["contract_facts_count"] == 0
            assert s["corrected_recommended_role"] in {"OFFLINE_EVIDENCE_ONLY", "DEPENDENCY_BLOCKED", "REJECT_LOW_VALUE"}


def test_l2b_missing_credential_is_not_low_value() -> None:
    # SportDB and football-data.org must not be coerced to low value/metadata-only
    scorecard_path = L2B_DIR / "05_corrected_source_value_scorecard.json"
    scorecards = json.loads(scorecard_path.read_text(encoding="utf-8"))["scorecards"]

    for s in scorecards:
        fam = s["source_family"]
        if fam in {"sportdb", "football-data.org"}:
            assert s["corrected_recommended_role"] in {"CURRENT_SHADOW_CANDIDATE", "REFERENCE_CANDIDATE"}
            assert "REJECT" not in s["next_action"]


def test_l2b_parser_gap_distinct_from_low_value() -> None:
    # parser gap is distinct from low value
    scorecard_path = L2B_DIR / "05_corrected_source_value_scorecard.json"
    scorecards = json.loads(scorecard_path.read_text(encoding="utf-8"))["scorecards"]

    for s in scorecards:
        fam = s["source_family"]
        if fam in {"fotmob_probe", "sofascore_rich_probe"}:
            assert s["corrected_recommended_role"] == "OFFLINE_EVIDENCE_ONLY"
            assert "parser_gap" in s["remaining_blockers"]


def test_l2b_dependency_missing_distinct_from_low_value() -> None:
    # dependency missing is distinct from low value
    scorecard_path = L2B_DIR / "05_corrected_source_value_scorecard.json"
    scorecards = json.loads(scorecard_path.read_text(encoding="utf-8"))["scorecards"]

    for s in scorecards:
        fam = s["source_family"]
        if fam in {"statsbombpy", "scraperfc_sofascore", "socceraction", "kloppy", "floodlight", "mplsoccer"}:
            assert s["corrected_recommended_role"] == "DEPENDENCY_BLOCKED"


def test_l2b_historical_cannot_confirm_current_live() -> None:
    # historical datasets cannot confirm current live score
    scorecards = json.loads((L2B_DIR / "05_corrected_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    for s in scorecards:
        if s["proof_level"] == "REAL_LOCAL_OPEN_DATA_PROOF":
            assert s["corrected_recommended_role"] in {"HISTORICAL_ENRICHMENT_CANDIDATE", "REFERENCE_CANDIDATE"}


def test_l2b_scorecard_gates_override() -> None:
    # scorecard hard gates override numeric score
    scorecards = json.loads((L2B_DIR / "05_corrected_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    for s in scorecards:
        if len(s["remaining_blockers"]) > 0 and s["source_family"] != "espn_live_baseline":
            assert s["corrected_recommended_role"] in {
                "CONNECTOR_REPLAY_CANDIDATE", "OFFLINE_EVIDENCE_ONLY", "DEPENDENCY_BLOCKED",
                "CURRENT_SHADOW_CANDIDATE", "REFERENCE_CANDIDATE", "REJECT_LOW_VALUE"
            }


def test_l2b_no_selectable_decisions() -> None:
    # No decision contains SELECTABLE, CERTIFIED_SELECTABLE, PRODUCTION_READY
    decisions_path = L2B_DIR / "06_corrected_admission_decision_matrix.json"
    assert decisions_path.exists()
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"]

    forbidden = {"SELECTABLE", "CERTIFIED_SELECTABLE", "PRODUCTION_READY"}
    for d in decisions:
        dec = d["corrected_decision"]
        for f in forbidden:
            assert f not in dec


def test_l2b_next_implementation_plan_excludes_rejected() -> None:
    # Next implementation plan excludes rejected sources
    plan_path = L2B_DIR / "07_corrected_next_implementation_plan.json"
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))["plan_steps"]

    admitted_fams = {p["source_family"] for p in plan}
    scorecards = json.loads((L2B_DIR / "05_corrected_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]

    deferred_or_rejected = {
        s["source_family"] for s in scorecards
        if s["corrected_recommended_role"] in {"DEPENDENCY_BLOCKED", "REJECT_LOW_VALUE"}
    }

    for f in admitted_fams:
        assert f not in deferred_or_rejected


def test_l2b_no_secrets_serialized() -> None:
    # No secrets are serialized
    for fpath in L2B_DIR.glob("**/*.json"):
        content = fpath.read_text(encoding="utf-8")
        assert "api_key" not in content.lower() or "present" in content.lower()
        assert "password" not in content.lower()
        assert "token" not in content.lower()


def test_l2b_manifest_hash_integrity() -> None:
    # Manifest hash sidecar matches manifest bytes
    manifest_path = L2B_DIR / "l2b_corrected_admission_manifest.json"
    sha_path = L2B_DIR / "l2b_corrected_admission_manifest.sha256"

    assert manifest_path.exists()
    assert sha_path.exists()

    import hashlib
    computed_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    recorded_sha = sha_path.read_text(encoding="utf-8").strip()

    assert computed_sha == recorded_sha


def test_l2b_public_raw_thresholds() -> None:
    # Verifies that public raw line thresholds are met locally
    s_path = "src/bet/enrichment/football_data_foundation/source_admission_benchmark.py"
    assert Path(s_path).read_text(encoding="utf-8").count("\n") >= 800
    assert Path("src/bet/enrichment/football_data_foundation/source_probe_runner.py").read_text(encoding="utf-8").count("\n") >= 350
    t_path = "tests/enrichment/football_data_foundation/test_source_admission_benchmark.py"
    assert Path(t_path).read_text(encoding="utf-8").count("\n") >= 250
    assert (L2B_DIR / "05_corrected_source_value_scorecard.json").read_text(encoding="utf-8").count("\n") >= 250
    assert (L2B_DIR / "06_corrected_admission_decision_matrix.json").read_text(encoding="utf-8").count("\n") >= 100
    assert (L2B_DIR / "07_corrected_next_implementation_plan.md").read_text(encoding="utf-8").count("\n") >= 20


def test_l2b_markdown_plans_multiline() -> None:
    # Verify that plan and validation markdown files have multiple lines and are formatted correctly
    for md_path in L2B_DIR.glob("*.md"):
        content = md_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert len(lines) >= 10
        # Check there are no carriage returns
        assert "\r" not in content


def test_l2b_proof_level_and_scorecard_facts_cannot_diverge() -> None:
    # Verify that proof-level and scorecard fact counts cannot diverge (synthetic or docs-only must have 0 real facts)
    scorecards = json.loads((L2B_DIR / "05_corrected_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    for s in scorecards:
        if s["proof_level"] in {"SYNTHETIC_CONTRACT_PROOF", "DOCS_CAPABILITY_ONLY", "NO_PROOF"}:
            assert s["real_value_facts_count"] == 0


def test_l2b_synthetic_contract_proof_cannot_admit_direct_implementation() -> None:
    # Verify that synthetic contract proof cannot produce direct implementation admission
    scorecards = json.loads((L2B_DIR / "05_corrected_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    decisions = json.loads((L2B_DIR / "06_corrected_admission_decision_matrix.json").read_text(encoding="utf-8"))["decisions"]

    dec_map = {d["source_family"]: d for d in decisions}
    for s in scorecards:
        if s["proof_level"] == "SYNTHETIC_CONTRACT_PROOF":
            fam = s["source_family"]
            dec = dec_map[fam]["corrected_decision"]
            assert dec in {
                "DEFER_REAL_PROOF_REQUIRED",
                "CONTRACT_READY_NEEDS_REAL_PROOF",
                "DEFER_CREDENTIAL_REQUIRED",
                "DEFER_CONNECTOR_REPLAY_CAPTURE"
            }


def test_l2b_docs_only_proof_cannot_admit_direct_implementation() -> None:
    # Verify that docs-only proof cannot produce implementation admission
    scorecards = json.loads((L2B_DIR / "05_corrected_source_value_scorecard.json").read_text(encoding="utf-8"))["scorecards"]
    decisions = json.loads((L2B_DIR / "06_corrected_admission_decision_matrix.json").read_text(encoding="utf-8"))["decisions"]

    dec_map = {d["source_family"]: d for d in decisions}
    for s in scorecards:
        if s["proof_level"] == "DOCS_CAPABILITY_ONLY":
            fam = s["source_family"]
            dec = dec_map[fam]["corrected_decision"]
            assert dec in {
                "DEFER_REAL_PROOF_REQUIRED",
                "DEFER_RESEARCH_REQUIRED",
                "REJECT_LOW_VALUE",
                "REJECT_OUT_OF_SCOPE"
            }


def test_l2b_missing_credential_cannot_admit_measured_current_source() -> None:
    # Verify that missing credentials cannot admit measured current source
    decisions = json.loads((L2B_DIR / "06_corrected_admission_decision_matrix.json").read_text(encoding="utf-8"))["decisions"]
    for d in decisions:
        if d["source_family"] in {"sportdb", "football-data.org"}:
            assert d["corrected_decision"] == "DEFER_CREDENTIAL_REQUIRED"


def test_l2b_implementation_plan_cannot_include_source_absent_from_decision_matrix() -> None:
    # Verify that implementation plan cannot include source absent from decision matrix
    plan = json.loads((L2B_DIR / "07_corrected_next_implementation_plan.json").read_text(encoding="utf-8"))["plan_steps"]
    decisions = json.loads((L2B_DIR / "06_corrected_admission_decision_matrix.json").read_text(encoding="utf-8"))["decisions"]

    decision_fams = {d["source_family"] for d in decisions}
    for p in plan:
        assert p["source_family"] in decision_fams


def test_l2b_no_production_activation_fields_are_true() -> None:
    # Verify no production activation fields are true
    proof = json.loads((L2B_DIR / "no_production_activation_proof.json").read_text(encoding="utf-8"))
    assert proof["no_production_activation"] is True
    for k, v in proof["checks_executed"].items():
        assert v is True


def test_l2b_and_l2a_json_pretty_printed() -> None:
    # JSON reports are pretty printed (i.e. have multiple lines) and are not single line
    for p in L2B_DIR.glob("**/*.json"):
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        assert len(lines) > 5


def test_markdown_next_plan_multiline() -> None:
    # Markdown next plan is multi-line
    plan_md = L2B_DIR / "07_corrected_next_implementation_plan.md"
    assert plan_md.exists()
    lines = plan_md.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 20


def test_source_files_exceed_lf_thresholds() -> None:
    # source files exceed LF thresholds
    # source_admission_benchmark.py: LF >= 800
    # source_probe_runner.py: LF >= 350
    # source_probe_contracts.py: LF >= 30
    assert len(Path(
        "src/bet/enrichment/football_data_foundation/"
        "source_admission_benchmark.py"
    ).read_text(encoding="utf-8").splitlines()) >= 800
    assert len(Path("src/bet/enrichment/football_data_foundation/source_probe_runner.py").read_text(encoding="utf-8").splitlines()) >= 350
    assert len(Path("src/bet/enrichment/football_data_foundation/source_probe_contracts.py").read_text(encoding="utf-8").splitlines()) >= 30


def test_no_python_source_line_exceeds_140() -> None:
    # No Python source has max line > 140
    src_files = [
        "src/bet/enrichment/football_data_foundation/source_admission_benchmark.py",
        "src/bet/enrichment/football_data_foundation/source_probe_runner.py",
        "src/bet/enrichment/football_data_foundation/source_probe_contracts.py",
        "tests/enrichment/football_data_foundation/test_source_admission_benchmark.py"
    ]
    for sf in src_files:
        lines = Path(sf).read_text(encoding="utf-8").splitlines()
        for line in lines:
            assert len(line) <= 140


def test_no_report_line_exceeds_240() -> None:
    # No report has max line > 240 (for JSON reports and next plan Markdown)
    for p in L2B_DIR.glob("**/*.json"):
        lines = p.read_text(encoding="utf-8").splitlines()
        for line in lines:
            assert len(line) <= 240

    plan_md = L2B_DIR / "07_corrected_next_implementation_plan.md"
    assert plan_md.exists()
    for line in plan_md.read_text(encoding="utf-8").splitlines():
        assert len(line) <= 240


def test_public_raw_verifier_sha_validation() -> None:
    from scripts.verify_public_raw_exact_sha import is_valid_sha
    assert is_valid_sha("df487b2fced1da6bc72a66754a9e2793d8de084d") is True
    assert is_valid_sha("main") is False
    assert is_valid_sha("feat/multisport-enrichment-v1") is False
    assert is_valid_sha("12345") is False


def test_public_raw_verifier_builds_exact_sha_urls_only() -> None:
    # Check that public raw URL build does not accept branch names and builds exact sha url
    import subprocess
    import sys
    res = subprocess.run(
        [sys.executable, "scripts/verify_public_raw_exact_sha.py", "main", "some_path.py"],
        capture_output=True,
        text=True
    )
    assert res.returncode != 0
    assert "Invalid END_SHA format" in res.stderr


def test_mismatch_detection_on_different_bytes() -> None:
    from unittest.mock import MagicMock, patch

    import scripts.verify_public_raw_exact_sha as verifier

    # Mock urllib to return dummy bytes
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.getcode.return_code = 200
    mock_response.getcode.return_value = 200
    mock_response.read.return_value = b"mismatched_public_bytes_different_from_git"

    # Mock subprocess to return different git bytes
    mock_subprocess = MagicMock()
    mock_subprocess.returncode = 0
    mock_subprocess.stdout = b"git_bytes_here"

    with patch("urllib.request.urlopen", return_value=mock_response), \
         patch("subprocess.run", return_value=mock_subprocess), \
         patch("sys.exit"):

        # We need to temporarily mock sys.argv
        with patch("sys.argv", ["verify_public_raw_exact_sha.py", "df487b2fced1da6bc72a66754a9e2793d8de084d", "some_path.py"]):
            # We capture stdout to inspect JSON
            from io import StringIO
            with patch("sys.stdout", new=StringIO()) as fake_out:
                verifier.main()

                # Check JSON output
                output = json.loads(fake_out.getvalue())
                assert output["overall_success"] is False
                assert output["results"][0]["bytes_match"] is False
                assert output["results"][0]["status"] == "FAILED"
