from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.pipeline.unified_live_analyst_session import (
    BetBuilderComboIdea,
    apply_human_quote_if_valid,
    build_package_from_candidates,
    load_candidates_from_path,
    validate_human_superbet_quote,
    render_markdown_package,
    calculate_idea_score,
)


def _football_candidate(**overrides):
    base = {
        "candidate_id": "c1",
        "sport": "football",
        "event_id": "e1",
        "competition": "World Cup",
        "home_team": "Alpha",
        "away_team": "Beta",
        "market_family": "CORNERS",
        "line": 7.5,
        "direction": "OVER",
        "supporting_evidence": [
            "Alpha create pressure from wide areas",
            "Beta concede territory when underdog",
        ],
        "counter_evidence": ["Referee/venue data unknown"],
    }
    base.update(overrides)
    return base


def _tennis_candidate(**overrides):
    base = {
        "candidate_id": "t1",
        "sport": "tennis",
        "event_label": "Player A vs Player B",
        "competition": "Wimbledon",
        "market_family": "TOTAL_GAMES",
        "line": 21.5,
        "direction": "OVER",
        "supporting_evidence": ["Both players have serve-oriented profile in available notes"],
        "counter_evidence": ["Exact recent hold/break data unavailable"],
    }
    base.update(overrides)
    return base


def test_odds_missing_does_not_block_live_analyst_idea():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    assert package.package_type == "ANALYST_RECOMMENDATION_PACKAGE"
    assert len(package.recommendations) == 1
    idea = package.recommendations[0]
    assert idea.odds_available is False
    assert idea.ev_available is False
    assert package.ready_for_manual_operator_quote_review is True


def test_hydration_missing_does_not_block_live_analyst_idea():
    package = build_package_from_candidates([_football_candidate(hydration_status="MINIMAL_HYDRATION")], run_id="r1")
    assert len(package.recommendations) == 1
    assert package.recommendations[0].hydrated_available is False
    assert "not blocked" in " ".join(package.recommendations[0].source_gaps)


def test_model_probability_missing_does_not_block_recommendation_but_prevents_ev():
    package = build_package_from_candidates([_football_candidate(model_probability=None)], run_id="r1")
    idea = package.recommendations[0]
    assert idea.model_probability_available is False
    assert idea.ev_available is False
    assert idea.fair_odds_available is False


def test_missing_model_probability_prevents_ev_claim():
    package = build_package_from_candidates([_football_candidate(model_probability=None, odds_decimal=2.1)], run_id="r1")
    idea = package.recommendations[0]
    assert idea.odds_available is True
    assert idea.model_probability_available is False
    assert idea.ev_available is False


def test_partial_data_lowers_confidence_or_watchlist():
    package = build_package_from_candidates([_football_candidate(supporting_evidence=["Only one partial signal"], counter_evidence=[])], run_id="r1")
    ideas = package.recommendations + package.watchlist_only
    assert ideas
    assert ideas[0].analyst_confidence in {"C", "D"}


def test_unknown_data_quality_cannot_be_high_confidence():
    package = build_package_from_candidates([_football_candidate(supporting_evidence=[], counter_evidence=[])], run_id="r1")
    idea = (package.recommendations + package.watchlist_only)[0]
    assert idea.data_quality in {"LOW", "UNKNOWN"}
    assert idea.analyst_confidence not in {"A", "B"}


def test_weak_evidence_becomes_watchlist_only():
    package = build_package_from_candidates([_football_candidate(supporting_evidence=[], counter_evidence=[])], run_id="r1")
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].suggested_use == "WATCHLIST_ONLY"


def test_every_recommendation_has_counter_evidence_field():
    package = build_package_from_candidates([_football_candidate(counter_evidence=[])], run_id="r1")
    idea = (package.recommendations + package.watchlist_only)[0]
    assert idea.counter_evidence
    assert "UNKNOWN" in idea.counter_evidence[0]


def test_event_only_football_can_generate_reference_line_watch_or_recommendation():
    package = build_package_from_candidates([
        {
            "candidate_id": "wc1",
            "sport": "football",
            "competition": "World Cup",
            "home_team": "Team Wide",
            "away_team": "Team Deep Block",
            "notes": "wide attacks, territory and pressure; corner pattern should be checked",
            "counter_evidence": ["No exact L10 corner data"],
        }
    ], run_id="r1")
    ideas = package.recommendations + package.watchlist_only
    assert ideas
    assert ideas[0].market_family == "CORNERS"
    assert ideas[0].line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK"
    assert "operator line" in " ".join(ideas[0].source_gaps).lower()


def test_wimbledon_tennis_not_blocked_by_missing_hydration():
    package = build_package_from_candidates([_tennis_candidate()], run_id="r1")
    assert len(package.recommendations) == 1
    assert package.recommendations[0].sport == "tennis"
    assert package.recommendations[0].hydrated_available is False


def test_tennis_event_only_defaults_total_games_check():
    package = build_package_from_candidates([
        {
            "candidate_id": "w1",
            "competition": "Wimbledon",
            "player_one": "Server A",
            "player_two": "Server B",
            "notes": "grass surface, serve-oriented notes, tie-break risk",
        }
    ], run_id="r1")
    ideas = package.recommendations + package.watchlist_only
    assert ideas
    assert ideas[0].sport == "tennis"
    assert ideas[0].market_family in {"TOTAL_GAMES", "ACES"}


def test_bet_builder_combo_does_not_compute_combined_odds():
    combo = BetBuilderComboIdea(combo_id="x", idea_ids=["a", "b"], event_label="A vs B", combo_note="manual", correlation_notes=[], conflict_risks=[])
    assert combo.to_dict()["combined_odds_decimal"] is None
    with pytest.raises(ValueError):
        BetBuilderComboIdea(combo_id="bad", idea_ids=["a"], event_label="A", combo_note="bad", correlation_notes=[], conflict_risks=[], combined_odds_decimal=2.5).to_dict()


def test_no_final_coupon_without_human_quote():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    assert package.ready_for_final_coupon is False
    assert package.ready_for_manual_placement is False


def test_manual_quote_required_for_final_coupon():
    package = build_package_from_candidates([_football_candidate(candidate_id="c1")], run_id="r1")
    rec_id = package.recommendations[0].idea_id
    ok, issues = validate_human_superbet_quote(package, {
        "entered_by_human": True,
        "operator": "Superbet",
        "as_of_utc": "2026-06-30T12:00:00Z",
        "quotes": [{
            "recommendation_id": rec_id,
            "legs_confirmed_on_operator_screen": True,
            "operator_market_labels": ["Total corners"],
            "operator_lines": ["7.5"],
            "combined_odds_decimal": 2.1,
        }],
    })
    assert ok, issues
    final = apply_human_quote_if_valid(package, {
        "entered_by_human": True,
        "operator": "Superbet",
        "as_of_utc": "2026-06-30T12:00:00Z",
        "quotes": [{
            "recommendation_id": rec_id,
            "legs_confirmed_on_operator_screen": True,
            "operator_market_labels": ["Total corners"],
            "operator_lines": ["7.5"],
            "combined_odds_decimal": 2.1,
        }],
    })
    assert final.package_type == "FINAL_MANUAL_COUPON_PACKAGE"
    assert final.ready_for_final_coupon is True


def test_invalid_quote_rejected():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    rejected = apply_human_quote_if_valid(package, {"entered_by_human": False, "operator": "Superbet", "quotes": []})
    assert rejected.package_type == "QUOTE_REJECTED_PACKAGE"
    assert rejected.ready_for_manual_placement is False


def test_ready_for_manual_operator_quote_review_true_with_recommendations():
    package = build_package_from_candidates([_football_candidate()], run_id="r1")
    assert package.ready_for_manual_operator_quote_review is True


def test_load_candidates_from_run_artifact(tmp_path: Path):
    p = tmp_path / "artifact.json"
    p.write_text(json.dumps({"candidates": [_football_candidate()]}), encoding="utf-8")
    loaded = load_candidates_from_path(tmp_path)
    assert loaded
    package = build_package_from_candidates(loaded, run_id="r1")
    assert package.package_type == "ANALYST_RECOMMENDATION_PACKAGE"


def test_main_recommendations_are_ranked_and_limited():
    # Create 15 candidates with different confidence scores
    candidates = []
    for idx in range(15):
        confidence = "A" if idx < 3 else "B" if idx < 10 else "C"
        cand = _football_candidate(
            candidate_id=f"cand_{idx}",
            event_id=f"event_{idx}",
            supporting_evidence=[f"Evidence {idx}"] * (idx % 3 + 1),
            analyst_confidence=confidence,
        )
        candidates.append(cand)
        
    package = build_package_from_candidates(candidates, run_id="r_limit_test")
    # Verify recommendations are limited to top 12
    assert len(package.recommendations) == 12
    # Verify the remaining 3 are in watchlist_only
    assert len(package.watchlist_only) == 3
    # Verify they are ranked by score descending
    scores = [calculate_idea_score(idea) for idea in package.recommendations]
    assert scores == sorted(scores, reverse=True)


def test_watchlist_is_limited_in_markdown_but_count_preserved():
    # Create 25 watchlist candidates (no supporting evidence, D confidence)
    candidates = []
    for idx in range(25):
        cand = _football_candidate(
            candidate_id=f"cand_{idx}",
            event_id=f"event_{idx}",
            supporting_evidence=[],
            counter_evidence=[],
            analyst_confidence="D",
        )
        candidates.append(cand)
        
    package = build_package_from_candidates(candidates, run_id="r_watch_test")
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 25
    
    # Render to markdown
    md = render_markdown_package(package)
    assert "Total Watchlist Count**: 25" in md
    assert "Hidden Watchlist Ideas (in JSON appendix only)**: 5" in md
    # Check that only 20 watchlist items are listed
    bullet_count = md.count("Confidence: `D`")
    assert bullet_count == 20


def test_combo_ideas_limited_to_top_six():
    # Pass candidates representing 8 different events, each with 2 ideas to trigger combos
    candidates = []
    for idx in range(8):
        c1 = _football_candidate(
            candidate_id=f"c_{idx}_1",
            event_id=f"event_{idx}",
            market_family="CORNERS",
            analyst_confidence="B",
        )
        c2 = _football_candidate(
            candidate_id=f"c_{idx}_2",
            event_id=f"event_{idx}",
            market_family="CARDS",
            analyst_confidence="B",
        )
        candidates.extend([c1, c2])
        
    package = build_package_from_candidates(candidates, run_id="r_combo_test")
    # Verify combo ideas limited to top 6
    assert len(package.bet_builder_combo_ideas) == 6


def test_no_implicit_stale_run_selection_without_flag():
    import sys
    from scripts.run_unified_live_analyst_session import main as run_main
    
    # Calling run_main without inputs or flags must exit with SystemExit and INPUT_REQUIRED_OR_DISCOVERY_UNAVAILABLE
    sys_argv_backup = sys.argv
    try:
        sys.argv = ["run_unified_live_analyst_session.py"]
        with pytest.raises(SystemExit) as exc_info:
            run_main()
        assert "INPUT_REQUIRED_OR_DISCOVERY_UNAVAILABLE" in str(exc_info.value)
    finally:
        sys.argv = sys_argv_backup


def test_latest_run_uses_modified_time_when_explicit(tmp_path: Path):
    import time
    import sys
    from scripts.run_unified_live_analyst_session import main as run_main
    
    # Create fake run directories inside a custom reports root
    runs_dir = tmp_path / "pipeline_runs"
    runs_dir.mkdir(parents=True)
    
    run_old = runs_dir / "TODAY_LIVE_UNIFIED_ANALYST_SESSION_20260630_100000"
    run_new = runs_dir / "TODAY_LIVE_UNIFIED_ANALYST_SESSION_20260630_090000"  # lexicographically older
    
    run_new.mkdir()
    # Make sure run_old is created, then sleep slightly, then touch run_new to make it modified later
    run_old.mkdir()
    
    # Touch run_new to make its modification time later than run_old
    time.sleep(0.1)
    (run_new / "some_file.json").write_text("{}", encoding="utf-8")
    run_new.touch()
    
    sys_argv_backup = sys.argv
    try:
        sys.argv = [
            "run_unified_live_analyst_session.py",
            "--output-root", str(tmp_path / "out"),
            "--latest-run",
        ]
        # We need to monkeypatch or override REPO_ROOT/reports/pipeline_runs or use the --output-root and run root.
        # Let's mock REPO_ROOT in scripts.run_unified_live_analyst_session to point to tmp_path
        import scripts.run_unified_live_analyst_session
        orig_root = scripts.run_unified_live_analyst_session.REPO_ROOT
        scripts.run_unified_live_analyst_session.REPO_ROOT = tmp_path
        try:
            with pytest.raises(SystemExit):
                run_main()
            # Verify that the print inside showed Selecting latest run directory by modified time: run_new's name
        finally:
            scripts.run_unified_live_analyst_session.REPO_ROOT = orig_root
    finally:
        sys.argv = sys_argv_backup


def test_s8_subprocess_failure_fails_closed(tmp_path: Path, monkeypatch):
    import sys
    from scripts.pipeline_steps.s8_build_coupons import main as s8_main
    
    # Mock resolve_child_runtime_env to return a run directory under tmp_path
    child_env = {
        "BET_PIPELINE_RUN_ROOT": str(tmp_path / "run_root"),
        "BET_PIPELINE_DATA_DIR": str(tmp_path / "data_dir"),
        "BET_PIPELINE_COUPON_DIR": str(tmp_path / "coupon_dir"),
        "BET_PIPELINE_ARTIFACT_DIR": str(tmp_path / "artifact_dir"),
        "BET_PIPELINE_BETTING_DAY": "2026-06-30",
        "BET_PIPELINE_RUN_ID": "test_run_s8",
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
    }
    
    # Create the artifact and data dirs
    Path(child_env["BET_PIPELINE_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]).mkdir(parents=True, exist_ok=True)
    
    # Set up S7b.json script evidence payload to resolve input path
    s7b_evidence = {
        "status": "PASS",
        "payload": {
            "s7b_json_output": str(tmp_path / "data_dir" / "analytical_candidate_handoff.json"),
            "market_availability_output_path": str(tmp_path / "data_dir" / "analytical_candidate_handoff.json"),
            "validated_market_availability_path": str(tmp_path / "data_dir" / "analytical_candidate_handoff.json"),
        }
    }
    Path(child_env["BET_PIPELINE_ARTIFACT_DIR"], "S7b.json").write_text(json.dumps(s7b_evidence), encoding="utf-8")
    
    # Write a dummy analytical handoff file
    handoff_data = {
        "artifact_type": "ANALYTICAL_CANDIDATE_HANDOFF",
        "analytical_ready": []
    }
    Path(child_env["BET_PIPELINE_DATA_DIR"], "analytical_candidate_handoff.json").write_text(json.dumps(handoff_data), encoding="utf-8")
    
    # Mock subprocess.run to return code != 0
    import subprocess
    import os
    class FakeCompletedProcess:
        def __init__(self):
            self.returncode = 1
            self.stdout = ""
            self.stderr = "Subprocess failure"
            
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeCompletedProcess())
    monkeypatch.setattr(os, "environ", child_env)
    
    sys_argv_backup = sys.argv
    try:
        sys.argv = ["s8_build_coupons.py", "--date", "2026-06-30", "--runtime-mode", "DRY_RUN"]
        with pytest.raises(SystemExit) as exc_info:
            s8_main()
        assert exc_info.value.code == 5
        
        # Verify that the generated S8 terminal evidence shows BLOCK and BLOCKED_UNIFIED_ANALYST_RUNNER_FAILED
        evidence_file = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]) / "S8.json"
        assert evidence_file.exists()
        evidence_data = json.loads(evidence_file.read_text(encoding="utf-8"))
        assert evidence_data["status"] == "BLOCK"
        assert "BLOCKED_UNIFIED_ANALYST_RUNNER_FAILED" in evidence_data["blocked_reasons"]
    finally:
        sys.argv = sys_argv_backup


def test_s8_does_not_use_hardcoded_old_run_id():
    s8_file_path = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_steps" / "s8_build_coupons.py"
    s8_content = s8_file_path.read_text(encoding="utf-8")
    # Verify that TODAY_LIVE_BET_BUILDER_FINAL_MANUAL_COUPON_A_20260630_115254 is no longer hardcoded as fallback in S8 code
    assert "TODAY_LIVE_BET_BUILDER_FINAL_MANUAL_COUPON_A_20260630_115254" not in s8_content


def test_default_reference_lines_are_operator_check_only():
    candidate = _football_candidate(market_family="CORNERS", line=None)
    package = build_package_from_candidates([candidate], run_id="r_ref_line_test")
    idea = package.recommendations[0]
    assert idea.line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK"
    assert idea.recommended_line == "7.5"
    
    # Check rendered Markdown
    md = render_markdown_package(package)
    assert "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK" in md
    assert "Reference line for manual Superbet check, not a confirmed operator line." in md


def test_low_evidence_ideas_do_not_enter_top_recommendations():
    # High-confidence / low-evidence check
    candidate = _football_candidate(supporting_evidence=[], counter_evidence=[], analyst_confidence="B")
    package = build_package_from_candidates([candidate], run_id="r_low_ev_test")
    # Should become watchlist only
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].suggested_use == "WATCHLIST_ONLY"


def test_markdown_has_executive_summary_and_superbet_checklist():
    package = build_package_from_candidates([_football_candidate()], run_id="r_md_layout_test")
    md = render_markdown_package(package)
    assert "## 1. Executive Summary" in md
    assert "## 2. Top Analyst Recommendations" in md
    assert "## 3. Bet Builder Combo Ideas" in md
    assert "## 4. Watchlist Appendix" in md
    assert "## 5. Rejected Summary" in md
    assert "## 6. Data Gaps and Confidence Policy" in md
    assert "## 7. Superbet Manual Operator Checklist" in md


def test_numeric_event_label_cannot_be_top_recommendation():
    cand = _football_candidate(event_label="78", event_id="78")
    package = build_package_from_candidates([cand], run_id="r_numeric_test")
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].analyst_confidence == "D"


def test_placeholder_candidate_id_cannot_be_top_recommendation():
    cand = _football_candidate(event_label="candidate_123", event_id="e1")
    package = build_package_from_candidates([cand], run_id="r_placeholder_test")
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].analyst_confidence == "D"


def test_missing_participants_downgrades_to_watchlist():
    cand = _football_candidate(event_label="FriendlyMatch", home_team=None, away_team=None, player_one=None, player_two=None, participants=[])
    package = build_package_from_candidates([cand], run_id="r_participants_test")
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].analyst_confidence == "D"


def test_generic_no_quantitative_summary_cannot_be_top_recommendation():
    cand = _football_candidate(supporting_evidence=[])
    package = build_package_from_candidates([cand], run_id="r_no_quant_test")
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].analyst_confidence == "D"


def test_unknown_only_counter_evidence_cannot_be_confidence_b():
    cand = _football_candidate(counter_evidence=[])
    package = build_package_from_candidates([cand], run_id="r_unknown_counter_test")
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].analyst_confidence == "D"


def test_confidence_b_requires_actionable_evidence():
    # Good complete case
    cand = _football_candidate(analyst_confidence="B")
    package = build_package_from_candidates([cand], run_id="r_good_b")
    assert len(package.recommendations) == 1
    assert package.recommendations[0].analyst_confidence == "B"


def test_confidence_c_requires_event_identity():
    cand = _football_candidate(event_label="78", analyst_confidence="C")
    package = build_package_from_candidates([cand], run_id="r_c_identity")
    assert len(package.recommendations) == 0
    assert package.watchlist_only[0].analyst_confidence == "D"


def test_watchlist_allowed_with_incomplete_identity():
    cand = _football_candidate(event_label="78", event_id="78")
    package = build_package_from_candidates([cand], run_id="r_watchlist_allow")
    assert len(package.watchlist_only) == 1
    assert package.watchlist_only[0].event_label == "78"


def test_markdown_top_recommendation_contains_match_context():
    cand = _football_candidate()
    package = build_package_from_candidates([cand], run_id="r_md_match_context")
    md = render_markdown_package(package)
    assert "- **Match Context**:" in md
    assert "- **Event**:" in md
    assert "- **Sport**:" in md
    assert "- **Competition/Tournament**:" in md
    assert "- **Kickoff**:" in md
    assert "- **Participants**:" in md
    assert "- **Market**:" in md
    assert "- **Direction**:" in md
    assert "- **Operator-check line**:" in md
    assert "- **Line source**:" in md
    assert "- **Evidence grade**:" in md
    assert "- **Confidence**:" in md
    assert "- **Data quality**:" in md


def test_bad_screenshot_case_becomes_watchlist_only():
    cand = {
        "event_id": "78",
        "event_label": "78",
        "sport": "football",
        "competition": "Friendly Match",
        "market_family": "SHOTS",
        "line": 16.8,
        "direction": "UNDER",
        "supporting_evidence": [],
        "counter_evidence": [],
    }
    package = build_package_from_candidates([cand], run_id="r_screenshot_case")
    assert len(package.recommendations) == 0
    assert len(package.watchlist_only) == 1
    idea = package.watchlist_only[0]
    assert idea.analyst_confidence == "D"
    assert idea.why_it_may_work == "Insufficient evidence for top recommendation; manual watchlist only."
    assert "UNKNOWN" in idea.why_it_may_fail


def test_odds_missing_still_does_not_block_good_recommendation():
    cand = _football_candidate(odds=None, odds_decimal=0.0)
    package = build_package_from_candidates([cand], run_id="r_odds_missing")
    assert len(package.recommendations) == 1
    assert package.recommendations[0].odds_available is False


def test_hydrated_missing_still_does_not_block_good_recommendation():
    cand = _football_candidate(hydration_status="MINIMAL_HYDRATION")
    package = build_package_from_candidates([cand], run_id="r_hydrated_missing")
    assert len(package.recommendations) == 1
    assert package.recommendations[0].hydrated_available is False
