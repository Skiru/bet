from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_unified_live_analyst_session_preserves_superbet_manual_quote_gate() -> None:
    path = ROOT / "src" / "bet" / "pipeline" / "unified_live_analyst_session.py"
    assert path.exists(), "unified_live_analyst_session.py is missing"
    text = path.read_text(encoding="utf-8")
    required_any = ["Superbet", "operator odds", "manual", "combined_odds_decimal"]
    missing = [term for term in required_any if term not in text]
    assert not missing, f"Unified live analyst session missing Superbet/manual quote terms: {missing}"
    forbidden_snippets = [
        "combined_odds = leg1_odds * leg2_odds",
        "combined_odds_decimal = math.prod",
        "automated_placement_ready = True",
        "production_selectable = True  # without human quote",
    ]
    found = [snippet for snippet in forbidden_snippets if snippet in text]
    assert not found, f"Forbidden synthetic Bet Builder or placement pattern found: {found}"


def test_analytical_contract_has_quote_ready_fields() -> None:
    candidates = [
        ROOT / "src" / "bet" / "pipeline" / "bet_builder_analytical.py",
        ROOT / "src" / "bet" / "pipeline" / "analytical_candidate_bridge.py",
        ROOT / "scripts" / "pipeline_steps" / "s8_build_coupons.py",
    ]
    existing = [path for path in candidates if path.exists()]
    assert existing, "No analytical/Bet Builder contract files found"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in existing)
    required = [
        "ready_for_manual_operator_quote_review",
        "combined_bookmaker_odds_computed",
        "min_acceptable_operator_odds",
    ]
    missing = [term for term in required if term not in combined]
    assert not missing, f"Analytical bridge/S8 contract missing quote-ready fields: {missing}"
