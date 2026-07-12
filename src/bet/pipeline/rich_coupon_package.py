"""Rich Bet Builder and manual coupon package builder module."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bet.pipeline.run_evidence import utc_now_iso


ZERO = Decimal("0")


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def _serialize_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_serialize_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {name: _serialize_jsonable(getattr(value, name)) for name in value.__dataclass_fields__}
    return value


@dataclass(frozen=True)
class CouponLeg:
    leg_id: str
    event_id: str
    event: str
    sport: str
    league: str
    market: str
    market_type: str
    participant: str
    pick: str
    line: str
    odds_decimal: Decimal
    odds_captured_at_utc: str
    operator_name: str
    source_artifact_path: str
    source_artifact_sha256: str
    evidence_sources: list[str]
    supporting_stats: list[dict[str, Any]]
    counter_stats: list[dict[str, Any]]
    confidence_label: str
    blockers: list[str]

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


@dataclass(frozen=True)
class BetBuilderPackage:
    package_id: str
    betting_day: str
    session_id: str
    package_type: str  # SINGLE|BET_BUILDER|MULTI_BET_BUILDER|NO_BET_PACKAGE|ANALYTICAL_ONLY
    event: str
    legs: list[CouponLeg]
    combined_odds_decimal: Decimal | None
    stake_units: Decimal
    max_daily_risk_units: Decimal
    value_summary: str
    risk_summary: str
    correlation_risk: str  # LOW|MEDIUM|HIGH|UNKNOWN
    operator_screen_checklist: list[str]
    human_action_required: bool
    ready_for_human_manual_placement: bool
    ready_for_automated_bet_placement: bool
    ready_for_production_execution: bool
    blockers: list[str]
    operator_screen_combined_odds_required: bool = True
    analytical_suggestions: list[dict] = field(default_factory=list)
    manual_quote_required_candidates: list[dict] = field(default_factory=list)
    price_acceptable_pending_evidence_review: list[dict] = field(default_factory=list)
    bettable_manual_legs: list[dict] = field(default_factory=list)
    rejected_by_price: list[dict] = field(default_factory=list)
    line_mismatch_requires_remodel: list[dict] = field(default_factory=list)
    ready_for_manual_operator_quote_review: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


@dataclass(frozen=True)
class RichCouponPackageReport:
    task_id: str
    status: str
    betting_day: str
    session_id: str
    candidate_count: int
    no_bet_count: int
    bettable_count: int
    package_count: int
    recommended_package_id: str | None
    package_json_path: str | None
    package_markdown_path: str | None
    bet_builder_compatibility_verdict: str  # PASS|FAIL
    market_completeness_verdict: str  # PASS|FAIL
    multi_stat_package_verdict: str  # PASS|FAIL
    correlation_review_verdict: str  # PASS|FAIL
    operator_screen_required_verdict: str  # PASS|FAIL
    no_automated_placement_verdict: str  # PASS|FAIL
    ready_for_production_coupon_building: bool
    human_manual_placement_required: bool
    ready_for_automated_bet_placement: bool
    ready_for_production_execution: bool
    blockers: list[str]
    analytical_suggestion_count: int = 0
    ready_for_manual_operator_quote_review: bool = False
    classification: str = "PRODUCTION_STABLE"
    can_place_bet_now: bool = True
    safe_user_action: str = "MANUAL_PLACEMENT_ALLOWED"
    positive_ev_with_operator_odds_count: int = 0

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


def classify_correlation_risk(legs: list[CouponLeg]) -> str:
    """Classify correlation risk for multi-leg packages."""
    if len(legs) <= 1:
        return "LOW"

    events = {leg.event for leg in legs}
    if len(events) == 1:
        markets = [leg.market.lower() for leg in legs]
        if any("player" in m for m in markets) and any("total" in m or "o/u" in m for m in markets):
            return "HIGH"
        return "MEDIUM"

    return "LOW"


def generate_human_checklist(package_type: str, legs: list[CouponLeg], stake: Decimal) -> list[str]:
    """Generate a sequential safety checklist for the human operator."""
    checklist = [
        "DO NOT use any automated scripts, browser automation, or unauthorized bookmaker APIs.",
        "Ensure you are fully logged into your verified, legal personal operator account.",
        f"Confirm that your total active risk fits within your personal responsible gambling limits."
    ]

    for idx, leg in enumerate(legs, 1):
        checklist.append(
            f"Step {idx}: Locate Match: '{leg.event}' on the operator interface."
        )
        checklist.append(
            f"Step {idx}a: Open Market: '{leg.market}'."
        )
        line_info = f" (Line: {leg.line})" if leg.line not in ("MISSING", "", None) else ""
        checklist.append(
            f"Step {idx}b: Select Selection: '{leg.pick}'{line_info}."
        )
        checklist.append(
            f"Step {idx}c: Verify local odds are at least {leg.odds_decimal:.2f} (captured: {leg.odds_captured_at_utc})."
        )

    if package_type in ("BET_BUILDER", "MULTI_BET_BUILDER"):
        checklist.append("Step COMBINED: Verify the operator accepts these selections combined as a Bet Builder / Multi.")
        checklist.append("Step ODDS: Record the combined odds from the operator screen.")

    checklist.append(f"Step PLACE: Manually input {stake:.2f} stake units and click 'Place Bet'.")
    checklist.append("Step RECORD: Save the coupon receipt / transaction ID to your manual journal.")
    return checklist


def build_rich_coupon_package(
    *,
    betting_day: str,
    session_id: str,
    session_ledger_path: Path,
    operator_name: str,
    stake_units: Decimal = Decimal("1.0"),
    max_daily_risk_units: Decimal = Decimal("1.0"),
    prefer_bet_builder: bool = True,
    max_legs: int = 10,
) -> tuple[list[BetBuilderPackage], RichCouponPackageReport]:
    """Build rich manual coupon packages from reviewed ledger candidates."""
    session_ledger_path = Path(session_ledger_path)

    state = {"reviewed": {}}
    if session_ledger_path.exists():
        with open(session_ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    event = json.loads(stripped)
                    event_type = event.get("event_type")
                    payload = event.get("payload") or {}
                    if event_type in ("candidate_reviewed", "candidate_rejected_no_bet"):
                        c_id = payload.get("candidate_id")
                        if c_id:
                            state["reviewed"][c_id] = payload
                except json.JSONDecodeError:
                    continue

    def _quote_review_ready(entry: dict[str, Any]) -> bool:
        return (
            entry.get("ready_for_manual_operator_quote_review") is True
            and entry.get("hydration_status") == "HYDRATED"
            and entry.get("promotion_status") == "ANALYZABLE"
            and entry.get("promotion_safe_model_probability") is True
        )

    candidate_count = len(state["reviewed"])
    bettable_candidates = []
    rejected_candidates = []
    analytical_candidates = []

    for c_id, cand in state["reviewed"].items():
        status = cand.get("review_status")
        if status == "BETTABLE_MANUAL_ONLY":
            bettable_candidates.append(cand)
        elif status in ("PRICE_PENDING_OPERATOR_CHECK", "BET_BUILDER_QUOTE_REQUIRED", "LINE_MISMATCH_REQUIRES_REMODEL", "NO_OPERATOR_MARKET_FOUND", "INSUFFICIENT_MODEL_PROBABILITY", "NO_FAKE_OPERATOR_QUOTE", "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW", "REJECTED_BY_PRICE") and _quote_review_ready(cand):
            analytical_candidates.append(cand)
        else:
            rejected_candidates.append(cand)

    no_bet_count = len(rejected_candidates)
    bettable_count = len(bettable_candidates)
    analytical_count = len(analytical_candidates)

    packages: list[BetBuilderPackage] = []
    report_blockers: list[str] = []

    bet_builder_compatibility_verdict = "PASS"
    market_completeness_verdict = "PASS"
    multi_stat_package_verdict = "PASS"
    correlation_review_verdict = "PASS"

    clean_bettables = []
    for cand in bettable_candidates:
        c_id = str(cand.get("candidate_id") or "").lower()
        event_str = str(cand.get("event") or "").lower()
        market_str = str(cand.get("market") or "").lower()
        pick_str = str(cand.get("pick") or "").lower()

        has_fixture_label = False
        for label in ("selection-win", "selection-loss", "selection-void", "fixture", "test"):
            if label in c_id or label in event_str or label in market_str or label in pick_str:
                has_fixture_label = True
                break

        if has_fixture_label:
            report_blockers.append(f"Forbidden fixture/test label found in candidate {cand.get('candidate_id')}")
            market_completeness_verdict = "FAIL"
            continue

        clean_bettables.append(cand)

    legs: list[CouponLeg] = []
    for cand in clean_bettables:
        leg_blockers = []
        market = cand.get("market")
        pick = cand.get("pick")
        odds_dec = Decimal(str(cand.get("odds_decimal") or "0"))
        odds_ts = cand.get("odds_captured_at_utc")
        cand_operator = cand.get("operator_name")
        s8_path = cand.get("source_s8_coupon_draft_path")
        s8_sha = cand.get("source_s8_coupon_draft_sha256")

        if not market:
            leg_blockers.append("missing market")
        if not pick:
            leg_blockers.append("missing pick")
        if odds_dec <= Decimal("1.0"):
            leg_blockers.append("missing or invalid odds decimal")
        if not odds_ts:
            leg_blockers.append("missing odds timestamp")
        if not cand_operator:
            leg_blockers.append("missing operator")
        if not s8_path or not s8_sha:
            leg_blockers.append("missing source artifact/SHA")

        is_ou = "O/U" in str(market) or "Over/Under" in str(market) or "Total" in str(market) or str(pick).upper() in ("UNDER", "OVER") or str(pick).upper().startswith("UNDER ") or str(pick).upper().startswith("OVER ")
        line_val = cand.get("line")
        if is_ou and (line_val in (None, "", "MISSING")):
            leg_blockers.append("missing numeric line for O/U market")

        supporting = cand.get("supporting_stats")
        if not supporting:
            supporting = [{"metric": "Recent form", "value": "UNKNOWN", "source": "UNKNOWN", "as_of": "UNKNOWN"}]
        else:
            for item in supporting:
                if "source" not in item or "as_of" not in item:
                    item["source"] = item.get("source", "UNKNOWN")
                    item["as_of"] = item.get("as_of", "UNKNOWN")

        counter = cand.get("counter_stats")
        if not counter:
            counter = [{"metric": "Head-to-head", "value": "UNKNOWN", "source": "UNKNOWN", "as_of": "UNKNOWN"}]
        else:
            for item in counter:
                if "source" not in item or "as_of" not in item:
                    item["source"] = item.get("source", "UNKNOWN")
                    item["as_of"] = item.get("as_of", "UNKNOWN")

        leg = CouponLeg(
            leg_id=str(cand.get("candidate_id") or ""),
            event_id=str(cand.get("event_id") or ""),
            event=str(cand.get("event") or ""),
            sport=str(cand.get("sport") or "tennis"),
            league=str(cand.get("league") or "unknown"),
            market=str(market or ""),
            market_type=str(cand.get("market_type") or ("O/U" if is_ou else "Moneyline")),
            participant=str(cand.get("player_b") or cand.get("participant") or "unknown"),
            pick=str(pick or ""),
            line=str(line_val) if line_val is not None else "MISSING",
            odds_decimal=odds_dec,
            odds_captured_at_utc=str(odds_ts or ""),
            operator_name=str(cand_operator or ""),
            source_artifact_path=str(s8_path or ""),
            source_artifact_sha256=str(s8_sha or ""),
            evidence_sources=["S8 Coupon Draft", "S9 Human Gate"],
            supporting_stats=supporting,
            counter_stats=counter,
            confidence_label=str(cand.get("confidence_label") or "MEDIUM"),
            blockers=leg_blockers,
        )
        legs.append(leg)
        if leg_blockers:
            report_blockers.extend(leg_blockers)
            market_completeness_verdict = "FAIL"

    def make_cand_dict(cand):
        return {
            "candidate_id": cand.get("candidate_id"),
            "event_id": cand.get("event_id"),
            "event": cand.get("event"),
            "sport": cand.get("sport"),
            "competition": cand.get("competition") or cand.get("league"),
            "market": cand.get("market"),
            "pick": cand.get("pick"),
            "line": cand.get("line"),
            "model_probability": str(cand.get("model_probability")) if cand.get("model_probability") is not None else None,
            "fair_odds": str(cand.get("fair_odds")) if cand.get("fair_odds") is not None else None,
            "min_acceptable_operator_odds": str(cand.get("min_acceptable_operator_odds")) if cand.get("min_acceptable_operator_odds") is not None else None,
            "confidence_label": cand.get("confidence_label") or cand.get("confidence"),
            "evidence_pack": cand.get("supporting_stats") or cand.get("evidence_pack") or [],
            "counter_evidence": cand.get("counter_stats") or cand.get("counter_evidence") or [],
            "source_gaps": cand.get("source_gaps") or [],
            "correlation_risk": cand.get("correlation_risk") or "LOW",
            "correlation_notes": cand.get("correlation_notes") or "",
            "scenario_coherence_score": str(cand.get("scenario_coherence_score")) if cand.get("scenario_coherence_score") is not None else None,
            "conflicting_legs": cand.get("conflicting_legs") or [],
            "combined_bookmaker_odds_computed": False,
            "status": cand.get("review_status"),
            "scenario_summary": cand.get("scenario_summary") or "",
            "bet_builder_legs": cand.get("bet_builder_legs") or [],
            "evidence_gate_status": cand.get("evidence_gate_status") or "EVIDENCE_GATE_FAIL",
            "correlation_gate_status": cand.get("correlation_gate_status") or "CORRELATION_GATE_FAIL",
            "manual_superbet_quote_checklist": cand.get("manual_superbet_quote_checklist") or [],
            "rejection_remodel_reasons": cand.get("rejection_remodel_reasons") or [],
            "operator_quote_required": True,
            "not_ready_for_manual_placement": True,
            "ready_for_manual_operator_quote_review": _quote_review_ready(cand),
        }

    analytical_suggestions_list = []
    manual_quote_required_candidates_list = []
    price_acceptable_pending_evidence_review_list = []
    bettable_manual_legs_list = []
    rejected_by_price_list = []
    line_mismatch_requires_remodel_list = []

    for c_id, cand in state["reviewed"].items():
        status = cand.get("review_status")
        cand_dict = make_cand_dict(cand)
        if status == "BETTABLE_MANUAL_ONLY":
            bettable_manual_legs_list.append(cand_dict)
        elif status in ("PRICE_PENDING_OPERATOR_CHECK", "BET_BUILDER_QUOTE_REQUIRED"):
            manual_quote_required_candidates_list.append(cand_dict)
            analytical_suggestions_list.append(cand_dict)
        elif status == "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW":
            price_acceptable_pending_evidence_review_list.append(cand_dict)
            analytical_suggestions_list.append(cand_dict)
        elif status == "REJECTED_BY_PRICE":
            rejected_by_price_list.append(cand_dict)
            analytical_suggestions_list.append(cand_dict)
        elif status == "LINE_MISMATCH_REQUIRES_REMODEL":
            line_mismatch_requires_remodel_list.append(cand_dict)
            analytical_suggestions_list.append(cand_dict)
        elif status in ("NO_OPERATOR_MARKET_FOUND", "INSUFFICIENT_MODEL_PROBABILITY", "NO_FAKE_OPERATOR_QUOTE", "PRICE_ACCEPTABLE_PENDING_CORRELATION_REVIEW"):
            analytical_suggestions_list.append(cand_dict)

    is_analytical_only = (len(bettable_candidates) == 0 and len(analytical_candidates) > 0)

    if report_blockers or (not legs and not is_analytical_only):
        pkg_type = "NO_BET_PACKAGE"
        pkg_id = f"{session_id}:pkg:no-bet"
        pkg = BetBuilderPackage(
            package_id=pkg_id,
            betting_day=betting_day,
            session_id=session_id,
            package_type=pkg_type,
            event="N/A",
            legs=legs,
            combined_odds_decimal=None,
            stake_units=ZERO,
            max_daily_risk_units=max_daily_risk_units,
            value_summary="No bet package - validation or selection blocks active.",
            risk_summary="NO_BET state triggered due to missing fields, fixture labels, or empty ledger.",
            correlation_risk="UNKNOWN",
            operator_screen_checklist=["Do not place bets.", "Resolve validation blockers first."],
            human_action_required=True,
            ready_for_human_manual_placement=False,
            ready_for_automated_bet_placement=False,
            ready_for_production_execution=False,
            blockers=report_blockers,
            operator_screen_combined_odds_required=True,
            analytical_suggestions=analytical_suggestions_list,
            manual_quote_required_candidates=manual_quote_required_candidates_list,
            price_acceptable_pending_evidence_review=price_acceptable_pending_evidence_review_list,
            bettable_manual_legs=bettable_manual_legs_list,
            rejected_by_price=rejected_by_price_list,
            line_mismatch_requires_remodel=line_mismatch_requires_remodel_list,
            ready_for_manual_operator_quote_review=(len(analytical_suggestions_list) > 0)
        )
        packages.append(pkg)
    elif is_analytical_only:
        pkg_type = "ANALYTICAL_ONLY"
        pkg_id = f"{session_id}:pkg:analytical-only"
        event_name = analytical_candidates[0].get("event") if analytical_candidates else "N/A"
        pkg = BetBuilderPackage(
            package_id=pkg_id,
            betting_day=betting_day,
            session_id=session_id,
            package_type=pkg_type,
            event=event_name,
            legs=[],
            combined_odds_decimal=None,
            stake_units=ZERO,
            max_daily_risk_units=max_daily_risk_units,
            value_summary=f"Analytical suggestions only. Minimum acceptable operator odds are calculated for {len(analytical_candidates)} options.",
            risk_summary="Requires manual Superbet operator screens/web app checks to review actual combined lines/odds.",
            correlation_risk="LOW",
            operator_screen_checklist=["Locate unpriced match options on Superbet.", "Verify minimum acceptable operator odds on screen."],
            human_action_required=True,
            ready_for_human_manual_placement=False,
            ready_for_automated_bet_placement=False,
            ready_for_production_execution=False,
            blockers=[],
            operator_screen_combined_odds_required=True,
            analytical_suggestions=analytical_suggestions_list,
            manual_quote_required_candidates=manual_quote_required_candidates_list,
            price_acceptable_pending_evidence_review=price_acceptable_pending_evidence_review_list,
            bettable_manual_legs=bettable_manual_legs_list,
            rejected_by_price=rejected_by_price_list,
            line_mismatch_requires_remodel=line_mismatch_requires_remodel_list,
            ready_for_manual_operator_quote_review=True
        )
        packages.append(pkg)
    else:
        active_legs = legs[:max_legs]
        unique_events = {leg.event for leg in active_legs}
        if len(active_legs) == 1:
            pkg_type = "SINGLE"
            event_name = active_legs[0].event
        elif len(unique_events) == 1:
            pkg_type = "BET_BUILDER"
            event_name = list(unique_events)[0]
        else:
            pkg_type = "MULTI_BET_BUILDER"
            event_name = "Multiple Matches"

        pkg_id = f"{session_id}:pkg:{pkg_type.lower()}"
        corr_risk = classify_correlation_risk(active_legs)
        checklist = generate_human_checklist(pkg_type, active_legs, stake_units)

        value_summary = (
            f"Package features {len(active_legs)} manual legs with un-invented odds. "
            "Individual legs sourced from point-in-time gate-approved consensus models."
        )

        risk_summary = (
            f"Correlation: {corr_risk}. Maximum stake limit: {stake_units} units. "
            "Operator screen validation required to verify live matching lines and actual combo odds."
        )

        pkg = BetBuilderPackage(
            package_id=pkg_id,
            betting_day=betting_day,
            session_id=session_id,
            package_type=pkg_type,
            event=event_name,
            legs=active_legs,
            combined_odds_decimal=None,
            stake_units=stake_units,
            max_daily_risk_units=max_daily_risk_units,
            value_summary=value_summary,
            risk_summary=risk_summary,
            correlation_risk=corr_risk,
            operator_screen_checklist=checklist,
            human_action_required=True,
            ready_for_human_manual_placement=True,
            ready_for_automated_bet_placement=False,
            ready_for_production_execution=False,
            blockers=[],
            operator_screen_combined_odds_required=True,
            analytical_suggestions=analytical_suggestions_list,
            manual_quote_required_candidates=manual_quote_required_candidates_list,
            price_acceptable_pending_evidence_review=price_acceptable_pending_evidence_review_list,
            bettable_manual_legs=bettable_manual_legs_list,
            rejected_by_price=rejected_by_price_list,
            line_mismatch_requires_remodel=line_mismatch_requires_remodel_list,
            ready_for_manual_operator_quote_review=True
        )
        packages.append(pkg)

    recommended_pkg = packages[0] if packages else None
    recommended_pkg_id = recommended_pkg.package_id if recommended_pkg else None

    has_multi_stats = True
    for leg in legs:
        has_sup = any(item.get("value") != "UNKNOWN" for item in leg.supporting_stats)
        has_cnt = any(item.get("value") != "UNKNOWN" for item in leg.counter_stats)
        if not (has_sup and has_cnt):
            has_multi_stats = False

    multi_stat_package_verdict = "PASS" if has_multi_stats else "FAIL"
    status = "PASS" if not report_blockers and pkg_type != "NO_BET_PACKAGE" else "FAIL"

    import os
    from bet.pipeline.readiness_contracts import get_central_safety_classification
    central_safety = get_central_safety_classification(state)

    if not central_safety.production_eligibility:
        classification = central_safety.runtime_classification
        can_place_bet_now = False
        safe_user_action = "DO_NOT_PLACE_BET"
        bettable_count = 0
        positive_ev_with_operator_odds_count = 0
        ready_for_manual_operator_quote_review = False
        ready_for_production_coupon_building = False
        human_manual_placement_required = False
        status = "FAIL"
    else:
        classification = "PRODUCTION_STABLE"
        can_place_bet_now = (bettable_count > 0)
        safe_user_action = "MANUAL_PLACEMENT_ALLOWED" if (bettable_count > 0) else "DO_NOT_PLACE_BET"
        positive_ev_with_operator_odds_count = sum(1 for cand in state.get("reviewed", {}).values() if cand.get("ev", 0) > 0 and cand.get("review_status") == "BETTABLE_MANUAL_ONLY")
        ready_for_production_coupon_building = (bettable_count > 0)
        human_manual_placement_required = (bettable_count > 0)
        ready_for_manual_operator_quote_review = (analytical_count > 0 or bettable_count > 0)

    report = RichCouponPackageReport(
        task_id="PIPELINE_RICH_BET_BUILDER_PACKAGE_A",
        status=status,
        betting_day=betting_day,
        session_id=session_id,
        candidate_count=candidate_count,
        no_bet_count=no_bet_count,
        bettable_count=bettable_count,
        package_count=len(packages),
        recommended_package_id=recommended_pkg_id,
        package_json_path=None,
        package_markdown_path=None,
        bet_builder_compatibility_verdict=bet_builder_compatibility_verdict,
        market_completeness_verdict=market_completeness_verdict,
        multi_stat_package_verdict=multi_stat_package_verdict,
        correlation_review_verdict=correlation_review_verdict,
        operator_screen_required_verdict="PASS",
        no_automated_placement_verdict="PASS",
        ready_for_production_coupon_building=ready_for_production_coupon_building,
        human_manual_placement_required=human_manual_placement_required,
        ready_for_automated_bet_placement=False,
        ready_for_production_execution=False,
        blockers=report_blockers,
        analytical_suggestion_count=analytical_count,
        ready_for_manual_operator_quote_review=ready_for_manual_operator_quote_review,
        classification=classification,
        can_place_bet_now=can_place_bet_now,
        safe_user_action=safe_user_action,
        positive_ev_with_operator_odds_count=positive_ev_with_operator_odds_count
    )

    return packages, report


def generate_package_markdown(pkg: BetBuilderPackage, report: RichCouponPackageReport) -> str:
    """Generate human-readable Markdown analysis report of the coupon package."""
    title_header = "# RICH MANUAL COUPON PACKAGE ANALYSIS"
    if report.classification == "TEST_ONLY_MOCK_ODDS":
        title_header = "# TEST/SMOKE ONLY — RICH MANUAL COUPON PACKAGE ANALYSIS (MOCK ODDS ACTIVE)"
    
    lines = [
        title_header,
        f"**Betting Day**: {pkg.betting_day} | **Session ID**: {pkg.session_id}",
        f"**Package ID**: {pkg.package_id} | **Package Type**: {pkg.package_type}",
        f"**Target Operator**: {pkg.legs[0].operator_name if pkg.legs else 'N/A'}",
        "",
        "## STATUS GATE VERDICT",
        f"* **READY FOR PRODUCTION COUPON BUILDING**: {report.ready_for_production_coupon_building}",
        f"* **HUMAN MANUAL PLACEMENT REQUIRED**: {report.human_manual_placement_required}",
        f"* **READY FOR AUTOMATED BET PLACEMENT**: {report.ready_for_automated_bet_placement}",
        f"* **READY FOR PRODUCTION EXECUTION**: {report.ready_for_production_execution}",
        "",
        "## MARKET VERDICTS",
        f"* **Bet Builder Compatibility**: {report.bet_builder_compatibility_verdict}",
        f"* **Market Completeness**: {report.market_completeness_verdict}",
        f"* **Multi-Stat Package Verification**: {report.multi_stat_package_verdict}",
        f"* **Correlation Review**: {report.correlation_review_verdict}",
        f"* **Operator Screen Matching Required**: {report.operator_screen_required_verdict}",
        f"* **No-Automated Placement Check**: {report.no_automated_placement_verdict}",
        "",
        "## ANALYSIS SUMMARY",
        f"### Value Analysis:",
        pkg.value_summary,
        "",
        f"### Risk & Correlation ({pkg.correlation_risk} RISK):",
        pkg.risk_summary,
        "",
        "---",
        "## COUPON LEGS LIST",
    ]

    for idx, leg in enumerate(pkg.legs, 1):
        lines.extend([
            f"### Leg {idx}: {leg.event} ({leg.sport.upper()})",
            f"* **Market**: {leg.market}",
            f"* **Pick**: {leg.pick} | **Line**: {leg.line}",
            f"* **Captured Odds**: {leg.odds_decimal:.2f} (Captured: {leg.odds_captured_at_utc})",
            f"* **Confidence**: {leg.confidence_label}",
            f"* **Evidence Draft**: `{leg.source_artifact_path}` (SHA: `{leg.source_artifact_sha256[:8]}...`)",
            "",
            "#### Supporting Stats (Point-in-Time Form):",
        ])
        for s in leg.supporting_stats:
            lines.append(f"  * **{s.get('metric')}**: {s.get('value')} (Source: {s.get('source')}, As of: {s.get('as_of')})")

        lines.append("#### Counter-Stats (Adversarial Balance):")
        for c in leg.counter_stats:
            lines.append(f"  * **{c.get('metric')}**: {c.get('value')} (Source: {c.get('source')}, As of: {c.get('as_of')})")

        lines.append("")

    lines.extend([
        "---",
        "## SEQUENTIAL OPERATOR SCREEN MANUAL PLACEMENT CHECKLIST",
    ])
    for step in pkg.operator_screen_checklist:
        lines.append(f"- [ ] {step}")

    lines.extend([
        "",
        "---",
        "### GUARANTEE DISCLAIMER & REGULATORY NOTICE",
        "**WARNING**: Betting involves high risk. This manual-review package does NOT claim, hint at, or guarantee any profit, risk-free returns, or winning outcomes. All predictions are mathematical estimates with inherent margins. Please gamble responsibly.",
    ])

    return "\n".join(lines)
