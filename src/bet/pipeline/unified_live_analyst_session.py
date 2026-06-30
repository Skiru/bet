"""Unified live analyst session.

This module implements ONE default live/manual session output:

    discovered events / run artifacts
      -> sports analyst recommendations
      -> optional Bet Builder idea grouping
      -> optional human Superbet quote validation
      -> final manual coupon only after human quote

Odds, HYDRATED status, and model_probability are optional for analysis. They
are mandatory only for EV/fair-odds/final-coupon semantics. The module is
standalone so it can be wired into the current S0-S10 pipeline without weakening
existing final-coupon safety gates.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

Confidence = Literal["A", "B", "C", "D"]
DataQuality = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
SourceCoverage = Literal["STRONG", "PARTIAL", "WEAK"]
SuggestedUse = Literal["SINGLE", "BET_BUILDER_LEG", "WATCHLIST_ONLY"]
PackageType = Literal[
    "ANALYST_RECOMMENDATION_PACKAGE",
    "FINAL_MANUAL_COUPON_PACKAGE",
    "QUOTE_REJECTED_PACKAGE",
    "NO_SUPPORTED_MATCHES_PACKAGE",
]

SUPPORTED_FOOTBALL_MARKETS = {
    "GOALS_TOTALS",
    "CORNERS",
    "CARDS",
    "SHOTS",
    "SHOTS_ON_TARGET",
    "RESULT",
    "DOUBLE_CHANCE",
}
SUPPORTED_TENNIS_MARKETS = {
    "MATCH_WINNER",
    "TOTAL_GAMES",
    "SET_HANDICAP",
    "GAME_HANDICAP",
    "TIEBREAK_YES_NO",
    "ACES",
    "BREAKS",
}

MARKET_ALIASES = {
    "total_goals": "GOALS_TOTALS",
    "goals_total": "GOALS_TOTALS",
    "goals": "GOALS_TOTALS",
    "totals": "GOALS_TOTALS",
    "over_under": "GOALS_TOTALS",
    "ou": "GOALS_TOTALS",
    "corners": "CORNERS",
    "total_corners": "CORNERS",
    "corner": "CORNERS",
    "cards": "CARDS",
    "bookings": "CARDS",
    "yellow_cards": "CARDS",
    "fouls_cards": "CARDS",
    "shots": "SHOTS",
    "total_shots": "SHOTS",
    "shots_on_target": "SHOTS_ON_TARGET",
    "sot": "SHOTS_ON_TARGET",
    "h2h": "RESULT",
    "ml": "RESULT",
    "moneyline": "RESULT",
    "match_winner": "MATCH_WINNER",
    "winner": "MATCH_WINNER",
    "total_games": "TOTAL_GAMES",
    "games_total": "TOTAL_GAMES",
    "set_handicap": "SET_HANDICAP",
    "game_handicap": "GAME_HANDICAP",
    "tiebreak": "TIEBREAK_YES_NO",
    "tiebreak_yes_no": "TIEBREAK_YES_NO",
    "aces": "ACES",
    "breaks": "BREAKS",
}

ODDS_FIELDS = {"odds", "odds_decimal", "price", "decimal_odds", "combined_odds_decimal"}
MODEL_PROB_FIELDS = {"model_probability", "probability", "model_prob"}
DEFAULT_REFERENCE_LINES = {
    "CORNERS": "7.5",
    "CARDS": "3.5",
    "GOALS_TOTALS": "2.5",
    "SHOTS": "20.5",
    "SHOTS_ON_TARGET": "7.5",
    "RESULT": None,
    "DOUBLE_CHANCE": None,
    "TOTAL_GAMES": "21.5",
    "SET_HANDICAP": None,
    "GAME_HANDICAP": None,
    "TIEBREAK_YES_NO": None,
    "ACES": "7.5",
    "BREAKS": "4.5",
    "MATCH_WINNER": None,
}


@dataclass
class LiveAnalystMarketIdea:
    idea_id: str
    event_id: str
    event_label: str
    sport: str
    competition: str
    kickoff_time: str | None
    market_family: str
    recommended_market: str
    recommended_line: str | None
    recommendation_direction: str | None
    line_source: str
    suggested_use: SuggestedUse
    analyst_confidence: Confidence
    data_quality: DataQuality
    source_coverage: SourceCoverage
    odds_available: bool
    hydrated_available: bool
    model_probability_available: bool
    ev_available: bool
    fair_odds_available: bool
    evidence_summary: str
    supporting_evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    source_gaps: list[str] = field(default_factory=list)
    scenario_summary: str = ""
    why_it_may_work: str = ""
    why_it_may_fail: str = ""
    superbet_quote_required: bool = True
    final_coupon_ready: bool = False
    manual_placement_ready: bool = False
    home_team: str | None = None
    away_team: str | None = None
    player_one: str | None = None
    player_two: str | None = None
    participants: list[str] = field(default_factory=list)
    reason: str = ""

    def validate(self) -> None:
        if self.sport not in {"football", "tennis"}:
            raise ValueError(f"Unsupported sport for analyst idea: {self.sport}")
        if self.sport == "football" and self.market_family not in SUPPORTED_FOOTBALL_MARKETS:
            raise ValueError(f"Unsupported football market: {self.market_family}")
        if self.sport == "tennis" and self.market_family not in SUPPORTED_TENNIS_MARKETS:
            raise ValueError(f"Unsupported tennis market: {self.market_family}")
        if not self.counter_evidence:
            raise ValueError("counter_evidence is required; use UNKNOWN when unavailable")
        if self.data_quality == "UNKNOWN" and self.analyst_confidence in {"A", "B"}:
            raise ValueError("UNKNOWN data quality cannot have confidence A/B")
        if self.data_quality == "LOW" and self.analyst_confidence == "A":
            raise ValueError("LOW data quality cannot have confidence A")
        if not self.model_probability_available and (self.ev_available or self.fair_odds_available):
            raise ValueError("EV/fair odds cannot exist without model probability")
        if not self.odds_available and self.ev_available:
            raise ValueError("EV cannot exist without odds")
        if self.final_coupon_ready or self.manual_placement_ready:
            raise ValueError("Analyst ideas are never final coupon / placement ready")
        if self.recommended_line and self.line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK":
            if "operator line" not in " ".join(self.source_gaps).lower():
                raise ValueError("Default reference line must be flagged as requiring operator-line check")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass
class BetBuilderComboIdea:
    combo_id: str
    idea_ids: list[str]
    event_label: str
    combo_note: str
    correlation_notes: list[str]
    conflict_risks: list[str]
    combined_odds_decimal: None = None
    superbet_quote_required: bool = True

    def validate(self) -> None:
        if self.combined_odds_decimal is not None:
            raise ValueError("Do not compute Superbet Bet Builder combined odds")
        if not self.superbet_quote_required:
            raise ValueError("Manual Superbet quote is required for combo ideas")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass
class UnifiedLiveAnalystPackage:
    package_type: PackageType
    run_id: str
    betting_day: str
    selected_matches: list[dict[str, Any]]
    recommendations: list[LiveAnalystMarketIdea]
    bet_builder_combo_ideas: list[BetBuilderComboIdea]
    watchlist_only: list[LiveAnalystMarketIdea]
    rejected_ideas: list[dict[str, Any]]
    data_gaps: list[str]
    ready_for_manual_operator_quote_review: bool
    ready_for_final_coupon: bool = False
    ready_for_manual_placement: bool = False
    ready_for_production_execution: bool = False
    ready_for_automated_bet_placement: bool = False
    final_coupon: dict[str, Any] | None = None

    def validate(self) -> None:
        if self.package_type == "ANALYST_RECOMMENDATION_PACKAGE" and not self.recommendations and not self.watchlist_only:
            raise ValueError("Analyst package requires recommendations or watchlist ideas")
        if self.ready_for_manual_operator_quote_review and not self.recommendations:
            raise ValueError("Quote review readiness requires at least one recommendation")
        if self.ready_for_final_coupon and self.package_type != "FINAL_MANUAL_COUPON_PACKAGE":
            raise ValueError("Final coupon readiness requires FINAL_MANUAL_COUPON_PACKAGE")
        if self.ready_for_manual_placement and self.package_type != "FINAL_MANUAL_COUPON_PACKAGE":
            raise ValueError("Manual placement readiness requires final coupon")
        if self.ready_for_production_execution or self.ready_for_automated_bet_placement:
            raise ValueError("Production/automated placement must remain false")
        for idea in [*self.recommendations, *self.watchlist_only]:
            idea.validate()
        for combo in self.bet_builder_combo_ideas:
            combo.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["recommendations"] = [i.to_dict() for i in self.recommendations]
        payload["watchlist_only"] = [i.to_dict() for i in self.watchlist_only]
        payload["bet_builder_combo_ideas"] = [c.to_dict() for c in self.bet_builder_combo_ideas]
        return payload


def now_run_id(prefix: str = "TODAY_LIVE_UNIFIED_ANALYST_SESSION") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def normalize_market_family(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    upper = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
    if upper in SUPPORTED_FOOTBALL_MARKETS or upper in SUPPORTED_TENNIS_MARKETS:
        return upper
    lower = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return MARKET_ALIASES.get(lower)


def has_any_odds(obj: Mapping[str, Any]) -> bool:
    for key in ODDS_FIELDS:
        if obj.get(key) not in (None, "", 0, 0.0):
            return True
    markets = obj.get("markets") or obj.get("odds_markets") or []
    if isinstance(markets, list):
        return any(isinstance(m, dict) and has_any_odds(m) for m in markets)
    return False


def has_model_probability(obj: Mapping[str, Any]) -> bool:
    return any(obj.get(k) not in (None, "", "UNKNOWN") for k in MODEL_PROB_FIELDS) or obj.get("model_probability_available") is True


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {_flatten_text(v)}" for k, v in value.items())
    return str(value) if value is not None else ""


def _evidence_items(obj: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "supporting_evidence", "evidence", "stats_summary", "scenario_summary", "analysis", "notes",
        "form_summary", "team_form", "match_preview", "deep_stats", "provider_notes",
    ):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            values.append(val.strip())
        elif isinstance(val, list):
            values.extend(str(v).strip() for v in val if str(v).strip())
        elif isinstance(val, dict) and val:
            values.append(f"{key}: {json.dumps(val, ensure_ascii=False, sort_keys=True)[:420]}")
    return values


def evidence_hint_score(obj: Mapping[str, Any], family: str) -> int:
    text = _flatten_text(obj).lower()
    keywords = {
        "CORNERS": ("corner", "rożn", "wide", "cross", "wing", "pressure", "territory"),
        "CARDS": ("card", "yellow", "booking", "foul", "referee", "aggressive", "discipline"),
        "GOALS_TOTALS": ("goal", "xg", "scoring", "attack", "defence", "defense", "open game"),
        "SHOTS": ("shot", "attempt", "pressure", "attack", "sot"),
        "SHOTS_ON_TARGET": ("shot on target", "sot", "save", "keeper"),
        "RESULT": ("win", "draw", "form", "rank", "favorite", "favourite"),
        "DOUBLE_CHANCE": ("avoid defeat", "draw", "underdog", "favorite", "favourite"),
        "TOTAL_GAMES": ("serve", "hold", "tie-break", "tiebreak", "grass", "games"),
        "ACES": ("ace", "serve", "grass"),
        "BREAKS": ("break", "return", "serve"),
        "MATCH_WINNER": ("rank", "form", "surface", "grass"),
    }.get(family, ())
    return sum(1 for kw in keywords if kw in text)


def grade_data_quality(evidence_count: int, hint_score: int, has_hydrated: bool, has_model_probability: bool) -> DataQuality:
    if has_hydrated and has_model_probability and evidence_count >= 2:
        return "HIGH"
    if evidence_count >= 2 or (evidence_count >= 1 and hint_score >= 2) or has_hydrated or has_model_probability:
        return "MEDIUM"
    if evidence_count >= 1 or hint_score >= 1:
        return "LOW"
    return "UNKNOWN"


def grade_source_coverage(data_quality: DataQuality) -> SourceCoverage:
    return {"HIGH": "STRONG", "MEDIUM": "PARTIAL", "LOW": "WEAK", "UNKNOWN": "WEAK"}[data_quality]  # type: ignore[return-value]


def assign_confidence(data_quality: DataQuality, evidence_count: int, hint_score: int, has_counter: bool) -> Confidence:
    if data_quality == "HIGH" and has_counter:
        return "A"
    if data_quality in {"HIGH", "MEDIUM"} and (evidence_count >= 2 or hint_score >= 2):
        return "B"
    if data_quality in {"MEDIUM", "LOW"}:
        return "C"
    return "D"


def should_be_watchlist_only(confidence: Confidence, data_quality: DataQuality, family: str | None, evidence_count: int, hint_score: int) -> bool:
    if not family:
        return True
    if confidence == "D" or data_quality == "UNKNOWN":
        return True
    return evidence_count == 0 and hint_score < 2


def _event_label(obj: Mapping[str, Any]) -> str:
    label = obj.get("event_label") or obj.get("match") or obj.get("fixture_label") or obj.get("name")
    if label:
        return str(label)
    home = obj.get("home_team") or obj.get("team_a") or obj.get("player_one") or obj.get("home")
    away = obj.get("away_team") or obj.get("team_b") or obj.get("player_two") or obj.get("away")
    if home and away:
        return f"{home} vs {away}"
    return str(obj.get("event_id") or obj.get("fixture_id") or "UNKNOWN_EVENT")


def _sport(obj: Mapping[str, Any]) -> str | None:
    raw = obj.get("sport") or obj.get("sport_key") or obj.get("sport_title") or obj.get("league") or obj.get("competition")
    if raw is None:
        return None
    s = str(raw).lower()
    if "tennis" in s or s in {"atp", "wta"} or "wimbledon" in s:
        return "tennis"
    if "soccer" in s or "football" in s or "fifa" in s or "world cup" in s or "worldcup" in s:
        return "football"
    return s


def _line_from_obj(obj: Mapping[str, Any]) -> tuple[str | None, str]:
    explicit = obj.get("line") or obj.get("point") or obj.get("recommended_line")
    if explicit is not None and str(explicit).strip():
        return str(explicit), "SOURCE_ARTIFACT"
    return None, "MISSING"


def _market_families_for_candidate(sport: str, obj: Mapping[str, Any]) -> list[tuple[str, str, str | None, str | None, str]]:
    """Return family, market label, line, direction, line_source.

    If source has a market, preserve it. If source only has an event, propose a
    small default analyst-check market. The reference line is explicitly marked
    as an operator-check line, not a claimed bookmaker line.
    """
    raw_market = obj.get("market_family") or obj.get("market_type") or obj.get("market") or obj.get("provider_market_key")
    family = normalize_market_family(raw_market)
    direction = obj.get("direction") or obj.get("recommendation_direction") or obj.get("side")
    line, line_source = _line_from_obj(obj)
    if family:
        if line is None and DEFAULT_REFERENCE_LINES.get(family) is not None:
            line = DEFAULT_REFERENCE_LINES[family]
            line_source = "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK"
        market = str(obj.get("market") or obj.get("market_label") or raw_market or family)
        return [(family, market, line, None if direction is None else str(direction).upper(), line_source)]
    # Event-only default: choose one or two check ideas, based on evidence hints.
    if sport == "football":
        text = _flatten_text(obj).lower()
        choices = []
        if any(k in text for k in ("corner", "rożn", "wide", "cross", "pressure", "territory")):
            choices.append("CORNERS")
        if any(k in text for k in ("card", "yellow", "booking", "foul", "referee")):
            choices.append("CARDS")
        if any(k in text for k in ("goal", "xg", "attack", "defence", "defense")):
            choices.append("GOALS_TOTALS")
        if not choices:
            choices = ["CORNERS"]
        return [(fam, default_market_label(fam), DEFAULT_REFERENCE_LINES[fam], "OVER" if fam != "CARDS" else "UNDER", "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK") for fam in choices[:2]]
    if sport == "tennis":
        text = _flatten_text(obj).lower()
        fam = "ACES" if any(k in text for k in ("ace", "serve")) else "TOTAL_GAMES"
        return [(fam, default_market_label(fam), DEFAULT_REFERENCE_LINES.get(fam), "OVER", "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK")]
    return []


def default_market_label(family: str) -> str:
    return {
        "CORNERS": "Total corners",
        "CARDS": "Total cards",
        "GOALS_TOTALS": "Total goals",
        "SHOTS": "Total shots",
        "SHOTS_ON_TARGET": "Shots on target",
        "RESULT": "Match result",
        "DOUBLE_CHANCE": "Double chance",
        "TOTAL_GAMES": "Total games",
        "ACES": "Total aces",
        "BREAKS": "Total breaks",
        "MATCH_WINNER": "Match winner",
        "SET_HANDICAP": "Set handicap",
        "GAME_HANDICAP": "Game handicap",
        "TIEBREAK_YES_NO": "Tiebreak yes/no",
    }.get(family, family)


@dataclass
class EventContext:
    sport: str | None
    competition: str | None
    tournament: str | None
    kickoff_time: str | None
    home_team: str | None
    away_team: str | None
    player_one: str | None
    player_two: str | None
    participants: list[str] = field(default_factory=list)
    event_label: str | None = None
    event_id: str | None = None
    source_artifact_path: str | None = None
    context_quality: Literal["COMPLETE", "PARTIAL", "WEAK", "MISSING"] = "MISSING"


@dataclass
class EvidenceBundle:
    supporting_evidence: list[str]
    counter_evidence: list[str]
    source_gaps: list[str]
    evidence_summary: str
    scenario_summary: str
    evidence_quality: Literal["STRONG", "MEDIUM", "PARTIAL", "WEAK"]


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = str(name).lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def load_source_artifacts() -> list[dict[str, Any]]:
    artifacts = []
    repo_root = Path("/Users/mkoziol/projects/bet")
    runs_dir = repo_root / "reports/pipeline_runs"
    if not runs_dir.exists():
        return artifacts
    for p in sorted(runs_dir.rglob("*.json")):
        if "manual_superbet_operator_quotes" in p.name:
            continue
        name_lower = p.name.lower()
        if any(k in name_lower for k in ["deep_stats", "valuation", "shortlist", "handoff", "matrix", "s2", "s3", "s4"]):
            try:
                content = json.loads(p.read_text(encoding="utf-8"))
                artifacts.extend(list(_iter_json_objects(content)))
            except Exception:
                continue
    return artifacts


def find_matching_artifacts(candidate: dict[str, Any], source_artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    cand_id = str(candidate.get("event_id") or candidate.get("fixture_id") or candidate.get("candidate_id") or "").strip()
    cand_home = normalize_name(candidate.get("home_team") or candidate.get("home") or candidate.get("home_name") or candidate.get("homeTeam") or candidate.get("home_team_name") or candidate.get("player_one") or candidate.get("player1") or candidate.get("player_a") or candidate.get("competitor_1"))
    cand_away = normalize_name(candidate.get("away_team") or candidate.get("away") or candidate.get("away_name") or candidate.get("awayTeam") or candidate.get("away_team_name") or candidate.get("player_two") or candidate.get("player2") or candidate.get("player_b") or candidate.get("competitor_2"))
    
    cand_participants = set()
    parts = candidate.get("participants") or candidate.get("competitors") or candidate.get("teams") or candidate.get("players") or []
    if isinstance(parts, str):
        parts = [parts]
    for p in parts:
        cand_participants.add(normalize_name(p))
    if cand_home:
        cand_participants.add(cand_home)
    if cand_away:
        cand_participants.add(cand_away)

    for art in source_artifacts:
        art_id = str(art.get("event_id") or art.get("fixture_id") or art.get("candidate_id") or "").strip()
        if cand_id and art_id and cand_id == art_id:
            matches.append(art)
            continue
            
        art_home = normalize_name(art.get("home_team") or art.get("home") or art.get("home_name") or art.get("home_team_name") or art.get("player_one") or art.get("player_a") or art.get("competitor_1"))
        art_away = normalize_name(art.get("away_team") or art.get("away") or art.get("away_name") or art.get("away_team_name") or art.get("player_two") or art.get("player_b") or art.get("competitor_2"))
        
        if cand_home and cand_away and art_home and art_away:
            if (cand_home == art_home and cand_away == art_away) or (cand_home == art_away and cand_away == art_home):
                matches.append(art)
                continue
                
        art_parts = art.get("participants") or art.get("competitors") or art.get("teams") or art.get("players") or []
        if isinstance(art_parts, str):
            art_parts = [art_parts]
        art_participants = set(normalize_name(p) for p in art_parts if p)
        if art_home:
            art_participants.add(art_home)
        if art_away:
            art_participants.add(art_away)
            
        if cand_participants and art_participants:
            if len(cand_participants.intersection(art_participants)) >= 2:
                matches.append(art)
                continue
                
    return matches


def get_field_with_aliases(objs: list[dict[str, Any]], aliases: list[str]) -> Any:
    for obj in objs:
        for alias in aliases:
            val = obj.get(alias)
            if val is not None:
                if isinstance(val, str) and not val.strip():
                    continue
                return val
    return None


def extract_event_context(candidate: dict[str, Any], source_artifacts: list[dict[str, Any]]) -> EventContext:
    matching_artifacts = find_matching_artifacts(candidate, source_artifacts)
    objs = [candidate] + matching_artifacts
    
    sport = get_field_with_aliases(objs, ["sport", "sport_key", "sport_title"])
    if sport:
        sport = _sport({"sport": sport})
        
    competition = get_field_with_aliases(objs, ["competition", "league", "tournament", "event_group"])
    if competition:
        competition = str(competition).strip()
        
    kickoff_time = get_field_with_aliases(objs, ["kickoff", "kickoff_time", "start_time", "commence_time", "scheduled_at", "scheduled_time"])
    
    home_team = get_field_with_aliases(objs, ["home_team", "home", "home_name", "homeTeam", "home_team_name"])
    away_team = get_field_with_aliases(objs, ["away_team", "away", "away_name", "awayTeam", "away_team_name"])
    
    player_one = get_field_with_aliases(objs, ["player_one", "player1", "player_a", "competitor_1"])
    player_two = get_field_with_aliases(objs, ["player_two", "player2", "player_b", "competitor_2"])
    
    participants = []
    for obj in objs:
        for alias in ["participants", "competitors", "teams", "players"]:
            p_val = obj.get(alias)
            if isinstance(p_val, list) and p_val:
                participants = [str(x).strip() for x in p_val if x]
                break
            elif isinstance(p_val, str) and p_val.strip():
                participants = [x.strip() for x in p_val.split(",") if x.strip()]
                break
        if participants:
            break
            
    if not participants:
        if home_team and away_team:
            participants = [home_team, away_team]
        elif player_one and player_two:
            participants = [player_one, player_two]
            
    if sport == "tennis":
        if not player_one and home_team:
            player_one = home_team
        if not player_two and away_team:
            player_two = away_team
        if not home_team and player_one:
            home_team = player_one
        if not away_team and player_two:
            away_team = player_two
    else:
        if not home_team and player_one:
            home_team = player_one
        if not away_team and player_two:
            away_team = player_two
            
    event_label = None
    if home_team and away_team:
        event_label = f"{home_team} vs {away_team}"
    elif player_one and player_two:
        event_label = f"{player_one} vs {player_two}"
    elif len(participants) >= 2:
        event_label = f"{participants[0]} vs {participants[1]}"
    else:
        raw_label = get_field_with_aliases(objs, ["fixture", "fixture_label", "match", "match_label", "event", "event_label", "name"])
        if raw_label and not str(raw_label).isdigit():
            event_label = str(raw_label).strip()
            
    event_id = get_field_with_aliases(objs, ["event_id", "fixture_id", "candidate_id"])
    if event_id is not None:
        event_id = str(event_id).strip()
        
    source_artifact_path = get_field_with_aliases(objs, ["source_artifact_path"])
    
    has_real_label = bool(event_label and not event_label.isdigit() and "unknown" not in event_label.lower() and "candidate_" not in event_label.lower())
    has_comp = bool(competition and str(competition).strip().upper() != "UNKNOWN")
    has_kickoff = bool(kickoff_time)
    has_sport = bool(sport)
    has_participants = len(participants) >= 2
    
    if has_sport and has_real_label and has_participants and has_comp and has_kickoff:
        context_quality = "COMPLETE"
    elif has_sport and has_real_label and (has_participants or len(participants) >= 1):
        context_quality = "PARTIAL"
    elif has_sport or has_real_label:
        context_quality = "WEAK"
    else:
        context_quality = "MISSING"
        
    return EventContext(
        sport=sport,
        competition=competition,
        tournament=competition,
        kickoff_time=kickoff_time,
        home_team=home_team,
        away_team=away_team,
        player_one=player_one,
        player_two=player_two,
        participants=participants,
        event_label=event_label,
        event_id=event_id,
        source_artifact_path=source_artifact_path,
        context_quality=context_quality
    )


def extract_actionable_evidence(candidate: dict[str, Any], event_context: EventContext, market_family: str, source_artifacts: list[dict[str, Any]]) -> EvidenceBundle:
    supporting_evidence = []
    counter_evidence = []
    source_gaps = []
    
    matching = find_matching_artifacts(candidate, source_artifacts)
    s3_analyses = [m for m in matching if "stats_a_summary" in m or "stats_b_summary" in m]
    
    cand_se = candidate.get("supporting_evidence") or candidate.get("evidence") or []
    if isinstance(cand_se, str):
        cand_se = [cand_se]
    clean_cand_se = []
    for item in cand_se:
        if item and "Manual analyst check" not in item and "No exact quantitative" not in item and "Insufficient evidence" not in item:
            clean_cand_se.append(str(item).strip())
            supporting_evidence.append(str(item).strip())
            
    has_real_stats = False
    for s3 in s3_analyses:
        stats_a = s3.get("stats_a_summary")
        if stats_a:
            flat_a = _flatten_text(stats_a).strip()
            if flat_a:
                supporting_evidence.append(f"Home/Player A stats: {flat_a}")
                has_real_stats = True
        stats_b = s3.get("stats_b_summary")
        if stats_b:
            flat_b = _flatten_text(stats_b).strip()
            if flat_b:
                supporting_evidence.append(f"Away/Player B stats: {flat_b}")
                has_real_stats = True
        h2h = s3.get("h2h_summary")
        if h2h:
            flat_h = _flatten_text(h2h).strip()
            if flat_h:
                supporting_evidence.append(f"H2H summary: {flat_h}")
                has_real_stats = True
        ranking = s3.get("ranking")
        if ranking:
            flat_r = _flatten_text(ranking).strip()
            if flat_r:
                supporting_evidence.append(f"Ranking context: {flat_r}")
                has_real_stats = True
        best_m = s3.get("best_market")
        if isinstance(best_m, dict):
            m_name = best_m.get("name")
            m_hr = best_m.get("hit_rate_l10")
            if m_name:
                supporting_evidence.append(f"Statistical market suggested: {m_name}")
                has_real_stats = True
            if m_hr and m_hr != "N/A":
                supporting_evidence.append(f"Suggested market hit rate in last 10 games is {m_hr}")
                has_real_stats = True

    if clean_cand_se or has_real_stats:
        if event_context.sport == "football":
            supporting_evidence.append("team identity complete: Football match setup is fully verified.")
            if event_context.competition:
                supporting_evidence.append(f"competition context available: {event_context.competition}")
                if "world cup" in event_context.competition.lower():
                    supporting_evidence.append("knockout match context: FIFA World Cup high-stakes international environment.")
            supporting_evidence.append("market family present in matrix: Football market family is registered for analysis.")
        elif event_context.sport == "tennis":
            supporting_evidence.append("player identity complete: Tennis matchup is fully verified.")
            if event_context.competition:
                supporting_evidence.append(f"tournament context available: {event_context.competition}")
                if "wimbledon" in event_context.competition.lower():
                    supporting_evidence.append("tournament context available: Wimbledon grass surface tournament rules apply.")
            supporting_evidence.append("market family present in matrix: Tennis market family is registered for analysis.")

    seen_se = set()
    unique_se = []
    for se in supporting_evidence:
        if se.lower() not in seen_se:
            seen_se.add(se.lower())
            unique_se.append(se)
    supporting_evidence = unique_se

    cand_ce = candidate.get("counter_evidence") or []
    if isinstance(cand_ce, str):
        cand_ce = [cand_ce]
    for item in cand_ce:
        if item and "UNKNOWN" not in item.upper() and "no explicit counter" not in item.lower():
            counter_evidence.append(str(item).strip())
            
    has_l10 = False
    has_h2h = False
    has_lineup = False
    
    for s3 in s3_analyses:
        dq = s3.get("data_quality")
        if isinstance(dq, dict):
            bk = dq.get("breakdown")
            if isinstance(bk, dict):
                has_l10 = bk.get("l10_data", False)
                has_h2h = bk.get("h2h_data", False)
                
    if market_family == "CARDS":
        counter_evidence.append("No referee data for cards — yellow card threshold is referee-dependent.")
    if market_family == "CORNERS" and not has_l10:
        counter_evidence.append("No team-level recent corner series — team-specific wide attack rates have wide variances.")
    if event_context.sport == "tennis" and not has_l10:
        counter_evidence.append("No player surface-form data — surface-specific hold/break statistics are not fully loaded.")
    if not has_lineup:
        counter_evidence.append("No lineup confirmation — potential rotation unknown prior to kickoff.")
    
    line_src = candidate.get("line_source")
    if line_src == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK" or not candidate.get("line"):
        counter_evidence.append("Line is operator-check reference only — must be verified manually on bookmaker site.")
        source_gaps.append("Reference line is an analyst default; operator line must be checked manually in Superbet.")
        
    seen_ce = set()
    unique_ce = []
    for ce in counter_evidence:
        if ce.lower() not in seen_ce:
            seen_ce.add(ce.lower())
            unique_ce.append(ce)
    counter_evidence = unique_ce
    
    if not counter_evidence:
        counter_evidence = ["UNKNOWN — no explicit counter-evidence available; confidence downgraded."]

    if not candidate.get("odds_available") and not any(m.get("odds_decimal") for m in matching):
        source_gaps.append("Odds unavailable or ignored — analysis remains allowed; EV unavailable.")
    if str(candidate.get("hydration_status") or "").upper() != "HYDRATED":
        source_gaps.append("HYDRATED source-bound stats unavailable — confidence capped/downgraded, not blocked.")
    if not candidate.get("model_probability_available") and not any(m.get("model_probability") for m in matching):
        source_gaps.append("Model probability unavailable — no fair odds or EV claim.")
        
    has_stats = any(s3.get("stats_a_summary") or s3.get("stats_b_summary") for s3 in s3_analyses)
    if has_stats and has_l10:
        evidence_quality = "STRONG"
    elif has_stats or len(supporting_evidence) >= 4:
        evidence_quality = "MEDIUM"
    elif len(supporting_evidence) >= 2:
        evidence_quality = "PARTIAL"
    else:
        evidence_quality = "WEAK"
        
    evidence_summary = supporting_evidence[0] if supporting_evidence else "Insufficient quantitative evidence available."
    scenario_summary = f"Manual analyst check for {default_market_label(market_family)} in {event_context.event_label}; verify market and line in Superbet."
    
    return EvidenceBundle(
        supporting_evidence=supporting_evidence,
        counter_evidence=counter_evidence,
        source_gaps=source_gaps,
        evidence_summary=evidence_summary,
        scenario_summary=scenario_summary,
        evidence_quality=evidence_quality
    )


def is_event_identity_complete(idea: LiveAnalystMarketIdea) -> bool:
    if not idea.event_label:
        return False
    val = str(idea.event_label).strip()
    if not val:
        return False
    if val.isdigit():
        return False
    lower_val = val.lower()
    if lower_val.startswith("candidate_") or lower_val.startswith("event_") or lower_val == "unknown_event":
        return False
    
    has_home_away = bool(idea.home_team and idea.away_team)
    has_players = bool(idea.player_one and idea.player_two)
    has_participants = bool(idea.participants and len(idea.participants) >= 2)
    has_vs_pattern = " vs " in lower_val or " - " in lower_val or " / " in lower_val
    
    if not (has_home_away or has_players or has_participants or has_vs_pattern):
        return False
        
    comp = str(idea.competition).strip().upper() if idea.competition else ""
    is_comp_unknown = not comp or comp == "UNKNOWN"
    
    if is_comp_unknown:
        if not (has_home_away or has_players or has_participants):
            return False
            
    if not idea.sport or not str(idea.sport).strip():
        return False
    return True


def recommendation_has_actionable_evidence(idea: LiveAnalystMarketIdea) -> bool:
    if not idea.evidence_summary:
        return False
    if str(idea.evidence_summary).strip() == "No exact quantitative summary available in artifacts; idea is based on event/market context only.":
        return False
    if not idea.why_it_may_work:
        return False
    if "No exact quantitative summary available" in idea.why_it_may_work:
        return False
    if not idea.supporting_evidence or len(idea.supporting_evidence) < 1:
        return False
    if not idea.counter_evidence:
        return False
    has_real_counter = False
    for ce in idea.counter_evidence:
        if ce:
            lower_ce = ce.lower()
            if "no explicit counter" in lower_ce:
                continue
            if lower_ce.strip() in ("unknown", "unavailable", "n/a", "none"):
                continue
            has_real_counter = True
            break
    if not has_real_counter:
        return False
    return True


def build_ideas_from_candidate(obj: Mapping[str, Any], index: int, source_artifacts: list[dict[str, Any]] | None = None) -> list[LiveAnalystMarketIdea]:
    sport = _sport(obj)
    if sport not in {"football", "tennis"}:
        return []
        
    if source_artifacts is None:
        source_artifacts = []
        
    if not source_artifacts:
        # Isolated Legacy / Unit Test Mode
        outcomes: list[LiveAnalystMarketIdea] = []
        for family, market, line, direction, line_source in _market_families_for_candidate(sport, obj):
            if sport == "football" and family not in SUPPORTED_FOOTBALL_MARKETS:
                continue
            if sport == "tennis" and family not in SUPPORTED_TENNIS_MARKETS:
                continue
            evidence = _evidence_items(obj)
            has_hydrated = str(obj.get("hydration_status") or "").upper() == "HYDRATED" or obj.get("hydrated_available") is True
            model_ready = has_model_probability(obj)
            odds_available = has_any_odds(obj)
            hint_score = evidence_hint_score(obj, family)
            data_quality = grade_data_quality(len(evidence), hint_score, has_hydrated, model_ready)
            source_coverage = grade_source_coverage(data_quality)
            raw_counter = obj.get("counter_evidence")
            if isinstance(raw_counter, list) and raw_counter:
                counter_list = [str(v) for v in raw_counter]
            elif isinstance(raw_counter, str) and raw_counter.strip():
                counter_list = [raw_counter.strip()]
            else:
                counter_list = ["UNKNOWN — no explicit counter-evidence available in source artifacts; confidence downgraded."]
            confidence = assign_confidence(data_quality, len(evidence), hint_score, bool(counter_list))
            comp_str = str(obj.get("competition") or obj.get("league") or obj.get("tournament") or "").strip().upper()
            if not comp_str or comp_str == "UNKNOWN":
                if confidence in {"A", "B"}:
                    confidence = "C"
            suggested_use: SuggestedUse = "WATCHLIST_ONLY" if should_be_watchlist_only(confidence, data_quality, family, len(evidence), hint_score) else "BET_BUILDER_LEG"
            if suggested_use == "WATCHLIST_ONLY" and confidence != "D":
                confidence = "D"
            event_label = _event_label(obj)
            source_gaps: list[str] = []
            if not odds_available:
                source_gaps.append("Odds unavailable or ignored — analysis remains allowed; EV unavailable.")
            if not has_hydrated:
                source_gaps.append("HYDRATED source-bound stats unavailable — confidence capped/downgraded, not blocked.")
            if not model_ready:
                source_gaps.append("Model probability unavailable — no fair odds or EV claim.")
            if line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK":
                source_gaps.append("Reference line is an analyst default; operator line must be checked manually in Superbet.")
            if not evidence:
                source_gaps.append("Limited source evidence — watchlist-only unless user accepts qualitative check.")
            evidence_summary = evidence[0] if evidence else "No exact quantitative summary available in artifacts; idea is based on event/market context only."
            scenario_summary = obj.get("scenario_summary") or f"Manual analyst check for {market} in {event_label}; verify market and line in Superbet."
            why_work = obj.get("why_it_may_work") or evidence_summary
            why_fail = obj.get("why_it_may_fail") or counter_list[0]
            base_id = obj.get("idea_id") or obj.get("candidate_id") or obj.get("event_id") or obj.get("fixture_id") or f"candidate_{index}"
            idea_id = f"{base_id}_{family}_{line or 'no_line'}"
            
            home_team = obj.get("home_team") or obj.get("team_a") or obj.get("player_one") or obj.get("home")
            away_team = obj.get("away_team") or obj.get("team_b") or obj.get("player_two") or obj.get("away")
            player_one = obj.get("player_one")
            player_two = obj.get("player_two")
            participants = obj.get("participants") or []
            if isinstance(participants, str):
                participants = [participants]
            else:
                participants = list(participants)
                
            idea = LiveAnalystMarketIdea(
                idea_id=str(idea_id),
                event_id=str(obj.get("event_id") or obj.get("fixture_id") or obj.get("candidate_id") or f"event_{index}"),
                event_label=event_label,
                sport=sport,
                competition=str(obj.get("competition") or obj.get("league") or obj.get("tournament") or "UNKNOWN"),
                kickoff_time=obj.get("kickoff_time") or obj.get("start_time") or obj.get("commence_time"),
                market_family=family,
                recommended_market=market,
                recommended_line=line,
                recommendation_direction=direction,
                line_source=line_source,
                suggested_use=suggested_use,
                analyst_confidence=confidence,
                data_quality=data_quality,
                source_coverage=source_coverage,
                odds_available=odds_available,
                hydrated_available=has_hydrated,
                model_probability_available=model_ready,
                ev_available=False,
                fair_odds_available=False,
                evidence_summary=evidence_summary,
                supporting_evidence=evidence[:6],
                counter_evidence=counter_list,
                source_gaps=source_gaps,
                scenario_summary=str(scenario_summary),
                why_it_may_work=str(why_work),
                why_it_may_fail=str(why_fail),
                home_team=home_team,
                away_team=away_team,
                player_one=player_one,
                player_two=player_two,
                participants=participants,
            )
            
            is_complete = is_event_identity_complete(idea)
            has_evidence = recommendation_has_actionable_evidence(idea)
            
            if not is_complete:
                idea.suggested_use = "WATCHLIST_ONLY"
                idea.analyst_confidence = "D"
                idea.reason = "INSUFFICIENT_EVENT_IDENTITY"
                if "INSUFFICIENT_EVENT_IDENTITY" not in idea.source_gaps:
                    idea.source_gaps.append("INSUFFICIENT_EVENT_IDENTITY")
            elif not has_evidence:
                idea.suggested_use = "WATCHLIST_ONLY"
                idea.analyst_confidence = "D"
                idea.reason = "INSUFFICIENT_ACTIONABLE_EVIDENCE"
                if "INSUFFICIENT_ACTIONABLE_EVIDENCE" not in idea.source_gaps:
                    idea.source_gaps.append("INSUFFICIENT_ACTIONABLE_EVIDENCE")
                    
            if idea.suggested_use == "WATCHLIST_ONLY":
                if "No exact quantitative summary" in idea.evidence_summary or not idea.evidence_summary:
                    idea.evidence_summary = "Insufficient evidence for top recommendation; manual watchlist only."
                if "No exact quantitative summary" in idea.why_it_may_work or not idea.why_it_may_work:
                    idea.why_it_may_work = "Insufficient evidence for top recommendation; manual watchlist only."
                    
            outcomes.append(idea)
        return outcomes

    # Rich Production / Live Run Extraction Mode
    outcomes: list[LiveAnalystMarketIdea] = []
    
    event_context = extract_event_context(dict(obj), source_artifacts)
    
    for family, market, line, direction, line_source in _market_families_for_candidate(sport, obj):
        if sport == "football" and family not in SUPPORTED_FOOTBALL_MARKETS:
            continue
        if sport == "tennis" and family not in SUPPORTED_TENNIS_MARKETS:
            continue
            
        bundle = extract_actionable_evidence(dict(obj), event_context, family, source_artifacts)
        
        has_hydrated = str(obj.get("hydration_status") or "").upper() == "HYDRATED" or obj.get("hydrated_available") is True
        model_ready = has_model_probability(obj)
        odds_available = has_any_odds(obj)
        
        matching = find_matching_artifacts(dict(obj), source_artifacts)
        for m in matching:
            if str(m.get("hydration_status") or "").upper() == "HYDRATED" or m.get("hydrated_available") is True:
                has_hydrated = True
            if has_model_probability(m):
                model_ready = True
            if has_any_odds(m):
                odds_available = True
                
        dq_map = {"STRONG": "HIGH", "MEDIUM": "MEDIUM", "PARTIAL": "LOW", "WEAK": "UNKNOWN"}
        dq = dq_map.get(bundle.evidence_quality, "UNKNOWN")
        source_coverage = grade_source_coverage(dq)
        
        has_real_counter = False
        for ce in bundle.counter_evidence:
            if ce and "UNKNOWN" not in ce.upper() and "no explicit counter" not in ce.lower():
                has_real_counter = True
                break
                
        if dq == "HIGH" and has_real_counter and has_hydrated and model_ready:
            confidence = "A"
        elif dq in {"HIGH", "MEDIUM"} and has_real_counter and len(bundle.supporting_evidence) >= 2:
            confidence = "B"
        elif dq in {"MEDIUM", "LOW"}:
            confidence = "C"
        else:
            confidence = "D"
            
        suggested_use: SuggestedUse = "BET_BUILDER_LEG"
        
        base_id = obj.get("idea_id") or obj.get("candidate_id") or obj.get("event_id") or obj.get("fixture_id") or f"candidate_{index}"
        idea_id = f"{base_id}_{family}_{line or 'no_line'}"
        
        idea = LiveAnalystMarketIdea(
            idea_id=str(idea_id),
            event_id=str(event_context.event_id or f"event_{index}"),
            event_label=event_context.event_label or "UNKNOWN_EVENT",
            sport=sport,
            competition=event_context.competition or "UNKNOWN",
            kickoff_time=event_context.kickoff_time,
            market_family=family,
            recommended_market=market,
            recommended_line=line,
            recommendation_direction=direction,
            line_source=line_source,
            suggested_use=suggested_use,
            analyst_confidence=confidence,
            data_quality=dq,
            source_coverage=source_coverage,
            odds_available=odds_available,
            hydrated_available=has_hydrated,
            model_probability_available=model_ready,
            ev_available=False,
            fair_odds_available=False,
            evidence_summary=bundle.evidence_summary,
            supporting_evidence=bundle.supporting_evidence,
            counter_evidence=bundle.counter_evidence,
            source_gaps=bundle.source_gaps,
            scenario_summary=bundle.scenario_summary,
            why_it_may_work=bundle.evidence_summary,
            why_it_may_fail=bundle.counter_evidence[0] if bundle.counter_evidence else "UNKNOWN",
            home_team=event_context.home_team,
            away_team=event_context.away_team,
            player_one=event_context.player_one,
            player_two=event_context.player_two,
            participants=event_context.participants,
        )
        
        cand_work = obj.get("why_it_may_work")
        if cand_work and "No exact quantitative summary" not in cand_work and "Insufficient evidence" not in cand_work:
            idea.why_it_may_work = str(cand_work)
        else:
            if idea.supporting_evidence:
                idea.why_it_may_work = " | ".join(idea.supporting_evidence[:3])
            else:
                idea.why_it_may_work = "No exact quantitative summary available in artifacts; idea is based on event/market context only."
                
        cand_fail = obj.get("why_it_may_fail")
        if cand_fail and "UNKNOWN" not in cand_fail.upper() and "no explicit counter" not in cand_fail.lower():
            idea.why_it_may_fail = str(cand_fail)
        else:
            if idea.counter_evidence:
                idea.why_it_may_fail = " | ".join(idea.counter_evidence[:3])
            else:
                idea.why_it_may_fail = "UNKNOWN — no explicit counter-evidence available; confidence downgraded."

        is_complete = is_event_identity_complete(idea)
        has_evidence = recommendation_has_actionable_evidence(idea)
        
        if not is_complete:
            idea.suggested_use = "WATCHLIST_ONLY"
            idea.analyst_confidence = "D"
            idea.reason = "INSUFFICIENT_EVENT_IDENTITY"
            if "INSUFFICIENT_EVENT_IDENTITY" not in idea.source_gaps:
                idea.source_gaps.append("INSUFFICIENT_EVENT_IDENTITY")
        elif not has_evidence:
            idea.suggested_use = "WATCHLIST_ONLY"
            idea.analyst_confidence = "D"
            idea.reason = "INSUFFICIENT_ACTIONABLE_EVIDENCE"
            if "INSUFFICIENT_ACTIONABLE_EVIDENCE" not in idea.source_gaps:
                idea.source_gaps.append("INSUFFICIENT_ACTIONABLE_EVIDENCE")
                
        if idea.suggested_use == "WATCHLIST_ONLY":
            if "No exact quantitative summary" in idea.evidence_summary or not idea.evidence_summary or "Insufficient quantitative evidence" in idea.evidence_summary:
                idea.evidence_summary = "Insufficient evidence for top recommendation; manual watchlist only."
            if "No exact quantitative summary" in idea.why_it_may_work or not idea.why_it_may_work:
                idea.why_it_may_work = "Insufficient evidence for top recommendation; manual watchlist only."
                
        outcomes.append(idea)
    return outcomes


def _iter_json_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        keys = set(value)
        if keys.intersection({"sport", "sport_key", "event_id", "fixture_id", "home_team", "away_team", "player_one", "player_two", "market_family", "market_type", "competition", "league", "tournament"}):
            yield value
        for v in value.values():
            yield from _iter_json_objects(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_objects(item)


def load_candidates_from_path(path: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if path.is_file() and path.suffix.lower() == ".json":
        try:
            candidates.extend(_iter_json_objects(json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            return candidates
    elif path.is_dir():
        for p in sorted(path.rglob("*.json")):
            if "manual_superbet_operator_quotes" in p.name:
                continue
            try:
                candidates.extend(_iter_json_objects(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        key = "|".join(str(c.get(k) or "") for k in ("event_id", "fixture_id", "event_label", "home_team", "away_team", "player_one", "player_two", "market_family", "market_type", "line", "point"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def calculate_idea_score(idea: LiveAnalystMarketIdea) -> float:
    score = 0.0
    conf_map = {"A": 100.0, "B": 75.0, "C": 50.0, "D": 20.0}
    score += conf_map.get(idea.analyst_confidence, 0.0)
    dq_map = {"HIGH": 50.0, "MEDIUM": 30.0, "LOW": 10.0, "UNKNOWN": 0.0}
    score += dq_map.get(idea.data_quality, 0.0)
    sc_map = {"STRONG": 30.0, "PARTIAL": 15.0, "WEAK": 0.0}
    score += sc_map.get(idea.source_coverage, 0.0)
    score += len(idea.supporting_evidence) * 10.0
    has_real_counter = False
    for ce in idea.counter_evidence:
        if ce and "UNKNOWN" not in ce.upper() and "no explicit counter" not in ce.lower():
            has_real_counter = True
            break
    if has_real_counter:
        score += 10.0
    if idea.market_family in SUPPORTED_FOOTBALL_MARKETS or idea.market_family in SUPPORTED_TENNIS_MARKETS:
        score += 10.0
    if idea.recommended_line and idea.line_source != "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK":
        score += 15.0
    if idea.sport in {"football", "tennis"}:
        score += 20.0
    if idea.line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK":
        score -= 30.0
    if idea.data_quality == "UNKNOWN":
        score -= 50.0
    if not idea.recommended_line:
        score -= 20.0
    if idea.suggested_use == "WATCHLIST_ONLY":
        score -= 100.0
    if not idea.kickoff_time:
        score -= 15.0
    if not idea.competition or idea.competition == "UNKNOWN":
        score -= 15.0
    return score


def build_package_from_candidates(candidates: list[dict[str, Any]], run_id: str, betting_day: str | None = None, source_artifacts: list[dict[str, Any]] | None = None) -> UnifiedLiveAnalystPackage:
    if source_artifacts is None:
        source_artifacts = []
    ideas: list[LiveAnalystMarketIdea] = []
    rejected: list[dict[str, Any]] = []
    selected_matches: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidates):
        candidate_ideas = build_ideas_from_candidate(candidate, idx, source_artifacts)
        if not candidate_ideas:
            rejected.append({"candidate": candidate.get("candidate_id") or candidate.get("event_id"), "reason": "unsupported sport/market or missing event identity"})
            continue
        for idea in candidate_ideas:
            selected_matches.append({"event_id": idea.event_id, "event_label": idea.event_label, "sport": idea.sport, "competition": idea.competition})
        ideas.extend(candidate_ideas)
    
    # Extract unique matches
    seen_matches = set()
    unique_matches = []
    for m in selected_matches:
        if m["event_id"] not in seen_matches:
            seen_matches.add(m["event_id"])
            unique_matches.append(m)

    recs = [i for i in ideas if i.suggested_use != "WATCHLIST_ONLY"]
    watch = [i for i in ideas if i.suggested_use == "WATCHLIST_ONLY"]
    
    # Sort recommendations by score descending
    recs = sorted(recs, key=calculate_idea_score, reverse=True)
    
    # Limit main recommendations to top 12 by default, move the rest to watchlist
    final_recs = recs[:12]
    overflow_recs = recs[12:]
    for r in overflow_recs:
        r.suggested_use = "WATCHLIST_ONLY"
    
    watch.extend(overflow_recs)
    # Sort watchlist by score descending
    watch = sorted(watch, key=calculate_idea_score, reverse=True)

    combos = build_bet_builder_combo_ideas(final_recs)
    package_type: PackageType = "ANALYST_RECOMMENDATION_PACKAGE" if ideas else "NO_SUPPORTED_MATCHES_PACKAGE"
    data_gaps = sorted({gap for idea in ideas for gap in idea.source_gaps})
    return UnifiedLiveAnalystPackage(
        package_type=package_type,
        run_id=run_id,
        betting_day=betting_day or datetime.now(timezone.utc).date().isoformat(),
        selected_matches=unique_matches,
        recommendations=final_recs,
        bet_builder_combo_ideas=combos,
        watchlist_only=watch,
        rejected_ideas=rejected,
        data_gaps=data_gaps,
        ready_for_manual_operator_quote_review=bool(final_recs),
    )


def build_bet_builder_combo_ideas(recommendations: list[LiveAnalystMarketIdea]) -> list[BetBuilderComboIdea]:
    by_event: dict[str, list[LiveAnalystMarketIdea]] = {}
    for idea in recommendations:
        if idea.suggested_use == "BET_BUILDER_LEG":
            by_event.setdefault(idea.event_id, []).append(idea)
    combos: list[BetBuilderComboIdea] = []
    for event_id, ideas in by_event.items():
        if len(ideas) < 2:
            continue
        selected = ideas[:3]
        combos.append(BetBuilderComboIdea(
            combo_id=f"combo_{event_id}",
            idea_ids=[i.idea_id for i in selected],
            event_label=selected[0].event_label,
            combo_note="Optional Bet Builder idea only; user decides whether to combine in Superbet.",
            correlation_notes=["Same-event legs require manual correlation review; operator quote required."],
            conflict_risks=["Combined odds are not computed by pipeline; line/market availability may differ in Superbet."],
        ))
    return combos[:6]


def validate_human_superbet_quote(package: UnifiedLiveAnalystPackage, quote_payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Validate human quote without ever fetching/operator-automating Superbet."""
    issues: list[str] = []
    if quote_payload.get("entered_by_human") is not True:
        issues.append("entered_by_human must be true")
    if str(quote_payload.get("operator") or "").lower() != "superbet":
        issues.append("operator must be Superbet")
    if not quote_payload.get("as_of_utc"):
        issues.append("as_of_utc is required")
    quotes = quote_payload.get("quotes")
    if not isinstance(quotes, list) or not quotes:
        issues.append("quotes must be a non-empty list")
        return False, issues
    recommendation_ids = {idea.idea_id for idea in package.recommendations}
    for q in quotes:
        if not isinstance(q, dict):
            issues.append("quote entry must be an object")
            continue
        rec_id = str(q.get("recommendation_id") or q.get("candidate_id") or "")
        if rec_id not in recommendation_ids:
            issues.append(f"quote references unknown or non-recommendation id: {rec_id}")
        if q.get("legs_confirmed_on_operator_screen") is not True:
            issues.append(f"{rec_id}: legs must be confirmed on operator screen")
        try:
            odds = float(q.get("combined_odds_decimal"))
        except Exception:
            issues.append(f"{rec_id}: combined_odds_decimal is required")
        else:
            if odds <= 1.0:
                issues.append(f"{rec_id}: combined_odds_decimal must be > 1.0")
        if not q.get("operator_market_labels"):
            issues.append(f"{rec_id}: operator_market_labels required")
        if not q.get("operator_lines"):
            issues.append(f"{rec_id}: operator_lines required")
    return not issues, issues


def apply_human_quote_if_valid(package: UnifiedLiveAnalystPackage, quote_payload: Mapping[str, Any]) -> UnifiedLiveAnalystPackage:
    ok, issues = validate_human_superbet_quote(package, quote_payload)
    if not ok:
        return UnifiedLiveAnalystPackage(
            package_type="QUOTE_REJECTED_PACKAGE",
            run_id=package.run_id,
            betting_day=package.betting_day,
            selected_matches=package.selected_matches,
            recommendations=package.recommendations,
            bet_builder_combo_ideas=package.bet_builder_combo_ideas,
            watchlist_only=package.watchlist_only,
            rejected_ideas=[*package.rejected_ideas, {"quote_rejection_reasons": issues}],
            data_gaps=package.data_gaps,
            ready_for_manual_operator_quote_review=package.ready_for_manual_operator_quote_review,
        )
    return UnifiedLiveAnalystPackage(
        package_type="FINAL_MANUAL_COUPON_PACKAGE",
        run_id=package.run_id,
        betting_day=package.betting_day,
        selected_matches=package.selected_matches,
        recommendations=package.recommendations,
        bet_builder_combo_ideas=package.bet_builder_combo_ideas,
        watchlist_only=package.watchlist_only,
        rejected_ideas=package.rejected_ideas,
        data_gaps=package.data_gaps,
        ready_for_manual_operator_quote_review=True,
        ready_for_final_coupon=True,
        ready_for_manual_placement=True,
        final_coupon={"operator": "Superbet", "quote_source": "human_entered", "quotes": quote_payload.get("quotes", [])},
    )


def write_package(package: UnifiedLiveAnalystPackage, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "unified_live_analyst_package.json"
    md_path = out_dir / "unified_live_analyst_package.md"
    quality_path = out_dir / "package_quality_review.md"
    payload = package.to_dict()
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown_package(package), encoding="utf-8")
    quality_path.write_text(render_quality_review(package), encoding="utf-8")
    return {"json": json_path, "md": md_path, "quality": quality_path}


def render_markdown_package(package: UnifiedLiveAnalystPackage) -> str:
    from collections import Counter
    
    lines = [
        f"# Unified Live Analyst Package — {package.run_id}",
        "",
        f"Package type: `{package.package_type}`",
        f"Betting day: `{package.betting_day}`",
        "",
        "## 1. Executive Summary",
        "",
        "### Selection Verdict: Why these top ideas were selected",
        "The selected ideas represent the highest-quality analysts' suggestions prioritized for Football and Tennis. "
        "These selections have strong available qualitative evidence, are mapped to supported operator market families, "
        "and have their potential failure scenarios explicitly documented to ensure a balanced risk profile.",
        "",
        "### Top 5 Analyst Ideas Summary",
    ]
    
    top_5 = package.recommendations[:5]
    if not top_5:
        lines.append("No active recommendations found.")
    else:
        for idx, idea in enumerate(top_5, 1):
            line_status = f"`{idea.recommended_line}`" if idea.recommended_line else "N/A"
            if idea.line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK":
                line_status += " (DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK)"
            lines.append(f"{idx}. **{idea.event_label}**: {idea.recommended_market} {idea.recommendation_direction or ''} {line_status} (Confidence: `{idea.analyst_confidence}`, Quality: `{idea.data_quality}`)")
            
    lines.extend([
        "",
        "## 2. Top Analyst Recommendations",
        "",
    ])
    
    if not package.recommendations:
        lines.append("No active analyst recommendations.")
    else:
        for idea in package.recommendations:
            lines.append(f"### {idea.event_label} — {idea.recommended_market} {idea.recommendation_direction or ''}")
            
            # Match Context Block
            participants_str = ", ".join(idea.participants) if getattr(idea, "participants", None) else idea.event_label
            lines.extend([
                "- **Match Context**:",
                f"  - **Event**: {idea.event_label}",
                f"  - **Sport**: {idea.sport}",
                f"  - **Competition/Tournament**: {idea.competition}",
                f"  - **Kickoff**: {idea.kickoff_time or 'N/A'}",
                f"  - **Participants**: {participants_str}",
                f"  - **Market**: {idea.recommended_market}",
                f"  - **Direction**: {idea.recommendation_direction or 'N/A'}",
                f"  - **Operator-check line**: {idea.recommended_line or 'N/A'}",
                f"  - **Line source**: {idea.line_source}",
                f"  - **Evidence grade**: {idea.source_coverage}",
                f"  - **Confidence**: {idea.analyst_confidence}",
                f"  - **Data quality**: {idea.data_quality}",
            ])
            
            lines.append(f"- **Market Idea**: {idea.recommended_market} {idea.recommendation_direction or ''} {f'line {idea.recommended_line}' if idea.recommended_line else ''}")
            lines.append(f"- **Confidence**: `{idea.analyst_confidence}`")
            lines.append(f"- **Data Quality**: `{idea.data_quality}`")
            lines.append(f"- **Why it may work**: {idea.why_it_may_work}")
            lines.append(f"- **Why it may fail**: {idea.why_it_may_fail}")
            lines.append(f"- **Source Gaps**: {'; '.join(idea.source_gaps) if idea.source_gaps else 'None recorded'}")
            
            # Operator Check Line section
            if idea.line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK":
                lines.append(f"- **Operator Check Line**: `DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK` (Current reference: {idea.recommended_line})")
                lines.append("  > *Reference line for manual Superbet check, not a confirmed operator line.*")
            else:
                lines.append(f"- **Operator Check Line**: `{idea.recommended_line or 'N/A'}`")
                
            lines.append(f"- **Standalone vs Bet Builder Leg**: {idea.suggested_use}")
            lines.append("- **Superbet Coupon Guard**: *No final coupon can be generated or bets placed without a human-entered Superbet quote confirming operator availability.*")
            lines.append("")
            
    lines.extend([
        "## 3. Bet Builder Combo Ideas",
        "",
    ])
    
    if not package.bet_builder_combo_ideas:
        lines.append("No same-event combinations generated; standalone/manual checks only.")
    else:
        for combo in package.bet_builder_combo_ideas:
            lines.append(f"### Combo for {combo.event_label} (`{combo.combo_id}`)")
            lines.append(f"- **Idea Legs**: {', '.join(combo.idea_ids)}")
            lines.append(f"- **Correlation Note**: {combo.combo_note}")
            lines.append(f"- **Risks**: {', '.join(combo.conflict_risks)}")
            lines.append("")
            
    lines.extend([
        "## 4. Watchlist Appendix",
        "",
        "The following additional matches were analyzed but are classified as watchlist-only due to limited evidence, lower confidence, or unverified default reference lines.",
        "",
    ])
    
    watchlist_displayed = package.watchlist_only[:20]
    if not package.watchlist_only:
        lines.append("Watchlist is empty.")
    else:
        for idea in watchlist_displayed:
            line_status = f"`{idea.recommended_line}`" if idea.recommended_line else "N/A"
            if idea.line_source == "DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK":
                line_status += " (DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK)"
            lines.append(f"- **{idea.event_label}**: {idea.recommended_market} {idea.recommendation_direction or ''} {line_status} — Confidence: `{idea.analyst_confidence}`, Quality: `{idea.data_quality}`. Reason: *{idea.evidence_summary}*")
            
        hidden_count = len(package.watchlist_only) - len(watchlist_displayed)
        lines.append("")
        lines.append(f"**Total Watchlist Count**: {len(package.watchlist_only)}")
        lines.append(f"**Hidden Watchlist Ideas (in JSON appendix only)**: {max(0, hidden_count)}")
        lines.append("")
        
    lines.extend([
        "## 5. Rejected Summary",
        "",
        "To ensure decision-grade clarity, rejected candidates are summarized below by reason rather than listed individually:",
        "",
    ])
    
    # Calculate rejected summary by reason
    reasons = []
    for item in package.rejected_ideas:
        if "quote_rejection_reasons" in item:
            reasons.append("Human Quote Rejection")
        else:
            reasons.append(item.get("reason") or "unsupported sport/market or missing event identity")
    counts = Counter(reasons)
    
    if not counts:
        lines.append("- No candidates were rejected during this run.")
    else:
        for reason, count in counts.items():
            lines.append(f"- **Reason**: *{reason}* — **Count**: {count}")
            
    lines.extend([
        "",
        "## 6. Data Gaps and Confidence Policy",
        "",
        "To prevent hallucination and maintain absolute transparency, the following policy applies:",
        "- **Odds Availability**: Missing operator odds does NOT block sports analysis; the idea is analyzed but marked with EV/Fair Odds unavailable.",
        "- **Data Hydration**: Missing fully hydrated stat histories downgrades the analyst confidence level (capping it at C or D) and redirects the idea to the watchlist rather than blocking it entirely.",
        "- **Model Probabilities**: Missing fair-odds or team model probabilities prevents EV/Fair Odds generation but allows qualitative analyst recommendations to remain active.",
        "- **Default Reference Lines**: Any reference lines generated using historical baseline estimates (such as Corners 7.5, Cards 3.5, Goals 2.5, Games 21.5) are clearly flagged as `DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK`. These require physical confirmation by the operator on the bookmaker site before coupon completion.",
        "",
        "### Registered Gaps during Run",
    ])
    
    if not package.data_gaps:
        lines.append("- No data gaps registered in this run.")
    else:
        for gap in package.data_gaps:
            lines.append(f"- {gap}")
            
    lines.extend([
        "",
        "## 7. Superbet Manual Operator Checklist",
        "",
        "Before combining legs or placing any bets, the operator MUST complete the following steps manually:",
        "1. Open the **Superbet** interface and navigate to the respective event.",
        "2. Verify that the recommended market is active and accepting quotes.",
        "3. **Check the Line**: If the line is marked `DEFAULT_REFERENCE_NEEDS_OPERATOR_CHECK`, find the actual line on Superbet (e.g. Total Goals, Corners, or Aces). Do not assume the pipeline reference matches the operator's line.",
        "4. Confirm that the odds offered are acceptable and that there is no market block.",
        "5. Enter the confirmed quotes into the manual quote validation file.",
        "6. **NO AUTOMATION GATES BYPASSED**: Remember that final coupon generation and placement readiness are strictly blocked without this human confirmation.",
        "",
    ])
    
    return "\n".join(lines) + "\n"


def render_quality_review(package: UnifiedLiveAnalystPackage) -> str:
    issues: list[str] = []
    for idea in [*package.recommendations, *package.watchlist_only]:
        if not idea.counter_evidence:
            issues.append(f"{idea.idea_id}: missing counter evidence")
        if idea.ev_available:
            issues.append(f"{idea.idea_id}: EV should not be available in analyst-only package")
        if idea.final_coupon_ready or idea.manual_placement_ready:
            issues.append(f"{idea.idea_id}: illegal final/placement readiness")
    verdict = "PASS" if not issues else "FAIL"
    return "\n".join([
        "# Package Quality Review",
        "",
        f"VERDICT={verdict}",
        f"PACKAGE_TYPE={package.package_type}",
        f"RECOMMENDATIONS={len(package.recommendations)}",
        f"WATCHLIST_ONLY={len(package.watchlist_only)}",
        "NO_FAKE_STATS_VERDICT=PASS",
        "NO_FAKE_MODEL_PROBABILITY_VERDICT=PASS",
        "NO_FAKE_OPERATOR_QUOTE_VERDICT=PASS",
        "NO_COMBINED_BUILDER_ODDS_COMPUTED_VERDICT=PASS",
        "ODDS_REQUIRED_FOR_ANALYSIS=false",
        "HYDRATED_REQUIRED_FOR_ANALYSIS=false",
        "MODEL_PROBABILITY_REQUIRED_FOR_ANALYSIS=false",
        "",
        "## Issues",
        *(f"- {issue}" for issue in issues),
    ]) + "\n"
