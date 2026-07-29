"""Market-specific probability inputs schema, derivation and validation."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import re
from typing import Any, List, Optional

from bet.stats.market_ranking import SPORT_STAT_KEYS


PERCENTAGE_STAT_KEYS = frozenset(
    {
        "possession",
        "fg_pct",
        "three_pct",
        "ft_pct",
        "faceoff_pct",
        "first_serve_pct",
        "first_serve_win_pct",
        "second_serve_win_pct",
        "break_points_saved_pct",
        "hold_pct",
        "break_pct",
        "hitting_pct",
        "kd_ratio",
        "map_win_rate",
        "win_rate_l10",
        "checkout_pct",
    }
)
KNOWN_SPLIT_STAT_KEYS = frozenset(
    stat_key for stat_keys in SPORT_STAT_KEYS.values() for stat_key in stat_keys
)
SUPPORTED_MARKET_FAMILIES = frozenset({
    "RESULT",
    "GOALS_TOTALS",
    "CORNERS",
    "CARDS",
    "SHOTS",
    "SHOTS_ON_TARGET",
})
LINE_REQUIRED_MARKET_FAMILIES = frozenset({
    "GOALS_TOTALS",
    "CORNERS",
    "CARDS",
    "SHOTS",
    "SHOTS_ON_TARGET",
})
PARTIAL_PROBABILITY_CONFIDENCES = frozenset({"PARTIAL"})
MINIMAL_HYDRATION_PROBABILITY_CONFIDENCES = frozenset({
    "BLOCKED",
    "LOW",
    "LOW_CONFIDENCE",
    "MINIMAL",
    "UNKNOWN",
    "",
})
BLOCKED_PROBABILITY_CONFIDENCES = (
    PARTIAL_PROBABILITY_CONFIDENCES | MINIMAL_HYDRATION_PROBABILITY_CONFIDENCES
)
_LINE_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_line(*values: Any) -> float | None:
    for value in values:
        coerced = _coerce_float(value)
        if coerced is not None:
            return coerced
        text = _normalized_text(value)
        if not text:
            continue
        match = _LINE_RE.search(text)
        if match:
            try:
                return float(match.group(0))
            except (TypeError, ValueError):
                continue
    return None


def _normalized_tokens(*values: Any) -> str:
    return " ".join(_normalized_text(value).lower() for value in values if _normalized_text(value))


def _confidence_rank(value: Any) -> int:
    normalized = _normalized_text(value).upper()
    if normalized == "HIGH":
        return 3
    if normalized == "MEDIUM":
        return 2
    if normalized == "LOW":
        return 1
    return 0


def _artifact_path_matches(expected: str, actual: str) -> bool:
    expected_normalized = _normalized_text(expected)
    actual_normalized = _normalized_text(actual)
    if not expected_normalized:
        return True
    return bool(actual_normalized) and actual_normalized == expected_normalized


def _direction_matches(expected: str, actual: str) -> bool:
    expected_normalized = _normalized_text(expected).upper()
    actual_normalized = _normalized_text(actual).upper()
    if not expected_normalized:
        return True
    if not actual_normalized:
        return True
    return expected_normalized == actual_normalized


def _line_matches(expected: float | None, actual: float | None) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    return abs(actual - expected) < 0.01


def _has_known_as_of(*values: Any) -> bool:
    for value in values:
        normalized = _normalized_text(value).upper()
        if normalized and normalized != "UNKNOWN":
            return True
    return False


def _hydrated_confidence_gap_status(value: Any) -> str:
    normalized = _normalized_text(value).upper()
    if normalized in PARTIAL_PROBABILITY_CONFIDENCES:
        return "REVIEW_ONLY_PARTIAL_DATA"
    if normalized in MINIMAL_HYDRATION_PROBABILITY_CONFIDENCES:
        return "RESEARCH_GAP_MINIMAL_HYDRATION"
    return ""


def _result_selection(value: Any, participants: list[str]) -> str:
    token = _normalized_text(value)
    lowered = token.lower()
    if lowered == "home" and participants:
        return participants[0]
    if lowered == "away" and len(participants) > 1:
        return participants[1]
    if lowered == "draw":
        return "DRAW"
    return token


def _direction_from_values(*values: Any) -> str:
    for value in values:
        text = _normalized_text(value).upper()
        if text in {"OVER", "UNDER"}:
            return text
    return ""


@dataclass(frozen=True)
class MarketSemantics:
    market_family: str = ""
    market_type: str = ""
    market_label: str = ""
    outcome_name: str = ""
    selection: str = ""
    direction: str = ""
    line: float | None = None
    point: float | None = None
    provider_market_key: str = ""
    bookmaker: str = ""
    source_artifact_path: str = ""
    confidence: str = ""
    mapping_source: str = ""
    mapping_status: str = ""
    field_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_market_semantics(
    seed: dict[str, Any] | None,
    *,
    participants: list[str] | None = None,
    source_artifact_path: str = "",
    field_path: str = "",
) -> MarketSemantics:
    participants = list(participants or [])
    if not isinstance(seed, dict):
        return MarketSemantics(source_artifact_path=source_artifact_path, field_path=field_path)

    explicit_family = _normalized_text(seed.get("market_family")).upper()
    provider_market_key = _normalized_text(
        seed.get("provider_market_key")
        or seed.get("market_type")
        or seed.get("market_key")
    )
    market_label = _normalized_text(
        seed.get("market_label")
        or seed.get("market")
        or seed.get("name")
        or provider_market_key
    )
    outcome_name = _normalized_text(seed.get("outcome_name") or seed.get("outcome"))
    bookmaker = _normalized_text(seed.get("bookmaker") or seed.get("best_bookmaker"))
    selection = _normalized_text(seed.get("selection") or seed.get("pick") or outcome_name)
    direction = _direction_from_values(seed.get("direction"), selection, outcome_name, market_label)
    point = _extract_line(seed.get("point"))
    line = _extract_line(seed.get("line"), seed.get("point"), selection, outcome_name, market_label)
    has_market_hint = bool(
        explicit_family
        or provider_market_key
        or _normalized_text(seed.get("market_label"))
        or _normalized_text(seed.get("market"))
        or _normalized_text(seed.get("name"))
        or _normalized_text(seed.get("market_type"))
    )

    combined = _normalized_tokens(explicit_family, provider_market_key, market_label, outcome_name, selection)
    market_family = explicit_family
    confidence = ""
    mapping_source = ""
    mapping_status = ""

    if market_family:
        confidence = "HIGH"
        mapping_source = "explicit_market_family"
    elif any(token in combined for token in ("player_", "player ", "goalscorer", "to score", "to assist", "to be fouled", "to be booked")):
        market_family = "UNSUPPORTED_PROP_MATCH"
        confidence = "HIGH"
        mapping_source = "market_label"
        mapping_status = "UNSUPPORTED_PROP_MATCH"
    elif any(token in combined for token in ("player_tackles", "player_passes", "player shots", "player_shots", "player cards", "player_cards", "player games", "player_games")):
        market_family = "UNSUPPORTED_PROP_MATCH"
        confidence = "HIGH"
        mapping_source = "market_label"
        mapping_status = "UNSUPPORTED_PROP_MATCH"
    elif any(token in combined for token in ("shots on target", "shots_on_target", "sot")):
        market_family = "SHOTS_ON_TARGET"
        confidence = "HIGH" if provider_market_key else "MEDIUM"
        mapping_source = "provider_market_key" if provider_market_key else "market_label"
    elif any(token in combined for token in ("total shots", "match_shots", "team_shots", "shots")):
        market_family = "SHOTS"
        confidence = "HIGH" if provider_market_key else "MEDIUM"
        mapping_source = "provider_market_key" if provider_market_key else "market_label"
    elif any(token in combined for token in ("yellow cards", "cards", "bookings", "bookings_totals", "number_of_cards_in_match", "card_handicap")):
        market_family = "CARDS"
        confidence = "HIGH" if provider_market_key else "MEDIUM"
        mapping_source = "provider_market_key" if provider_market_key else "market_label"
    elif any(token in combined for token in ("total corners", "corners", "corner_handicap", "corners_totals", "corners_2-way")):
        market_family = "CORNERS"
        confidence = "HIGH" if provider_market_key else "MEDIUM"
        mapping_source = "provider_market_key" if provider_market_key else "market_label"
    elif any(token in combined for token in ("goals total", "total goals", "goals_over/under", "over_under", "totals", "goals total o/u", "alternative_goal_line", "alternative_total_goals", "number_of_goals_in_match", "games o/u", "games over/under", "total games", "total sets", "sets won", "sets o/u", "rebounds o/u", "points o/u", "assists o/u")):
        market_family = "GOALS_TOTALS"
        confidence = "HIGH" if provider_market_key else "MEDIUM"
        mapping_source = "provider_market_key" if provider_market_key else "market_label"
    elif provider_market_key.lower() in {"h2h", "match winner", "moneyline", "ml"} or any(token in combined for token in (" match winner", "moneyline", " h2h", "ml:", "ml ")):
        market_family = "RESULT"
        confidence = "HIGH" if provider_market_key else "MEDIUM"
        mapping_source = "provider_market_key" if provider_market_key else "market_label"

    if market_family == "RESULT":
        selection = _result_selection(selection or outcome_name or seed.get("direction"), participants)
        if not direction:
            direction = selection
    else:
        selection = _normalized_text(selection or outcome_name or direction)

    if not market_family and has_market_hint:
        mapping_status = "AMBIGUOUS_MARKET_LABEL"
    elif market_family in LINE_REQUIRED_MARKET_FAMILIES and not direction:
        mapping_status = "DIRECTION_MISSING"
    elif market_family in LINE_REQUIRED_MARKET_FAMILIES and line is None:
        mapping_status = "LINE_MISSING"

    return MarketSemantics(
        market_family=market_family,
        market_type=provider_market_key or market_label,
        market_label=market_label,
        outcome_name=outcome_name,
        selection=selection,
        direction=direction,
        line=line,
        point=point if point is not None else line,
        provider_market_key=provider_market_key,
        bookmaker=bookmaker,
        source_artifact_path=_normalized_text(seed.get("source_artifact_path") or source_artifact_path),
        confidence=confidence,
        mapping_source=mapping_source,
        mapping_status=mapping_status,
        field_path=field_path,
    )


def split_stat_aggregation_policy(stat_key: str) -> str | None:
    normalized = str(stat_key or "").strip().lower()
    if normalized in PERCENTAGE_STAT_KEYS or normalized.endswith("_pct"):
        return "MEAN_OF_HOME_AWAY_PERCENTAGES"
    if normalized in KNOWN_SPLIT_STAT_KEYS:
        return "MEAN_OF_HOME_AWAY_RATES"
    return None


def aggregate_split_stat_value(
    stat_key: str,
    home_value: Any,
    away_value: Any,
) -> tuple[float | None, str]:
    policy = split_stat_aggregation_policy(stat_key)
    if policy is None:
        return None, "UNKNOWN_SPLIT_STAT_SEMANTICS"

    numeric_values: list[float] = []
    for raw_value in (home_value, away_value):
        if raw_value in (None, ""):
            continue
        try:
            numeric_values.append(float(raw_value))
        except (TypeError, ValueError):
            continue

    if not numeric_values:
        return None, policy

    return round(sum(numeric_values) / len(numeric_values), 2), policy


def _derive_summary_average(summary: dict[str, Any], stat_key: str) -> tuple[float | None, str]:
    averages = summary.get("l10_avg", {}) or {}
    direct_value = averages.get(stat_key)
    if direct_value is not None:
        try:
            return float(direct_value), "DIRECT_STAT_VALUE"
        except (TypeError, ValueError):
            return None, "INVALID_DIRECT_STAT_VALUE"

    aggregated_value, policy = aggregate_split_stat_value(
        stat_key,
        averages.get(f"{stat_key}_home"),
        averages.get(f"{stat_key}_away"),
    )
    return aggregated_value, policy


@dataclass
class MarketProbabilityInputV1:
    candidate_id: str = ""
    event_id: str = ""
    market: str = ""
    sport: str = "football"
    competition: str = ""
    home_team: str = ""
    away_team: str = ""
    market_family: str = ""
    market_type: str = ""
    selection: str = ""
    direction: str = ""
    line: Optional[float] = None
    team_a_name: str = ""
    team_b_name: str = ""
    market_label: str = ""
    outcome_name: str = ""
    point: Optional[float] = None
    provider_market_key: str = ""
    bookmaker: str = ""
    team_a_l10: List[float] = field(default_factory=list)
    team_b_l10: List[float] = field(default_factory=list)
    h2h_l5: Optional[List[float]] = None
    source_artifact_path: str = ""
    semantics_field_path: str = ""
    stats_as_of: str = "UNKNOWN"
    sample_size: int = 0
    aggregation_policy: str = ""
    semantics_issue: str = ""
    mapping_source: str = ""
    mapping_status: str = ""
    confidence: str = ""
    missing_fields: List[str] = field(default_factory=list)
    hydration_status: str = "HYDRATED"
    promotion_status: str = "ANALYZABLE"
    source_provider: str = ""
    as_of_utc: str = "UNKNOWN"
    stat_semantics_status: str = "UNKNOWN"
    probability_confidence: str = ""
    probability_method: str = ""
    promotion_safe_model_probability: bool = False
    source_market_id: str = ""

    def __init__(self, **kwargs):
        if "caller_provided_probability" in kwargs:
            raise ValueError("CALLER_PROBABILITY_FORBIDDEN: probability must be derived by model package")
        self.candidate_id = ""
        self.event_id = ""
        self.market = ""
        self.sport = "football"
        self.competition = ""
        self.home_team = ""
        self.away_team = ""
        self.market_family = ""
        self.market_type = ""
        self.selection = ""
        self.direction = ""
        self.line = None
        self.team_a_name = ""
        self.team_b_name = ""
        self.market_label = ""
        self.outcome_name = ""
        self.point = None
        self.provider_market_key = ""
        self.bookmaker = ""
        self.team_a_l10 = []
        self.team_b_l10 = []
        self.h2h_l5 = None
        self.source_artifact_path = ""
        self.semantics_field_path = ""
        self.stats_as_of = "UNKNOWN"
        self.sample_size = 0
        self.aggregation_policy = ""
        self.semantics_issue = ""
        self.mapping_source = ""
        self.mapping_status = ""
        self.confidence = ""
        self.missing_fields = []
        self.hydration_status = "HYDRATED"
        self.promotion_status = "ANALYZABLE"
        self.source_provider = ""
        self.as_of_utc = "UNKNOWN"
        self.stat_semantics_status = "UNKNOWN"
        self.probability_confidence = ""
        self.probability_method = ""
        self.promotion_safe_model_probability = False
        self.source_market_id = ""

        if "event_id" in kwargs and "candidate_id" not in kwargs:
            kwargs["candidate_id"] = kwargs["event_id"]
        elif "candidate_id" in kwargs and "event_id" not in kwargs:
            kwargs["event_id"] = kwargs["candidate_id"]

        for k, v in kwargs.items():
            setattr(self, k, v)


MarketProbabilityInput = MarketProbabilityInputV1


def derive_l10_series_for_market_family(
    stats_seed: dict[str, Any],
    market_family: str,
    line: float | None,
    direction: str,
    source_artifact_path: str = "",
) -> tuple[list[float], list[float], list[float] | None, str, str]:
    raw_data = stats_seed.get("raw_data") or {}
    safety_input = raw_data.get("safety_input") or {}
    markets = safety_input.get("markets") or []

    # Path 1: safety_input markets
    if markets:
        stats_seed_artifact_path = _normalized_text(stats_seed.get("source_artifact_path"))
        expected_artifact_path = _normalized_text(source_artifact_path or stats_seed_artifact_path)
        matching_markets: list[tuple[int, dict[str, Any], MarketSemantics, str]] = []
        for idx, market_entry in enumerate(markets):
            market_artifact_path = _normalized_text(
                market_entry.get("source_artifact_path")
                or stats_seed.get("source_artifact_path")
            )
            market_semantics = extract_market_semantics(
                market_entry,
                source_artifact_path=market_artifact_path,
                field_path=f"safety_input.markets[{idx}]",
            )
            if market_semantics.market_family != market_family:
                continue
            if not _artifact_path_matches(expected_artifact_path, market_artifact_path):
                continue
            if market_family in LINE_REQUIRED_MARKET_FAMILIES:
                if not _line_matches(line, market_semantics.line):
                    continue
                if not _direction_matches(direction, market_semantics.direction):
                    continue
            matching_markets.append((idx, market_entry, market_semantics, market_artifact_path))

        if not matching_markets:
            return [], [], None, "", "MARKET_SERIES_NOT_FOUND_FOR_FAMILY_LINE"

        matching_markets.sort(
            key=lambda item: (-_confidence_rank(item[2].confidence or item[1].get("confidence")), item[0])
        )

        if len(matching_markets) > 1:
            best_idx, best_m, best_semantics, best_artifact_path = matching_markets[0]
            _, second_m, second_semantics, second_artifact_path = matching_markets[1]
            best_conf = _confidence_rank(best_semantics.confidence or best_m.get("confidence"))
            second_conf = _confidence_rank(second_semantics.confidence or second_m.get("confidence"))
            if best_conf < 3 or best_conf == second_conf:
                return [], [], None, "", "AMBIGUOUS_MARKET_SERIES_MATCH"
        else:
            best_idx, best_m, best_semantics, best_artifact_path = matching_markets[0]

        team_a_l10 = best_m.get("team_a_l10") or []
        team_b_l10 = best_m.get("team_b_l10") or []
        h2h_l5 = best_m.get("h2h_values") or []
        m_id = str(best_m.get("id") or best_m.get("market_id") or "")
        f_path = f"safety_input.markets[{best_idx}]"
        policy = f"SAFETY_INPUT_MARKET_SERIES|id:{m_id}|path:{f_path}|artifact:{best_artifact_path}"
        return team_a_l10, team_b_l10, h2h_l5, policy, ""

    # Path 2: Reconstruct from l10_matches or summaries
    stats_a = stats_seed.get("stats_a_summary") or {}
    stats_b = stats_seed.get("stats_b_summary") or {}

    stat_key_map = {
        "GOALS_TOTALS": "goals",
        "CORNERS": "corners",
        "CARDS": "yellow_cards",
        "SHOTS": "shots",
        "SHOTS_ON_TARGET": "shots_on_target",
        "RESULT": "goals",
    }

    stat_key = stat_key_map.get(market_family)
    sport = _normalized_text(stats_seed.get("sport")).lower()

    if sport == "tennis":
        stat_key = "games_won"
        combined_text = str(market_family).lower() + " " + str((stats_seed.get("best_market") or {}).get("name", "")).lower() + " " + str(stats_seed.get("market_label", "")).lower() + " " + str(stats_seed.get("market", "")).lower()
        if "set" in combined_text:
            stat_key = "sets_won"
    elif sport == "basketball":
        stat_key = "points"
        combined_text = str(market_family).lower() + " " + str((stats_seed.get("best_market") or {}).get("name", "")).lower() + " " + str(stats_seed.get("market_label", "")).lower() + " " + str(stats_seed.get("market", "")).lower()
        if "rebound" in combined_text:
            stat_key = "rebounds"
        elif "assist" in combined_text:
            stat_key = "assists"

    if not stat_key:
        return [], [], None, "", "UNSUPPORTED_MARKET_FAMILY"

    team_a_l10 = []
    team_b_l10 = []

    team_a_raw = raw_data.get("team_a_l10") or {}
    team_b_raw = raw_data.get("team_b_l10") or {}

    for team_raw, target_list in ((team_a_raw, team_a_l10), (team_b_raw, team_b_l10)):
        matches = team_raw.get("l10_matches") or []
        for match in matches:
            stats = match.get("stats", match)
            val = stats.get(stat_key)
            if val is not None:
                if isinstance(val, dict):
                    aggregated_value, policy = aggregate_split_stat_value(
                        stat_key,
                        val.get("home"),
                        val.get("away"),
                    )
                    if aggregated_value is None:
                        return [], [], None, policy, "UNKNOWN_SPLIT_STAT_SEMANTICS"
                    target_list.append(aggregated_value)
                else:
                    target_list.append(float(val))

    aggregation_policy = "DIRECT_MATCH_SERIES"
    if not team_a_l10 and stats_a.get("has_data"):
        l10_avg, aggregation_policy = _derive_summary_average(stats_a, stat_key)
        l5_avg = stats_a.get("l5_avg", {}).get(stat_key)
        if l10_avg is not None:
            try:
                from normalize_stats import _synthesize_l10
            except ImportError:
                from scripts.normalize_stats import _synthesize_l10
            team_a_l10 = _synthesize_l10(l10_avg, l5_avg, seed_key=stats_a.get("team", "A"))
        elif aggregation_policy == "UNKNOWN_SPLIT_STAT_SEMANTICS":
            return [], [], None, aggregation_policy, aggregation_policy

    if not team_b_l10 and stats_b.get("has_data"):
        l10_avg, aggregation_policy_b = _derive_summary_average(stats_b, stat_key)
        l5_avg = stats_b.get("l5_avg", {}).get(stat_key)
        if l10_avg is not None:
            try:
                from normalize_stats import _synthesize_l10
            except ImportError:
                from scripts.normalize_stats import _synthesize_l10
            team_b_l10 = _synthesize_l10(l10_avg, l5_avg, seed_key=stats_b.get("team", "B"))
            if aggregation_policy == "DIRECT_MATCH_SERIES":
                aggregation_policy = aggregation_policy_b
        elif aggregation_policy_b == "UNKNOWN_SPLIT_STAT_SEMANTICS":
            return [], [], None, aggregation_policy_b, aggregation_policy_b

    h2h_summary = stats_seed.get("h2h_summary") or {}
    h2h_l5 = []
    if h2h_summary.get("has_data"):
        avg_val = h2h_summary.get("averages", {}).get(stat_key)
        if avg_val is not None:
            h2h_l5 = [float(avg_val)] * min(5, h2h_summary.get("meetings_count", 0))

    return team_a_l10, team_b_l10, h2h_l5 if h2h_l5 else None, aggregation_policy, ""


def build_market_probability_input(candidate: dict[str, Any], stats_seed: dict[str, Any] | None) -> MarketProbabilityInput:
    candidate_id = candidate.get("candidate_id") or candidate.get("fixture_key") or ""
    sport = candidate.get("sport") or ""
    team_a_name = candidate.get("home_team") or ""
    team_b_name = candidate.get("away_team") or ""
    participants = [name for name in (team_a_name, team_b_name) if name]
    candidate_semantics = extract_market_semantics(
        candidate,
        participants=participants,
        source_artifact_path=_normalized_text(candidate.get("source_artifact_path")),
        field_path="candidate",
    )
    market_family = candidate_semantics.market_family
    market_type = candidate_semantics.market_type
    market_label = candidate_semantics.market_label
    outcome_name = candidate_semantics.outcome_name
    selection = candidate_semantics.selection
    direction = candidate_semantics.direction
    line = candidate_semantics.line
    point = candidate_semantics.point
    provider_market_key = candidate_semantics.provider_market_key
    bookmaker = candidate_semantics.bookmaker
    semantics_field_path = candidate_semantics.field_path
    mapping_source = candidate_semantics.mapping_source
    mapping_status = candidate_semantics.mapping_status
    confidence = candidate_semantics.confidence

    if not stats_seed:
        return MarketProbabilityInput(
            candidate_id=candidate_id,
            sport=sport,
            market_family=market_family,
            market_type=market_type,
            market_label=market_label,
            outcome_name=outcome_name,
            selection=selection,
            direction=direction,
            line=line,
            point=point,
            provider_market_key=provider_market_key,
            bookmaker=bookmaker,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            source_artifact_path=candidate_semantics.source_artifact_path,
            semantics_field_path=semantics_field_path,
            mapping_source=mapping_source,
            mapping_status=mapping_status,
            confidence=confidence,
            missing_fields=["stats_seed"],
            hydration_status="DATA_UNAVAILABLE",
            promotion_status="BLOCKED_HYDRATION_FAILED",
            source_provider=candidate.get("source_provider") or "",
            as_of_utc="UNKNOWN",
            stats_as_of="UNKNOWN",
            stat_semantics_status="UNKNOWN",
            probability_confidence=str(candidate.get("probability_confidence") or "").upper().strip(),
            probability_method=str(candidate.get("probability_method") or "").upper().strip(),
            promotion_safe_model_probability=False,
            source_market_id="",
        )

    best_market = candidate.get("best_market") or stats_seed.get("best_market") or {}
    if best_market:
        fallback_semantics = extract_market_semantics(
            best_market,
            participants=participants,
            source_artifact_path=_normalized_text(stats_seed.get("source_artifact_path") or candidate_semantics.source_artifact_path),
            field_path="best_market",
        )
        if not market_family:
            market_family = fallback_semantics.market_family
            mapping_source = mapping_source or fallback_semantics.mapping_source
            mapping_status = mapping_status or fallback_semantics.mapping_status
            confidence = confidence or fallback_semantics.confidence
            semantics_field_path = semantics_field_path or fallback_semantics.field_path
        if not market_type:
            market_type = fallback_semantics.market_type
        if not market_label:
            market_label = fallback_semantics.market_label
        if not outcome_name:
            outcome_name = fallback_semantics.outcome_name
        if not selection:
            selection = fallback_semantics.selection
        if not direction:
            direction = fallback_semantics.direction
        if line is None:
            line = fallback_semantics.line
        if point is None:
            point = fallback_semantics.point
        if not provider_market_key:
            provider_market_key = fallback_semantics.provider_market_key
        if not bookmaker:
            bookmaker = fallback_semantics.bookmaker

    team_a_l10, team_b_l10, h2h_l5, aggregation_policy, semantics_issue = derive_l10_series_for_market_family(
        stats_seed,
        market_family,
        line,
        direction,
        candidate_semantics.source_artifact_path or _normalized_text(stats_seed.get("source_artifact_path")),
    )

    sample_size = max(len(team_a_l10), len(team_b_l10))

    stats_as_of = (
        stats_seed.get("probability_as_of")
        or stats_seed.get("generated_at")
        or stats_seed.get("as_of_utc")
        or candidate.get("stats_as_of")
        or candidate.get("as_of_utc")
        or ""
    )
    if not stats_as_of:
        stats_as_of = "UNKNOWN"

    source_provider = _normalized_text(
        stats_seed.get("source_provider")
        or candidate.get("source_provider")
        or (stats_seed.get("best_market") or {}).get("source")
        or stats_seed.get("source")
    )

    source_artifact_path = _normalized_text(
        candidate_semantics.source_artifact_path
        or stats_seed.get("source_artifact_path")
        or candidate.get("source_artifact_path")
    )

    # Parse packed market id and field path from policy if applicable
    source_market_id = ""
    if aggregation_policy.startswith("SAFETY_INPUT_MARKET_SERIES|"):
        parts = aggregation_policy.split("|")
        for part in parts:
            if part.startswith("id:"):
                source_market_id = part.split(":", 1)[1]
            elif part.startswith("path:"):
                semantics_field_path = part.split(":", 1)[1]

    # Hydration Status
    if len(team_a_l10) >= 5 and len(team_b_l10) >= 5:
        hydration_status = "HYDRATED"
    elif len(team_a_l10) > 0 or len(team_b_l10) > 0:
        hydration_status = "PARTIAL_HYDRATION"
    else:
        hydration_status = "MINIMAL_HYDRATION"

    probability_confidence = str(candidate.get("probability_confidence") or stats_seed.get("probability_confidence") or "").upper().strip()
    probability_method = str(candidate.get("probability_method") or stats_seed.get("probability_method") or "").upper().strip()

    if semantics_issue == "UNKNOWN_SPLIT_STAT_SEMANTICS":
        stat_semantics_status = "UNKNOWN"
    else:
        stat_semantics_status = "KNOWN"

    # Evaluate promotion eligibility
    is_exact_market_match = (
        market_family in SUPPORTED_MARKET_FAMILIES
        and mapping_status not in {"AMBIGUOUS_MARKET_LABEL", "UNSUPPORTED_PROP_MATCH", "LINE_MISSING", "DIRECTION_MISSING"}
        and semantics_issue not in {"AMBIGUOUS_MARKET_LABEL", "UNSUPPORTED_PROP_MATCH", "AMBIGUOUS_MARKET_SERIES_MATCH", "MARKET_SERIES_NOT_FOUND_FOR_FAMILY_LINE"}
    )
    is_line_dir_ok = True
    if market_family in LINE_REQUIRED_MARKET_FAMILIES:
        if line is None or not direction:
            is_line_dir_ok = False

    is_l10_valid = len(team_a_l10) >= 5 and len(team_b_l10) >= 5
    is_stat_semantics_ok = (stat_semantics_status == "KNOWN" and semantics_issue != "UNKNOWN_SPLIT_STAT_SEMANTICS")
    is_traceable = bool(source_provider and source_artifact_path and _has_known_as_of(stats_as_of))
    is_confidence_ok = probability_confidence not in BLOCKED_PROBABILITY_CONFIDENCES
    is_method_ok = (probability_method != "BOOKMAKER_IMPLIED_REFERENCE_ONLY")

    confidence_gap_status = _hydrated_confidence_gap_status(probability_confidence)

    if hydration_status == "DATA_UNAVAILABLE":
        promotion_status = "BLOCKED_HYDRATION_FAILED"
    elif hydration_status != "HYDRATED" and hydration_status != "PARTIAL_HYDRATION" and hydration_status != "MINIMAL_HYDRATION":
        promotion_status = "BLOCKED_UNKNOWN_HYDRATION_STATUS"
    elif hydration_status == "HYDRATED" and is_exact_market_match and is_line_dir_ok and is_l10_valid and is_stat_semantics_ok and is_traceable and is_confidence_ok and is_method_ok:
        promotion_status = "ANALYZABLE"
    elif hydration_status == "HYDRATED" and is_exact_market_match and is_line_dir_ok and is_l10_valid and is_stat_semantics_ok and is_traceable and is_method_ok and confidence_gap_status:
        promotion_status = confidence_gap_status
    else:
        promotion_status = "RESEARCH_GAP_MARKET_INPUT_NOT_BUILT"

    promotion_safe_model_probability = promotion_status == "ANALYZABLE"

    missing_fields = []
    if mapping_status == "AMBIGUOUS_MARKET_LABEL":
        missing_fields.append("market_label")
    if not market_family:
        missing_fields.append("market_family")
    if market_family in LINE_REQUIRED_MARKET_FAMILIES and not direction:
        missing_fields.append("direction")
    if line is None and market_family in LINE_REQUIRED_MARKET_FAMILIES:
        missing_fields.append("line")
    if semantics_issue == "UNKNOWN_SPLIT_STAT_SEMANTICS":
        missing_fields.append("unknown_split_stat_semantics")
    if not source_provider:
        missing_fields.append("source_provider")
    if not source_artifact_path:
        missing_fields.append("source_artifact_path")
    if not _has_known_as_of(stats_as_of):
        missing_fields.append("stats_as_of")
    if not is_confidence_ok:
        missing_fields.append("probability_confidence")
    if not is_method_ok:
        missing_fields.append("probability_method")

    return MarketProbabilityInput(
        candidate_id=candidate_id,
        sport=sport,
        market_family=market_family,
        market_type=market_type,
        market_label=market_label,
        outcome_name=outcome_name,
        selection=selection,
        direction=direction,
        line=line,
        point=point,
        provider_market_key=provider_market_key,
        bookmaker=bookmaker,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        team_a_l10=team_a_l10,
        team_b_l10=team_b_l10,
        h2h_l5=h2h_l5,
        source_artifact_path=source_artifact_path,
        semantics_field_path=semantics_field_path,
        stats_as_of=stats_as_of,
        sample_size=sample_size,
        aggregation_policy=aggregation_policy,
        semantics_issue=semantics_issue,
        mapping_source=mapping_source,
        mapping_status=mapping_status,
        confidence=confidence,
        missing_fields=missing_fields,
        hydration_status=hydration_status,
        promotion_status=promotion_status,
        source_provider=source_provider,
        as_of_utc=stats_as_of,
        stat_semantics_status=stat_semantics_status,
        probability_confidence=probability_confidence,
        probability_method=probability_method,
        promotion_safe_model_probability=promotion_safe_model_probability,
        source_market_id=source_market_id,
    )


def validate_market_probability_input(input_data: MarketProbabilityInput) -> tuple[bool, str]:
    if input_data.probability_method == "BOOKMAKER_IMPLIED_REFERENCE_ONLY":
        return False, "BOOKMAKER_IMPLIED_REFERENCE_ONLY"

    if input_data.semantics_issue in {"AMBIGUOUS_MARKET_SERIES_MATCH", "MARKET_SERIES_NOT_FOUND_FOR_FAMILY_LINE"}:
        return False, input_data.semantics_issue

    if input_data.stat_semantics_status == "UNKNOWN" or input_data.semantics_issue == "UNKNOWN_SPLIT_STAT_SEMANTICS" or "unknown_split_stat_semantics" in input_data.missing_fields:
        return False, "UNKNOWN_SPLIT_STAT_SEMANTICS"

    if input_data.mapping_status == "AMBIGUOUS_MARKET_LABEL":
        return False, "AMBIGUOUS_MARKET_LABEL"

    if input_data.mapping_status == "UNSUPPORTED_PROP_MATCH":
        return False, "UNSUPPORTED_PROP_MATCH"

    if not input_data.market_family:
        return False, "MARKET_SPECIFIC_INPUT_NOT_BUILT"

    if "UNSUPPORTED" in input_data.market_family or "PROP" in input_data.market_family or "tackles" in input_data.market_type:
        return False, "UNSUPPORTED_PROP_MATCH"

    if input_data.market_family not in SUPPORTED_MARKET_FAMILIES:
        return False, "MARKET_FAMILY_NOT_SUPPORTED_BY_ENGINE"

    if input_data.market_family in LINE_REQUIRED_MARKET_FAMILIES:
        if input_data.line is None:
            return False, "LINE_MISSING"

    if input_data.market_family in LINE_REQUIRED_MARKET_FAMILIES and not input_data.direction:
        return False, "DIRECTION_MISSING"

    if not input_data.source_provider:
        return False, "SOURCE_PROVIDER_MISSING"

    if not input_data.source_artifact_path:
        return False, "SOURCE_ARTIFACT_PATH_MISSING"

    if not _has_known_as_of(input_data.stats_as_of, input_data.as_of_utc):
        return False, "STATS_AS_OF_MISSING_OR_UNKNOWN"

    if input_data.hydration_status != "HYDRATED":
        return False, input_data.hydration_status

    confidence_gap_status = _hydrated_confidence_gap_status(input_data.probability_confidence)
    if confidence_gap_status and input_data.promotion_status != "ANALYZABLE":
        return False, confidence_gap_status

    if input_data.promotion_status != "ANALYZABLE":
        return False, input_data.promotion_status

    if input_data.market_family in LINE_REQUIRED_MARKET_FAMILIES:
        if not input_data.team_a_l10 or not input_data.team_b_l10:
            return False, "L10_SERIES_MISSING"
        if len(input_data.team_a_l10) < 5 or len(input_data.team_b_l10) < 5:
            return False, "INSUFFICIENT_SAMPLE_SIZE"

    elif input_data.market_family == "RESULT":
        if not input_data.team_a_l10 or not input_data.team_b_l10:
            return False, "L10_SERIES_MISSING"
        if len(input_data.team_a_l10) < 5 or len(input_data.team_b_l10) < 5:
            return False, "INSUFFICIENT_SAMPLE_SIZE"

    if input_data.probability_confidence in BLOCKED_PROBABILITY_CONFIDENCES:
        return False, _hydrated_confidence_gap_status(input_data.probability_confidence) or "PROMOTION_CONFIDENCE_LOW_OR_MINIMAL"

    if input_data.stat_semantics_status == "UNKNOWN" or input_data.semantics_issue == "UNKNOWN_SPLIT_STAT_SEMANTICS" or "unknown_split_stat_semantics" in input_data.missing_fields:
        return False, "UNKNOWN_SPLIT_STAT_SEMANTICS"

    return True, "PASS"


def explain_probability_input_gap(input_data: MarketProbabilityInput) -> str:
    valid, reason = validate_market_probability_input(input_data)
    if valid:
        return ""
    return reason


def validate_model_scope_match(
    model_scope: dict[str, Any],
    event_scope: dict[str, Any],
) -> bool:
    """Validate exact match between model scope and event scope (sport, competition, market)."""
    if not isinstance(model_scope, dict) or not isinstance(event_scope, dict):
        return False
    sport_match = str(model_scope.get("sport", "")).lower() == str(event_scope.get("sport", "")).lower()
    comp_match = str(model_scope.get("competition", "")).lower() == str(event_scope.get("competition", "")).lower()
    market_match = str(model_scope.get("market", "")).lower() == str(event_scope.get("market", "")).lower()
    return bool(sport_match and comp_match and market_match)
