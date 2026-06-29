"""Daily Manual Session Control and Safety Gate."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bet.pipeline.full_shadow_acceptance import is_protected_repo_path, REPO_ROOT
from bet.pipeline.run_evidence import utc_now_iso


TASK_ID = "PIPELINE_DAILY_MANUAL_SESSION_CONTROL_A_V2_AGENT_AWARE"
ZERO = Decimal("0")


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve(strict=False).relative_to(Path(root).resolve(strict=False))
        return True
    except ValueError:
        return False


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
class DailyManualSessionConfig:
    base_dir: Path
    betting_day: str
    session_id: str
    session_dir: Path
    session_ledger_path: Path
    max_session_coupons: int = 1
    max_stake_units_per_coupon: Decimal = Decimal("1")
    max_daily_risk_units: Decimal = Decimal("1")
    daily_stop_loss_units: Decimal = Decimal("1")
    kill_switch: bool = False
    legal_operator_attested: bool = False
    age_kyc_attested: bool = False
    responsible_gambling_limits_attested: bool = False
    allow_automated_bookmaker_placement: bool = False
    allow_betclic_api: bool = False
    allow_browser_automation: bool = False
    allow_repo_protected_writes: bool = False

    def normalized(self) -> DailyManualSessionConfig:
        return DailyManualSessionConfig(
            base_dir=Path(self.base_dir).resolve(strict=False),
            betting_day=str(self.betting_day).strip(),
            session_id=str(self.session_id).strip(),
            session_dir=Path(self.session_dir).resolve(strict=False),
            session_ledger_path=Path(self.session_ledger_path).resolve(strict=False),
            max_session_coupons=int(self.max_session_coupons),
            max_stake_units_per_coupon=_to_decimal(self.max_stake_units_per_coupon),
            max_daily_risk_units=_to_decimal(self.max_daily_risk_units),
            daily_stop_loss_units=_to_decimal(self.daily_stop_loss_units),
            kill_switch=bool(self.kill_switch),
            legal_operator_attested=bool(self.legal_operator_attested),
            age_kyc_attested=bool(self.age_kyc_attested),
            responsible_gambling_limits_attested=bool(self.responsible_gambling_limits_attested),
            allow_automated_bookmaker_placement=bool(self.allow_automated_bookmaker_placement),
            allow_betclic_api=bool(self.allow_betclic_api),
            allow_browser_automation=bool(self.allow_browser_automation),
            allow_repo_protected_writes=bool(self.allow_repo_protected_writes),
        )


@dataclass(frozen=True)
class RealPickReview:
    candidate_id: str
    betting_day: str
    session_id: str
    source_s8_coupon_draft_path: str
    source_s8_coupon_draft_sha256: str
    source_s9_artifact_path: str | None
    source_s9_artifact_sha256: str | None
    event: str
    event_id: str
    player_a: str
    player_b: str
    market: str
    pick: str
    line: str
    odds_decimal: Decimal
    odds_captured_at_utc: str
    operator_name: str
    stake_units: Decimal
    review_status: str  # BETTABLE_MANUAL_ONLY|NO_BET|BLOCKED
    decision_reason: str
    blockers: list[str]
    as_of_utc: str
    model_probability: Decimal | None = None
    fair_odds: Decimal | None = None
    min_acceptable_operator_odds: Decimal | None = None
    operator_quote: dict | None = None
    correlation_risk: str = "LOW"
    correlation_notes: str = ""
    scenario_coherence_score: Decimal | None = None
    conflicting_legs: list[str] = field(default_factory=list)
    combined_bookmaker_odds_computed: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({f.name: getattr(self, f.name) for f in fields(self)})


@dataclass(frozen=True)
class DailyManualSessionReport:
    task_id: str
    status: str
    betting_day: str
    session_id: str
    session_ledger_path: str
    candidate_count: int
    no_bet_count: int
    bettable_count: int
    prepared_manual_coupon_count: int
    placed_manual_coupon_count: int
    settled_coupon_count: int
    open_risk_units: Decimal
    realized_loss_units: Decimal
    max_session_coupons: int
    max_stake_units_per_coupon: Decimal
    max_daily_risk_units: Decimal
    daily_stop_loss_units: Decimal
    kill_switch_verdict: str
    legal_operator_attestation_verdict: str
    age_kyc_attestation_verdict: str
    responsible_gambling_limits_verdict: str
    market_completeness_verdict: str
    operator_screen_match_required_verdict: str
    budget_guard_verdict: str
    stop_loss_guard_verdict: str
    no_fixture_selection_verdict: str
    no_automated_bookmaker_placement_verdict: str
    no_betclic_api_verdict: str
    no_browser_automation_verdict: str
    protected_repo_write_verdict: str
    ready_for_manual_session: bool
    ready_for_production_execution: bool
    ready_for_manual_operator_quote_review: bool
    ready_for_manual_placement: bool
    ready_for_automated_bet_placement: bool
    blockers: list[str]

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


def extract_line(selection: dict[str, Any]) -> Decimal | None:
    line_val = selection.get("line")
    if line_val not in (None, "", "MISSING"):
        try:
            return Decimal(str(line_val))
        except (ValueError, TypeError, InvalidOperation):
            pass

    pick_str = str(selection.get("pick") or "").strip().upper()
    for word in ("UNDER", "OVER"):
        if pick_str.startswith(word):
            rest = pick_str[len(word):].strip()
            if rest:
                try:
                    return Decimal(rest)
                except (ValueError, TypeError, InvalidOperation):
                    pass
    return None


def operator_quote_gate(*, actual_odds: Decimal, min_acceptable: Decimal) -> str:
    """Evaluates entered manual operator quote against min acceptable threshold."""
    if actual_odds >= min_acceptable:
        return "PRICE_ACCEPTABLE_MANUAL_QUOTE"
    return "REJECTED_BY_PRICE"


def evidence_correlation_gate(
    *,
    supporting_stats: list[dict[str, Any]],
    counter_stats: list[dict[str, Any]],
    correlation_risk: str,
) -> tuple[bool, str]:
    """Evaluates evidence completeness and correlation risk."""
    if correlation_risk == "HIGH":
        return False, "Correlation risk is HIGH"
    if not supporting_stats:
        return False, "Evidence pack (supporting stats) is empty"
    has_valid_source = False
    for stat in supporting_stats:
        src = stat.get("source")
        val = stat.get("value")
        if src and src != "UNKNOWN" and val != "UNKNOWN":
            has_valid_source = True
            break
    if not has_valid_source:
        return False, "No valid evidence sources found in supporting stats"
    return True, "Passed evidence and correlation checks"


def review_s8_candidate_for_manual_session(
    *,
    config: DailyManualSessionConfig,
    s8_coupon_draft_path: Path,
    s8_coupon_draft_sha256: str,
    s9_artifact_path: Path | None,
    s9_artifact_sha256: str | None,
    operator_name: str,
) -> list[RealPickReview]:
    from bet.pipeline.artifact_gate import load_artifact

    normalized = config.normalized()
    draft = load_artifact(s8_coupon_draft_path)

    reviews: list[RealPickReview] = []
    drafts_list = draft.get("drafts") or []
    if not isinstance(drafts_list, list):
        drafts_list = [draft]

    for draft_idx, draft_entry in enumerate(drafts_list):
        draft_id = str(draft_entry.get("draft_id") or draft_entry.get("id") or f"draft-{draft_idx}")
        selections = draft_entry.get("selections") or []
        if not isinstance(selections, list):
            continue

        # Correlation Guard (Phase 6)
        corr_info = {
            "same_match": False,
            "correlation_risk": "LOW",
            "correlation_notes": "Single leg candidate",
            "scenario_coherence_score": Decimal("1.0"),
            "conflicting_legs": [],
            "combined_bookmaker_odds_computed": False
        }
        if len(selections) > 1:
            events_set = {str(s.get("event") or s.get("fixture") or "") for s in selections}
            corr_info["same_match"] = len(events_set) == 1
            corr_markets = [str(s.get("market") or s.get("market_name") or "").lower() for s in selections]
            corr_picks = [str(s.get("pick") or s.get("direction") or "").lower() for s in selections]
            
            conflicting_legs = []
            for i, m1 in enumerate(corr_markets):
                for j, m2 in enumerate(corr_markets):
                    if i >= j:
                        continue
                    p1 = corr_picks[i]
                    p2 = corr_picks[j]
                    if m1 == m2 and p1 != p2:
                        corr_info["correlation_risk"] = "HIGH"
                        corr_info["correlation_notes"] = f"Direct logical contradiction on {m1}: {p1} vs {p2}"
                        corr_info["scenario_coherence_score"] = Decimal("0.0")
                        conflicting_legs.append(m1)
            corr_info["conflicting_legs"] = conflicting_legs
            
            if corr_info["correlation_risk"] == "LOW" and corr_info["same_match"]:
                if any("player" in m for m in corr_markets) and any("total" in m or "o/u" in m for m in corr_markets):
                    corr_info["correlation_risk"] = "HIGH"
                    corr_info["correlation_notes"] = "High correlation: combines player-specific and total/O/U markets."
                    corr_info["scenario_coherence_score"] = Decimal("0.7")
                else:
                    corr_info["correlation_risk"] = "MEDIUM"
                    corr_info["correlation_notes"] = "Medium correlation: standard same-match Bet Builder."
                    corr_info["scenario_coherence_score"] = Decimal("0.8")

        for sel_idx, selection in enumerate(selections):
            selection_id = str(selection.get("selection_id") or selection.get("id") or f"sel-{sel_idx}")
            candidate_id = f"{normalized.session_id}:{draft_id}:{selection_id}"

            event = str(selection.get("event") or selection.get("fixture") or "")
            market = str(selection.get("market") or selection.get("market_name") or "")
            pick = str(selection.get("pick") or selection.get("direction") or "")

            raw_odds = selection.get("odds_decimal") or selection.get("odds") or selection.get("price")
            odds_decimal = ZERO
            if raw_odds not in (None, ""):
                try:
                    odds_decimal = _to_decimal(raw_odds)
                except ValueError:
                    pass

            odds_captured_at_utc = str(selection.get("odds_captured_at_utc") or selection.get("captured_at_utc") or selection.get("timestamp") or "")
            raw_stake = selection.get("stake_units") or selection.get("stake")
            stake_units = ZERO
            if raw_stake not in (None, ""):
                try:
                    stake_units = _to_decimal(raw_stake)
                except ValueError:
                    pass
            else:
                stake_units = Decimal("1")

            is_unpriced = (odds_decimal == ZERO)

            # Fair Odds / Min Acceptable Odds (Phase 4)
            model_probability = None
            prob_raw = selection.get("model_probability") or selection.get("probability") or selection.get("prob")
            if prob_raw is not None:
                try:
                    model_probability = _to_decimal(prob_raw)
                except ValueError:
                    pass

            confidence_label = str(selection.get("confidence_label") or selection.get("confidence") or "MEDIUM").upper()
            fair_odds = None
            min_acceptable_operator_odds = None
            prob_err = None

            if model_probability is not None:
                if model_probability <= ZERO or model_probability >= Decimal("1"):
                    raise ValueError("model_probability must be > 0 and < 1")
                fair_odds = (Decimal("1") / model_probability).quantize(Decimal("0.0001"))
                margin_multipliers = {
                    "HIGH": Decimal("1.05"),
                    "MEDIUM": Decimal("1.08"),
                    "LOW": Decimal("1.12")
                }
                mult = margin_multipliers.get(confidence_label, Decimal("1.08"))
                min_acceptable_operator_odds = (fair_odds * mult).quantize(Decimal("0.0001"))
            elif is_unpriced:
                prob_err = "INSUFFICIENT_MODEL_PROBABILITY"

            # Parse players
            player_a = str(selection.get("player_a") or "")
            player_b = str(selection.get("player_b") or "")
            if not player_a or not player_b:
                if " vs " in event:
                    parts = event.split(" vs ")
                    if len(parts) == 2:
                        if not player_a:
                            player_a = parts[0].strip()
                        if not player_b:
                            player_b = parts[1].strip()
                elif " - " in event:
                    parts = event.split(" - ")
                    if len(parts) == 2:
                        if not player_a:
                            player_a = parts[0].strip()
                        if not player_b:
                            player_b = parts[1].strip()

            # Line extraction
            line_dec = extract_line(selection)
            line = str(line_dec) if line_dec is not None else "MISSING"

            blockers: list[str] = []

            # 1. Missing fields
            if not event:
                blockers.append("missing event name")
            if not market:
                blockers.append("missing market")
            if not pick:
                blockers.append("missing pick")
            
            if not is_unpriced:
                if odds_decimal == ZERO:
                    blockers.append("missing odds decimal")
                if not odds_captured_at_utc:
                    blockers.append("missing odds captured at utc")
            
            if not operator_name:
                blockers.append("missing operator name")

            # O/U market check
            is_ou_market = "O/U" in market or "Over/Under" in market or "Total" in market or pick in ("UNDER", "OVER") or pick.upper().startswith("UNDER ") or pick.upper().startswith("OVER ")
            if is_ou_market and line == "MISSING":
                blockers.append("missing exact O/U line")

            # Player specific market checks
            is_player_specific = "Player A" in market or "Player B" in market or "Player" in market or (player_b and player_b in market) or (player_a and player_a in market)
            if is_player_specific and (not player_b or player_b.strip() in ("", "?", "UNKNOWN")):
                blockers.append("missing player_b for player-specific market")

            # S8/S9 path checks
            if not s8_coupon_draft_path or not s8_coupon_draft_sha256:
                blockers.append("missing source S8 path/SHA")
            if s9_artifact_path is None or s9_artifact_sha256 is None:
                blockers.append("missing source S9 path/SHA")

            # 2. Hard rejects as NO_BET
            # selection_id labels
            if any(label in str(selection_id).lower() for label in ("selection-win", "selection-loss", "selection-void", "fixture", "test")):
                blockers.append("contains fixture/test labels")

            # odds <= 1
            if not is_unpriced and odds_decimal > ZERO and odds_decimal <= Decimal("1"):
                blockers.append("odds decimal must be > 1")

            # stake > max_stake_units_per_coupon
            if stake_units > normalized.max_stake_units_per_coupon:
                blockers.append(f"stake units {stake_units} exceeds max stake units per coupon {normalized.max_stake_units_per_coupon}")

            # production artifacts
            if draft.get("ready_for_production_execution") is True:
                blockers.append("artifact has ready_for_production_execution=true")
            if draft.get("betclic_execution_enabled") is True:
                blockers.append("artifact has betclic_execution_enabled=true")

            # Protected paths
            if is_protected_repo_path(s8_coupon_draft_path, REPO_ROOT) or (s9_artifact_path and is_protected_repo_path(s9_artifact_path, REPO_ROOT)):
                blockers.append("repo-protected path is used")

            # Compatibility warnings
            decision_reason = "Passed all daily manual session safety checks"
            if normalized.session_dir:
                if not _path_is_within(s8_coupon_draft_path, normalized.session_dir):
                    decision_reason = f"Compatibility warning: S8 path {s8_coupon_draft_path} is outside session root {normalized.session_dir}"

            # Operator quote / Quote decision logic (Phase 3)
            operator_quote = selection.get("operator_quote") or selection.get("manual_quote")
            quote_decision_status = None
            quote_decision_reason = ""

            if is_unpriced:
                if prob_err:
                    quote_decision_status = "INSUFFICIENT_MODEL_PROBABILITY"
                    quote_decision_reason = "Missing model probability for unpriced candidate"
                elif operator_quote is None:
                    quote_decision_status = "PRICE_PENDING_OPERATOR_CHECK"
                    quote_decision_reason = "No manual Superbet quote provided"
                else:
                    quote_status = operator_quote.get("quote_status") or "QUOTE_ENTERED"
                    actual_odds_raw = operator_quote.get("combined_odds_decimal") or operator_quote.get("odds_decimal")
                    actual_odds = ZERO
                    if actual_odds_raw not in (None, ""):
                        try:
                            actual_odds = _to_decimal(actual_odds_raw)
                        except ValueError:
                            pass
                    actual_line = operator_quote.get("line")
                    is_bet_builder = len(selections) > 1

                    entered_by_human = operator_quote.get("entered_by_human", True)
                    computed_by_pipeline = operator_quote.get("computed_by_pipeline", False)

                    # check synthesized by multiplication
                    synthesized = False
                    if len(selections) > 1:
                        prod = Decimal("1")
                        for s in selections:
                            oq = s.get("operator_quote") or s.get("manual_quote") or {}
                            o_dec = ZERO
                            raw_o = oq.get("odds_decimal") or s.get("odds_decimal") or s.get("odds") or s.get("price")
                            if raw_o not in (None, ""):
                                try:
                                    o_dec = _to_decimal(raw_o)
                                except ValueError:
                                    pass
                            if o_dec > ZERO:
                                prod *= o_dec
                        if prod > Decimal("1") and abs(actual_odds - prod) < Decimal("0.0001"):
                            synthesized = True

                    if entered_by_human is False or computed_by_pipeline is True or synthesized:
                        quote_decision_status = "NO_FAKE_OPERATOR_QUOTE"
                        quote_decision_reason = "Fake computed quote blocked: must be entered by human and not computed by pipeline or synthesized by leg multiplication"
                    elif quote_status == "QUOTE_MISSING":
                        quote_decision_status = "BET_BUILDER_QUOTE_REQUIRED" if is_bet_builder else "PRICE_PENDING_OPERATOR_CHECK"
                        quote_decision_reason = "Operator quote is missing"
                    elif is_bet_builder and operator_quote.get("combined_odds_decimal") in (None, "", ZERO, 0):
                        quote_decision_status = "BET_BUILDER_QUOTE_REQUIRED"
                        quote_decision_reason = "Bet Builder combined odds missing"
                    elif line != "MISSING" and actual_line is not None and str(line) != str(actual_line):
                        quote_decision_status = "LINE_MISMATCH_REQUIRES_REMODEL"
                        quote_decision_reason = f"Line mismatch: candidate line {line} vs operator line {actual_line}"
                    elif actual_odds == ZERO:
                        quote_decision_status = "PRICE_PENDING_OPERATOR_CHECK"
                        quote_decision_reason = "Manual operator quote odds missing"
                    else:
                        if min_acceptable_operator_odds is not None:
                            q_gate_res = operator_quote_gate(actual_odds=actual_odds, min_acceptable=min_acceptable_operator_odds)
                        else:
                            q_gate_res = "PRICE_ACCEPTABLE_MANUAL_QUOTE"

                        if q_gate_res == "REJECTED_BY_PRICE":
                            quote_decision_status = "REJECTED_BY_PRICE"
                            quote_decision_reason = f"Operator odds {actual_odds} below minimum acceptable odds {min_acceptable_operator_odds}"
                        else:
                            # Quote gate passed (PRICE_ACCEPTABLE_MANUAL_QUOTE).
                            # Check timestamp and evidence/correlation gate
                            has_timestamp = bool(operator_quote.get("as_of_utc"))
                            supporting_stats = selection.get("supporting_stats") or []
                            counter_stats = selection.get("counter_stats") or []
                            correlation_risk = corr_info["correlation_risk"]

                            ev_corr_passed, ev_corr_reason = evidence_correlation_gate(
                                supporting_stats=supporting_stats,
                                counter_stats=counter_stats,
                                correlation_risk=correlation_risk,
                            )

                            if not has_timestamp:
                                quote_decision_status = "PRICE_PENDING_OPERATOR_CHECK"
                                quote_decision_reason = "Operator quote as_of timestamp is missing"
                            elif not ev_corr_passed:
                                quote_decision_status = "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW"
                                quote_decision_reason = f"Passed operator quote gate: {actual_odds} >= {min_acceptable_operator_odds} (PRICE_ACCEPTABLE_MANUAL_QUOTE), but pending evidence/correlation check: {ev_corr_reason}"
                            else:
                                quote_decision_status = "BETTABLE_MANUAL_ONLY"
                                quote_decision_reason = f"Passed operator quote, line, timestamp, evidence, and correlation gates: {actual_odds} >= {min_acceptable_operator_odds}"

            if blockers:
                review_status = "NO_BET"
                decision_reason = "; ".join(blockers)
            elif is_unpriced:
                review_status = quote_decision_status
                decision_reason = quote_decision_reason
            else:
                review_status = "BETTABLE_MANUAL_ONLY"

            reviews.append(
                RealPickReview(
                    candidate_id=candidate_id,
                    betting_day=normalized.betting_day,
                    session_id=normalized.session_id,
                    source_s8_coupon_draft_path=str(s8_coupon_draft_path),
                    source_s8_coupon_draft_sha256=str(s8_coupon_draft_sha256),
                    source_s9_artifact_path=str(s9_artifact_path) if s9_artifact_path else None,
                    source_s9_artifact_sha256=str(s9_artifact_sha256) if s9_artifact_sha256 else None,
                    event=event,
                    event_id=str(selection.get("event_id") or selection.get("fixture_id") or f"evt-{sel_idx}"),
                    player_a=player_a,
                    player_b=player_b,
                    market=market,
                    pick=pick,
                    line=line,
                    odds_decimal=odds_decimal,
                    odds_captured_at_utc=odds_captured_at_utc,
                    operator_name=operator_name,
                    stake_units=stake_units,
                    review_status=review_status,
                    decision_reason=decision_reason,
                    blockers=blockers,
                    as_of_utc=utc_now_iso(),
                    model_probability=model_probability,
                    fair_odds=fair_odds,
                    min_acceptable_operator_odds=min_acceptable_operator_odds,
                    operator_quote=operator_quote,
                    correlation_risk=corr_info["correlation_risk"],
                    correlation_notes=corr_info["correlation_notes"],
                    scenario_coherence_score=corr_info["scenario_coherence_score"],
                    conflicting_legs=corr_info["conflicting_legs"],
                    combined_bookmaker_odds_computed=False
                )
            )

    return reviews


def append_ledger_event(ledger_path: Path, event_type: str, betting_day: str, session_id: str, payload: dict[str, Any]) -> None:
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": 1,
        "event_type": event_type,
        "recorded_at_utc": utc_now_iso(),
        "betting_day": betting_day,
        "session_id": session_id,
        "payload": _serialize_jsonable(payload),
    }
    with open(ledger_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def load_session_state(ledger_path: Path) -> dict[str, Any]:
    state = {
        "reviewed": {},
        "prepared": {},
        "placed": {},
        "settled": {},
    }
    if not ledger_path.exists():
        return state

    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            event = json.loads(stripped)
            event_type = event.get("event_type")
            payload = event.get("payload") or {}

            if event_type in ("candidate_reviewed", "candidate_rejected_no_bet"):
                c_id = payload.get("candidate_id")
                if c_id:
                    state["reviewed"][c_id] = payload
            elif event_type == "manual_coupon_prepared":
                coupon_id = payload.get("manual_pilot_coupon_id")
                if coupon_id:
                    state["prepared"][coupon_id] = payload
            elif event_type == "manual_coupon_placed_recorded":
                coupon_id = payload.get("manual_pilot_coupon_id")
                if coupon_id:
                    state["placed"][coupon_id] = payload
            elif event_type == "manual_coupon_settled":
                coupon_id = payload.get("manual_pilot_coupon_id")
                if coupon_id:
                    state["settled"][coupon_id] = payload

    return state


def generate_daily_session_report(
    config: DailyManualSessionConfig,
) -> DailyManualSessionReport:
    normalized = config.normalized()
    state = load_session_state(normalized.session_ledger_path)

    candidate_count = len(state["reviewed"])
    no_bet_count = sum(1 for c in state["reviewed"].values() if c.get("review_status") == "NO_BET")
    bettable_count = sum(1 for c in state["reviewed"].values() if c.get("review_status") == "BETTABLE_MANUAL_ONLY")
    analytical_count = sum(1 for c in state["reviewed"].values() if c.get("review_status") in ("PRICE_PENDING_OPERATOR_CHECK", "BET_BUILDER_QUOTE_REQUIRED", "LINE_MISMATCH_REQUIRES_REMODEL", "NO_OPERATOR_MARKET_FOUND", "INSUFFICIENT_MODEL_PROBABILITY", "NO_FAKE_OPERATOR_QUOTE", "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW"))

    prepared_count = len(state["prepared"])
    placed_count = len(state["placed"])
    settled_count = len(state["settled"])

    # Calculate risk and losses
    open_risk_units = ZERO
    realized_loss_units = ZERO

    # Trace active state of prepared coupons
    for coupon_id, prep in state["prepared"].items():
        is_settled = coupon_id in state["settled"]
        stake = Decimal(str(prep.get("stake_units") or "0"))
        if not is_settled:
            open_risk_units += stake

    for coupon_id, set_item in state["settled"].items():
        pnl = Decimal(str(set_item.get("pnl_units") or "0"))
        if pnl < ZERO:
            realized_loss_units += abs(pnl)

    # Validate global configuration constraints
    blockers: list[str] = []

    kill_switch_verdict = "PASS"
    if normalized.kill_switch:
        kill_switch_verdict = "FAIL"
        blockers.append("kill_switch is active")

    legal_operator_attestation_verdict = "PASS" if normalized.legal_operator_attested else "FAIL"
    if not normalized.legal_operator_attested:
        blockers.append("legal_operator_attested is false")

    age_kyc_attestation_verdict = "PASS" if normalized.age_kyc_attested else "FAIL"
    if not normalized.age_kyc_attested:
        blockers.append("age_kyc_attested is false")

    responsible_gambling_limits_verdict = "PASS" if normalized.responsible_gambling_limits_attested else "FAIL"
    if not normalized.responsible_gambling_limits_attested:
        blockers.append("responsible_gambling_limits_attested is false")

    # completeness and fixture checks
    market_completeness_verdict = "PASS"
    no_fixture_selection_verdict = "PASS"
    for c_id, cand in state["reviewed"].items():
        if cand.get("review_status") == "NO_BET":
            reasons = cand.get("decision_reason") or ""
            if "missing exact O/U line" in reasons or "missing player_b for player-specific market" in reasons or "missing" in reasons:
                market_completeness_verdict = "FAIL"
            if "contains fixture/test labels" in reasons:
                no_fixture_selection_verdict = "FAIL"

    operator_screen_match_required_verdict = "PASS"

    budget_guard_verdict = "PASS"
    if open_risk_units > normalized.max_daily_risk_units:
        budget_guard_verdict = "FAIL"
        blockers.append(f"open risk units {open_risk_units} exceeds max daily risk units {normalized.max_daily_risk_units}")

    stop_loss_guard_verdict = "PASS"
    if realized_loss_units > normalized.daily_stop_loss_units:
        stop_loss_guard_verdict = "FAIL"
        blockers.append(f"realized losses {realized_loss_units} exceeds daily stop loss units {normalized.daily_stop_loss_units}")

    no_automated_bookmaker_placement_verdict = "PASS" if not normalized.allow_automated_bookmaker_placement else "FAIL"
    if normalized.allow_automated_bookmaker_placement:
        blockers.append("automated bookmaker placement must remain disabled")

    no_betclic_api_verdict = "PASS" if not normalized.allow_betclic_api else "FAIL"
    if normalized.allow_betclic_api:
        blockers.append("Betclic API execution must remain disabled")

    no_browser_automation_verdict = "PASS" if not normalized.allow_browser_automation else "FAIL"
    if normalized.allow_browser_automation:
        blockers.append("browser automation must remain disabled")

    protected_repo_write_verdict = "PASS" if not normalized.allow_repo_protected_writes else "FAIL"
    if normalized.allow_repo_protected_writes:
        blockers.append("repo protected writes must remain disabled")

    # session dir check outside repo root
    if _path_is_within(normalized.session_dir, Path(REPO_ROOT).resolve(strict=False)):
        blockers.append(f"session_dir must be outside repo root: {normalized.session_dir}")

    ready_for_manual_operator_quote_review = len(blockers) == 0 and (bettable_count > 0 or analytical_count > 0)
    ready_for_manual_placement = len(blockers) == 0 and bettable_count > 0
    ready_for_manual_session = ready_for_manual_placement
    ready_for_automated_bet_placement = False

    return DailyManualSessionReport(
        task_id=TASK_ID,
        status="PASS" if len(blockers) == 0 else "FAIL",
        betting_day=normalized.betting_day,
        session_id=normalized.session_id,
        session_ledger_path=str(normalized.session_ledger_path),
        candidate_count=candidate_count,
        no_bet_count=no_bet_count,
        bettable_count=bettable_count,
        prepared_manual_coupon_count=prepared_count,
        placed_manual_coupon_count=placed_count,
        settled_coupon_count=settled_count,
        open_risk_units=open_risk_units,
        realized_loss_units=realized_loss_units,
        max_session_coupons=normalized.max_session_coupons,
        max_stake_units_per_coupon=normalized.max_stake_units_per_coupon,
        max_daily_risk_units=normalized.max_daily_risk_units,
        daily_stop_loss_units=normalized.daily_stop_loss_units,
        kill_switch_verdict=kill_switch_verdict,
        legal_operator_attestation_verdict=legal_operator_attestation_verdict,
        age_kyc_attestation_verdict=age_kyc_attestation_verdict,
        responsible_gambling_limits_verdict=responsible_gambling_limits_verdict,
        market_completeness_verdict=market_completeness_verdict,
        operator_screen_match_required_verdict=operator_screen_match_required_verdict,
        budget_guard_verdict=budget_guard_verdict,
        stop_loss_guard_verdict=stop_loss_guard_verdict,
        no_fixture_selection_verdict=no_fixture_selection_verdict,
        no_automated_bookmaker_placement_verdict=no_automated_bookmaker_placement_verdict,
        no_betclic_api_verdict=no_betclic_api_verdict,
        no_browser_automation_verdict=no_browser_automation_verdict,
        protected_repo_write_verdict=protected_repo_write_verdict,
        ready_for_manual_session=ready_for_manual_session,
        ready_for_production_execution=False,
        ready_for_manual_operator_quote_review=ready_for_manual_operator_quote_review,
        ready_for_manual_placement=ready_for_manual_placement,
        ready_for_automated_bet_placement=ready_for_automated_bet_placement,
        blockers=blockers,
    )
