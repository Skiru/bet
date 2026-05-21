"""Tests for agent communication protocol."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_protocol import (
    DATA_FLOW_CONTRACTS,
    PIPELINE_STEPS,
    STRUCTURED_OUTPUT_PROTOCOL,
    write_step_output,
    read_agent_review,
    STEP_AGENT_CONFIG,
    REVIEWS_DIR,
)
from agent_output import AgentOutput


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def test_write_step_output_creates_file():
    """Verify JSON file is created in correct location."""
    tmp = tempfile.mkdtemp()
    reviews_dir = Path(tmp) / "reviews"

    with patch("agent_protocol.REVIEWS_DIR", reviews_dir):
        result = write_step_output(
            date="2099-01-01",
            step_id="s3_deep_stats",
            metrics={"candidates_analyzed": 5, "avg_safety_score": 0.72},
            artifacts=["betting/data/2099-01-01_s3_deep_stats.json"],
        )

    out_path = Path(result)
    assert out_path.exists()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["step_id"] == "s3_deep_stats"
    assert data["date"] == "2099-01-01"
    assert data["metrics"]["candidates_analyzed"] == 5
    assert "written_at" in data

    import shutil
    shutil.rmtree(tmp)


def test_read_agent_review_returns_none_when_missing():
    """Verify graceful None return when no review file exists."""
    tmp = tempfile.mkdtemp()
    reviews_dir = Path(tmp) / "reviews"

    with patch("agent_protocol.REVIEWS_DIR", reviews_dir):
        result = read_agent_review("2099-01-01", "s3_deep_stats")

    assert result is None

    import shutil
    shutil.rmtree(tmp)


def test_read_agent_review_reads_existing():
    """Verify review file is read correctly when it exists."""
    tmp = tempfile.mkdtemp()
    reviews_dir = Path(tmp) / "reviews"
    date_dir = reviews_dir / "2099-01-01"
    date_dir.mkdir(parents=True)

    review = {
        "agent": "bet-statistician",
        "step_id": "s3_deep_stats",
        "status": "approved",
        "flags": [],
        "enrichments": {"top_pick": "Liverpool corners"},
    }
    (date_dir / "s3_deep_stats_review.json").write_text(
        json.dumps(review), encoding="utf-8"
    )

    with patch("agent_protocol.REVIEWS_DIR", reviews_dir):
        result = read_agent_review("2099-01-01", "s3_deep_stats")

    assert result is not None
    assert result["status"] == "approved"
    assert result["agent"] == "bet-statistician"

    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Config coverage
# ---------------------------------------------------------------------------


def test_step_agent_config_has_required_keys():
    """Verify STEP_AGENT_CONFIG entries have expected structure."""
    for step_id, config in STEP_AGENT_CONFIG.items():
        assert "agent" in config, f"Step {step_id} missing 'agent' key"


def test_data_flow_contracts_cover_current_readiness_boundaries():
    """Protocol contracts should expose the current S2-S10 readiness surfaces."""
    s2_tipster = DATA_FLOW_CONTRACTS["s2_tipster"]
    assert "betting/data/{date}_s2_shortlist.json" in s2_tipster["produces"]["files"]
    assert "tipster_xref.py mutates shortlist" in s2_tipster["source_of_truth"]["ownership"]

    s2_scrapers = DATA_FLOW_CONTRACTS["s2_3_scrapers"]
    assert "bridge_league_to_team_form.py" in s2_scrapers["source_of_truth"]["ownership"]
    assert "scraper_to_team_form.py" in s2_scrapers["source_of_truth"]["ownership"]

    assert "stats_summary_json" in DATA_FLOW_CONTRACTS["s4_odds_eval"]["source_of_truth"]["working_set"]
    assert "context_flags" in DATA_FLOW_CONTRACTS["s5_context"]["source_of_truth"]["working_set"]
    assert "upset_risk" in DATA_FLOW_CONTRACTS["s6_upset_risk"]["source_of_truth"]["working_set"]

    s7_gate = DATA_FLOW_CONTRACTS["s7_gate"]
    assert s7_gate["source_of_truth"]["buckets"] == ["approved", "extended_pool", "rejected"]

    s7_betclic = DATA_FLOW_CONTRACTS["s7_5_betclic"]
    assert "betting/data/betclic_market_validation_{date}.json" in s7_betclic["produces"]["files"]

    s7_repeats = DATA_FLOW_CONTRACTS["s7_6_repeats"]
    assert s7_repeats["source_of_truth"]["working_set"] == "pipeline_runs[s7_6_repeat_loss_check].stats"
    assert "betting/data/repeat_loss_handoff_{date}.json" in s7_repeats["produces"]["files"]

    s10_output = DATA_FLOW_CONTRACTS["s10_output"]
    assert s10_output["source_of_truth"]["working_set"] == "betting/coupons/pdf/{date}/"


def test_pipeline_steps_and_summary_inventory_match_current_runtime_flow():
    """Step map and AGENT_SUMMARY inventory should reflect the runtime scripts we rely on."""
    assert PIPELINE_STEPS["S2"]["script"] == "tipster_aggregator.py + tipster_xref.py"
    assert PIPELINE_STEPS["S2.3"]["script"] == "run_scrapers.py"
    assert PIPELINE_STEPS["S7.5"]["script"] == "validate_betclic_markets.py"
    assert PIPELINE_STEPS["S7.6"]["script"] == "check_48h_repeats.py"
    assert PIPELINE_STEPS["S10"]["script"] == "generate_coupon_pdf.py"

    inventory = STRUCTURED_OUTPUT_PROTOCOL["script_inventory"]
    assert inventory["coupon_builder.py"]["contract_step"] == "s8_coupons"
    assert inventory["coupon_builder.py"]["summary_step"] == "s8_coupon"
    assert inventory["coupon_builder.py"]["emitter"] == "AgentOutput"
    assert "NO_BET is a valid verdict" in inventory["coupon_builder.py"]["notes"]
    assert inventory["run_scrapers.py"]["emitter"] == "manual_agent_summary"
    assert inventory["validate_betclic_markets.py"]["emitter"] == "manual_agent_summary"
    assert inventory["generate_coupon_pdf.py"]["emitter"] == "none"


def test_agent_output_validate_summary_accepts_no_bet():
    """NO_BET is a valid AgentOutput verdict for coupon_builder no-pick sessions."""
    warnings = AgentOutput.validate_summary(
        {
            "step": "s8_coupon",
            "verdict": "NO_BET",
            "metrics": {"reason": "Brak zatwierdzonych typów."},
            "issues": [],
        }
    )

    assert warnings == []
