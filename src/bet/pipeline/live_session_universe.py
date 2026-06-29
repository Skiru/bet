"""Live Session Candidate Universe Controller and Quality Gate."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

@dataclass
class LiveSessionUniverseConfig:
    min_candidates: int = 8
    stale_threshold_seconds: int = 0
    provider_universe_exhausted: bool = False
    allowed_sports: set[str] = field(default_factory=lambda: {
        "football", "volleyball", "basketball", "tennis", "hockey",
        "cs2", "dota2", "valorant"
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_candidates": self.min_candidates,
            "stale_threshold_seconds": self.stale_threshold_seconds,
            "provider_universe_exhausted": self.provider_universe_exhausted,
            "allowed_sports": list(self.allowed_sports),
        }

@dataclass
class CandidateInput:
    candidate_id: str
    event_id: str
    event: str
    sport: str
    competition: str
    kickoff: str
    market: str
    pick: str
    line: Any
    odds_decimal: Decimal
    odds_captured_at_utc: str
    operator_name: str
    supporting_stats: list[dict[str, Any]] = field(default_factory=list)
    counter_stats: list[dict[str, Any]] = field(default_factory=list)
    is_live: bool = False
    player_b: str = ""
    participant: str = ""
    model_probability: Decimal | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateInput:
        # Extract best market odds if nested
        market = data.get("market") or data.get("best_market", {}).get("name") or ""
        pick = data.get("pick") or data.get("best_market", {}).get("direction") or ""
        line = data.get("line") or data.get("best_market", {}).get("line") or ""
        
        # Fallback for nested S4/S7 structure
        best_market = data.get("best_market") or {}
        if not market and best_market:
            market = best_market.get("name") or ""
            pick = best_market.get("direction") or ""
            line = best_market.get("line") or ""
            
        ev_components = data.get("ev_components") or {}
        odds_dec = Decimal("0")
        if data.get("odds_decimal") is not None:
            odds_dec = Decimal(str(data["odds_decimal"]))
        elif ev_components.get("odds") is not None:
            odds_dec = Decimal(str(ev_components["odds"]))
        elif data.get("best_odds") is not None:
            odds_dec = Decimal(str(data["best_odds"]))
        elif data.get("odds") is not None:
            if isinstance(data["odds"], dict) and data["odds"]:
                # Try to get first value
                for val in data["odds"].values():
                    try:
                        odds_dec = Decimal(str(val))
                        break
                    except Exception:
                        pass
            else:
                try:
                    odds_dec = Decimal(str(data["odds"]))
                except Exception:
                    pass

        # Scheduled time resolution
        scheduled_time = data.get("scheduled_time") or data.get("kickoff") or ""
        comp = data.get("competition") or ""
        sport = data.get("sport") or ""
        
        supporting = data.get("supporting_stats") or []
        counter = data.get("counter_stats") or []
        
        model_prob = None
        prob_raw = data.get("model_probability") or data.get("probability") or data.get("prob")
        if prob_raw is not None:
            try:
                model_prob = Decimal(str(prob_raw))
            except Exception:
                pass

        return cls(
            candidate_id=str(data.get("candidate_id") or data.get("fixture_key") or data.get("fixture_id") or ""),
            event_id=str(data.get("event_id") or data.get("fixture_id") or ""),
            event=str(data.get("event") or f"{data.get('home_team', '')} vs {data.get('away_team', '')}"),
            sport=str(sport).strip(),
            competition=str(comp).strip(),
            kickoff=str(scheduled_time).strip(),
            market=str(market).strip(),
            pick=str(pick).strip(),
            line=line,
            odds_decimal=odds_dec,
            odds_captured_at_utc=str(data.get("odds_captured_at_utc") or ev_components.get("odds_captured_at_utc") or data.get("odds_as_of") or ""),
            operator_name=str(data.get("operator_name") or data.get("best_bookmaker") or ev_components.get("best_bookmaker") or ""),
            supporting_stats=supporting,
            counter_stats=counter,
            is_live=bool(data.get("is_live") or data.get("live") or False),
            player_b=str(data.get("player_b") or ""),
            participant=str(data.get("participant") or ""),
            model_probability=model_prob,
        )

# Contract naming compatibility aliases
CandidateUniverseInput = CandidateInput

@dataclass(frozen=True)
class SourceGap:
    candidate_id: str
    gap_type: str  # "H2H" | "INJURY" | "TIPSTER" | "SECOND_SOURCE" | "STAT_H2H"
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "gap_type": self.gap_type,
            "description": self.description,
        }

@dataclass(frozen=True)
class CandidateQualityResult:
    candidate_id: str
    is_valid: bool
    verdict: str
    reasons: list[str]
    source_gaps: list[SourceGap]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "is_valid": self.is_valid,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "source_gaps": [gap.to_dict() for gap in self.source_gaps],
        }

# Class alias to support ENUM/string constants pattern
class CandidateQualityVerdict:
    VALID = "VALID"
    REJECTED_STALE = "REJECTED_STALE"
    REJECTED_MISSING_SPORT = "REJECTED_MISSING_SPORT"
    REJECTED_MISSING_COMPETITION = "REJECTED_MISSING_COMPETITION"
    REJECTED_MISSING_MARKET = "REJECTED_MISSING_MARKET"
    REJECTED_MISSING_LINE = "REJECTED_MISSING_LINE"
    REJECTED_MISSING_ODDS = "REJECTED_MISSING_ODDS"
    REJECTED_MISSING_TIMESTAMP = "REJECTED_MISSING_TIMESTAMP"
    REJECTED_FIXTURE_LABEL = "REJECTED_FIXTURE_LABEL"
    REJECTED_INVALID_KICKOFF_FORMAT = "REJECTED_INVALID_KICKOFF_FORMAT"

@dataclass(frozen=True)
class UniverseQualityReport:
    status: str
    total_input_count: int
    valid_count: int
    rejected_count: int
    source_gap_count: int
    rejected_reasons: dict[str, int]
    source_gaps: list[SourceGap]
    valid_candidates: list[dict[str, Any]]
    as_of_utc: str
    priced_valid_candidates: list[dict[str, Any]] = field(default_factory=list)
    unpriced_analytical_candidates: list[dict[str, Any]] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_input_count": self.total_input_count,
            "valid_count": self.valid_count,
            "rejected_count": self.rejected_count,
            "source_gap_count": self.source_gap_count,
            "rejected_reasons": self.rejected_reasons,
            "source_gaps": [gap.to_dict() for gap in self.source_gaps],
            "valid_candidates": self.valid_candidates,
            "priced_valid_candidates": self.priced_valid_candidates,
            "unpriced_analytical_candidates": self.unpriced_analytical_candidates,
            "rejected_candidates": self.rejected_candidates,
            "as_of_utc": self.as_of_utc,
        }

# Alias compatibility
CandidateUniverseReport = UniverseQualityReport

def classify_candidate_quality(candidate: CandidateInput, config: LiveSessionUniverseConfig) -> CandidateQualityResult:
    reasons = []
    source_gaps = []
    is_valid = True
    verdict = CandidateQualityVerdict.VALID

    # 1. Fixture/Test Labels check
    c_id = candidate.candidate_id.lower()
    event_str = candidate.event.lower()
    market_str = candidate.market.lower()
    pick_str = candidate.pick.lower()
    
    has_fixture_label = False
    for label in ("selection-win", "selection-loss", "selection-void", "fixture", "test"):
        if label in c_id or label in event_str or label in market_str or label in pick_str:
            has_fixture_label = True
            break
            
    if has_fixture_label:
        is_valid = False
        reasons.append("Forbidden fixture/test label found in fields")
        verdict = CandidateQualityVerdict.REJECTED_FIXTURE_LABEL
        return CandidateQualityResult(candidate.candidate_id, is_valid, verdict, reasons, [])

    # 2. Missing Sport/Competition
    if not candidate.sport:
        is_valid = False
        reasons.append("Missing sport name")
        verdict = CandidateQualityVerdict.REJECTED_MISSING_SPORT
    elif not candidate.competition:
        is_valid = False
        reasons.append("Missing competition name")
        verdict = CandidateQualityVerdict.REJECTED_MISSING_COMPETITION

    # 3. Missing Market name
    elif not candidate.market:
        is_valid = False
        reasons.append("Missing market name")
        verdict = CandidateQualityVerdict.REJECTED_MISSING_MARKET

    # 4. Missing O/U Market line
    elif ("O/U" in candidate.market or "Over/Under" in candidate.market or "Total" in candidate.market or candidate.pick.upper() in ("UNDER", "OVER") or candidate.pick.upper().startswith("UNDER ") or candidate.pick.upper().startswith("OVER ")) and (candidate.line in (None, "", "MISSING")):
        is_valid = False
        reasons.append("Missing numeric line for O/U market")
        verdict = CandidateQualityVerdict.REJECTED_MISSING_LINE

    # 5. Missing Odds
    elif candidate.odds_decimal <= Decimal("1.0"):
        is_valid = False
        reasons.append("Missing provider odds decimal")
        verdict = CandidateQualityVerdict.REJECTED_MISSING_ODDS

    # 6. Missing Odds Timestamp
    elif not candidate.odds_captured_at_utc:
        is_valid = False
        reasons.append("Missing odds timestamp")
        verdict = CandidateQualityVerdict.REJECTED_MISSING_TIMESTAMP

    # 7. Stale kickoff (unless live)
    elif not candidate.kickoff:
        is_valid = False
        reasons.append("Missing kickoff time")
        verdict = CandidateQualityVerdict.REJECTED_MISSING_TIMESTAMP
    else:
        try:
            k_str = candidate.kickoff
            if k_str.endswith("Z"):
                k_str = k_str[:-1] + "+00:00"
            dt_kickoff = datetime.fromisoformat(k_str)
            now = datetime.now(timezone.utc)
            if dt_kickoff < now and not candidate.is_live:
                is_valid = False
                reasons.append(f"Stale event kickoff ({candidate.kickoff}) is in the past and is not live")
                verdict = CandidateQualityVerdict.REJECTED_STALE
        except Exception as e:
            is_valid = False
            reasons.append(f"Invalid kickoff format: {candidate.kickoff} ({e})")
            verdict = CandidateQualityVerdict.REJECTED_INVALID_KICKOFF_FORMAT

    if not is_valid:
        return CandidateQualityResult(candidate.candidate_id, is_valid, verdict, reasons, [])

    # 8. Source Gaps check for valid candidates
    # Check H2H presence
    has_h2h = True
    if not candidate.counter_stats:
        has_h2h = False
    else:
        # Check if they are just placeholders or have actual sources
        real_h2h = False
        for stat in candidate.counter_stats:
            src = stat.get("source") or ""
            if src and src != "UNKNOWN" and stat.get("value") != "UNKNOWN":
                real_h2h = True
                break
        if not real_h2h:
            has_h2h = False
            
    if not has_h2h:
        source_gaps.append(SourceGap(candidate.candidate_id, "H2H", "No historical H2H meetings dataset exists"))

    # Check Injury/Suspensions
    has_injuries = False
    for stat in candidate.supporting_stats:
        metric = str(stat.get("metric") or "").lower()
        src = str(stat.get("source") or "").lower()
        if "injury" in metric or "injuries" in metric or "suspension" in metric or "injury" in src or "injuries" in src:
            if stat.get("value") != "UNKNOWN" and stat.get("source") != "UNKNOWN":
                has_injuries = True
                break
    if not has_injuries:
        source_gaps.append(SourceGap(candidate.candidate_id, "INJURY", "No injury or suspension data detected"))

    # Check Tipsters Consensus
    has_tipsters = False
    for stat in candidate.supporting_stats:
        src = str(stat.get("source") or "").lower()
        metric = str(stat.get("metric") or "").lower()
        if "tipster" in src or "consensus" in src or "tip" in src or "tipster" in metric or "consensus" in metric or "tip" in metric or "blogabet" in src:
            if stat.get("value") != "UNKNOWN" and stat.get("source") != "UNKNOWN":
                has_tipsters = True
                break
    if not has_tipsters:
        source_gaps.append(SourceGap(candidate.candidate_id, "TIPSTER", "No valid tipster consensus arguments found"))

    # Check Second Source
    sources = set()
    for stat in candidate.supporting_stats + candidate.counter_stats:
        src = stat.get("source")
        if src and src != "UNKNOWN":
            sources.add(src)
    if len(sources) < 2:
        source_gaps.append(SourceGap(candidate.candidate_id, "SECOND_SOURCE", f"Fewer than 2 independent sources (found: {list(sources)})"))

    # Check Stat-H2H
    has_stat_h2h = False
    for stat in candidate.counter_stats:
        metric = str(stat.get("metric") or "").lower()
        src = str(stat.get("source") or "").lower()
        if "exact" in metric or "stat-specific" in metric or "market-specific" in metric or "exact" in src or "stat" in src:
            if stat.get("value") != "UNKNOWN" and stat.get("source") != "UNKNOWN":
                has_stat_h2h = True
                break
    if not has_stat_h2h:
        source_gaps.append(SourceGap(candidate.candidate_id, "STAT_H2H", "No exact stat-specific H2H historical data exists"))

    return CandidateQualityResult(candidate.candidate_id, is_valid, verdict, reasons, source_gaps)

def classify_unpriced_analytical_candidate(candidate: CandidateInput, raw_dict: dict[str, Any]) -> bool:
    """Check if candidate matches unpriced analytical candidate rules."""
    if not candidate.event or not candidate.sport or not candidate.competition:
        return False
    if not candidate.market or not candidate.pick:
        return False
    is_ou_market = "O/U" in candidate.market or "Over/Under" in candidate.market or "Total" in candidate.market or candidate.pick.upper() in ("UNDER", "OVER") or candidate.pick.upper().startswith("UNDER ") or candidate.pick.upper().startswith("OVER ")
    if is_ou_market and candidate.line in (None, "", "MISSING"):
        return False
    prob = candidate.model_probability
    if prob is None or prob <= Decimal("0") or prob >= Decimal("1"):
        return False
    if not candidate.supporting_stats:
        return False
    return True

def validate_candidate_sufficiency(valid_count: int, config: LiveSessionUniverseConfig) -> str:
    if valid_count >= config.min_candidates:
        return "READY_FOR_S7"
    if config.provider_universe_exhausted:
        return "BLOCKED_PROVIDER_UNIVERSE_EXHAUSTED"
    return "BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE"

def build_pre_s7_universe(raw_candidates: list[dict[str, Any]], config: LiveSessionUniverseConfig) -> UniverseQualityReport:
    priced_valid_candidates = []
    unpriced_analytical_candidates = []
    rejected_candidates = []
    source_gaps = []
    rejected_reasons = {}

    for raw in raw_candidates:
        cand = CandidateInput.from_dict(raw)
        res = classify_candidate_quality(cand, config)
        if res.is_valid:
            priced_valid_candidates.append(raw)
            source_gaps.extend(res.source_gaps)
        else:
            if cand.odds_decimal <= Decimal("1.0") and classify_unpriced_analytical_candidate(cand, raw):
                raw_copy = dict(raw)
                raw_copy["status"] = "PRICE_PENDING_OPERATOR_CHECK"
                unpriced_analytical_candidates.append(raw_copy)
                source_gaps.extend(res.source_gaps)
            else:
                rejected_candidates.append(raw)
                rejected_reasons[res.verdict] = rejected_reasons.get(res.verdict, 0) + 1

    if len(priced_valid_candidates) >= config.min_candidates:
        status = "READY_FOR_S7"
    elif len(unpriced_analytical_candidates) > 0:
        status = "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"
    elif config.provider_universe_exhausted:
        status = "BLOCKED_PROVIDER_UNIVERSE_EXHAUSTED"
    else:
        status = "BLOCKED_INSUFFICIENT_CANDIDATE_UNIVERSE"

    return UniverseQualityReport(
        status=status,
        total_input_count=len(raw_candidates),
        valid_count=len(priced_valid_candidates),
        rejected_count=len(rejected_candidates),
        source_gap_count=len(source_gaps),
        rejected_reasons=rejected_reasons,
        source_gaps=source_gaps,
        valid_candidates=priced_valid_candidates,
        priced_valid_candidates=priced_valid_candidates,
        unpriced_analytical_candidates=unpriced_analytical_candidates,
        rejected_candidates=rejected_candidates,
        as_of_utc=datetime.now(timezone.utc).isoformat()
    )

def write_universe_report(report: UniverseQualityReport, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def build_s7_traceability_fields(
    report: UniverseQualityReport,
    *,
    report_path: Path,
    input_path: Path | None,
    selection_policy: str = "none",
    selection_reason: str = "N/A",
    selection_source_path: Path | None = None,
    selected_count: int | None = None,
    metric_context: str = "E2E_S7",
) -> dict[str, Any]:
    resolved_report_path = str(Path(report_path))
    resolved_selection_source = selection_source_path or input_path

    if selection_policy == "top_n":
        if selected_count is None:
            raise ValueError("top_n selection requires selected_count")
        if not selection_reason or selection_reason == "N/A":
            raise ValueError("top_n selection requires explicit selection_reason")
        if resolved_selection_source is None:
            raise ValueError("top_n selection requires explicit selection_source_path")
    else:
        selected_count = report.valid_count
        selection_reason = "N/A"

    return {
        "pre_s7_universe_report_path": resolved_report_path,
        "pre_s7_total_input_count": report.total_input_count,
        "pre_s7_valid_count": report.valid_count,
        "pre_s7_metric_context": metric_context,
        "s7_input_count": selected_count,
        "s7_selection_policy": selection_policy,
        "s7_selection_reason": selection_reason,
        "s7_selected_count": selected_count,
        "s7_selection_source_path": str(resolved_selection_source) if resolved_selection_source else None,
        "s7_metric_context": metric_context,
    }


def classify_wiring_fault(
    *,
    pre_s7_metric_context: str,
    s7_metric_context: str,
    pre_s7_valid_count: int | None,
    s7_input_count: int | None,
    s7_selection_policy: str | None,
    s7_selection_reason: str | None,
    s7_selection_source_path: str | None,
) -> str:
    if pre_s7_metric_context != s7_metric_context:
        return "METRIC_CONTEXT_MIXED"
    if s7_selection_policy == "top_n":
        if not s7_selection_reason or s7_selection_reason == "N/A" or not s7_selection_source_path:
            return "EXPLICIT_TOP_N_SELECTION_MISSING"
        return "NONE"
    if pre_s7_valid_count is not None and s7_input_count is not None and pre_s7_valid_count != s7_input_count:
        return "S7_WIRING_BUG"
    return "NONE"
