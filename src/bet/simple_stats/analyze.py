"""ANALYZE: STATS_SHEET_V1 hit-rate rows over STANDARD_MARKET_LINES.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2 (Krok 2).
"""
from __future__ import annotations

import json
import statistics
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from bet.stats.market_ranking import player_prop_lines, standard_market_lines

from bet.simple_stats.providers import _normalize_team_name, _team_matches
from bet.simple_stats.context_flags import context_flags_for_row
from bet.simple_stats.offered_lines import (
    MAX_OFFERED_LINES_PER_SAMPLE,
    OfferedLines,
    select_lines,
)

from bet.simple_stats.contracts import (
    PERCENTAGE_METRICS,
    EventDossierListV1,
    EventDossierV1,
    MetricObservation,
    ProviderValue,
    StatsSheetRow,
    StatsSheetV1,
)

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
_OBSERVATION_SCOPE_PATH = _CONFIG_DIR / "observation_scope.json"
_TENNIS_FORMAT_PATH = _CONFIG_DIR / "tennis_match_format.json"
_CONFIG_LOCK = threading.Lock()
_OBSERVATION_SCOPE_CACHE: dict[str, dict[str, str]] | None = None
_TENNIS_FORMAT_CACHE: dict[str, str] | None = None


def _load_json(path: Path) -> dict:
    """A config document, or ``{}`` when it is missing or malformed.

    Never raises. A config problem must degrade this stage to the behaviour it
    had before the config existed, not empty the sheet -- the same failure mode
    ``coupons._competition_tier_map`` already chose.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def observation_scope() -> dict[str, dict[str, str]]:
    """``{provider: {competition_id: reason}}`` from config/observation_scope.json.

    Read once. The reason string is what lands in ``StatsSheetRow.
    sample_excluded``, so a dropped observation can always be traced back to
    the pin that dropped it.
    """
    global _OBSERVATION_SCOPE_CACHE
    with _CONFIG_LOCK:
        if _OBSERVATION_SCOPE_CACHE is not None:
            return _OBSERVATION_SCOPE_CACHE
    document = _load_json(_OBSERVATION_SCOPE_PATH).get("excluded_competitions") or {}
    scope: dict[str, dict[str, str]] = {}
    if isinstance(document, dict):
        for provider, entries in document.items():
            if not isinstance(entries, dict):
                continue
            scope[str(provider)] = {
                str(competition_id): str((entry or {}).get("reason") or "EXCLUDED_COMPETITION")
                for competition_id, entry in entries.items()
                if isinstance(entry, dict)
            }
    with _CONFIG_LOCK:
        if _OBSERVATION_SCOPE_CACHE is None:
            _OBSERVATION_SCOPE_CACHE = scope
        return _OBSERVATION_SCOPE_CACHE


def tennis_match_format(competition: str | None) -> str | None:
    """``"BO5"``, ``"BO3"`` or None when this competition is not pinned.

    None is deliberately not BO3. Guessing best-of-three from a name is how the
    sheet came to price a men's Grand Slam off a best-of-three sample in the
    first place; an unpinned competition gates nothing and is emitted exactly
    as it was before this file existed.
    """
    global _TENNIS_FORMAT_CACHE
    with _CONFIG_LOCK:
        cache = _TENNIS_FORMAT_CACHE
    if cache is None:
        formats = _load_json(_TENNIS_FORMAT_PATH).get("formats") or {}
        cache = {
            str(name): str(value)
            for name, value in formats.items()
            if isinstance(formats, dict)
        }
        with _CONFIG_LOCK:
            if _TENNIS_FORMAT_CACHE is None:
                _TENNIS_FORMAT_CACHE = cache
            cache = _TENNIS_FORMAT_CACHE
    return cache.get(competition or "")


def reset_scope_caches() -> None:
    """Forget both cached config documents. For tests only."""
    global _OBSERVATION_SCOPE_CACHE, _TENNIS_FORMAT_CACHE
    with _CONFIG_LOCK:
        _OBSERVATION_SCOPE_CACHE = None
        _TENNIS_FORMAT_CACHE = None

# STANDARD_MARKET_LINES' "stat" field uses the pre-existing (non-"_total")
# taxonomy; MetricObservation keys use our canonical names (section 5). Two
# tables, because one market stat now addresses two different metrics: the
# match total both sides contributed to, and one team's own contribution.
_MARKET_STAT_TO_CANONICAL = {
    "corners": "corners_total",
    "yellow_cards": "cards_total",
    "fouls": "fouls_total",
    "shots_on_target": "shots_on_target_total",
    "shots": "shots_total",
    "goals": "goals_total",
    "goals_1h": "goals_1h_total",
    "goals_2h": "goals_2h_total",
    "offsides": "offsides_total",
    "red_cards": "red_cards_total",
    "total_games": "total_games",
    "aces": "aces_total",
    "sets_won": "total_sets",
    "double_faults": "double_faults_total",
    "breaks": "breaks_total",
}

# is_combined=False markets. Until a provider kept the home/away split past its
# own client these were unreachable and ANALYZE skipped them outright; Bzzoiro's
# /events/{id}/stats/ is what populates the "_for" metrics they read.
_TEAM_MARKET_STAT_TO_CANONICAL = {
    "corners": "corners_for",
    "yellow_cards": "cards_for",
    "fouls": "fouls_for",
    "shots_on_target": "shots_on_target_for",
    "shots": "shots_for",
    "goals": "goals_for",
    "offsides": "offsides_for",
    # Tennis. "Per team" is "per player" here, and it is the same mechanism:
    # one side's own line, one row per side, told apart by team_name. Tennis got
    # this in one wave because bzzoiro's box score is already p1_*/p2_*.
    "aces": "aces_for",
    "double_faults": "double_faults_for",
    "games_won": "games_won",
}

_CONFIDENCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_hit_rate(values: list[float], line: float, direction: str) -> tuple[int, int, int]:
    """Count how many values are over/under the line, excluding pushes.

    Derived from scripts/compute_safety_scores.py:357-380 (a pure function with
    no other repo coupling) rather than imported: scripts/ has no __init__.py
    and is not an importable package from src/bet/.

    Args:
        values: list of stat values
        line: the betting line (e.g., 9.5)
        direction: "OVER" or "UNDER"

    Returns: (hits, settled, pushes)
        settled = observations that resolve the bet, i.e. len(values) - pushes
        pushes  = values exactly on the line (only whole-number lines can push)

    ``settled`` is deliberately not ``len(values)``. A value sitting exactly on
    the line is a push: it is not a hit for OVER and not a hit for UNDER, so
    including it deflates hit_rate on both sides of the same line at once. It
    also reaches further than the ratio, because ``sample_size`` is what
    _confidence thresholds on -- a whole-number line would otherwise buy HIGH
    (>=8) with observations that settle no bet. Football lines are all .5 so
    nothing pushes there; tennis totals are not, which is where this bites.
    """
    if not values:
        return 0, 0, 0

    hits = 0
    pushes = 0
    for v in values:
        if v == line:
            pushes += 1
        elif direction == "OVER" and v > line:
            hits += 1
        elif direction == "UNDER" and v < line:
            hits += 1

    return hits, len(values) - pushes, pushes


def wilson_lower_bound(hits: int, sample_size: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for hits/sample_size.

    This is the sheet's ranking number. A raw hit rate cannot order rows,
    because it reads 4/4 as 1.00 and 9/12 as 0.75 and so puts the four-match
    sample on top -- the exact inversion this pipeline exists to avoid. Wilson
    charges each row for its own thinness: 4/4 comes out at 0.51, below 9/12 at
    0.58, without a hand-tuned small-sample penalty anywhere.

    z defaults to 1.96, the two-sided 95% normal quantile.

    Returns 0.0 for an empty sample: no observations is no evidence, which is
    the floor and not a missing value.
    """
    if sample_size <= 0:
        return 0.0
    p = hits / sample_size
    z2 = z * z
    denominator = 1 + z2 / sample_size
    centre = p + z2 / (2 * sample_size)
    margin = z * ((p * (1 - p) / sample_size + z2 / (4 * sample_size * sample_size)) ** 0.5)
    return max(0.0, (centre - margin) / denominator)


def _all_values(obs) -> list[ProviderValue]:
    """Every observation for one metric, each historical match counted once.

    The three buckets overlap by construction. A league fixture the two sides
    already played this season is in team_a's last-10 *and* team_b's last-10
    *and* h2h, so before deduplication one match contributed three values to
    sample_size, hit_rate, mean and median -- and sample_size is exactly what
    _confidence reads to award HIGH (>=8) or LOW (<5). A 4-match sample read
    as 12 is not a rounding error, it is a confidence tier bought with
    duplicates.

    The key is (provider, match_id), not match_id: two providers reporting the
    same match is the corroboration that _cross_provider_agreement exists to
    check, and must survive. Observations with no match_id are all kept, since
    without an id there is nothing to prove they are the same match.

    That makes this list the *agreement* sample, not the statistical one. The
    hit rate and Wilson bound instead read a sample built per bucket by
    ``_one_per_day`` (pooled for a match total by ``_independent_match_sample``),
    which collapses a corroborated match back to one observation; see those for
    why a surviving duplicate would otherwise buy confidence it did not earn.
    """
    return _dedup((*obs.team_a_l10, *obs.team_b_l10, *obs.h2h))


def _dedup(values) -> list[ProviderValue]:
    """One observation per (provider, match_id), order preserved.

    Split out of ``_all_values`` because a per-team or per-player sample is a
    *single* bucket -- there is no team_a/team_b/h2h overlap to collapse -- but
    the same match can still arrive twice within it, and the same
    confidence-tier-bought-with-duplicates failure applies.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[ProviderValue] = []
    for pv in values:
        if not pv.match_id:
            unique.append(pv)
            continue
        key = (pv.provider, pv.match_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(pv)
    return unique


_DAY_KEY_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d, %Y",
)


def _day_key(match_date: str | None) -> str:
    """The calendar day an observation belongs to, as ``YYYY-MM-DD``.

    Slicing ``[:10]`` off the raw string was only a day key for providers that
    happen to emit ISO. sportdb does (``2026-08-22T10:30:00.000Z``); a provider
    stamping ``22/08/2026`` landed in its own bucket and could never corroborate
    the same match, which reports SINGLE_SOURCE for data that in fact agreed --
    the quietest possible failure, since a missing corroboration looks exactly
    like a provider that had nothing to say.

    Unparseable input returns ``""``, which the caller already treats as "cannot
    tell which match this is" rather than as a day that groups.
    """
    raw = (match_date or "").strip()
    if not raw:
        return ""
    # Fast path: ISO-8601, with or without a time part and any timezone suffix.
    head = raw[:10]
    try:
        return datetime.strptime(head, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass
    # Whole string first, then the leading date token. "22 Aug 2026" only parses
    # whole; "2026-08-22T10:30:00.000Z" only parses as a token. Trying the token
    # alone reduced the former to "22".
    candidates = (raw, raw.replace("T", " ").split(" ")[0])
    for fmt in _DAY_KEY_FORMATS:
        for candidate in candidates:
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return ""


def _season_sort_key(pv: ProviderValue) -> tuple[str, str]:
    """Newest-first ordering key for picking a competition's current season.

    ``_day_key`` rather than the raw string, so a provider stamping
    ``22/08/2026`` sorts against one stamping ISO instead of landing before
    every date in the sample. ``match_id`` breaks ties so the choice is stable
    for two observations of the same day.
    """
    return (_day_key(pv.match_date), pv.match_id)


def scope_values(values: list[ProviderValue]) -> tuple[list[ProviderValue], dict[str, int]]:
    """The observations that may enter a sample, and what was removed.

    Two rules, counted separately because they answer different objections and
    a reader of the sheet needs to know which one fired.

    **Out-of-scope competition** (``config/observation_scope.json``). A
    pre-season friendly is not a trial of the competition being priced: the
    opposition is drawn from other divisions, the sides are experimenting, and
    the result settles nothing. The analyst doc's §67 already says so and the
    analyst already applies it in prose; ``p_low`` kept counting them. Pinned
    by exact provider competition id, never by name.

    **Stale season**, per competition. For each competition present, only the
    season of its newest observation survives. Doing it per competition and not
    per sample is the whole point: Sheffield United's Championship 26/27 and
    Carabao Cup 26/27 matches are both current and both stay, while a Serie A
    25/26 observation sitting in a Serie A 26/27 sample goes -- on 2026-09-01
    that was seven of Parma's fourteen shots observations, six of thirteen for
    Al-Hilal's corners, and a Monza observation twelve and a half months old.

    An observation missing either id is kept and counted against neither rule.
    Not knowing which competition a match belonged to is not evidence that it
    belonged to the wrong one, and dropping it would quietly delete every
    provider that does not publish league ids.

    Returns ``(kept, {reason: count})``. Order is preserved, so every caller
    downstream -- ``_dedup``, ``_one_per_day``, ``_cross_provider_agreement`` --
    sees the sample it would have seen had the removed matches never been
    fetched.
    """
    scope = observation_scope()
    kept: list[ProviderValue] = []
    dropped: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    after_pin: list[ProviderValue] = []
    for pv in values:
        reason = scope.get(pv.provider, {}).get(pv.competition_id or "")
        if reason is not None:
            drop(reason)
            continue
        after_pin.append(pv)

    # Current season per competition, decided by the newest observation that
    # names one. A competition whose observations carry no season_id at all
    # yields no target and filters nothing.
    newest_of: dict[str, ProviderValue] = {}
    for pv in after_pin:
        if not pv.competition_id or not pv.season_id:
            continue
        incumbent = newest_of.get(pv.competition_id)
        if incumbent is None or _season_sort_key(pv) > _season_sort_key(incumbent):
            newest_of[pv.competition_id] = pv
    current_season = {
        competition_id: pv.season_id
        for competition_id, pv in newest_of.items()
        if pv.season_id
    }

    for pv in after_pin:
        target = current_season.get(pv.competition_id or "")
        if target is not None and pv.season_id and pv.season_id != target:
            drop("STALE_SEASON")
            continue
        kept.append(pv)
    return kept, dropped


def _scope_observation(obs: MetricObservation) -> tuple[MetricObservation, dict[str, int]]:
    """``scope_values`` over all three buckets of one metric, as one decision.

    The season target is computed across the buckets pooled, not per bucket:
    an h2h meeting from last season must be measured against the *sample's*
    current season, and a bucket holding only stale meetings would otherwise
    declare its own oldest season current and keep everything.
    """
    pooled = [*obs.team_a_l10, *obs.team_b_l10, *obs.h2h]
    kept, dropped = scope_values(pooled)
    survivors = {(pv.provider, pv.match_id, pv.value) for pv in kept}

    def surviving(bucket: list[ProviderValue]) -> list[ProviderValue]:
        return [pv for pv in bucket if (pv.provider, pv.match_id, pv.value) in survivors]

    return (
        MetricObservation(
            canonical_name=obs.canonical_name,
            team_a_l10=surviving(obs.team_a_l10),
            team_b_l10=surviving(obs.team_b_l10),
            h2h=surviving(obs.h2h),
        ),
        dropped,
    )


# Tennis markets whose value scales with how long the match is allowed to run.
# A best-of-three sample cannot describe any of them for a best-of-five tie:
# "under 3.5 sets" is 100% of every best-of-three match ever played, and the
# games, aces and double faults it produces are drawn from at most three sets.
_TENNIS_LENGTH_DEPENDENT_MARKETS = frozenset(
    {
        "total_sets", "total_games", "games_won",
        "aces_total", "aces_for",
        "double_faults_total", "double_faults_for",
        "breaks_total",
    }
)

# A best-of-five match can run to four or five sets; a best-of-three cannot.
# One observation at or above this proves the sample contains best-of-five
# tennis, which is all the gate below needs to know.
_BO5_MIN_SETS = 4.0


def _sample_is_best_of_five(dossier: EventDossierV1) -> bool:
    """Whether this fixture's own sample contains any best-of-five match.

    Read off ``total_sets`` -- the one metric that states match length directly
    -- rather than inferred from game counts, which a long best-of-three can
    fake. No observation of it at all answers False: a sample that cannot show
    a four-set match is not a sample of best-of-five tennis.
    """
    obs = dossier.metrics.get("total_sets")
    if obs is None:
        return False
    return any(
        pv.value >= _BO5_MIN_SETS
        for pv in (*obs.team_a_l10, *obs.team_b_l10, *obs.h2h)
    )


def _cross_provider_agreement(metric: str, observations: list[ProviderValue]) -> str:
    """Classify whether providers agree on the same historical match.

    Providers spell opponents differently ("Ulsan Hyundai FC" vs "Ulsan HD",
    "Real Betis" vs "Betis") and stamp dates in different formats, so
    observations are bucketed by calendar day and then clustered within the day
    by fuzzy opponent match. Keying on the raw opponent string instead made
    every cross-provider pair look like SINGLE_SOURCE, which silently disabled
    the agreement check this pipeline exists to surface.

    Disagreeing values are never averaged away: they drive the AGREE/DISAGREE
    verdict and both stay in the dossier.
    """
    by_day: dict[str, list[ProviderValue]] = {}
    for pv in observations:
        by_day.setdefault(_day_key(pv.match_date), []).append(pv)

    threshold = 5.0 if metric in PERCENTAGE_METRICS else 1.0
    saw_single = False
    saw_multi = False
    for day, day_observations in by_day.items():
        if not day:
            # No usable date: cannot tell which match this belongs to, so it
            # cannot corroborate or contradict anything.
            saw_single = True
            continue
        for cluster in _cluster_by_opponent(day_observations):
            providers = {pv.provider for pv in cluster}
            if len(providers) < 2:
                saw_single = True
                continue
            saw_multi = True
            values = [pv.value for pv in cluster]
            if max(values) - min(values) > threshold:
                return "DISAGREE"

    if saw_multi:
        return "AGREE"
    if saw_single:
        return "SINGLE_SOURCE"
    return "NOT_APPLICABLE"


def _cluster_by_opponent(observations: list[ProviderValue]) -> list[list[ProviderValue]]:
    """Greedily group same-day observations whose opponent names refer to the
    same team, using the provider-abbreviation-tolerant matcher from
    providers.py."""
    clusters: list[list[ProviderValue]] = []
    for pv in observations:
        name = _normalize_team_name(pv.opponent)
        for cluster in clusters:
            if _team_matches(name, _normalize_team_name(cluster[0].opponent)):
                cluster.append(pv)
                break
        else:
            clusters.append([pv])
    return clusters


def _representative(group: list[ProviderValue]) -> ProviderValue:
    """The one observation a set of duplicate reports of one match is worth.

    ``median_low`` rather than a mean: it returns a value some provider actually
    reported, so nothing synthetic enters the sample and no average can land a
    manufactured value exactly on a whole-number line, where it would push and
    silently leave the sample. Order-independent, and deterministic when several
    observations share the median value.
    """
    consensus = statistics.median_low([pv.value for pv in group])
    return next(pv for pv in group if pv.value == consensus)


def _tennis_match_key(pv: ProviderValue) -> str:
    """Which match a tennis observation is, within one player's bucket.

    The opponent, not the day -- because for tennis the day is not reliable and
    the opponent is. ``tennis-abstract`` stamps every match of a tournament with
    the tournament's *start* date: measured on 2026-08-28, 1945 of its 2550
    observations fell on a Monday, while ``espn-tennis`` spread its 510 evenly
    across the week. That single fact broke the day key in both directions at
    once, and the two failures do not cancel:

    * **Across providers, too little collapsing.** One match carries a Monday
      from tennis-abstract and its real Wednesday from espn-tennis, so the day
      key sees two days and counts one match as two independent trials. 44 such
      matches across 15 events.
    * **Within tennis-abstract, too much.** Every match of one tournament week
      shares a date, so the day key treats a whole run as one match and keeps a
      single representative. 140 such collisions -- and because
      ``_representative`` takes the median, the one it keeps can be the win and
      the one it drops the loss. Single #34 of that day (Semenistaja - Hunter,
      aces UNDER 8.5) reported 10/10 while Storm Hunter's 9-ace match, a loss at
      that line, shared a Monday with a 5-ace match and vanished.

    Opponent names are why this is defensible here and was not for football.
    ``_one_per_day`` replaced opponent clustering precisely because club names
    are spelled 72 different ways across feeds ("mk dons" / "milton keynes
    dons"). Player names are not: measured on the same slate, across every
    tennis bucket carrying two providers, the two providers' opponent sets were
    *identical* wherever both described the same player -- "Clara Tauson",
    "Elise Mertens", "Kayla Day" character for character, with "Shuai Zhang" /
    "Zhang Shuai" the only variation, which ``_team_matches`` already handles.

    A repeat pairing is not lost to this. The key carries how many times *this
    provider* has already named that opponent in this bucket, so a provider
    listing six meetings with Terence Atmane yields six keys, while the same
    single meeting reported by two providers yields one. The provider's own row
    count is the only evidence available about how often two players met, so it
    is what decides -- rather than a date the provider does not really have.
    """
    return _normalize_team_name(pv.opponent) or ""


def _tennis_match_keys(values: list[ProviderValue]) -> list[str]:
    """``_tennis_match_key`` for a whole bucket, with repeat meetings numbered.

    Numbering is per (provider, opponent): the first Tauson match tennis-abstract
    reports keys to the same slot as the first Tauson match espn-tennis reports,
    so the pair collapses, while a second Tauson match from either provider gets
    its own slot and survives.
    """
    seen: dict[tuple[str, str], int] = {}
    keys: list[str] = []
    for pv in values:
        opponent = _tennis_match_key(pv)
        if not opponent:
            keys.append("")
            continue
        slot = (pv.provider, opponent)
        occurrence = seen.get(slot, 0)
        seen[slot] = occurrence + 1
        keys.append(f"{opponent}#{occurrence}")
    return keys


def _one_per_day(values: list[ProviderValue], sport: str = "football") -> list[ProviderValue]:
    """One observation per calendar day within a *single* bucket.

    A team plays at most one match on a given day. So two observations in the
    same bucket stamped the same day are the same match -- whatever each
    provider called the opponent, and whatever native ``match_id`` each stamped
    on it. That makes the day the whole identity here and removes name matching
    from the collapse entirely.

    This replaced a (day + fuzzy opponent name) clustering that read the pooled
    buckets. Names were the wrong instrument: measured over the 2026-08-25 and
    2026-08-28 runs, **72** same-bucket same-day pairs failed to cluster because
    two providers spelled one club differently -- ``mk dons`` vs
    ``milton keynes dons``, ``atletico junior`` vs ``junior barranquilla``,
    ``shenzhen peng city`` vs ``shenzhen xinpengcheng`` -- so one match counted
    as two independent trials and *inflated* p_low. Loosening the matcher was
    the wrong fix twice over: it cannot be made safe (``real madrid`` and
    ``real sociedad`` share a substantive token too), and `_team_matches` is the
    same predicate team-identity resolution depends on, where a false positive
    files another team's data.

    Undated observations are kept whole: with no day there is nothing to place
    them by, and merging on name alone is exactly the guess this avoids. That is
    the one residual path by which a sample can still be overstated, and it did
    not occur in either measured run.
    """
    keys = (
        _tennis_match_keys(values)
        if sport == "tennis"
        else [_day_key(pv.match_date) for pv in values]
    )
    grouped: dict[str, list[ProviderValue]] = {}
    order: list[str] = []
    unkeyed: list[ProviderValue] = []
    for pv, key in zip(values, keys):
        if not key:
            unkeyed.append(pv)
            continue
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(pv)
    return [_representative(grouped[key]) for key in order] + unkeyed


def _head_to_head_days(
    obs, team_a_name: str | None, team_b_name: str | None, sport: str = "football"
) -> set[str]:
    """Days on which the two sides of *this* fixture played each other.

    Such a match is in team A's last-10, in team B's last-10 **and** in h2h, and
    `_one_per_day` cannot see that: it works one bucket at a time, and the three
    buckets name different opponents for it (A's bucket says "B", B's says "A").
    Within one provider `_dedup` already collapses it on the shared match_id;
    across providers the ids differ, so without this it survives as two or three
    trials for one match.

    Identified against the dossier's own team names rather than by comparing the
    opponents to each other -- the two are *supposed* to differ here, so their
    disagreement carries no information.
    """
    if sport == "tennis":
        # Keyed the same way _one_per_day keys tennis: by opponent. Every row in
        # a tennis h2h bucket names one of these two players by construction, so
        # the pair *is* the key, and the shared match is whichever row in either
        # l10 bucket names the other side.
        keys = {
            _normalize_team_name(name)
            for name in (team_a_name, team_b_name)
            if name
        }
        keys |= {_tennis_match_key(pv) for pv in obs.h2h}
        keys.discard("")
        return keys
    days: set[str] = {_day_key(pv.match_date) for pv in obs.h2h}
    for bucket, other_side in ((obs.team_a_l10, team_b_name), (obs.team_b_l10, team_a_name)):
        if not other_side:
            continue
        target = _normalize_team_name(other_side)
        for pv in bucket:
            if _team_matches(_normalize_team_name(pv.opponent), target):
                days.add(_day_key(pv.match_date))
    days.discard("")
    return days


def _independent_match_sample(
    obs, team_a_name: str | None, team_b_name: str | None, sport: str = "football"
) -> list[ProviderValue]:
    """One observation per real-world match, for a pooled match-total sample.

    Collapses each bucket by day, then folds the head-to-head day -- the one
    match that legitimately appears in all three buckets -- back to a single
    observation.
    """
    h2h_keys = _head_to_head_days(obs, team_a_name, team_b_name, sport)
    key_of = _tennis_match_key if sport == "tennis" else (lambda pv: _day_key(pv.match_date))
    independent: list[ProviderValue] = []
    shared: list[ProviderValue] = []
    for bucket in (obs.team_a_l10, obs.team_b_l10, obs.h2h):
        for pv in _one_per_day(bucket, sport):
            if key_of(pv) in h2h_keys:
                shared.append(pv)
            else:
                independent.append(pv)

    # Football folds the shared match per day; tennis folds every meeting
    # between these two players into one, because its day is a tournament week
    # and cannot separate two meetings anyway. That understates a repeat
    # pairing, which is the safe direction for a lower bound.
    grouped: dict[str, list[ProviderValue]] = {}
    for pv in shared:
        grouped.setdefault("h2h" if sport == "tennis" else _day_key(pv.match_date), []).append(pv)
    independent.extend(_representative(group) for group in grouped.values())
    return independent


def _confidence(agreement: str, sample_size: int) -> str:
    """Explicit 1->2->3 evaluation order (section 2): DISAGREE or a thin
    sample is LOW regardless of anything else; AGREE/SINGLE_SOURCE/
    NOT_APPLICABLE all get the same treatment past that point, since none of
    them is itself a quality problem."""
    if agreement == "DISAGREE" or sample_size < 5:
        return "LOW"
    if sample_size >= 8:
        return "HIGH"
    return "MEDIUM"


def _rows_for_sample(
    *,
    dossier: EventDossierV1,
    canonical: str,
    lines: list[float],
    observations: list[ProviderValue],
    independent: list[ProviderValue],
    team_name: str | None = None,
    player_id: str | None = None,
    player_name: str | None = None,
    lineup_status: str | None = None,
    line_limit: int | None = None,
    sample_excluded: dict[str, int] | None = None,
) -> list[StatsSheetRow]:
    """Every (line x direction) row for one sample of one metric.

    One function for all three row families -- match total, per-team, per-player
    -- because the arithmetic must not differ between them. Wilson, the push
    rule and the confidence tiers are the sheet's whole claim to being auditable;
    a per-player copy of them that drifted by one threshold would be undetectable
    from the artifact.
    """
    if not observations:
        return []
    sources = sorted({pv.provider for pv in observations})
    # Two samples, because two consumers need different things. The agreement
    # check reads every observation -- two providers on one match is the
    # corroboration it exists to find. The statistics read one value per match,
    # because that corroboration is evidence the value is right, not a second
    # trial. ``independent`` is built by the caller, which still knows which
    # bucket each observation came from; see ``_one_per_day``.
    agreement = _cross_provider_agreement(canonical, observations)
    values = [pv.value for pv in independent]
    if not values:
        return []
    mean = statistics.fmean(values)
    median = statistics.median(values)

    rows: list[StatsSheetRow] = []
    # Trimming happens here, not at the call site, because it is measured
    # against this sample's own median and nothing upstream has computed one.
    # ``line_limit`` is set only for offer-driven ladders: Superbet posts up to
    # sixteen corner lines where the static grid had seven, and the ones four
    # goals clear of anything the sample ever produced yield 22/22 and a p_low
    # that means nothing.
    for line in select_lines(lines, median=median, limit=line_limit):
        for direction in ("OVER", "UNDER"):
            hits, sample_size, pushes = compute_hit_rate(values, float(line), direction)
            if sample_size == 0:
                continue
            row = StatsSheetRow(
                event_id=dossier.event_id,
                sport=dossier.sport,
                market=canonical,
                line=float(line),
                direction=direction,
                team_name=team_name,
                player_id=player_id,
                player_name=player_name,
                lineup_status=lineup_status,
                hits=hits,
                sample_size=sample_size,
                pushes=pushes,
                hit_rate=hits / sample_size,
                p_low=wilson_lower_bound(hits, sample_size),
                mean=mean,
                median=median,
                sources=sources,
                cross_provider_agreement=agreement,
                confidence=_confidence(agreement, sample_size),
                data_quality=dossier.readiness,
                sample_excluded=dict(sorted((sample_excluded or {}).items())),
            )
            # Context flags read the row's own market/line/direction, so they
            # can only be computed once the row exists; StatsSheetRow is
            # frozen, so the flagged version is a copy, not a mutation.
            flags = context_flags_for_row(row, dossier)
            if flags:
                row = row.model_copy(update={"context_flags": flags})
            rows.append(row)
    return rows


def _resolve_lines(
    offered: OfferedLines | None,
    *,
    event_id: str,
    market: str,
    static: list[float],
    team_name: str | None = None,
    player_name: str | None = None,
) -> tuple[list[float], int | None]:
    """``(lines, limit)`` for one sample: the book's ladder, or the static grid.

    The whole inversion described in ``offered_lines`` lands here. When a
    SUPERBET offer is loaded and carries this exact (event, market, side,
    player), those are the lines that get priced -- because they are the only
    lines the operator can take. Otherwise the static grid, unchanged and
    untrimmed, so a run with no SUPERBET step produces the sheet it always did.
    """
    if offered is not None:
        posted = offered.lines_for(
            event_id=event_id, market=market,
            team_name=team_name, player_name=player_name,
        )
        if posted:
            return (list(posted), MAX_OFFERED_LINES_PER_SAMPLE)
    return (list(static), None)


def _match_total_rows(
    dossier: EventDossierV1,
    offered: OfferedLines | None = None,
    *,
    suppressed_markets: frozenset[str] = frozenset(),
) -> list[StatsSheetRow]:
    rows: list[StatsSheetRow] = []
    for market_def in standard_market_lines().get(dossier.sport, []):
        if not market_def.get("is_combined", False):
            continue
        canonical = _MARKET_STAT_TO_CANONICAL.get(market_def["stat"])
        if canonical is None or canonical in suppressed_markets:
            continue
        obs = dossier.metrics.get(canonical)
        if obs is None:
            continue
        obs, sample_excluded = _scope_observation(obs)
        lines, limit = _resolve_lines(
            offered, event_id=dossier.event_id, market=canonical,
            static=market_def["lines"],
        )
        rows.extend(
            _rows_for_sample(
                dossier=dossier,
                canonical=canonical,
                lines=lines,
                line_limit=limit,
                observations=_all_values(obs),
                independent=_independent_match_sample(
                    obs, dossier.team_a_name, dossier.team_b_name, dossier.sport
                ),
                sample_excluded=sample_excluded,
            )
        )
    return rows


def _team_total_rows(
    dossier: EventDossierV1,
    offered: OfferedLines | None = None,
    *,
    suppressed_markets: frozenset[str] = frozenset(),
) -> list[StatsSheetRow]:
    """Per-team rows: one team's own contribution, not the match total.

    The two sides are analysed as **two separate samples**, never merged. The
    "_for" metric stores team A's own figures in ``team_a_l10`` and team B's in
    ``team_b_l10``, so pooling them the way ``_all_values`` pools a match total
    would build one twenty-match sample out of two different teams -- a number
    that describes neither of them and reads as twice the evidence.

    ``h2h`` is deliberately not read here. An H2H bucket has no marker for which
    side a value belongs to, so attributing it to either team would do exactly
    the mixing this function exists to avoid; ENRICH therefore never populates
    "_for" from the H2H slot.

    A row with no team name is not emitted: "corners_for OVER 4.5" naming nobody
    is not a bet, and two such rows for the same event are indistinguishable.
    """
    rows: list[StatsSheetRow] = []
    for market_def in standard_market_lines().get(dossier.sport, []):
        if market_def.get("is_combined", True):
            continue
        canonical = _TEAM_MARKET_STAT_TO_CANONICAL.get(market_def["stat"])
        if canonical is None or canonical in suppressed_markets:
            continue
        obs = dossier.metrics.get(canonical)
        if obs is None:
            continue
        for raw_bucket, team_name in (
            (obs.team_a_l10, dossier.team_a_name),
            (obs.team_b_l10, dossier.team_b_name),
        ):
            if not raw_bucket or not team_name:
                continue
            # Scoped per bucket, not pooled: a per-team sample *is* one bucket,
            # so this team's own newest season is the right target for it. The
            # two sides are never merged here (see the docstring) and must not
            # be merged by the scope filter either -- one side's cup run would
            # otherwise decide what counts as current for the other.
            bucket, sample_excluded = scope_values(raw_bucket)
            if not bucket:
                continue
            lines, limit = _resolve_lines(
                offered, event_id=dossier.event_id, market=canonical,
                static=market_def["lines"], team_name=team_name,
            )
            rows.extend(
                _rows_for_sample(
                    dossier=dossier,
                    canonical=canonical,
                    lines=lines,
                    line_limit=limit,
                    observations=_dedup(bucket),
                    independent=_one_per_day(bucket, dossier.sport),
                    team_name=team_name,
                    sample_excluded=sample_excluded,
                )
            )
    return rows


def _unavailable_player_ids(dossier: EventDossierV1) -> set[str]:
    """Every player id either side's squad reports as unavailable.

    docs/PLAN_BOGATE_STATYSTYKI.md Faza 4b: a prop on somebody injured is void,
    not losing, and ``squad_availability`` is already in the dossier -- so the
    filter belongs here, in code, rather than in ``bet-analyst.md`` prose that
    depends on someone remembering to check.
    """
    ids: set[str] = set()
    for squad in dossier.squad_availability:
        for entry in squad.unavailable:
            player_id = str(entry.get("provider_player_id") or "").strip()
            if player_id:
                ids.add(player_id)
    return ids


def _player_prop_rows(
    dossier: EventDossierV1,
    offered: OfferedLines | None = None,
    *,
    suppressed_markets: frozenset[str] = frozenset(),
) -> list[StatsSheetRow]:
    """Per-player rows from ``dossier.player_metrics``.

    Every row carries ``lineup_status`` from the dossier, because the sample says
    nothing about whether the player is actually starting: a prop computed off a
    predicted XI has the same arithmetic and a weaker premise, and the row is the
    only place that difference can be recorded.
    """
    rows: list[StatsSheetRow] = []
    if not dossier.player_metrics:
        return rows
    unavailable_ids = _unavailable_player_ids(dossier)
    by_stat: dict[str, list] = {}
    for observation in dossier.player_metrics:
        if observation.player_id in unavailable_ids:
            continue
        by_stat.setdefault(observation.canonical_name, []).append(observation)

    side_names = {"home": dossier.team_a_name, "away": dossier.team_b_name}
    for market_def in player_prop_lines().get(dossier.sport, []):
        canonical = market_def["stat"]
        if canonical in suppressed_markets:
            continue
        for observation in by_stat.get(canonical, []):
            l10, sample_excluded = scope_values(observation.l10)
            if not l10:
                continue
            lines, limit = _resolve_lines(
                offered, event_id=dossier.event_id, market=canonical,
                static=market_def["lines"], player_name=observation.player_name,
            )
            rows.extend(
                _rows_for_sample(
                    dossier=dossier,
                    canonical=canonical,
                    lines=lines,
                    line_limit=limit,
                    observations=_dedup(l10),
                    independent=_one_per_day(l10, dossier.sport),
                    team_name=side_names.get(observation.team_side),
                    player_id=observation.player_id,
                    player_name=observation.player_name,
                    lineup_status=dossier.lineup_status or None,
                    sample_excluded=sample_excluded,
                )
            )
    return rows


def suppressed_markets_for(
    dossier: EventDossierV1, competition: str | None
) -> frozenset[str]:
    """Markets this fixture's sample cannot speak to, so no row is emitted.

    One rule today, and it is not a judgement call. A men's Grand Slam tie is
    best-of-five; ``total_sets``, ``total_games``, aces, double faults and
    breaks all scale with how long the match runs. If the sample contains no
    best-of-five match, then every length-dependent line measured against it is
    describing a different game -- "under 3.5 sets, 15 from 15" is not a read,
    it is the definition of best-of-three.

    This is deliberately a *suppression* and not a downgrade. A tier step still
    leaves the row on the sheet at CALL-minus-one for an analyst to read as
    evidence, and the 2026-09-01 file shows what that costs: 137 of the day's
    154 vetoes were an analyst deleting these rows by hand, one line at a time,
    and the one that slipped past reached the operator as a Bet Builder.
    A measurement of a tautology is not weak evidence; it is not evidence.

    Both halves must be known for the gate to fire. An unpinned competition
    (``tennis_match_format`` returns None) suppresses nothing, and a sample that
    does contain a four- or five-set match is a best-of-five sample and is left
    entirely alone.
    """
    if dossier.sport != "tennis":
        return frozenset()
    if tennis_match_format(competition) != "BO5":
        return frozenset()
    if _sample_is_best_of_five(dossier):
        return frozenset()
    return _TENNIS_LENGTH_DEPENDENT_MARKETS


def analyze_dossier(
    dossier: EventDossierV1,
    offered: OfferedLines | None = None,
    *,
    competition: str | None = None,
) -> list[StatsSheetRow]:
    """STATS_SHEET_V1 rows for one event. BLOCKED dossiers never enter
    ANALYZE (section 2).

    Three families, distinguishable by the row's own fields rather than by a
    type tag: a match total has ``team_name`` and ``player_id`` unset, a per-team
    row has ``team_name`` only, a prop has both. They share one event_id and one
    ranking key, so a consumer that wants them separately can group on those
    fields and one that wants the day's strongest read can just sort.

    ``offered`` is the SUPERBET ladder for the day, when one was loaded. Where it
    covers a sample, its lines replace the static grid -- a line the operator
    cannot take is not a bet, however well evidenced. Omitting it is not a
    degraded mode: it is the sheet this function produced before the book was
    ever read, byte for byte.

    ``competition`` is the fixture's own competition name from EVENT_LIST_V1.
    The dossier does not carry it and cannot be made to answer for it, but two
    fixtures with identical statistics are different bets when one is a
    best-of-three and the other a best-of-five -- see ``suppressed_markets_for``.
    Omitting it suppresses nothing, which is exactly the behaviour of every run
    before this argument existed.
    """
    if dossier.readiness == "BLOCKED":
        return []
    suppressed = suppressed_markets_for(dossier, competition)
    return [
        *_match_total_rows(dossier, offered, suppressed_markets=suppressed),
        *_team_total_rows(dossier, offered, suppressed_markets=suppressed),
        *_player_prop_rows(dossier, offered, suppressed_markets=suppressed),
    ]


def analyze_dossiers(
    dossier_list: EventDossierListV1,
    offered: OfferedLines | None = None,
    *,
    competitions: Mapping[str, str] | None = None,
) -> StatsSheetV1:
    """Every dossier's rows, strongest first.

    ``competitions`` maps event_id to the competition name DISCOVER recorded.
    Absent, every fixture is analysed with ``competition=None`` and the
    format gate is inert -- an older caller keeps the sheet it always got.
    """
    rows: list[StatsSheetRow] = []
    lookup = competitions or {}
    for dossier in dossier_list.dossiers:
        rows.extend(
            analyze_dossier(
                dossier, offered, competition=lookup.get(dossier.event_id)
            )
        )
    # p_low first, tier second. Sorting on -hit_rate inside a confidence tier
    # reproduced the very inversion p_low exists to prevent: a 4/4 row (hit_rate
    # 1.00, p_low 0.51) outranked a 9/12 row (0.75, 0.58) whenever both landed
    # in the same tier. Ranking on p_low needs no tier tie-break to be correct,
    # so the tier is kept only as a stable secondary key.
    rows.sort(key=lambda r: (-r.p_low, _CONFIDENCE_ORDER[r.confidence]))
    return StatsSheetV1(
        run_id=dossier_list.run_id,
        date=dossier_list.date,
        generated_at=_now_iso(),
        rows=rows,
    )


def limit_rows_per_event(rows: list[StatsSheetRow], max_per_event: int | None) -> list[StatsSheetRow]:
    """Cap how many rows one event contributes to the sheet (Faza 2 sizing).

    ``rows`` is expected pre-sorted strongest-first (as ``analyze_dossiers``
    leaves it), so keeping the first ``max_per_event`` rows seen per
    ``event_id`` keeps each event's *best* rows and preserves the overall
    order. ``None`` means unlimited -- the default, so nothing changes unless
    a caller opts in.
    """
    if max_per_event is None:
        return rows
    seen: dict[str, int] = {}
    kept: list[StatsSheetRow] = []
    for row in rows:
        count = seen.get(row.event_id, 0)
        if count >= max_per_event:
            continue
        seen[row.event_id] = count + 1
        kept.append(row)
    return kept
