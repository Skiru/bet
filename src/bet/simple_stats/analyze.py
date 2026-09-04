"""ANALYZE: STATS_SHEET_V1 hit-rate rows over STANDARD_MARKET_LINES.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2 (Krok 2).
"""
from __future__ import annotations

import json
import math
import statistics
import threading
from collections.abc import Mapping
from typing import NamedTuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bet.stats.market_ranking import player_prop_lines, standard_market_lines

from bet.simple_stats.providers import (
    _normalize_team_name,
    _team_matches,
    reset_tennis_match_format_cache,
    reset_tennis_surface_cache,
    reset_tennis_tournament_map_cache,
    tennis_match_format_for_competition,
    tennis_surface_for_competition,
)
from bet.simple_stats.context_flags import (
    context_flags_for_row,
    lean_ceilings_for_row,
    referee_card_points_per_match,
)
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
_MARKET_PRIORS_PATH = _CONFIG_DIR / "market_priors.json"
_CONFIG_LOCK = threading.Lock()
_OBSERVATION_SCOPE_CACHE: dict[str, dict[str, str]] | None = None
_MARKET_PRIORS_CACHE: dict[str, float] | None = None


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

    Delegates to ``providers.tennis_match_format_for_competition`` rather than
    reading the config a second time -- the move ``tennis_surface`` below made
    first, for the reason it gives. Both sides of the draw comparison meet in
    ``scope_values``: the fixture's format, resolved here, and a historical
    ESPN row's tournament, resolved in ``providers.py``. Two loaders of one
    table is how the two come to disagree about a name and delete every
    observation that was in fact a match.

    None is deliberately not BO3. Guessing best-of-three from a name is how the
    sheet came to price a men's Grand Slam off a best-of-three sample in the
    first place; an unpinned competition gates nothing and is emitted exactly
    as it was before this file existed.
    """
    return tennis_match_format_for_competition(competition)


def tennis_surface(competition: str | None) -> str | None:
    """``"Hard"``, ``"Clay"``, ``"Grass"`` or None when unpinned.

    Delegates to ``providers.tennis_surface_for_competition`` rather than
    reading the config a second time. The two sides of the surface rule -- the
    fixture's surface, resolved here, and a historical ESPN row's, resolved in
    ``providers.py`` -- meet in an ``!=`` inside ``scope_values``, so they have
    to come from one table read one way. Two loaders is how "Hard" comes to be
    compared with "hard" and every correctly surfaced observation is dropped.

    None is deliberately not a guess. An unpinned competition filters nothing
    and its samples are scoped exactly as they were before
    ``config/tennis_surface_map.json`` existed -- the same rule
    ``tennis_match_format`` above follows, and for the same reason: inferring a
    surface from a tournament name is how a wrong pin would silently delete
    real observations, which is worse than the leak the file closes.
    """
    return tennis_surface_for_competition(competition)


def _load_market_priors() -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """``config/market_priors.json``, read once, as (pooled, per-venue).

    A metric absent from the file is absent from both dicts, and
    ``shrunk_centre`` then leaves its sample alone. That is the pre-2026-09-02
    behaviour and never an error -- the same "unknown is not degraded" rule
    ``scope_values`` and the entitlement paths already follow. A metric with a
    pooled ``mean`` and no ``home``/``away`` pair keeps the pooled prior at
    every venue, which is the case for every match total, every player market,
    every tennis market, and the football ``*_for`` markets where the venue
    effect was measured and found absent (``fouls_for`` z=-0.6,
    ``offsides_for`` z=+1.3).
    """
    raw = _load_json(_MARKET_PRIORS_PATH).get("priors", {})
    priors: dict[str, float] = {}
    by_venue: dict[tuple[str, str], float] = {}
    # ``priors`` itself may be any JSON value. Checked here rather than trusted,
    # because ``.items()`` on a string is an AttributeError that would abort
    # ANALYZE outright -- and this module's whole contract for a config problem
    # (see ``_load_json``) is to degrade to the behaviour it had before the
    # config existed, never to empty the sheet.
    if not isinstance(raw, dict):
        return priors, by_venue
    for market, block in raw.items():
        if str(market).startswith("_") or not isinstance(block, dict):
            continue
        mean = block.get("mean")
        if not (isinstance(mean, (int, float)) and not isinstance(mean, bool) and mean > 0):
            # No usable pooled prior means no usable venue prior either. A
            # market whose ``mean`` failed validation is a market this file
            # cannot be trusted about, and accepting only its ``home`` value
            # would leave a row shrinking toward a target with no fallback --
            # the away rows of the same market would be unshrunk while the home
            # ones were pulled hard. Measured on a corrupted config: with
            # ``mean: 0`` and ``home: 5.2`` the home centre moved to 4.40 and
            # the away centre stayed at the raw 2.80.
            continue
        priors[str(market)] = float(mean)
        for venue in ("home", "away"):
            value = block.get(venue)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                by_venue[(str(market), venue)] = float(value)
    return priors, by_venue


def market_priors() -> dict[str, float]:
    """``{canonical metric: prior mean}``, pooled over both venues."""
    global _MARKET_PRIORS_CACHE
    with _CONFIG_LOCK:
        if _MARKET_PRIORS_CACHE is None:
            _MARKET_PRIORS_CACHE = _load_market_priors()
        return _MARKET_PRIORS_CACHE[0]


def venue_market_priors() -> dict[tuple[str, str], float]:
    """``{(canonical metric, "home"|"away"): prior mean}``.

    Only the football ``*_for`` markets where the split was measured at
    ``|z| >= 3`` over both slates with the same sign on each, and at least 120
    observations a side. ``config/market_priors.json`` carries the full
    reasoning and the rejected alternative.
    """
    global _MARKET_PRIORS_CACHE
    with _CONFIG_LOCK:
        if _MARKET_PRIORS_CACHE is None:
            _MARKET_PRIORS_CACHE = _load_market_priors()
        return _MARKET_PRIORS_CACHE[1]


# How many notional prior observations a sample is weighed against, as
# ``n / (n + SHRINKAGE_K)``.
#
# Fitted 2026-09-02 against Superbet's own devigged ladder median over 373
# samples of the 2026-09-01 slate -- the only yardstick available that is
# independent of our own sample and known to be calibrated. Median relative
# error of the estimated centre:
#
#     flat sample mean (what shipped)   0.114
#     prior only, sample ignored        0.094
#     n/(n+10)                          0.069
#
# The middle line is the finding. The pipeline's own point estimate was a
# *worse* predictor of where a market sits than a constant, which is the
# textbook symptom of an unshrunk thin sample. That there is an interior
# optimum at all is what says the sample carries real signal; that the optimum
# sits at k=10 against a typical n of 6 says it carries about a third of the
# weight it was being given.
#
# The curve is flat from 8 to 25 (0.095, 0.092, 0.091, 0.090, 0.088, 0.088), so
# nothing here turns on the exact value and 10 is chosen as the round number at
# the near edge -- the least shrinkage that reaches the plateau, because the
# error of trusting the sample too much is the one this pipeline has already
# paid for.
#
# Fitted on two slates, which is the honest limit. Re-fit over a longer window
# before moving it.
SHRINKAGE_K = 10.0


def shrunk_centre(values: list[float], market: str, venue: str | None = None) -> float:
    """The sample's centre, pulled toward its market's prior by ``n/(n+k)``.

    ``venue`` is which side the subject plays on in *tonight's* fixture, and it
    changes only which prior is the target: a home ``corners_for`` row is
    pulled toward 5.25 rather than toward the pooled 4.74, because that is what
    the market averages at home. Measured over both slates by labelling every
    historical observation home or away from bzzoiro's own fixture listings
    (1,852 match-venue pairs, 191 teams): ``shots_for`` +2.59 a game at home
    (z=+8.2), ``shots_on_target_for`` +1.12 (z=+7.6), ``corners_for`` +1.05
    (z=+6.8), ``goals_for`` +0.31 (z=+4.5), and ``cards_for`` **-0.52**
    (z=-6.7) -- the referee home bias, and the opposite sign is what says this
    is an effect and not a fit. ``fouls_for`` and ``offsides_for`` show none
    (z=-0.6, +1.3) and get no venue prior at all.

    Only the *target* moves. The sample stays venue-blind, so a team with eight
    away matches and two at home is still pulled toward the home prior without
    its own observations being re-centred. That is deliberate: re-centring each
    observation would rewrite ``row.mean``, ``row.dispersion`` and
    ``hit_rate``, which are the evidence a reader checks the row against.

    ``venue=None``, or a market with no measured split, uses the pooled prior.
    A match total always does: every match has one home side and one away side,
    so the total has no venue of its own.

    This is the number ``count_model_central`` and ``count_model_bound`` price
    from. Three things deliberately do **not** use it:

    * ``hits``/``sample_size`` and therefore ``wilson_lower_bound`` -- those
      count what actually happened, and an empirical count is not a quantity
      you shrink.
    * ``row.mean`` and ``row.median``, which stay the raw sample's own, because
      they are the evidence a reader checks the row against.
    * ``row.dispersion``, and so ``coupons.ladder_sigma``. That gate asks
      whether the *sample* is describing this fixture at all -- a data-quality
      question about the evidence -- and answering it from an estimate already
      pulled toward the market would be circular: shrinking moves us closer to
      the book by construction, so the gate would quietly stop firing. Measured
      on the 2026-09-01 losers it does exactly that: Sheffield's ladder sigma
      goes from -1.77 to -1.00 and Preston's from -1.33 to -0.28. The diagnostic
      stays on the raw mean; only the price moves.

    Returns the raw mean unchanged when the market has no pinned prior.
    """
    if not values:
        return 0.0
    mean = statistics.fmean(values)
    prior = None
    if venue is not None:
        prior = venue_market_priors().get((market, venue))
    if prior is None:
        prior = market_priors().get(market)
    if prior is None:
        return mean
    n = float(len(values))
    weight = n / (n + SHRINKAGE_K)
    return weight * mean + (1.0 - weight) * prior


def reset_scope_caches() -> None:
    """Forget every cached config document. For tests only.

    The surface and format tables now live in ``providers.py`` -- one table for
    both sides of each comparison -- so their caches are reset there.
    """
    global _OBSERVATION_SCOPE_CACHE, _MARKET_PRIORS_CACHE
    with _CONFIG_LOCK:
        _OBSERVATION_SCOPE_CACHE = None
        _MARKET_PRIORS_CACHE = None
    reset_tennis_surface_cache()
    reset_tennis_match_format_cache()
    reset_tennis_tournament_map_cache()

# STANDARD_MARKET_LINES' "stat" field uses the pre-existing (non-"_total")
# taxonomy; MetricObservation keys use our canonical names (section 5). Two
# tables, because one market stat now addresses two different metrics: the
# match total both sides contributed to, and one team's own contribution.
_MARKET_STAT_TO_CANONICAL = {
    "corners": "corners_total",
    # "Cards Total" prices booking points, not yellows -- see
    # ``providers.card_points``. ``yellow_cards`` stays mapped because the
    # dossier still carries ``cards_total`` for every provider that has only
    # yellows, and a market for it may exist again; nothing in
    # STANDARD_MARKET_LINES points at it today.
    "cards_points": "cards_points_total",
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
    "cards_points": "cards_points_for",
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


CONFLICT_RESOLVED_ADVERSE = "CONFLICT_RESOLVED_ADVERSE"
CONFLICT_ON_LINE = "CONFLICT_ON_LINE"


class HitCount(NamedTuple):
    hits: int
    sample_size: int
    pushes: int
    # Conflicted matches whose providers straddled this line -- one said hit,
    # another said miss -- and which therefore settle nothing.
    conflicts_on_line: int
    # Conflicted matches resolved away from the priced side.
    conflicts_resolved_adverse: int


def count_hits(
    observations: list[ProviderValue], line: float, direction: str
) -> HitCount:
    """``compute_hit_rate`` over observations that may carry a provider conflict.

    Two rules, and they are the whole of Phase 6's first half.

    **Resolve adverse to the priced side.** A match two providers reported
    differently enters the sample as the value that argues *against* the row --
    the maximum for an UNDER, the minimum for an OVER. Not because the higher
    or lower number is more likely right, but because a conflict is a statement
    that we do not know, and a sample that resolves every "do not know" in the
    direction it is being sold is not evidence. The old rule -- ``median_low``,
    which over a pair keeps the smaller -- resolved every conflict toward the
    UNDER, and every card row on the 2026-09-03 slate is an UNDER.

    **A conflict that straddles the line settles nothing.** When one provider's
    figure is a hit and the other's is a miss, the match is neither, and
    counting it as the adverse one would charge the sample for a disagreement
    twice: once by dropping n, once by dropping the rate. It leaves the sample,
    which is visible in ``sample_size``, and is counted so the row can say so.
    """
    hits = pushes = on_line = adverse = 0
    settled = 0
    for pv in observations:
        low, high = pv.conflict_low, pv.conflict_high
        if low is not None and high is not None and low < line < high:
            on_line += 1
            continue
        if low is not None and high is not None:
            value = high if direction == "UNDER" else low
            # Counted whichever way it fell. The flag says "a provider conflict
            # entered this sample and was resolved against you", and that is
            # true of the OVER side too even though the minimum happens to be
            # what ``median_low`` would also have kept.
            adverse += 1
        else:
            value = pv.value
        if value == line:
            pushes += 1
            continue
        settled += 1
        if direction == "OVER" and value > line:
            hits += 1
        elif direction == "UNDER" and value < line:
            hits += 1
    return HitCount(hits, settled, pushes, on_line, adverse)


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


# Markets whose value is a count of discrete events, so a distribution can be
# fitted to a sample of them. Everything else -- possession, expected goals,
# percentages -- is continuous or bounded and gets no model bound.
_COUNT_MARKETS_EXCLUDED = frozenset({*PERCENTAGE_METRICS, "expected_goals_total", "possession"})


def _sample_dispersion(values: list[float]) -> float:
    """Variance to use for a count sample, never below the Poisson floor.

    A count process has variance at least equal to its mean; corners, shots and
    double faults are all overdispersed relative to that in reality. A *sample*
    can nonetheless come out far tighter than its own mean by chance or because
    the provider is serving a smoothed figure -- Torino/Monza's six scoped
    corner observations on 2026-09-01 were {6,6,6,6,7,7}, variance 0.27 against
    a mean of 6.33, and the match returned 16. Trusting that variance would
    hand the row a near-certainty it has not earned, so the mean is the floor.
    """
    mean = statistics.fmean(values)
    observed = statistics.variance(values) if len(values) > 1 else 0.0
    return max(observed, mean)


def _winning_boundary(line: float, direction: str) -> float:
    """The half-integer a count must clear for this bet to settle as a win.

    For the half lines this pipeline mostly prices it is the line itself, and
    this function is the identity. It exists for the whole-number lines
    ``compute_hit_rate`` already anticipates ("tennis totals are not [all .5],
    which is where this bites"): a value exactly on such a line is a **push**,
    which is not a win for either side, and a continuous approximation has no
    atom there to leave out. Reading Phi at the line itself would hand half the
    push mass to the OVER and half to the UNDER, inflating both -- exactly the
    direction that flatters a bet, and invisible because the two would still
    sum to 1.

    UNDER 21.0 wins on 20 or fewer, so its boundary is 20.5. OVER 21.0 wins on
    22 or more, so its boundary is 21.5. At 21.5 both come back to 21.5 and
    nothing changes. Verified against ``compute_hit_rate``'s own push rule in
    ``test_computation_invariants.py`` rather than asserted here.
    """
    if direction == "UNDER":
        return math.ceil(line) - 0.5
    return math.floor(line) + 0.5


def count_model_central(
    values: list[float], line: float, direction: str, centre: float | None = None
) -> float:
    """P(bet wins) at the sample's own centre, with no conservatism added.

    The companion to ``count_model_bound`` and deliberately not a bound: this
    is the sheet's *opinion*, the number to put next to the book's when asking
    whether the two of us actually disagree.

    ``p_low`` cannot answer that question, and 2026-09-01 is the proof. It is a
    lower bound and ``min_acceptable_odds`` stacks a further 5-10% tier margin
    on top of it, so "the price beats my floor by the margin" devigs to "I am
    at least 8-13 points above the book" -- for *every* VALUE row, whatever the
    sample says. A gate on that gap can only be a no-op (above ~0.13) or a
    blanket ban (at or below ~0.09); it cannot discriminate, because most of
    what it measures is our own conservatism rather than the book's view.

    Measured against this instead, the gap means what it says. Sheffield
    United's corners on 2026-09-01 put P(UNDER 4.5) at 0.845 from a sample
    centred on 2.80; Superbet's devigged ladder said 0.341. That is a 50-point
    disagreement about a single outcome, and no threshold has to be tuned to
    see that one of the two is broken.
    """
    if not values:
        return 0.0
    mean = statistics.fmean(values) if centre is None else centre
    spread = _sample_dispersion(values) ** 0.5
    boundary = _winning_boundary(line, direction)
    if spread <= 0:
        inside = boundary > mean if direction == "UNDER" else boundary < mean
        return 1.0 if inside else 0.0
    z = (boundary - mean) / spread
    if direction == "OVER":
        z = -z
    return _standard_normal_cdf(z)


def count_model_bound(
    values: list[float], line: float, direction: str, centre: float | None = None
) -> float:
    """A line-aware lower bound on P(bet wins), fitted to the sample itself.

    This exists because ``wilson_lower_bound`` cannot see the line. For a
    sample that has not missed once, Wilson reads ``hits/n = 1`` and returns
    the same number for *every* line above the sample's maximum: Sheffield
    United's five corner observations {2,4,3,2,3} scored 0.5655085 at 4.5, 5.5,
    6.5 and 7.5 alike on 2026-09-01. ``min_acceptable_odds`` is 1/p_low times a
    tier margin, so it was constant down the ladder too, and the only rung
    whose price cleared it was the one the book priced longest -- 4.5 at 2.70,
    where the book's own devigged ladder implied 34%. The pipeline was not
    finding value on that rung, it was reading the book's risk premium for a
    line near the middle of the distribution as surplus. The match returned 5.

    So the sample is read as a count distribution instead of a coin. The mean
    is estimated from the observations, the variance floored at the mean (see
    ``_sample_dispersion``), and the mean is then pushed 95% of the way against
    the bet -- upward for an UNDER, downward for an OVER -- to charge the row
    for how few observations fixed it. The resulting probability *falls* as the
    line approaches the sample's centre, which is the whole point.

    A normal approximation to the count, not an exact negative binomial: these
    means are between 2 and 25 where the approximation holds well enough, and a
    closed form is auditable from the artifact with a calculator. The
    half-point continuity correction is unnecessary because every line this
    pipeline prices is already a half.

    ``centre`` overrides the sample's own mean, and is how ``shrunk_centre``
    reaches this function. Left None the behaviour is the plain sample, which
    keeps the function readable on its own and every existing caller and test
    unchanged. The spread is deliberately still the *sample's*: shrinkage is a
    claim about where the distribution sits, not about how wide it is.

    Returns 1.0 for an empty sample so the caller's ``min`` is a no-op rather
    than a veto -- no observations is Wilson's problem to price, not this
    function's.
    """
    if not values:
        return 1.0
    n = len(values)
    mean = statistics.fmean(values) if centre is None else centre
    variance = _sample_dispersion(values)
    # Standard error of the mean, from the floored variance.
    se = (variance / n) ** 0.5
    # 1.96 matches wilson_lower_bound's z: both are the same 95% claim.
    if direction == "UNDER":
        centre = mean + 1.96 * se
    else:
        centre = max(mean - 1.96 * se, 0.0)
    spread = variance ** 0.5
    boundary = _winning_boundary(line, direction)
    if spread <= 0:
        inside = boundary > centre if direction == "UNDER" else boundary < centre
        return 1.0 if inside else 0.0
    z = (boundary - centre) / spread
    if direction == "OVER":
        z = -z
    return _standard_normal_cdf(z)


def _standard_normal_cdf(z: float) -> float:
    """Phi(z), via the error function in the stdlib -- no scipy dependency."""
    return 0.5 * (1.0 + math.erf(z / (2.0 ** 0.5)))


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


def scope_values(
    values: list[ProviderValue],
    *,
    surface: str | None = None,
    match_format: str | None = None,
) -> tuple[list[ProviderValue], dict[str, int]]:
    """The observations that may enter a sample, and what was removed.

    Four rules, counted separately because they answer different objections
    and a reader of the sheet needs to know which one fired.

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

    **Surface mismatch**, tennis only. A match on another surface is not a
    trial of tonight's: on 2026-09-02 the sheet's only priced-through row was
    Boulter-Muchova ``aces_total`` OVER 5.5 off a sample whose median was 10.5,
    and every one of Muchova's eight observations was grass while the fixture
    was hard. By surface those two players' hard-court median match total is
    6.0 and 5.0 -- Superbet's 5.5 line -- against 9.0 and 11.0 on grass.
    Requires both sides to be known: the fixture's surface comes from
    ``tennis_surface(competition)`` and the observation's from
    ``ProviderValue.surface``, and if either is None nothing is dropped.

    **Wrong draw**, best-of-five fixtures only. A best-of-three match is not a
    trial of a men's Grand Slam tie: ``total_games``, ``total_sets``, aces and
    double faults all scale with how long the match is allowed to run, and
    "under 3.5 sets, 15 from 15" measured over best-of-three is not a read, it
    is the definition of best-of-three. Until 2026-09-03 this was handled a
    market at a time -- ``suppressed_markets_for`` deleted every length-
    dependent row whenever it could not prove the sample was best-of-five --
    and the whole of ATP came off the sheet, all 21 fixtures on 2026-09-02 and
    all 15 on 2026-09-03, dossiers fully enriched and every row discarded.
    Suppressing the market was the wrong instrument: the objection is to
    *observations*, and the sample holds both kinds. So the tour matches leave
    and the Grand Slam matches stay, exactly as the surface rule already treats
    a grass match in a hard-court sample.

    This rule is the one place where an observation that states nothing is
    dropped rather than kept, and the asymmetry is deliberate. For a surface or
    a competition, unknown is genuinely two-sided -- the match might have been
    on either. For a draw against a best-of-five fixture it is not: four of a
    men's roughly sixty-five events a year are best-of-five, so an unstated
    draw is best-of-three with near-certainty, and the artefact it produces is
    not a slightly wrong number but a tautology priced against Superbet's
    best-of-five ladder (games 30.5-46.5, sets 3.5/4.5). That is the failure
    that put 78 of 82 bettable rows on one sheet and reached the operator as a
    Bet Builder. ``MATCH_FORMAT_UNKNOWN`` is counted separately from
    ``MATCH_FORMAT_MISMATCH`` so the two are never confused for each other:
    the first is a provider we have not taught to say, the second is a match
    that was measurably a different game.

    Only the best-of-five direction is implemented. A fixture pinned BO3 drops
    nothing here, because ``config/tennis_match_format.json`` pins only Grand
    Slams and a Grand Slam observation in a *women's* sample is best-of-three
    too -- the draw is the same, the format is not. The day a men's
    best-of-three event is pinned, this rule needs to know the sample's tour to
    go the other way; espn-tennis already states it per row (``tour``) and
    tennis-abstract per player route.

    An observation missing a competition id or a surface is kept and counted
    against neither of those rules. Not knowing which competition a match
    belonged to is not evidence that it belonged to the wrong one, and dropping
    it would quietly delete every provider that does not publish league ids.

    Returns ``(kept, {reason: count})``. Order is preserved, so every caller
    downstream -- ``_dedup``, ``_one_per_day``, ``_cross_provider_agreement`` --
    sees the sample it would have seen had the removed matches never been
    fetched.
    """
    values = _share_within_a_match(values, "surface")
    values = _share_within_a_match(values, "match_level")
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
        # Surface after season, so a row dropped for being last season is not
        # also counted as a surface mismatch -- the counts are reported to the
        # operator and must partition, not overlap.
        if surface is not None and pv.surface is not None and pv.surface != surface:
            drop("SURFACE_MISMATCH")
            continue
        # Draw last, on the same partition rule: a grass tour match against a
        # hard-court best-of-five tie is counted once, as the surface mismatch
        # it also is, because that is the objection the operator can check
        # against the tournament name in front of them.
        if match_format == "BO5":
            if pv.match_level is None:
                drop("MATCH_FORMAT_UNKNOWN")
                continue
            if pv.match_level != "GRAND_SLAM":
                drop("MATCH_FORMAT_MISMATCH")
                continue
        kept.append(pv)
    return kept, dropped


def _share_within_a_match(
    values: list[ProviderValue], field: str
) -> list[ProviderValue]:
    """Let a match's own properties reach the rows of that match that omit them.

    ``field`` is ``"surface"`` or ``"match_level"``: both are properties of a
    *match*, both are stated by tennis-abstract and not by espn-tennis, and
    both are compared against the fixture's pin inside ``scope_values``. One
    helper rather than two, because a second copy would be a second place for
    the unanimity rule below to be got wrong.

    A rule that needs both sides known cannot fire on a provider that never
    states one, so such a provider is not merely uninformative -- it is
    **immune**. Until 2026-09-02 espn-tennis was exactly that for surface, and
    the filter that removed 145 of tennis-abstract's 522 ``total_games``
    observations removed 0 of ESPN's 478, quietly reweighting the sample toward
    one provider. The draw rule would repeat it exactly: ESPN's own cache
    spells its tournaments "ATP National Bank Open presented by Rogers", so
    the format pin resolves its Grand Slam rows and leaves the rest unstated.

    Giving ESPN rows a surface from their tournament closed most of that and not
    all of it: the surface table pins ten Grand Slam names, and on the deeper
    365-day history that is **16%** of ESPN's cached rows. The rest are events
    like "ATP Rolex Monte-Carlo Masters".

    Pinning those by name is the one thing not to do. tennis-abstract calls it
    "Monte Carlo Masters" and tennis-abstract is the only place a surface can be
    proved from, so a name join would have to be fuzzy -- and its own cache
    contains ``Ostrava`` (Hard, n=36) alongside ``Ostrava CH`` (Clay, n=120).
    A city-level match there pins the wrong surface, and a wrong pin does not
    leak observations in, it silently deletes real ones.

    So nothing is joined by name. Both providers describe the *same matches*,
    identified the way tennis is already identified everywhere else in this
    module -- by opponent, through ``_team_matches`` -- and a surface, like a
    draw, is a property of a match and not of a row. A group where the rows
    that do state the field all state the same value hands it to the rows that
    state none.

    Unanimity is required, and it is what makes repeat meetings safe: two
    matches against one opponent on different surfaces put both into one group,
    the group disagrees, and every row in it keeps whatever it already had.
    Nothing is ever overwritten and no value is ever invented -- the only ones
    that move are ones a provider observed about a match in this sample.

    The residual, unchanged by the draw rule joining this helper and worth
    naming: a group is opponent-wide, not match-wide, so when only *one* of two
    meetings with the same opponent is stated, the other inherits it. The
    obvious tightening -- add the date to the key -- does not work here,
    because tennis-abstract stamps every round of a tournament with the
    tournament's start date (all six of Struff's 2026 Wimbledon rows read
    2026-06-29) while ESPN stamps the match, so the two providers would stop
    grouping altogether and the immunity above would come straight back.
    """
    unknown = [pv for pv in values if getattr(pv, field) is None]
    if not unknown or all(getattr(pv, field) is None for pv in values):
        return values

    groups: list[tuple[str, list[ProviderValue]]] = []
    for pv in values:
        name = _normalize_team_name(pv.opponent)
        if not name:
            continue
        for index, (key, members) in enumerate(groups):
            if _team_matches(name, key):
                members.append(pv)
                break
        else:
            groups.append((name, [pv]))

    resolved: dict[int, str] = {}
    for _key, members in groups:
        stated = {
            value for pv in members if (value := getattr(pv, field)) is not None
        }
        if len(stated) != 1:
            continue
        only = stated.pop()
        for pv in members:
            if getattr(pv, field) is None:
                resolved[id(pv)] = only
    if not resolved:
        return values

    return [
        pv.model_copy(update={field: resolved[id(pv)]})
        if id(pv) in resolved
        else pv
        for pv in values
    ]


def _scope_observation(
    obs: MetricObservation,
    *,
    surface: str | None = None,
    match_format: str | None = None,
) -> tuple[MetricObservation, dict[str, int]]:
    """``scope_values`` over all three buckets of one metric, as one decision.

    The season target is computed across the buckets pooled, not per bucket:
    an h2h meeting from last season must be measured against the *sample's*
    current season, and a bucket holding only stale meetings would otherwise
    declare its own oldest season current and keep everything.

    ``surface`` is the fixture's own surface, not the sample's. Unlike the
    season target it cannot be inferred from the observations -- a sample that
    is entirely grass would declare grass current and keep everything, which
    is exactly the 2026-09-02 defect -- so it is passed in from
    ``tennis_surface(competition)`` or left None.

    ``match_format`` is the fixture's own pinned format, and cannot be inferred
    from the observations for a sharper version of the same reason: a
    best-of-three sample asked to describe itself says best-of-three and keeps
    everything, which is the defect this argument exists to close.
    """
    pooled = [*obs.team_a_l10, *obs.team_b_l10, *obs.h2h]
    kept, dropped = scope_values(pooled, surface=surface, match_format=match_format)
    survivors = {(pv.provider, pv.match_id, pv.value) for pv in kept}

    def surviving(bucket: list[ProviderValue]) -> list[ProviderValue]:
        return [pv for pv in bucket if (pv.provider, pv.match_id, pv.value) in survivors]

    h2h, stale = _drop_stale_h2h(surviving(obs.h2h), pooled)
    if stale:
        dropped["STALE_H2H"] = dropped.get("STALE_H2H", 0) + stale

    return (
        MetricObservation(
            canonical_name=obs.canonical_name,
            team_a_l10=surviving(obs.team_a_l10),
            team_b_l10=surviving(obs.team_b_l10),
            h2h=h2h,
        ),
        dropped,
    )


# How old a head-to-head meeting may be before it stops describing these two
# sides. Fifteen months, which is a whole season plus the part of the next one
# in which the same squads are still recognisable.
#
# It exists because ``STALE_SEASON`` structurally cannot fire here: that rule
# keys on ``competition_id``/``season_id``, and the h2h route reads
# ``head_to_head.recent_matches`` off the fixture, which carries neither. So on
# the 2026-09-03 slate a 15-month-old meeting sat in a "current" sample with no
# rule able to see it -- the Grenal's own 2025-04-20 meeting among them.
#
# Measured against the sample's *newest* observation rather than against the
# fixture's kickoff, for the same reason ``STALE_SEASON`` reads the newest
# observation to decide what "current" means: the dossier carries no date of
# its own, and the newest l10 match is within days of the fixture by
# construction.
#
# H2H only. The l10 buckets are already bounded by the provider window and by
# the season rule, and applying a flat age cutoff to them would silently
# re-open the argument those rules settled.
_MAX_H2H_AGE_DAYS = 456


def _drop_stale_h2h(
    h2h: list[ProviderValue], pooled: list[ProviderValue]
) -> tuple[list[ProviderValue], int]:
    """H2H meetings inside the age cutoff, and how many were removed."""
    if not h2h:
        return h2h, 0
    dates = [_parse_day(pv.match_date) for pv in pooled]
    newest = max((d for d in dates if d is not None), default=None)
    if newest is None:
        return h2h, 0
    cutoff = newest - timedelta(days=_MAX_H2H_AGE_DAYS)
    kept = []
    removed = 0
    for pv in h2h:
        day = _parse_day(pv.match_date)
        # An undated meeting is kept: no date is not evidence of age, and the
        # same "unknown is not degraded" rule the competition and surface
        # filters follow.
        if day is not None and day < cutoff:
            removed += 1
            continue
        kept.append(pv)
    return kept, removed


def _parse_day(raw: str) -> date | None:
    text = (raw or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


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
# Kept as the *check* on the draw rule rather than as the rule itself: no
# scoped best-of-five sample may contain a two-set match unless somebody
# retired, so this is the arithmetic that would catch a bad ``level`` mapping.
_BO5_MIN_SETS = 4.0


def _market_has_a_best_of_five_sample(
    dossier: EventDossierV1,
    canonical: str,
    *,
    surface: str | None = None,
    match_format: str | None = None,
) -> bool:
    """Whether *this market* has any best-of-five observation left to price.

    Asked per market, from that market's own sample. It used to be asked once
    per fixture off ``total_sets`` alone, and that is a defect once the draw
    rule exists rather than the old length heuristic: ``total_sets`` reaches
    the dossier from both tennis providers while aces and double faults come
    from tennis-abstract only, so a fixture whose ``total_sets`` sample is all
    tour tennis suppressed genuine Grand Slam aces observations for no reason
    connected to them. Constructed and confirmed on 2026-09-03: three slam
    aces observations, deleted by a different metric's emptiness.

    The draw is read from ``ProviderValue.match_level`` by ``scope_values`` and
    no longer guessed from match length. What that replaced was a share
    threshold on "four sets or longer", which cannot answer the question asked
    of it: a best-of-five won 3-0 and a best-of-three won 2-1 are both three
    sets. On the 2026-09-03 ATP slate 225 of 474 ``total_sets`` observations
    were exactly three and therefore mute, every one of the 15 fixtures scored
    under the threshold, and ATP came off the sheet in its entirety -- Taylor
    Fritz included, whose six 2026 Grand Slam wins all came in straight sets
    and scored zero.

    Measured on the sample as ``scope_values`` admits it -- same surface, same
    competition pins, same season rule, same draw rule -- because that is the
    sample the rows are priced from. Judged on the raw sample instead, four
    grass Grand Slam matches can stand the gate down while the surface rule
    deletes exactly those four from pricing, and the surviving hard-court tour
    sample meets the best-of-five ladder unguarded: the 2026-09-02 artefact
    reintroduced.

    A market the dossier does not carry answers True. There is nothing to
    suppress and nothing to price; answering False would be a claim about a
    sample that does not exist.
    """
    obs = dossier.metrics.get(canonical)
    if obs is None:
        return True
    kept, _ = scope_values(
        [*obs.team_a_l10, *obs.team_b_l10, *obs.h2h],
        surface=surface,
        match_format=match_format,
    )
    return bool(kept)


# How many *matches* in a sample a second provider has to have reported before
# the sample counts as corroborated.
#
# One is not enough, and it used to be. ``AGREE`` was returned when any single
# cluster held two providers, and downstream ``tier_for_row`` reads AGREE as
# "this sample is corroborated" and hands it CALL -- the top tier, with the
# thinner 1.05 price margin. On 2026-09-01 nineteen samples took AGREE on
# exactly one corroborated match, one of them a tennis ``total_games`` sample
# where espn-tennis overlapped tennis-abstract on 1 match out of 23.
#
# The concentration is the tell: sixteen of those nineteen were ``total_games``
# and three were ``red_cards_total``. Both are metrics where agreement is
# nearly free -- most matches have no red card at all, and the tolerance is
# ``max - min > 1``, so 0 against 1 also passes. A lone agreement on a metric
# whose modal value is zero is not evidence that a provider is reliable.
#
# Two is the same argument this pipeline already makes about sample size,
# applied to corroboration itself: one trial is not a rate. It reclassifies
# 6.9% of that day's AGREE samples to SINGLE_SOURCE, which caps them at LEAN
# rather than removing them.
MIN_CORROBORATED_MATCHES = 2

# What share of a sample a second provider has to have seen before "AGREE" is
# a description of the sample rather than of two matches in it.
#
# ``MIN_CORROBORATED_MATCHES`` above is a floor on the *count* and it is not
# enough on a big sample. On the 2026-09-03 Grenal, AGREE meant 3 of 20 matches
# corroborated -- the field that says so, ``corroborated_matches``, was already
# on the row and the label ignored it -- while ``tier_for_row`` reads AGREE as
# "this sample is corroborated" and hands out CALL. Three matches in twenty is
# not a second measurement of the sample; it is a second measurement of three
# matches.
#
# A half, which is the point at which "corroborated" stops being a claim about
# a minority of the evidence. Below it the sample is ``PARTIAL_AGREE`` and the
# coupon prints the share rather than the word.
MIN_CORROBORATED_SHARE = 0.5


def corroborated_matches(metric: str, observations: list[ProviderValue]) -> int:
    """How many distinct matches in this sample a second provider also reported.

    Counted the same way ``_cross_provider_agreement`` clusters, so the two can
    never disagree about what a corroborated match is.
    """
    by_day: dict[str, list[ProviderValue]] = {}
    for pv in observations:
        by_day.setdefault(_day_key(pv.match_date), []).append(pv)
    count = 0
    for day, day_observations in by_day.items():
        if not day:
            continue
        for cluster in _cluster_by_opponent(day_observations):
            if len({pv.provider for pv in cluster}) >= 2:
                count += 1
    return count


def _cross_provider_agreement(
    metric: str, observations: list[ProviderValue], sample_size: int | None = None
) -> str:
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
    multi_matches = 0
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
            multi_matches += 1
            values = [pv.value for pv in cluster]
            if max(values) - min(values) > threshold:
                return "DISAGREE"

    # ``saw_multi`` alone used to be enough. It is now the *count* that decides,
    # for the reason in MIN_CORROBORATED_MATCHES: one corroborated match out of
    # twenty-three bought the whole sample its top tier.
    #
    # Note the asymmetry that is deliberately kept: DISAGREE still returns on
    # the first conflicting cluster above, because a single provider conflict is
    # a reason to distrust the sample, while a single provider agreement is not
    # a reason to trust it. The permissive direction is the one that needed a
    # floor.
    if saw_multi and multi_matches >= MIN_CORROBORATED_MATCHES:
        # ``AGREE`` is a claim about the *sample*, so it needs a share and not
        # only a count -- see MIN_CORROBORATED_SHARE. ``sample_size`` is the
        # priced sample's own size (one observation per match); absent, the
        # count rule alone decides, which is the pre-2026-09-03 behaviour and
        # the right answer for a caller that cannot say how big the sample was.
        if sample_size and multi_matches / sample_size < MIN_CORROBORATED_SHARE:
            return "PARTIAL_AGREE"
        return "AGREE"
    if saw_single or saw_multi:
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

    **The disagreement survives the collapse.** When the group holds more than
    one value the range is recorded on the representative
    (``conflict_low``/``conflict_high``) so the hit count can resolve it against
    the direction being priced, rather than inheriting whichever way
    ``median_low`` happened to fall. Over a pair -- which is what a conflict
    almost always is -- ``median_low`` keeps the *smaller* value, and that
    favours every UNDER on every conflicted match.

    ``mean``, ``median`` and ``dispersion`` still read this representative's own
    ``value``, unchanged: they are the evidence a reader checks the row
    against, and they must not differ between the OVER and UNDER rows of one
    line.
    """
    values = [pv.value for pv in group]
    consensus = statistics.median_low(values)
    chosen = next(pv for pv in group if pv.value == consensus)
    low, high = min(values), max(values)
    if low == high:
        return chosen
    return chosen.model_copy(update={"conflict_low": low, "conflict_high": high})


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

    The "character for character" claim above was measured on 2026-08-28 and is
    **false in general**; it was re-measured on 2026-09-01 and broke on ten
    opponent pairs. The name orders and middle names it broke on are exactly
    what ``_team_matches`` exists to absorb -- "juncheng shang" / "shang
    juncheng", "coleman wong" / "chak lam coleman wong", "soon woo kwon" /
    "soonwoo kwon" -- but this function used to return the bare normalized
    string, so the matcher was named in the reasoning and never called. Every
    such pair opened a second slot and counted one match as two independent
    trials. ``_tennis_match_keys`` now canonicalizes through the matcher, which
    is why this returns a *normalized* name to be clustered rather than a key.
    """
    return _normalize_team_name(pv.opponent) or ""


def _tennis_match_keys(values: list[ProviderValue]) -> list[str]:
    """``_tennis_match_key`` for a whole bucket, with repeat meetings numbered.

    Numbering is per (provider, opponent): the first Tauson match tennis-abstract
    reports keys to the same slot as the first Tauson match espn-tennis reports,
    so the pair collapses, while a second Tauson match from either provider gets
    its own slot and survives.

    Opponent names are canonicalized through ``_team_matches`` before they
    become slots, the same matcher ``_cluster_by_opponent`` uses for football.
    Without it "shang juncheng" and "juncheng shang" are two slots, and one
    match enters the sample twice -- on 2026-09-01 that happened to nine
    opponent pairs across the tennis slate. Canonicalization is greedy and so
    order-dependent, exactly as ``_cluster_by_opponent`` is.

    One class is still missed: a diminutive against its full given name, where
    the surname matches and nothing else does -- "caty mcnally" against
    "catherine mcnally", which counted Tatjana Maria's 29-game match as two.
    ``_team_matches`` rejects it and so does ``bet.tipsters.matching``'s
    ``_person_score``, which needs the unshared name covered by an *initial*.
    Closing it needs either a nickname table or a fuzzy ratio on the given name,
    and a ratio there would merge the sibling pairs tennis actually has
    (Mirra/Erika Andreeva), so it is left open rather than guessed at.
    """
    seen: dict[tuple[str, str], int] = {}
    canonical: list[str] = []
    keys: list[str] = []
    for pv in values:
        opponent = _tennis_match_key(pv)
        if not opponent:
            keys.append("")
            continue
        for known in canonical:
            if _team_matches(opponent, known):
                opponent = known
                break
        else:
            canonical.append(opponent)
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


# How many observations each *side* of a match-total sample needs before the
# total is a description of the fixture rather than of one participant.
#
# ``sample_size`` alone cannot answer it. A match total pools both teams' last
# tens and their h2h, so an n of 14 can be 3 from one side and 11 from the
# other -- and the 3 is the binding constraint on anything the fixture does
# jointly. On the 2026-09-03 slate 3+11 and 4+4 both read HIGH, which is the
# word this sheet uses for "settled".
#
# Five and two, and five rather than the three the handoff note proposed.
#
# Three does not catch the case the note itself named. Neom-Al-Khaleej and
# Al-Fayha-Al-Kholood both carry 4 observations a side on ``cards_points_total``
# -- the note's own "4+4 reads as settled" -- and ``min(4, 4) >= 3`` reads HIGH.
# Five is not a number chosen to catch them either: it is the number ENRICH
# already uses for the same question. ``data_quality == "READY"`` means the
# primary provider served **at least five matches a side** on all three
# priority metrics (``enrich._compute_readiness``), and that is the condition
# ``tier_for_row`` hands CALL out on. A sheet whose word for "settled" and
# whose tier for "settled" disagreed about how many matches a side that takes
# would be two rules wearing one name.
#
# Two for MEDIUM, which is the floor below which one side is a single trial.
_MIN_SIDE_FOR_HIGH = 5
_MIN_SIDE_FOR_MEDIUM = 2

ONE_SIDED_SAMPLE = "ONE_SIDED_SAMPLE"


def _adverse_values(observations: list[ProviderValue], direction: str) -> list[float]:
    """The sample as numbers, with every provider conflict resolved against
    the side being priced -- the maximum for an UNDER, the minimum for an OVER.

    Identical to ``[pv.value for pv in observations]`` on any sample with no
    conflict, which is the overwhelming majority: on the 2026-09-03 slate
    20,961 of 21,925 rows were SINGLE_SOURCE.
    """
    out: list[float] = []
    for pv in observations:
        low, high = pv.conflict_low, pv.conflict_high
        if low is None or high is None:
            out.append(pv.value)
        else:
            out.append(high if direction == "UNDER" else low)
    return out


def _confidence(
    agreement: str, sample_size: int, side_sizes: tuple[int, int] | None = None
) -> tuple[str, str | None]:
    """``(confidence, why not higher)``. Explicit 1->2->3 evaluation order
    (section 2): DISAGREE or a thin sample is LOW regardless of anything else;
    AGREE/SINGLE_SOURCE/NOT_APPLICABLE all get the same treatment past that
    point, since none of them is itself a quality problem.

    ``side_sizes`` is ``(n_a, n_b)`` for a match total, and None for every
    sample that has only one side to count -- a per-team row and a player prop
    are one participant's history by construction, and asking them for a second
    side would cap every one of them at LOW.
    """
    if agreement == "DISAGREE" or sample_size < 5:
        return "LOW", None
    weakest = min(side_sizes) if side_sizes else None
    if weakest is not None and weakest < _MIN_SIDE_FOR_MEDIUM:
        return "LOW", ONE_SIDED_SAMPLE
    if sample_size >= 8:
        if weakest is not None and weakest < _MIN_SIDE_FOR_HIGH:
            return "MEDIUM", ONE_SIDED_SAMPLE
        return "HIGH", None
    return "MEDIUM", None


# --- the referee ------------------------------------------------------------
#
# The one input to a card line that neither club's history says anything about.
# Measured live 2026-08-30 inside one league: Peter Bankes averages 4.15 yellows
# a match, Michael Oliver 3.10 -- a third of the spread in a cards line, decided
# by a man neither team's last ten mentions.
#
# It enters the *centre* the count model prices from and nothing else, on the
# same rule ``shrunk_centre`` follows: ``row.mean``, ``row.median``,
# ``row.dispersion``, ``hits`` and ``sample_size`` all stay the sample's own,
# because they are the evidence a reader checks the row against.
#
# Match totals only. A referee's average describes a whole match, and halving
# it for a per-team line would invent a number the provider never gave --
# the same restriction ``_referee_flag`` already applies.
#
# **The weight is the handoff note's and is not measured.** ``m / (m + 20)``
# puts a 20-match official at half the centre and a 60-match one at three
# quarters, which is a strong claim about a prior nobody has backtested here.
# It is written as one named constant so the measurement, when it happens, has
# exactly one number to move. The floor of 15 matches is the note's too, and it
# is above ``context_flags._MIN_REFEREE_MATCHES`` (8) on purpose: an average
# good enough to *flag* a row is not good enough to move its price.
_MIN_REFEREE_MATCHES_FOR_BLEND = 15
_REFEREE_BLEND_K = 20.0

_CARD_TOTAL_MARKETS = frozenset({"cards_points_total", "cards_total"})


def _blend_referee(
    centre: float | None,
    canonical: str,
    team_name: str | None,
    dossier: EventDossierV1,
) -> tuple[float | None, str | None]:
    """``(centre, what was blended in)`` for a card match total.

    Returns the centre unchanged, and None, for every other market and for
    every referee below the sample floor.
    """
    if centre is None or team_name is not None or canonical not in _CARD_TOTAL_MARKETS:
        return centre, None
    referee = dossier.referee
    if referee is None or (referee.matches or 0) < _MIN_REFEREE_MATCHES_FOR_BLEND:
        return centre, None
    rate = (
        referee_card_points_per_match(referee)
        if canonical == "cards_points_total"
        else referee.avg_yellow_per_match
    )
    if rate is None:
        return centre, None
    matches = float(referee.matches or 0)
    weight = matches / (matches + _REFEREE_BLEND_K)
    blended = (1.0 - weight) * centre + weight * rate
    note = (
        f"{referee.name or referee.provider_referee_id} averages {rate:.2f}/match "
        f"over {referee.matches} matches, blended at w={weight:.2f}"
    )
    return blended, note


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
    offered_sides: dict[str, frozenset[float]] | None = None,
    sample_excluded: dict[str, int] | None = None,
    venue: str | None = None,
    centre_override: float | None = None,
    side_sizes: tuple[int, int] | None = None,
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
    corroborated = corroborated_matches(canonical, observations)
    agreement = _cross_provider_agreement(canonical, observations, len(independent))
    # Counted over the sample that was actually priced, not over every
    # observation: a caveat on a duplicate report that ``_one_per_day``
    # discarded is a caveat on nothing.
    observation_flags: dict[str, int] = {}
    for pv in independent:
        if pv.quality_flag:
            observation_flags[pv.quality_flag] = observation_flags.get(pv.quality_flag, 0) + 1
    observation_flags = dict(sorted(observation_flags.items()))
    values = [pv.value for pv in independent]
    if not values:
        return []
    mean = statistics.fmean(values)
    median = statistics.median(values)
    sample_mode = min(statistics.multimode(values)) if values else None
    # The spread the count model actually uses: the sample's own standard
    # deviation with the Poisson floor already applied. Reported on the row
    # because every downstream check that has to compare this sample to
    # something else needs a scale to compare *in*, and a difference of "0.3"
    # means nothing until you know whether the metric is half-time goals or
    # total shots. Zero on a percentage market, where no count model is fitted.
    dispersion = (
        0.0 if canonical in _COUNT_MARKETS_EXCLUDED
        else _sample_dispersion(values) ** 0.5
    )
    # The centre the count model prices from, and the only place shrinkage
    # enters. mean/median/dispersion above stay the sample's own; see
    # ``shrunk_centre`` for why the diagnostic must not move with the price.
    # ``centre_override`` is the estimand-framed centre for a tennis match
    # total -- see ``_framed_tennis_total_centre``. It replaces the shrunk
    # pooled mean outright rather than being averaged with it: the pooled mean
    # targets a different quantity, so blending the two would only halve the
    # error instead of removing it.
    #
    # Computed per direction, because a provider conflict is resolved against
    # the side being priced (see ``count_hits``) and the centre is a *pricing*
    # quantity. A conflicted match entering the centre as 6 rather than 8 pulls
    # the centre down, which flatters every UNDER -- and every card row on the
    # 2026-09-03 slate is an UNDER. ``mean``, ``median`` and ``dispersion``
    # stay direction-neutral: they are the evidence a reader checks the row
    # against, and ``dispersion`` additionally feeds ``coupons.ladder_sigma``,
    # which must stay a question about the data and not about the bet.
    centres: dict[str, float | None] = {}
    centre_notes: dict[str, str | None] = {}
    for _direction in ("OVER", "UNDER"):
        if canonical in _COUNT_MARKETS_EXCLUDED:
            _centre = None
        elif centre_override is not None:
            _centre = centre_override
        else:
            _centre = shrunk_centre(
                _adverse_values(independent, _direction), canonical, venue
            )
        centres[_direction], centre_notes[_direction] = _blend_referee(
            _centre, canonical, team_name, dossier
        )

    rows: list[StatsSheetRow] = []
    # Trimming happens here, not at the call site, because it is measured
    # against this sample's own median and nothing upstream has computed one.
    # ``line_limit`` is set only for offer-driven ladders: Superbet posts up to
    # sixteen corner lines where the static grid had seven, and the ones four
    # goals clear of anything the sample ever produced yield 22/22 and a p_low
    # that means nothing.
    for line in select_lines(lines, median=median, limit=line_limit):
        for direction in ("OVER", "UNDER"):
            # A rung the book posts on one side only. ``offered_sides`` is None
            # for the static grid, which claims nothing about availability and
            # is priced both ways exactly as before.
            if offered_sides is not None and float(line) not in offered_sides[direction]:
                continue
            counted = count_hits(independent, float(line), direction)
            hits, sample_size, pushes = counted.hits, counted.sample_size, counted.pushes
            if sample_size == 0:
                continue
            row_flags = dict(observation_flags)
            if counted.conflicts_resolved_adverse:
                row_flags[CONFLICT_RESOLVED_ADVERSE] = counted.conflicts_resolved_adverse
            row_excluded = dict(sorted((sample_excluded or {}).items()))
            if counted.conflicts_on_line:
                row_excluded[CONFLICT_ON_LINE] = counted.conflicts_on_line
            # Two instruments, and the row is only as strong as the weaker.
            # Wilson prices how few trials there were; the count model prices
            # how close the line sits to what those trials actually measured.
            # Neither subsumes the other: Wilson alone cannot tell 4.5 from 7.5
            # on a clean sweep, and the model alone would let a two-observation
            # sample claim a tight distribution. ``min`` never lets a row be
            # more confident than either says, which is the only combination
            # that cannot manufacture certainty out of the pair.
            confidence, confidence_reason = _confidence(
                agreement, sample_size, side_sizes
            )
            empirical = wilson_lower_bound(hits, sample_size)
            centre = centres[direction]
            referee_note = centre_notes[direction]
            if canonical in _COUNT_MARKETS_EXCLUDED:
                p_low = empirical
                p_central = hits / sample_size
            else:
                directed = _adverse_values(independent, direction)
                p_low = min(
                    empirical,
                    count_model_bound(directed, float(line), direction, centre),
                )
                p_central = count_model_central(
                    directed, float(line), direction, centre
                )
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
                p_low=p_low,
                p_central=p_central,
                dispersion=dispersion,
                shrunk_mean=centre,
                centre_note=referee_note,
                venue=venue,
                mean=mean,
                median=median,
                mode=sample_mode,
                sample_min=min(values) if values else None,
                sample_max=max(values) if values else None,
                sources=sources,
                cross_provider_agreement=agreement,
                corroborated_matches=corroborated,
                confidence=confidence,
                confidence_reason=confidence_reason,
                data_quality=dossier.readiness,
                sample_excluded=dict(sorted(row_excluded.items())),
                observation_flags=dict(sorted(row_flags.items())),
            )
            # Context flags read the row's own market/line/direction, so they
            # can only be computed once the row exists; StatsSheetRow is
            # frozen, so the flagged version is a copy, not a mutation.
            flags = context_flags_for_row(row, dossier)
            ceilings = lean_ceilings_for_row(row, dossier)
            update: dict = {}
            if flags:
                update["context_flags"] = flags
            if ceilings:
                update["lean_ceiling_reasons"] = sorted(set(ceilings))
            if update:
                row = row.model_copy(update=update)
            rows.append(row)
    return _mark_model_separated_rungs(rows)


# Ladders where one rung's numbers differ from its neighbour's without a single
# observation between them.
#
# ``count_model_bound`` fixed the 2026-09-01 defect where ``p_low`` was
# *identical* down a ladder above the sample's maximum, and in doing so created
# a quieter one: the rungs are now ordered, but on a sample that never produced
# a value between 7.5 and 8.5 the ordering is the fitted distribution's opinion
# and not a measurement. On the 2026-09-03 slate Tagger's 7.5/8.5/9.5 rungs had
# identical hit counts and three different bars.
#
# Such a row is not deleted -- the model is the best available answer for a line
# the sample straddles -- but it cannot be a CALL, because CALL means the
# evidence settles it and here the evidence is silent about the difference
# between this rung and the next.
#
# Detected on ``(hits, sample_size)`` rather than by scanning the values for a
# gap, because they are the same test: two rungs of one direction with the same
# hit count are the two rungs no observation separates.
RUNG_SEPARATED_BY_MODEL = "RUNG_SEPARATED_BY_MODEL"


def _mark_model_separated_rungs(rows: list[StatsSheetRow]) -> list[StatsSheetRow]:
    """Cap at LEAN every rung a neighbour matches on hits but not on ``p_low``.

    Operates on one sample's rows, which is the only scope where "the next
    rung" means anything: the same market at a different line for the same
    subject, drawn from the same observations.
    """
    by_direction: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_direction.setdefault(row.direction, []).append(index)

    separated: set[int] = set()
    for indices in by_direction.values():
        ordered = sorted(indices, key=lambda i: rows[i].line)
        for left, right in zip(ordered, ordered[1:]):
            a, b = rows[left], rows[right]
            if (a.hits, a.sample_size) != (b.hits, b.sample_size):
                continue
            if a.p_low == b.p_low and a.p_central == b.p_central:
                # Genuinely indistinguishable rows. Nothing is being claimed
                # about the difference between them, so nothing is capped.
                continue
            separated.add(left)
            separated.add(right)

    if not separated:
        return rows
    return [
        row.model_copy(update={
            "lean_ceiling_reasons": sorted(
                {*row.lean_ceiling_reasons, RUNG_SEPARATED_BY_MODEL}
            )
        })
        if index in separated else row
        for index, row in enumerate(rows)
    ]


def _resolve_lines(
    offered: OfferedLines | None,
    *,
    event_id: str,
    market: str,
    static: list[float],
    team_name: str | None = None,
    player_name: str | None = None,
) -> tuple[list[float], int | None, dict[str, frozenset[float]] | None]:
    """``(lines, limit, by_direction)`` for one sample: the book's ladder, or
    the static grid.

    The whole inversion described in ``offered_lines`` lands here. When a
    SUPERBET offer is loaded and carries this exact (event, market, side,
    player), those are the lines that get priced -- because they are the only
    lines the operator can take. Otherwise the static grid, unchanged and
    untrimmed, so a run with no SUPERBET step produces the sheet it always did.

    ``by_direction`` is which side of each rung the book will actually take,
    and is None for the static grid (which makes no claim either way, so both
    sides are priced exactly as they always were). A rung the book quotes
    one-sided is a real thing and not rare -- ``red_cards_total`` 1.5 is
    routinely OVER-only, because "under 1.5 red cards" is a 1.02 shot nobody
    posts -- and pricing the missing side produces a row that cannot be taken
    at any price.
    """
    if offered is not None:
        posted = offered.lines_for(
            event_id=event_id, market=market,
            team_name=team_name, player_name=player_name,
        )
        if posted:
            sides = {
                direction: frozenset(
                    offered.lines_for(
                        event_id=event_id, market=market, team_name=team_name,
                        player_name=player_name, direction=direction,
                    ) or ()
                )
                for direction in ("OVER", "UNDER")
            }
            return (list(posted), MAX_OFFERED_LINES_PER_SAMPLE, sides)
    return (list(static), None, None)


# Which per-participant metric a tennis match total is the sum of.
#
# Only tennis, and only these three, because only here is the identity exact:
# a match's aces are the two players' aces and nothing else. ``total_sets`` has
# no per-player counterpart collected, so it keeps the pooled centre and stays
# exposed to the frame error below -- named here rather than left to be
# rediscovered.
_TENNIS_TOTAL_COMPONENT = {
    "aces_total": "aces_for",
    "double_faults_total": "double_faults_for",
    "total_games": "games_won",
}


def _framed_tennis_total_centre(
    dossier: EventDossierV1,
    canonical: str,
    surface: str | None,
    match_format: str | None = None,
) -> float | None:
    """The centre a tennis match total should be priced from: the two players'
    own rates summed, not the pooled sample's mean.

    ``_independent_match_sample`` pools ``team_a_l10 + team_b_l10 + h2h``, and
    a tennis ``*_total`` observation is *that* player's count plus whoever she
    happened to face (``providers.py`` defines ``aces_total`` as
    ``aces + opponent_aces``). So the pooled sample measures these two players
    plus a draw of third parties who are not on court, and the estimand -- the
    quantity Superbet prices -- is only the first part.

    On 2026-09-03 that shipped the day's rank-one single. Oliynykova-Eala
    ``aces_total`` 1.5 OVER read ``p_low`` 0.705 off a sample whose mean was
    5.23; the two players' own hard-court rates are 1.00 and 1.25, so the
    quantity being priced was **2.25**. The sample's right tail -- a 12 and an
    18 -- was Alycia Parks's and Qinwen Zheng's serving. Neither was playing.
    The tell was on the same sheet: our own ``aces_for`` rows for that fixture
    read ``p_low`` 0.353 and 0.306 and never became candidates, so the sheet
    contradicted itself and the pooled framing won.

    Summing the two per-participant centres also removes a second, independent
    error. The pooled route consults ``market_priors`` for ``aces_total``
    (8.066), which was measured over two ATP-heavy slates -- ATP averages 13.42
    a match against WTA's 5.74 -- and shrinkage pulled a WTA best-of-three
    centre *up* to 6.46, above its own sample mean. The per-participant
    markets carry no pinned prior, so the summed centre is unshrunk and
    tour-clean. A per-tour prior would let shrinkage back in and is the
    follow-up; mixing tours is worse than not shrinking.

    Returns ``(centre, suppress)``.

    ``(None, False)`` means there is nothing to frame from -- another sport, or
    a market with no per-participant counterpart collected -- and the caller
    keeps the pooled centre.

    ``(None, True)`` means the component exists but **one participant has no
    scoped observation at all**, and the market must not be priced. Falling
    back to the pooled centre there is the trap: the pooled sample is *most*
    wrong precisely when a side is unobserved, because then it consists
    entirely of the other player and her opponents. That is not hypothetical --
    it is Badosa-Gauff ``double_faults_total`` on this same slate, where
    ``SURFACE_MISMATCH`` removed all nine of Badosa's clay matches and the
    surviving n=9 was Coco Gauff alone (mean 6.5556 x 9 = 59 = the sum of
    Gauff's own nine values), while the row went on describing a two-player
    total. The first version of this function returned None there and let the
    pooled centre back in, which fixed the headline case and left its twin.
    """
    if dossier.sport != "tennis":
        return None, False
    component = _TENNIS_TOTAL_COMPONENT.get(canonical)
    if component is None:
        return None, False
    obs = dossier.metrics.get(component)
    if obs is None:
        return None, False
    # Scoped exactly as the row is, draw rule included. Both halves of the
    # component pair are length-dependent markets (``aces_for``,
    # ``games_won``), so a centre taken from the unscoped component would be
    # the two players' *tour* rates handed to a row whose own sample is
    # Grand Slam only -- an estimand fix that reintroduces the frame error it
    # exists to remove, one layer down.
    scoped, _ = _scope_observation(
        obs, surface=surface,
        match_format=_format_scope_for(component, match_format),
    )
    centres: list[float] = []
    # Own buckets only. The h2h bucket of a per-participant metric does not
    # record which side the value belongs to, so it cannot be attributed and
    # is left out -- the same reason ``_team_total_rows`` never reads it.
    for bucket in (scoped.team_a_l10, scoped.team_b_l10):
        collapsed = _one_per_day(bucket, dossier.sport)
        if not collapsed:
            return None, True
        centres.append(statistics.fmean(pv.value for pv in collapsed))
    return sum(centres), False


def _format_scope_for(canonical: str, match_format: str | None) -> str | None:
    """The fixture's format, but only for the markets it can object to.

    The draw rule exists because a market's *value scales with match length*,
    so it has no business shrinking a sample for one that does not.
    ``first_serve_pct``, ``break_points_saved_pct`` and the other rates are
    the same quantity in a best-of-three tour match as in a five-set tie, and
    a player's tour season is where nearly all of their observations live: on
    the 2026-09-03 ATP slate, scoping those to Grand Slams as well would have
    taken samples of 29-37 matches down to single digits to no purpose.

    So the two halves of the tennis draw rule are addressed to the same set,
    ``_TENNIS_LENGTH_DEPENDENT_MARKETS`` -- the markets ``suppressed_markets_for``
    withholds when there is no best-of-five sample, and the markets whose
    sample this scopes when there is one.
    """
    if canonical in _TENNIS_LENGTH_DEPENDENT_MARKETS:
        return match_format
    return None


def _side_sizes(obs, sport: str) -> tuple[int, int]:
    """How many independent observations each participant contributes.

    Collapsed per bucket the same way the pooled sample is, so the two numbers
    add up to something comparable to ``sample_size`` -- the h2h bucket is
    deliberately not counted on either side, because a meeting between these
    two describes both of them and attributing it to one would flatter the
    thinner side, which is the exact thing this measures.
    """
    return (
        len(_one_per_day(list(obs.team_a_l10), sport)),
        len(_one_per_day(list(obs.team_b_l10), sport)),
    )


def _match_total_rows(
    dossier: EventDossierV1,
    offered: OfferedLines | None = None,
    *,
    suppressed_markets: frozenset[str] = frozenset(),
    surface: str | None = None,
    match_format: str | None = None,
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
        framed_centre, one_sided = _framed_tennis_total_centre(
            dossier, canonical, surface, match_format
        )
        # A tennis total one of whose participants is unobserved is not a
        # thinner row, it is a row about somebody else. Dropped rather than
        # priced off the pooled sample; see ``_framed_tennis_total_centre``.
        if one_sided:
            continue
        obs, sample_excluded = _scope_observation(
            obs, surface=surface,
            match_format=_format_scope_for(canonical, match_format),
        )
        lines, limit, offered_sides = _resolve_lines(
            offered, event_id=dossier.event_id, market=canonical,
            static=market_def["lines"],
        )
        rows.extend(
            _rows_for_sample(
                dossier=dossier,
                canonical=canonical,
                lines=lines,
                line_limit=limit,
                offered_sides=offered_sides,
                observations=_all_values(obs),
                independent=_independent_match_sample(
                    obs, dossier.team_a_name, dossier.team_b_name, dossier.sport
                ),
                sample_excluded=sample_excluded,
                centre_override=framed_centre,
                side_sizes=_side_sizes(obs, dossier.sport),
            )
        )
    return rows


def _team_total_rows(
    dossier: EventDossierV1,
    offered: OfferedLines | None = None,
    *,
    suppressed_markets: frozenset[str] = frozenset(),
    surface: str | None = None,
    match_format: str | None = None,
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
        # ``venue`` is which side this team plays on *tonight*, not which side
        # its historical observations were on: football's team_a is always home
        # and team_b always away (``enrich._side_names``), and it selects the
        # shrinkage target only -- see ``shrunk_centre``. Tennis reaches this
        # loop too and passes a venue that no tennis market has a prior for, so
        # it falls back to the pooled one; naming the side there would be
        # meaningless rather than wrong.
        for raw_bucket, team_name, venue in (
            (obs.team_a_l10, dossier.team_a_name, "home"),
            (obs.team_b_l10, dossier.team_b_name, "away"),
        ):
            if not raw_bucket or not team_name:
                continue
            # Scoped per bucket, not pooled: a per-team sample *is* one bucket,
            # so this team's own newest season is the right target for it. The
            # two sides are never merged here (see the docstring) and must not
            # be merged by the scope filter either -- one side's cup run would
            # otherwise decide what counts as current for the other.
            bucket, sample_excluded = scope_values(
                raw_bucket, surface=surface,
                match_format=_format_scope_for(canonical, match_format),
            )
            if not bucket:
                continue
            lines, limit, offered_sides = _resolve_lines(
                offered, event_id=dossier.event_id, market=canonical,
                static=market_def["lines"], team_name=team_name,
            )
            rows.extend(
                _rows_for_sample(
                    dossier=dossier,
                    canonical=canonical,
                    lines=lines,
                    line_limit=limit,
                    offered_sides=offered_sides,
                    observations=_dedup(bucket),
                    independent=_one_per_day(bucket, dossier.sport),
                    team_name=team_name,
                    sample_excluded=sample_excluded,
                    venue=venue if dossier.sport == "football" else None,
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
    surface: str | None = None,
    match_format: str | None = None,
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
            l10, sample_excluded = scope_values(
                observation.l10, surface=surface,
                match_format=_format_scope_for(canonical, match_format),
            )
            if not l10:
                continue
            lines, limit, offered_sides = _resolve_lines(
                offered, event_id=dossier.event_id, market=canonical,
                static=market_def["lines"], player_name=observation.player_name,
            )
            rows.extend(
                _rows_for_sample(
                    dossier=dossier,
                    canonical=canonical,
                    lines=lines,
                    line_limit=limit,
                    offered_sides=offered_sides,
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

    What changed on 2026-09-03 is *when* it fires, not what it does. The
    best-of-three observations are now removed from the sample by
    ``scope_values``, so this function no longer asks "is the sample mostly
    best-of-five" -- a question the data could not answer -- but, market by
    market, "is there any best-of-five sample left". Fixtures whose Grand Slam
    history is empty or unfetched still suppress, and that is the honest answer
    for them; the fifteen ATP ties that suppressed on a full nine-metric
    dossier were not.

    Market by market, and not once per fixture, because the two tennis
    providers do not cover the same markets: ``total_sets`` and ``total_games``
    arrive from both, aces and double faults from tennis-abstract alone. Asked
    off ``total_sets`` for the whole fixture -- which is what it did until this
    was constructed and confirmed -- a fixture whose set-count sample happened
    to be all tour tennis deleted three genuine Grand Slam aces observations
    for a reason that had nothing to do with aces.

    Both halves must still be known for the gate to fire. An unpinned
    competition (``tennis_match_format`` returns None) suppresses nothing and
    scopes nothing.

    Belt on top of braces, since the scoping does the real work: an empty
    scoped sample already emits no rows, so this suppresses nothing that would
    otherwise appear. It stays because the contract above -- a tautology is not
    weak evidence, it is not evidence -- should be stated where it can be
    tested, rather than left to emerge from ``_rows_for_sample`` declining to
    iterate an empty list.
    """
    if dossier.sport != "tennis":
        return frozenset()
    match_format = tennis_match_format(competition)
    if match_format != "BO5":
        return frozenset()
    surface = tennis_surface(competition)
    return frozenset(
        market
        for market in _TENNIS_LENGTH_DEPENDENT_MARKETS
        if not _market_has_a_best_of_five_sample(
            dossier, market, surface=surface, match_format=match_format
        )
    )


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
    # Football never pins a surface or a format, so both are None for every
    # football fixture and both rules inside ``scope_values`` stay inert there.
    surface = tennis_surface(competition) if dossier.sport == "tennis" else None
    match_format = (
        tennis_match_format(competition) if dossier.sport == "tennis" else None
    )
    scoping = {"surface": surface, "match_format": match_format}
    return [
        *_match_total_rows(dossier, offered, suppressed_markets=suppressed, **scoping),
        *_team_total_rows(dossier, offered, suppressed_markets=suppressed, **scoping),
        *_player_prop_rows(dossier, offered, suppressed_markets=suppressed, **scoping),
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


def best_of_five_suppression_report(
    dossier_list: EventDossierListV1,
    competitions: Mapping[str, str] | None = None,
) -> dict:
    """Why the length-dependent tennis markets are missing, when they are.

    A suppressed market emits no row, and a row is the only place
    ``sample_excluded`` is reported -- so the reasons for the largest deletion
    this pipeline performs were, until now, unobservable. The operator saw
    silence, and silence reads as "priced it, not worth it" rather than "never
    looked". That is the same fault the result-market work fixed on the other
    side of the sheet, and it is worth more here: on 2026-09-02 and -03 it hid
    the entire men's slate.

    It also distinguishes the two ways a fixture can come back empty, which
    call for opposite responses:

    * ``MATCH_FORMAT_UNKNOWN`` dominating means the dossier predates
      ``ProviderValue.match_level`` -- the draw was never recorded, so every
      observation is unplaceable. Re-run ENRICH; ANALYZE alone cannot recover
      it, because the field is written at ingest.
    * ``MATCH_FORMAT_MISMATCH`` dominating means the sample was fetched and is
      genuinely best-of-three. Nothing to fix; that fixture has no Grand Slam
      history inside the observation window.

    Counted per (fixture, market) pair, with the observation-level reasons
    pooled, because that is the grain the decision is taken at.
    """
    lookup = competitions or {}
    reasons: dict[str, int] = {}
    pairs = 0
    fixtures: set[str] = set()
    unknown_dominated = 0
    for dossier in dossier_list.dossiers:
        if dossier.sport != "tennis":
            continue
        competition = lookup.get(dossier.event_id)
        suppressed = suppressed_markets_for(dossier, competition)
        if not suppressed:
            continue
        surface = tennis_surface(competition)
        match_format = tennis_match_format(competition)
        fixture_reasons: dict[str, int] = {}
        for market in sorted(suppressed):
            obs = dossier.metrics.get(market)
            if obs is None:
                continue
            pairs += 1
            fixtures.add(dossier.event_id)
            _, dropped = scope_values(
                [*obs.team_a_l10, *obs.team_b_l10, *obs.h2h],
                surface=surface,
                match_format=_format_scope_for(market, match_format),
            )
            for reason, count in dropped.items():
                reasons[reason] = reasons.get(reason, 0) + count
                fixture_reasons[reason] = fixture_reasons.get(reason, 0) + count
        if fixture_reasons and max(fixture_reasons, key=fixture_reasons.get) == (
            "MATCH_FORMAT_UNKNOWN"
        ):
            unknown_dominated += 1
    return {
        "fixtures": len(fixtures),
        "markets": pairs,
        "by_reason": dict(sorted(reasons.items())),
        "fixtures_mostly_unknown_draw": unknown_dominated,
    }


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
