"""Rank legs by how often they actually happen, not by how they price.

The coupon asks "is this worth its price". Measured on the 6,187 rows that
carry a real Superbet price, the model loses that argument to the price itself
(Brier 0.2067 against 0.1845), and ranking by surplus actively selects the
rows where it loses worst: past a model-minus-price gap of +0.10 the realised
rate falls BELOW a coin flip while the model claims 0.61 and upward.

This module asks the other question. Over 1,868,474 settled rows the model is
calibrated to within 0.3 pp everywhere up to about 0.90 — when it says 0.88 it
means 0.88. An operator who has decided to accept a shaded price is asking
exactly that, and it is a question the model can answer.

Two things this must never do, because both are how a confidence view turns
back into the coupon it replaced:

  - quote its own point estimate. Every number here is the LOWER bound of the
    measured realised rate, so a thin bucket reads as less confident, not as
    more precise.
  - claim certainty. The fitted curve tops out at 0.9202: the buckets
    0.900-0.925 and 0.925-0.950 both realise 0.9083, which is the model saying
    it has run out of resolution. A leg presented at 0.98 would be a lie of
    about seven points.
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.config import config_path
from bet.sofa.engine import NORMAL_NON_COUNT_METRICS, uses_empirical_frequency
from bet.sofa.epochs import STATS_ONLY_FROM_UTC
from bet.sofa.players import is_player_metric

# Resolved against the repo, not the working directory: run from anywhere
# else a relative path failed (or read another checkout's curves).
# SOFA_CONFIG_DIR (bet.sofa.config.config_dir) moves it for a scratch replay.
DEFAULT_CALIBRATION = config_path("sofa_confidence_calibration.json")

# The ceiling for an empirical / non-count market with no curve of its own
# when no empirical market has a curve either. Below the pool's 0.80-0.825
# bucket: with nothing measured, the unmeasured market gets less room, not more.
UNPROVEN_MARKET_CEILING = 0.80

# The measured disagreement ceiling. On the 6,187 rows carrying a real price,
# grouped by how far the model sat ABOVE the devigged market:
#
#     model - price     n     model says   realised
#     +0.00-0.05      1114      0.546       0.514
#     +0.05-0.10       780      0.595       0.530
#     +0.10-0.15       441      0.609       0.444
#     +0.20-0.30       255      0.677       0.400
#     +0.30 and up     328      0.800       0.451
#
# Past +0.10 the realised rate drops BELOW a coin flip while the model's claim
# keeps climbing. A leg where we say 0.81 and the book says 0.05 is not a
# shaded price being offered to us, it is our own error being offered to us.
# Accepting the book's shading and ignoring this are different decisions.
MAX_DISAGREEMENT = 0.10

# Top of the catch-all bottom bucket of every curve (fit_confidence.EDGES[1]).
# That bucket pools every claim from 0.00 to 0.60, so its realised rate is an
# average over rows the model rates anywhere from "never" to "slightly likely"
# and says nothing about any one of them. A leg whose own claim sits in it is
# refused whatever the bucket's lower bound says.
#
# Found 2026-10-03 (night review of the admitted player props): the refit's
# `player_offsides_for|UNDER` bucket 0.000-0.600 has realised_lo95 0.7215 -
# above both profiles' floors - so an UNDER offsides row the model put at
# p = 0.05 would have printed at confidence 0.72. Superbet quotes player props
# OVER only, so the 11-18 such sheet rows a day (10-01..10-03) were unpriced
# and it never happened; no other curve's bottom bucket reaches 0.60, so the
# gate changes no leg of any sheet 09-20..10-03.
CATCH_ALL_BUCKET_TOP = 0.60


def reads_catch_all_bucket(p_central: float) -> bool:
    """Is this claim inside the curves' catch-all bottom bucket?"""
    return p_central < CATCH_ALL_BUCKET_TOP

# Markets that are a FUNCTION of two sides rather than a count of one thing.
# They carry 2-252 settled rows each — both_over_shots has 26, both_over_fouls
# 18 — so no market-specific curve can be fitted, and the pooled curve they
# would otherwise fall back to was measured on 1.87M single-quantity counts.
# Nothing in the artifacts can check them either: no per-side sample reaches a
# joint, which is why every one of them also carries ONE_SIDED_LADDER and
# NO_MARKET_MARGINAL on the sheet. A confidence view exists to say how often a
# thing happens; for these the honest answer is that we have not measured it.
DERIVED_PREFIXES = ("both_over_", "handicap_", "most_")


def is_derived(market: str) -> bool:
    """True for a joint/comparative market. See DERIVED_PREFIXES."""
    return market.startswith(DERIVED_PREFIXES)

# Independence holds ACROSS quantities and fails WITHIN one, and the
# difference decides whether multiplying leg probabilities is arithmetic or
# fiction. Measured on 608 specific rung pairs out of the settled cache —
# conditioned on the exact (market, line, direction), because pooling OVER and
# UNDER across lines forces lambda to 1.000 by symmetry and hides everything:
#
#     goals_for   x goals_total      84 pairs   median lambda 2.165 (max 8.37)
#     fouls_for   x fouls_total      71 pairs   median lambda 1.455
#     corners_for x corners_total    72 pairs   median lambda 1.377
#     corners_total x goals_for      27 pairs   median lambda 1.017
#     corners_for x fouls_for        78 pairs   median lambda 0.964
#     corners_total x fouls_total    79 pairs   median lambda 0.964
#
# A team's goals are part of the total goals; its corners are part of the
# total corners. Those are one quantity counted twice, and a builder that
# multiplies them tells the operator he holds four independent legs when he
# holds two. Across different quantities lambda sits in 0.95-1.02 and the
# product is right.
#
# So a builder takes at most one leg per QUANTITY family, not per market.
QUANTITY_FAMILIES: dict[str, str] = {}
for _family, _prefixes in {
    "corners": ("corners_",),
    "fouls": ("fouls_", "player_fouls_"),
    "cards": ("cards_points_", "most_cards_points"),
    # F54. A player's shots are part of his team's shots are part of the
    # match's. Without these prefixes a player row would be its own family
    # (the fallback in `quantity_family`) and a builder could multiply
    # "Romarinho over 1.5 shots" by "Criciuma over 11.5 shots" as though they
    # were two independent facts. They are one fact counted twice, which is
    # the exact error this table exists to prevent.
    "shots": (
        "shots_",
        "shots_on_target_",
        "player_shots_",
        "player_shots_on_target_",
        # A save is the opponent's shot on target that did not go in, a goal
        # kick mostly the opponent's shot that went wide: the shots family
        # seen from the other goal (2026-09-25 coverage audit).
        "saves_",
        "goal_kicks_",
    ),
    # An assist is a goal seen from one pass earlier: it cannot happen without
    # the goal, so it is not independent of the scoring family.
    "goals": ("goals_", "player_assists_"),
    "offsides": ("offsides_", "player_offsides_"),
    "throw_ins": ("throw_ins_",),
    # An interception is a defensive action of the same kind as a tackle
    # (both are the team's ball-winning count); one family, conservatively.
    "tackles": ("tackles_", "player_tackles_", "player_interceptions_"),
    # A tiebreak IS a 13-game set, and a match that reaches one is a long
    # match: the same quantity as games and sets, as get_mechanism_family has
    # always said ("tennis_length"). Absent here, `tiebreaks_total` became a
    # family of its own the day CONFIDENCE stopped refusing it (2026-09-23),
    # and a builder could multiply it with a games leg as if independent.
    "games": ("games_", "handicap_games", "sets_", "tiebreaks_"),
    "aces": ("aces_",),
    "double_faults": ("double_faults_",),
}.items():
    for _p in _prefixes:
        QUANTITY_FAMILIES[_p] = _family


# The markets added by the 2026-09-25 coverage audit (metrics.py, "Second
# halves and the remaining"). None has a settled row yet, and without this
# each would borrow the football pool - 74k rows of goals and corners - and
# could reach the PDF on the next rebuild priced by a normal nobody measured
# on it. Refused until fit_confidence gives the market a curve of its own;
# the guard then lapses by itself, so it needs no removal. The full-match
# saves / throw-in / goal-kick / tackle markets get that curve from the cache
# replay (calibrate_from_cache), as every existing curve did. The per-half
# ones get it only from live SETTLE, unless a refit replays the halves
# (prepare_refit rebuild-cache-rows --with-halves, opt-in since 2026-10-04):
# then every per-half market here has a replayed curve and its guard lapses -
# an operator decision taken knowingly at that refit, not a side effect.
# Football player props (players.PLAYER_METRICS, listed here to keep this
# module free of that import; test_player_markets checks the two agree).
PLAYER_PROP_MARKETS = frozenset(
    {
        "player_shots_for",
        "player_shots_on_target_for",
        "player_assists_for",
        "player_fouls_for",
        "player_tackles_for",
        "player_interceptions_for",
        "player_offsides_for",
    }
)

AWAITING_OWN_CURVE = frozenset(
    f"{base}_{suffix}"
    for base in (
        "fouls_2h", "shots_2h", "shots_on_target_2h", "offsides_1h",
        "offsides_2h", "saves", "saves_1h", "throw_ins", "throw_ins_1h",
        "throw_ins_2h", "goal_kicks", "goal_kicks_1h", "goal_kicks_2h", "tackles",
    )
    for suffix in ("total", "for")
) | frozenset(
    # Football player props (players.PLAYER_METRICS, listed here to keep this
    # module free of that import; test_player_markets checks the two agree).
    # Measured 2026-09-29 on 3,509 settled player rows, every one priced from
    # "pooled:football": in the band that became PDF Bet Builder legs
    # (confidence >= 0.70, n=428) the pool claimed 0.776 and the rows
    # realised 0.624, ROI -22.8% at Superbet's one-sided prices; shots OVER
    # 0.430 claimed vs 0.317, on target 0.383 vs 0.236, assists 0.326 vs
    # 0.083. The pool is not a measurement of these markets, so they wait for
    # their own curve like every market above - and they had reached the PDF
    # as builder legs on 09-26..09-29 (1-3 a day).
    PLAYER_PROP_MARKETS
) | frozenset(
    # Tennis per-set serve markets (TENNIS_PER_SET_SERVE below). Measured
    # 2026-09-30 by sofa-verifier and re-counted from sofa_settled_row: since
    # the 09-24 model change, rows at p_central >= 0.70 realised 149/253 =
    # 0.589 against 0.777 claimed (devigged price 0.53); the three printed on
    # 09-30's coupon, 33/57 = 0.579. They had no curve of their own and read
    # the tennis pool, which is games markets - the player-props failure again.
    # The per-set GAMES markets have their own curves and realise as claimed
    # (0.766 at 0.75), so they are not here.
    f"{stat}_set{n}_{suffix}"
    for stat in ("aces", "double_faults", "serve_points")
    for n in (1, 2)
    for suffix in ("for", "total")
) | frozenset(
    # Full-match serve points (TENNIS_SERVE_POINTS below): no curve of their
    # own either, and the same read of the tennis pool. Re-counted
    # 2026-09-30, rows since 09-24 at p_central >= 0.70: serve_points_for
    # 15/31 = 0.484 against 0.782 claimed, serve_points_total 8/12. The
    # full-match aces / double faults have their own curves (20k+ rows each)
    # and stay.
    {"serve_points_for", "serve_points_total"}
)
TENNIS_SERVE_POINTS = frozenset({"serve_points_for", "serve_points_total"})
TENNIS_PER_SET_SERVE = frozenset(
    f"{stat}_set{n}_{suffix}"
    for stat in ("aces", "double_faults", "serve_points")
    for n in (1, 2)
    for suffix in ("for", "total")
)
# Tennis per-set GAMES markets. They have curves of their own, and the
# 2026-10-02 refit candidate gave them buckets up to 0.80-0.925 where the
# shipped curves stopped at 0.60-0.70 - out of sample by date the new curves
# overclaimed 2-3 pp, and the holes inside their range, read from the tennis
# pool (games_total / games_won_for shaped), overclaimed more. They printed
# only in the WARIANT of 09-23..09-25 (pooled:tennis, 157 legs), never since.
# A curve is not an admission: see Calibration.admitted_tennis_set_markets.
TENNIS_SET_GAMES = frozenset(
    {"games_set1_total", "games_set2_total", "games_won_set1_for",
     "games_won_set2_for"}
)
# Every tennis per-set market. None may borrow the tennis pool - neither
# above nor inside its own measured range (Calibration.realised): the pool is
# full-match markets, a set is a different quantity.
TENNIS_PER_SET = TENNIS_PER_SET_SERVE | TENNIS_SET_GAMES


def quantity_family(market: str) -> str:
    """The underlying quantity a market counts. See QUANTITY_FAMILIES.

    Falls back to the market's own name, so an unmapped market is treated as
    its own family and can still combine — never silently merged into another.
    """
    best = ""
    family = market
    for prefix, fam in QUANTITY_FAMILIES.items():
        if market.startswith(prefix) and len(prefix) > len(best):
            best, family = prefix, fam
    return family


# ---------------------------------------------------------------------------
# Gates added 2026-09-20, after a row-by-row review of that day's coupon.
# Each one is here because a specific leg on a built coupon failed it.
# ---------------------------------------------------------------------------

# The fitted curve tops out at 0.9202 (see the module docstring: the
# 0.900-0.925 and 0.925-0.950 buckets both realise 0.9083, which is the model
# saying it has run out of resolution). So the highest probability any leg is
# permitted to carry is 0.9202, and a leg priced below 1/0.9202 CANNOT have
# positive expected value under this curve — not because of the fixture, but
# because of the ceiling.
#
# `MIN_ODDS = 1.01` sat 0.077 below that. On the 2026-09-20 coupon it let 8
# legs through in 8 of 14 slips; dropping each one raised its slip's EV, in
# every case (Londrina +0.004 -> +0.097).
CONFIDENCE_CEILING = 0.9202
MIN_ODDS_FOR_CEILING = 1.0 / CONFIDENCE_CEILING

# A builder leg is built on a sample; under ten observations the mean is not
# yet a centre. The sheet's own floor is five, which is right for *reporting* a
# row and too thin for *staking* a multiplied one.
MIN_BUILDER_SAMPLE = 10

# A sample reaching back far enough describes a different squad under a
# different coach. Set to 120 days on 2026-09-20 by reasoning about the
# transfer window, then **measured** the next hour against the 5,220 settled
# legs of 2026-09-19 and moved, because the reasoning was wrong about where
# the effect sits:
#
#     oldest obs.      n    realised   declared    diff      ROI
#       <= 60d        913     0.878      0.858    +0.020    -3.0%
#       61-90d        446     0.877      0.861    +0.016    -3.8%
#       91-120d       695     0.847      0.857    -0.010    -6.6%
#      121-180d      3062     0.874      0.856    +0.018    -3.8%
#        > 180d       104     0.817      0.856    -0.039    -9.7%
#
# There is no degradation out to 180 days — the 121-180d band performs like
# the freshest one. A 120-day cut would have removed 60 of the 83 legs on
# that day's coupon while catching 6 of its 9 losses, a worse loss rate than
# the coupon's own. The effect only appears past 180 days, and even there
# n = 104, so this is a weak guard on purpose rather than a confident one.
MAX_BUILDER_SAMPLE_AGE_DAYS = 180


# How much of the ladder's price may be the bookmaker's own margin before the
# leg is called robbery and refused.
#
# Ranking legs by `leg_ev` is measured to be INVERTED, and the reason is
# structural rather than statistical. `confidence` is a step function: every
# leg landing in the same calibration bucket is handed the same number. So
# within a bucket `leg_ev = confidence * odds - 1` is a strictly increasing
# function of the price alone, and ranking by it ranks by "longest price in
# this bucket" — which is the book telling us the event is less likely than
# its bucket-mates. Measured inside each bucket, the longest-priced third
# hits less often than the shortest-priced third, every time, and the gap
# widens as the bucket rises:
#
#     bucket    n     short third    long third
#     0.811    527       0.817         0.794
#     0.836    456       0.875         0.822
#     0.858    449       0.899         0.779
#     0.884    354       0.924         0.847
#     0.906    291       0.928         0.825
#
# The devigged market price also beats our own curve outright (Brier 0.10880
# against 0.11161, on a constant-0.871 baseline of 0.11267).
#
# So singles are ranked by `confidence` and filtered on the ladder's margin
# instead. The threshold is the one place the outcomes separate: below 10.5%
# the return is flat, above it it falls by about two points.
#
#     ladder margin      n      hit      ROI
#     <= 8.0%          1683    0.905    -3.55%
#     8.0 - 9.0%       2411    0.854    -3.55%
#     9.0 - 10.5%       102    0.843    -3.38%
#     > 10.5%          1089    0.857    -5.69%
#
# Read all of the above as ONE slate: 5,220 of the 5,285 settled legs behind
# these tables are 2026-09-19. The mechanism is certain because it follows
# from the code; the magnitudes are not, and this constant should be refitted
# once a second day of legs has settled.
#
# Re-measured 2026-09-26 on the settled confidence legs of 22-25.09, and now
# re-measured every morning in audit_settlement section 7g:
#
#     legs of            margin          n     ROI
#     the coupon       <= 10.5%         78    -4.6%
#                     10.5 - 15%        50   -12.8%   (+32.6% on 09-25 alone)
#     the variant      <= 10.5%        570    -3.2%
#                     10.5 - 15%       100    -2.0%
#
# 09-25 on its own said "loosen" (the five legs this kept off the PDF all won:
# -0.1% would have been +6.4%); the coupon's four days say keep, the variant's
# three show no difference. Not enough to move it either way, so it stays.
MAX_OVERROUND = 0.105


def overround(over_odds: float | None, under_odds: float | None) -> float | None:
    """The bookmaker's margin on a two-sided rung, or None if it is one-sided.

    A one-sided rung cannot be measured — the missing side is exactly where
    the margin would show — so it is refused rather than assumed fair.
    """
    if not over_odds or not under_odds or over_odds <= 1.0 or under_odds <= 1.0:
        return None
    return 1.0 / over_odds + 1.0 / under_odds - 1.0


def single_is_fairly_priced(leg_overround: float | None) -> bool:
    """Is this leg's ladder cheap enough to be worth showing on its own?"""
    return leg_overround is not None and leg_overround <= MAX_OVERROUND


def has_unreachable_bar_note(notes: object) -> bool:
    """Did SHEET record that NO sample could clear this row's price?

    "This row missed the bar" and "no sample of this size could have cleared
    it" are different statements, and CONFIDENCE is only entitled to ignore
    the first. It deliberately does not ask COUPON's question — 9,867 of the
    2026-09-23 sheet's 10,917 rows are BELOW_BAR, and refusing them all would
    collapse this stage into the one it exists to complement.

    UNREACHABLE_BAR is the other kind: the offered price is unjustifiable at
    this sample size whatever the sample showed, so no confidence number can
    rescue it. run_coupon already drops these rows from its near-misses list
    on the same reasoning.

    On 2026-09-23 COUPON selected zero VALUE singles, the whole PDF therefore
    came from CONFIDENCE, and 29 of the 30 printed singles carried this note.
    """
    if not isinstance(notes, (list, tuple)):
        return False
    return any(str(note).startswith("UNREACHABLE_BAR") for note in notes)


# Match classes with a calibration curve of their own (Calibration.by_class).
CLASS_WOMEN = "women"
# Tennis team cups and exhibitions. tennis_rating.tier_group files them under
# TOUR, but a regional Davis Cup group is not a tour event. Measured
# 2026-09-30 on live settled rows at p_central >= 0.70: 236 rows / 26
# matches claimed 0.802 and realised 0.669 (ROI -8.2%), against ITF/CH
# 0.812 / 0.788. Its legs read only a curve fitted on its own rows
# (fit_confidence --classes-only) and are refused wherever it has none.
CLASS_TENNIS_TEAM_CUP = "tennis_team_cup"
# Women's tennis. Measured 2026-09-30 on the cache replay at p_central >=
# 0.70: women realised 0.5-1 pp further below the claim than men in every
# bucket (0.80-0.85: -3.5 pp on 8,558 rows vs -2.6 pp on 16,258), and the
# tennis curves pooled both.
CLASS_TENNIS_WOMEN = "tennis_women"
_TENNIS_TEAM_CUP_WORDS = (
    "davis cup", "billie jean king", "exhibition", "united cup", "hopman cup",
    "laver cup",
)
_WOMEN_BOARD_MARKERS = ("(k)", "(w)", "(f)", " kobiety", " women")
# Whole words (a prefix for the inflected ones), matched on the accent-folded
# name. A bare substring called 3,381 cached men's events women's - "liga f"
# inside Liga FUTVE (Venezuela) and 2. Liga FBIH - and missed "Féminine".
_WOMEN_COMPETITION_RE = re.compile(
    r"\b(?:women\w*|kobiet\w*|femin\w*|femenin\w*|femminil\w*|frauen\w*|"
    r"damen\w*|girls|vrouwen|dames|damallsvenskan|toppserien|nwsl|liga f|"
    r"we[- ]league|wsl)\b"
)


_WOMEN_COMPETITIONS_PATH = config_path("sofa_women_competitions.json")


def load_women_competitions(path: Path = _WOMEN_COMPETITIONS_PATH) -> frozenset[int]:
    """config/sofa_women_competitions.json (scripts/sofa/find_women_
    competitions.py); a missing or unreadable file is an empty set."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(
        int(e["competition_id"]) for e in doc.get("women", [])
        if isinstance(e, dict) and isinstance(e.get("competition_id"), int)
    )


WOMEN_COMPETITION_IDS = load_women_competitions()


def match_class(
    sport: str | None, competition_name: str | None,
    board_sides: tuple[str, str] | None = None,
    competition_id: int | None = None,
) -> str | None:
    """CLASS_WOMEN for a women's football match - the competition id in
    config/sofa_women_competitions.json, Superbet's "(K)" on a board side, or
    the competition name - and for tennis (read off the
    category name) CLASS_TENNIS_TEAM_CUP for a team cup or exhibition, else
    CLASS_TENNIS_WOMEN for a women's event; else None.

    Superbet marks a women's side "(K)" on the board, which is what put the
    women's leagues on the coupon on 2026-09-28; the competition name is the
    second carrier (entity 296052 is plainly "IF Gnistan").
    """
    if sport == "tennis":
        text = (competition_name or "").lower()
        if any(w in text for w in _TENNIS_TEAM_CUP_WORDS):
            return CLASS_TENNIS_TEAM_CUP
        name = (competition_name or "").strip()
        if "Women" in name or name.startswith("WTA"):
            return CLASS_TENNIS_WOMEN
        return None
    if sport != "football":
        return None
    if competition_id is not None and competition_id in WOMEN_COMPETITION_IDS:
        return CLASS_WOMEN
    for name in board_sides or ():
        lowered = f" {(name or '').lower().strip()}"
        if any(m in lowered for m in _WOMEN_BOARD_MARKERS):
            return CLASS_WOMEN
    if _WOMEN_COMPETITION_RE.search(_fold(competition_name or "")):
        return CLASS_WOMEN
    return None


def _fold(text: str) -> str:
    """Lower case, accents dropped: "Première Ligue, Féminine" -> "premiere
    ligue, feminine"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def has_cross_league_unlinked_note(notes: object) -> bool:
    """Did SHEET record that this football fixture's two sides share nothing?

    See football_rating.CROSS_LEAGUE_UNLINKED_NOTE. FK Aktobe (women,
    Kazakhstan: 20-0, 15-0, 12-0) against Ajax (women) in the UEFA Europa
    Cup, 2026-09-30, a week after losing 0-8 to them: goals UNDER 6.5 went
    onto the PDF at 0.823 from a centre of 4.0 goals built from Kazakh
    matches. When nothing the model holds compares the two sides, the price
    is the only number that does, and a confidence leg defers to it.
    """
    if not isinstance(notes, (list, tuple)):
        return False
    return any(
        str(note).startswith("CROSS_LEAGUE_UNLINKED") for note in notes)


def leg_is_ev_positive(confidence: float, odds: float) -> bool:
    """Does this leg clear its own price, using its own number?

    The check the coupon skipped. `ev_if_product_priced` is computed as
    prod(confidence * odds) - 1, so a leg with `confidence * odds < 1` drags
    the slip down by construction — the builder was reporting an EV it was
    simultaneously destroying.
    """
    return confidence * odds > 1.0


# How many singles a PDF prints (by confidence, see run_confidence). Shared
# with audit_settlement, which grades exactly the printed ones: grading every
# single in the artifact graded rows the operator never saw - 216 in the
# artifact against 30 on the page on 2026-09-23.
PDF_MAX_SINGLES = 30


@dataclass(frozen=True)
class ConfidenceProfile:
    """One setting of the two dials the operator chooses between.

    `min_ev` None is `leg_is_ev_positive` (x > 1.0, strictly) - the official
    rule until 2026-10-04. A number is a price TOLERANCE: the leg is accepted while
    confidence x odds >= min_ev, i.e. up to (1 - min_ev) below the price its
    own confidence asks for. `suffix` names the variant's artifacts, so the
    official coupon's files are never overwritten by a variant.
    """

    name: str
    floor: float
    min_ev: float | None
    suffix: str
    pdf_suffix: str
    # The ladder margin a leg may carry and still be printed as a single.
    max_overround: float = MAX_OVERROUND
    # How many singles the PDF prints; None prints the whole artifact.
    pdf_max_singles: int | None = PDF_MAX_SINGLES
    # Whether the PDF prints this profile's stakeable Bet Builders. Written
    # into the artifact, so a variant artifact from before 2026-09-29 (whose
    # PDF printed none) is never graded as if it had.
    prints_builders: bool = True
    # Whether an analyst's or the verifier's WATCH (reads.json) removes a
    # leg. The official coupon honours it; the WARIANT keeps a WATCH leg,
    # marked, so the ledger can measure WATCH (operator, 2026-10-04).
    honours_watch: bool = True
    # From this build time on (with a day in the stats-only epoch) the
    # profile is no longer built - its days stay readable for the
    # settlement, the ledger and the refit (plan 2026-10-05, K5).
    retired_from_utc: datetime | None = None

    def single_is_fairly_priced(self, leg_overround: float | None) -> bool:
        return leg_overround is not None and leg_overround <= self.max_overround

    def clears_price(self, confidence: float, odds: float) -> bool:
        if self.min_ev is None:
            return leg_is_ev_positive(confidence, odds)
        # Rounded before comparing: 0.75 x 1.20 is 0.8999999999999999 in
        # binary, and a leg printed as x = 0.90 must not be refused at 0.90.
        return round(confidence * odds, 9) >= self.min_ev


# A football leg whose model sits more than this above the hit rate of its own
# sample (the share of the sample's observations the line would have won) is
# an automatic WATCH (2026-10-04): the official coupon refuses it, the WARIANT
# keeps it marked. The threshold is the sofa-verifier's, written before it was
# measured; measured on 51,567 settled priced football rows with
# p_central >= 0.65, 2026-09-19..10-03 (scripts/sofa/measure_own_sample_gap.py,
# data/analysis_2026-10-04_history/own_sample_gap_football.md): gap > 0.15
# realised 2.1 pp under the devigged price [-3.9; -0.3], ROI -8.2%
# [-11.2; -5.5] against -3.6 .. -5.3% in every other band, both event-id
# halves -8.2%, worse than the rest on 11 of 15 days. Tennis showed nothing
# (gap > 0.15: -0.4 pp, ROI -3.7%), so it is football only. Farense - Chaves
# goals_total UNDER 3.5 was 0.786 against 14/20 - a gap of 0.086, under it.
MAX_OWN_SAMPLE_GAP = 0.15
OWN_SAMPLE_GAP_SPORTS = frozenset({"football"})
MIN_OWN_SAMPLE = 5


def own_hit_rate(values: list[float], line: float, direction: str) -> float | None:
    """How often the line held in these observations; None without any."""
    if not values:
        return None
    won = sum(1 for v in values if (v > line if direction == "OVER" else v < line))
    return won / len(values)


def model_above_own_sample(
    sport: str,
    model_p: float,
    values: list[float],
    line: float,
    direction: str,
    market: str | None = None,
) -> float | None:
    """The gap when it trips MAX_OWN_SAMPLE_GAP, else None."""
    # Player props were not in the measurement (measure_own_sample_gap.py
    # skips them): their "sample" is a player's appearances, not this one.
    if sport not in OWN_SAMPLE_GAP_SPORTS or len(values) < MIN_OWN_SAMPLE:
        return None
    if market is not None and is_player_metric(market):
        return None
    rate = own_hit_rate(values, line, direction)
    if rate is None:
        return None
    gap = model_p - rate
    return gap if gap > MAX_OWN_SAMPLE_GAP else None


# The official coupon, and the operator's variant of 2026-09-23: "65% and up to
# 10% below the price". Measured before it was added, leave-one-day-out over
# 18-22.09 (scripts/sofa/sweep_confidence_gates.py, stored p_central, each day
# on a curve that never saw it):
#
#     profile    bets   hit    ROI     95% CI (match bootstrap)
#     standard   1655   0.749  -2.9%   -6.6 .. +0.4
#     wariant    5802   0.768  -3.2%   -5.0 .. -1.6     tennis -5.4% (n=136)
#
# About the same loss per bet on 3.5x the bets: it buys volume, not edge. It is
# a variant to be settled beside the official coupon, never a replacement, and
# `audit_settlement` grades both. The disagreement limit is the same in both -
# without MAX_DISAGREEMENT the variant measured -5.0%.
#
# From 2026-09-23 13:30 UTC the variant also accepts a ladder margin up to 15%
# (the official coupon keeps MAX_OVERROUND = 10.5%). The operator's choice, made
# knowing the measurement: over 18-22.09, short-priced (1.09-1.60) settled rows
# returned -5.5% at <=10.5% margin (n=22,478), -7.1% at 10.5-13% (n=7,726) and
# -6.7% at 13-16% (n=1,082); 10.5-13% was worse than <=10.5% on every one of
# the five days. Variant results before and after this date are not the same
# experiment and must not be pooled.
#
# From 2026-10-05 the official coupon takes the variant's two price dials -
# confidence x odds >= 0.90 and a ladder margin up to 15% - and keeps its own
# floor (0.70) and its honouring of WATCH (the
# operator's order of 10-05: "more options to choose from"; a high confidence
# floor was considered and declined). Made knowing the measurement above: the
# variant's dials bought volume, not edge, and the coupon's 10.5-15% margin
# legs returned -12.8% (n=50) against -4.6% (n=78). The official coupon before
# and after 10-05 is not the same experiment and must not be pooled. Later
# that morning the operator also lifted its 30-single page limit ("don't
# limit to 30"): like the variant it prints its whole artifact. An artifact
# without `pdf_max_singles` still reads as the 30 its PDF printed.
#
# From 2026-09-29 the variant's PDF also prints its stakeable Bet Builders (the
# operator's request): same predicate as the coupon (`is_stakeable`: best for
# its fixture, EV > 0 after the 12% correlation haircut), built from the
# variant's looser legs. They were never measured before being added; 7d of the
# settlement grades them on their own, never pooled with the coupon's builders.
PROFILES: dict[str, ConfidenceProfile] = {
    "standard": ConfidenceProfile("standard", 0.70, 0.90, "", "",
                                  max_overround=0.15, pdf_max_singles=None),
    # Retired with the stats-only epoch (2026-10-05, the operator: one
    # coupon; WATCH is graded on its own, audit_settlement 7f).
    "wariant": ConfidenceProfile("wariant", 0.65, 0.90, "_wariant", "_WARIANT",
                                 max_overround=0.15, pdf_max_singles=None,
                                 honours_watch=False,
                                 retired_from_utc=STATS_ONLY_FROM_UTC),
}


def profile_retired(profile: ConfidenceProfile, date: str, build_at: datetime) -> bool:
    """Is a build of `profile` for `date` at `build_at` refused (K5)?"""
    from bet.sofa.epochs import STATS_ONLY_DATE

    return (
        profile.retired_from_utc is not None
        and date >= STATS_ONLY_DATE
        and build_at >= profile.retired_from_utc
    )


# The coupon artifact (plan 2026-10-05, K3). From the stats-only epoch the
# coupon is runs/sofa/<d>/11_coupon.json, assembled by build_coupon.py from
# 08_confidence.json (football, tennis) and 08_confidence_sports.json; it is
# a superset of the 08 format (singles, builders, legs, the dials), so every
# reader of "what was printed" reads it the same way. A day without it is a
# day before the epoch, and its coupon is 08_confidence.json as it always was.
COUPON_ARTIFACT = "11_coupon.json"


def coupon_artifact(run_dir: Path) -> Path:
    """11_coupon.json where it exists, else 08_confidence.json."""
    eleven = Path(run_dir) / COUPON_ARTIFACT
    return eleven if eleven.exists() else Path(run_dir) / "08_confidence.json"


# The stats-only order (K3): confidence, then the earlier start, then the
# match, market and line - never the price or the EV.
def coupon_sort_key(leg: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -float(leg["confidence"]),
        str(leg.get("kickoff_utc") or ""),
        int(leg["sofascore_event_id"]),
        str(leg.get("market") or leg.get("family") or ""),
        str(leg.get("subject") or ""),
        float(leg.get("line") or 0.0),
        str(leg.get("direction") or leg.get("side") or ""),
    )


def group_key(leg: Mapping[str, Any]) -> str:
    """One match, across sports: `sofa:<sofascore_event_id>`."""
    return str(leg.get("group_key") or f"sofa:{int(leg['sofascore_event_id'])}")


@dataclass
class Block:
    """The legs of one match, best first, printed together (K3)."""

    group_key: str
    legs: list[dict[str, Any]]


def coupon_order(legs: list[dict[str, Any]]) -> list[Block]:
    """Blocks of one match each, ordered by their best leg (confidence
    descending, earlier start, match id); inside a block by confidence, then
    market and line. No price and no EV in either key."""
    blocks: dict[str, list[dict[str, Any]]] = {}
    for leg in legs:
        blocks.setdefault(group_key(leg), []).append(leg)
    out = [Block(k, sorted(v, key=coupon_sort_key)) for k, v in blocks.items()]
    out.sort(key=lambda b: coupon_sort_key(b.legs[0]))
    return out


# K10: a stats-only builder is stakeable when its combined probability times
# the price after the correlation haircut clears the singles' own bar.
STAKEABLE_RULE_X = "x>=0.90"
BUILDER_MIN_X = 0.90


def printed_singles(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """The singles the PDF built from this artifact actually prints.

    Since 2026-09-24 the operator's variant prints every single in its
    artifact (the operator asked for the whole list, not the top 30). The
    limit is written into the artifact, so an artifact from before that
    carries no `pdf_max_singles` and is still read as the 30 its PDF printed -
    the settlement of 2026-09-23 must not start grading rows nobody saw.
    """
    singles: list[dict[str, Any]] = artifact.get("singles") or []
    limit = artifact.get("pdf_max_singles", PDF_MAX_SINGLES)
    return singles if limit is None else singles[:limit]


def prints_builders(artifact: dict[str, Any]) -> bool:
    """Whether the PDF built from this artifact prints Bet Builders at all."""
    return bool(artifact.get("prints_builders", artifact.get("min_ev") is None))


def printed_builders(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """The Bet Builders the PDF built from this artifact actually prints.

    `is_stakeable` builders, on an artifact whose profile prints builders.
    An artifact without `prints_builders` predates 2026-09-29: the official
    coupon (min_ev None) printed its builders, the variant printed none, and
    the settlement of those days must not start grading slips nobody saw.
    """
    if not prints_builders(artifact):
        return []
    return [b for b in artifact.get("builders") or [] if is_stakeable(b)]


# How many of the official coupon's printed singles need an analyst's read
# (audit_variants C3): the best READ_REQUIRED_SINGLES in the artifact's own
# order (confidence, then the shorter price; locked legs first), plus every
# leg of a printed builder. The operator's order of 2026-10-05, when the
# official page limit was lifted and the list grew from 30 to ~300 singles:
# "analysts read at most the 30 best". The rest prints unread.
READ_REQUIRED_SINGLES = 30


def legs_requiring_read(
    artifact: dict[str, Any],
    requests: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The printed legs C3 requires an analyst's read on (see above).

    A coupon artifact (11_coupon.json, K4) numbers its fresh singles 1..N:
    the first READ_REQUIRED_SINGLES positions that are not locked, every leg
    of a printed builder, and every position or leg the operator asked for in
    runs/sofa/<d>/read_requests.json (`requests`, else the copy the artifact
    carries). An older artifact keeps the 30 first printed singles, locked
    ones included, as its C3 was run.
    """
    if artifact.get("positions") is not None:
        asked = (
            requests if requests is not None
            else artifact.get("read_requests") or []
        )
        singles = printed_singles(artifact)
        fresh = [s for s in singles if not s.get("locked")]
        chosen = [
            s for s in fresh
            if int(s.get("position") or 0) <= READ_REQUIRED_SINGLES
        ]
        picked = {id(s) for s in chosen}
        for s in singles:
            if id(s) not in picked and any(request_covers(r, s) for r in asked):
                chosen.append(s)
                picked.add(id(s))
        return [
            *chosen,
            *(
                {**leg, "sofascore_event_id": b["sofascore_event_id"],
                 "match": b.get("match", ""), "locked": bool(b.get("locked"))}
                for b in printed_builders(artifact)
                for leg in b.get("legs") or []
            ),
        ]
    return [
        *printed_singles(artifact)[:READ_REQUIRED_SINGLES],
        *(
            {**leg, "sofascore_event_id": b["sofascore_event_id"],
             "match": b.get("match", ""), "locked": bool(b.get("locked"))}
            for b in printed_builders(artifact)
            for leg in b.get("legs") or []
        ),
    ]


def request_covers(request: Mapping[str, Any], leg: Mapping[str, Any]) -> bool:
    """Does one read_requests.json entry ask for this printed leg (K4)?

    `{"position": n}` names a position on the coupon; `{"group_key", "market"?,
    "line"?, "direction"?}` names a match and, optionally, a rung - a field
    left out covers every value."""
    if request.get("position") is not None:
        return leg.get("position") is not None and int(leg["position"]) == int(
            request["position"])
    if request.get("group_key") is None or group_key(leg) != request["group_key"]:
        return False
    for field_ in ("market", "line", "direction"):
        want = request.get(field_)
        if want is None:
            continue
        have = leg.get(field_)
        if field_ == "line":
            if have is None or float(have) != float(want):
                return False
        elif have != want:
            return False
    return True


def load_read_requests(path: Path) -> list[dict[str, Any]]:
    """runs/sofa/<d>/read_requests.json; a missing file is no request. An
    unreadable one or an entry without `requested_by` raises - a request
    that silently does nothing reads like one that was honoured."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, list):
        raise ValueError(f"{path}: a list of requests expected")
    for entry in doc:
        if not isinstance(entry, dict) or not (
                entry.get("requested_by") and entry.get("at_utc")):
            raise ValueError(
                f"{path}: every request needs requested_by and at_utc: {entry!r}")
        if entry.get("position") is None and entry.get("group_key") is None:
            raise ValueError(
                f"{path}: a request names a position or a group_key: {entry!r}")
    return doc


def fixture_leg_counts(singles: list[dict[str, Any]]) -> dict[int, int]:
    """How many of these singles stand on each fixture.

    Singles of one match win and lose together, so three of them are one bet
    cut into three pieces - on 2026-09-25 Boyaca Chico - Pasto carried three
    printed singles (1 won, 2 lost, -1.47 u of the day's -0.02) and nothing on
    the page said they were one match. The count is shown, not enforced: a cap
    of one leg per match, back-tested on the settled PDFs of 22-25.09, took the
    coupon from +0.1% to -3.5% (n=54 -> 50) and the variant from -3.3% to
    -3.8% (n=599 -> 292). It halves the variant's exposure; it does not
    improve the return, so it is the operator's call, not a gate.
    """
    counts: dict[int, int] = {}
    for leg in singles:
        eid = int(leg["sofascore_event_id"])
        counts[eid] = counts.get(eid, 0) + 1
    return counts


def ladder_key(leg: Mapping[str, Any]) -> tuple[int, str, str]:
    """One ladder: a fixture's market for one subject, every rung and side."""
    return (
        int(leg["sofascore_event_id"]),
        str(leg["market"]),
        str(leg.get("subject") or ""),
    )


def ladder_leg_counts(singles: list[dict[str, Any]]) -> dict[tuple[int, str, str], int]:
    """How many of these singles stand on each ladder (see ladder_key).

    Two rungs of one ladder are one claim about one count bought twice - on
    2026-09-30 the coupon printed corners_total 12.5 UNDER, 11.5 UNDER and
    7.5 OVER on one match, and on 2026-10-01 the WARIANT printed ten such
    ladders (22 rows). Like fixture_leg_counts it is shown, not enforced:
    the per-match cap was back-tested and is the operator's call.
    """
    counts: dict[tuple[int, str, str], int] = {}
    for leg in singles:
        k = ladder_key(leg)
        counts[k] = counts.get(k, 0) + 1
    return counts


def confidence_artifact(profile: ConfidenceProfile) -> str:
    """08_confidence.json, or the variant's own file."""
    return f"08_confidence{profile.suffix}.json"


def line_is_beyond_sample(
    line: float, direction: str, sample_values: list[float]
) -> bool:
    """Is the line outside everything the sample has ever seen?

    `UNDER 5.5` on a sample whose maximum is 5 is not a measurement of the
    tail, it is an extrapolation into a region with zero observations. The
    sample reports 20/20 and says nothing, because it could not have said
    anything else.

    This is the "certainty for free" case the operator's method already names,
    and it is how AC Milan's `goals_total UNDER 5.5 @1.08` reached a coupon.
    """
    if not sample_values:
        return False
    if direction == "UNDER":
        return line > max(sample_values)
    return line < min(sample_values)


def mode_loses(line: float, direction: str, sample_values: list[float]) -> bool:
    """Does the single most frequent observation settle this leg as a loss?

    Not "is the line near the mode" — that fires on safe legs too. The
    question is whether the sample's own modal outcome is on the losing side.
    Chaco For Ever's `goals_total OVER 0.5` had a modal sample value of 0:
    the most likely single outcome, by our own evidence, loses the bet.
    """
    if not sample_values:
        return False
    mode = statistics.mode(sample_values)
    return mode <= line if direction == "OVER" else mode >= line


def builder_legs_are_coherent(legs: list[dict[str, Any]]) -> bool:
    """Do these legs point the same way about how busy the match will be?

    `combined_probability` multiplies, which assumes independence. Across
    quantities that holds (lambda 0.95-1.02, see QUANTITY_FAMILIES). It stops
    holding when the legs disagree about tempo: `goals UNDER` with `corners
    OVER` is a negatively correlated pair, so the product OVERSTATES the joint
    and the slip's EV is reported too high.

    Legs that agree are positively correlated, where the product UNDERSTATES —
    an error in the operator's favour, and therefore allowed.

    On 2026-09-20 three of fourteen slips mixed directions this way.
    """
    tempo = {"goals", "corners", "shots"}
    directions = {
        leg["direction"] for leg in legs if quantity_family(leg["market"]) in tempo
    }
    return len(directions) <= 1


MAX_BUILDER_LEGS = 4
MIN_BUILDER_LEGS = 2


def best_leg_per_quantity(
    legs: list[dict[str, Any]],
    by_confidence: bool = False,
) -> dict[str, dict[str, Any]]:
    """One representative per quantity family, chosen by **leg EV**.

    A builder takes at most one leg per quantity, so this choice happens before
    any ranking and silently decides what the ranking is allowed to see.
    Choosing by `confidence` is choosing by shortness of price — the two are
    near-inverses, because the book prices a near-certainty at a
    near-certainty — so a family's EV-positive leg was discarded in favour of
    its shortest-priced sibling before the EV ordering ever ran. That is the
    2026-09-20 defect surviving one level below the sort that was supposed to
    have removed it.

    `by_confidence` (the stats-only epoch, operator's decision D3 of
    2026-10-05): the representative is the most confident leg of its family
    (ties: coupon_sort_key) - the price is no longer a ranking key.
    """
    best: dict[str, dict[str, Any]] = {}
    for leg in legs:
        family = quantity_family(leg["market"])
        current = best.get(family)
        if current is None:
            best[family] = leg
        elif by_confidence:
            if coupon_sort_key(leg) < coupon_sort_key(current):
                best[family] = leg
        elif leg["leg_ev"] > current["leg_ev"]:
            best[family] = leg
    return best


def displayed_ev(builder: dict[str, Any]) -> float | None:
    """The EV a builder should be *shown* with: after the correlation haircut.

    Separate from the selection key only because the two disagreed. In
    `build_coupon_pdf` the variable holding "ev_after_haircut" was named `key`
    and a per-leg loop rebound `key` to a tuple; a loop variable outlives its
    loop, so the summary row's `b.get(key, b.get("ev_if_product_priced"))`
    always fell through to the product EV. Selection was right and the printed
    number was wrong, on a page whose own text says the EV is computed from the
    post-haircut price.

    Falls back to the product EV only for an artifact written before the
    haircut existed, and that fallback is the reason the bug was invisible.
    """
    value = builder.get("ev_after_haircut")
    if value is None:
        value = builder.get("ev_if_product_priced")
    return value


def direction_key(market: str, direction: str) -> str:
    """`goals_for|OVER` - the key of a market's per-direction curve."""
    return f"{market}|{direction.upper()}"


def _gap_shrink_k(value: object) -> float:
    """The calibration file's "gap_shrink_k": absent or null is 0.0 (off).

    A value that is not a number in [0, 2] is refused loudly: a typo here
    would silently move every printed confidence.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"gap_shrink_k must be a number, got {value!r}")
    k = float(value)
    if not 0.0 <= k <= 2.0:
        raise ValueError(f"gap_shrink_k must be within [0, 2], got {k}")
    return k


@dataclass(frozen=True)
class Calibration:
    pooled: dict[str, dict[str, Any]]
    by_market: dict[str, dict[str, dict[str, Any]]]
    # Pooled per sport. The global pool is ~95% football counting markets, so
    # serving a tennis metric from it hands tennis football's shape.
    pooled_by_sport: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=dict
    )
    # The market's curve split by direction, keyed by `direction_key`. OVER
    # and UNDER of one rung are complements, so the market curve pools two
    # different populations and describes neither. Measured 2026-09-26 on
    # the live (non-cache) settled rows, the pooled lookup overstated football
    # team OVER legs by 3.0 pp (realised 0.731, printed 0.761, n=3,940) and the
    # per-direction lookup by 1.9 pp; goals_for OVER went from -2.8 to -1.3.
    # A file fitted before this existed has no such section and reads exactly
    # as it always did.
    by_market_direction: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=dict
    )
    # The direction buckets too thin for by_market_direction
    # (fit_confidence.MIN_THIN_BUCKET..MIN_MARKET_BUCKET rows). Never read as
    # a curve: where the lookup falls to a pool, the pool may not claim more
    # than this bucket's own lower bound (see realised) - and, in the
    # stats-only epoch (cap_market_by_thin), neither may the market's own
    # curve, which pools both directions. A file fitted before 2026-10-04
    # has no such section and reads exactly as it always did.
    thin_by_market_direction: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=dict
    )
    # Per match class (CLASS_WOMEN): the class's own market, direction and
    # sport-pool curves, fitted on the class's rows only. A leg of the class
    # is read from these and nothing else - see realised().
    by_class: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Player props the operator has admitted to the coupon by name
    # ("admitted_player_markets" in the calibration file). AWAITING_OWN_CURVE
    # lapses by itself once a market has a curve, and the next fit_confidence
    # gives every player prop one: their 09-26..09-29 builder legs realised
    # 0.624 against 0.776 claimed, and they price at one-sided offers, so
    # being curved is not a reason to print them. A deliberate decision is.
    admitted_player_markets: frozenset[str] = frozenset()
    # Tennis per-set games markets the operator has admitted by name
    # ("admitted_tennis_set_markets"), for the same reason: see
    # TENNIS_SET_GAMES. Empty by default - refused as
    # TENNIS_SET_MARKET_NOT_ADMITTED.
    admitted_tennis_set_markets: frozenset[str] = frozenset()
    # Markets the operator keeps off both coupons by name ("refused_markets"
    # in the calibration file): "market" for both directions or
    # "market|OVER" / "market|UNDER" for one. A curve the fit measured does
    # not override it, and a refit carries it over (fit_meta.OPERATOR_KEYS).
    # Built 2026-10-03 for the open decision on shots_total / fouls_total
    # UNDER (settled rows >=0.70: shots_total UNDER claimed 0.759 realised
    # 0.521, n=144; fouls_total UNDER >=0.65 0.729 / 0.389, n=36). Empty by
    # default - refused as OPERATOR_REFUSED.
    refused_markets: frozenset[str] = frozenset()
    # The anti-selection shrink ("gap_shrink_k" in the calibration file). 0.0
    # (the default, and what a file without the key reads) changes nothing.
    # See shrink_for_gap.
    gap_shrink_k: float = 0.0
    # K13 (plan 2026-10-05; the stats-only epoch only, set by CONFIDENCE).
    # The market curve `by_market` pools OVER and UNDER, so where a
    # direction's own bucket is too thin for by_market_direction the market
    # curve is a pool as much as the sport pool is, and is capped by the thin
    # bucket the same way. Found by the verifier on 10-05:
    # corners_1h_total|UNDER at p 0.75-0.80 - thin bucket n=225, lo95 0.663;
    # by_market (both directions) n=428, lo95 0.712, printed at 0.712.
    # Off, a lookup is exactly what it was before 10-05.
    cap_market_by_thin: bool = False

    def _cap_by_thin(
        self, market: str, direction: str | None, p: float,
        hit: tuple[float, str, int],
    ) -> tuple[float, str, int]:
        """`hit`, or the direction's thin bucket where that bounds it lower."""
        if not direction:
            return hit
        key = direction_key(market, direction)
        thin = self._find(self.thin_by_market_direction.get(key, {}), p)
        if thin is not None and thin["realised_lo95"] < hit[0]:
            return thin["realised_lo95"], f"market_thin:{key}", thin["n"]
        return hit

    def shrink_for_gap(
        self, confidence: float, p_central: float, market_p: float | None
    ) -> float:
        """The curve's number, lowered by k x how far the model sits above the price.

        The curve is fitted on rows that mostly carry no price (the cache
        replay), while the coupon prints only legs whose model sits ABOVE the
        devigged price - and there the curve over-states. Measured 2026-10-03
        night on 64,481 priced live settled rows at p >= 0.60 (09-17..10-02,
        installed 10-03 curve, data/night_2026-10-03/antisel/): realised
        minus curve falls with the gap model - price in 30 of 32 market x
        direction cells (slope CI below zero; ~ -0.7 .. -1.1), from +0.11 at
        gap < -0.10 to -0.13 at +0.10..+0.20; inside the installed rule's
        selection (4,762 legs) the printed confidence averaged 0.805 against
        0.745 realised and 0.742 devigged price. Fitted leave-one-day-out, k
        is 0.83-0.88 and the held-out Brier falls on 14 of 15 days
        (0.1888 -> 0.1836). It does NOT make the coupon pay: under it the rule
        keeps ~10% of the legs and those returned -7.4% [-13.6, -1.7] against
        -4.0% [-5.9, -1.9] for the installed rule. Off until the operator sets
        it; it only ever lowers a confidence, never raises one, and a rung
        without a devigged price is left alone.
        """
        if self.gap_shrink_k <= 0.0 or market_p is None:
            return confidence
        gap = max(float(p_central) - float(market_p), 0.0)
        return round(max(confidence - self.gap_shrink_k * gap, 0.0), 4)

    def refused_by_operator(self, market: str, direction: str | None) -> bool:
        if market in self.refused_markets:
            return True
        return bool(direction) and direction_key(
            market, str(direction)
        ) in self.refused_markets

    def player_prop_not_admitted(self, market: str) -> bool:
        return (
            market in PLAYER_PROP_MARKETS
            and market not in self.admitted_player_markets
        )

    def tennis_set_market_not_admitted(self, market: str) -> bool:
        return (
            market in TENNIS_SET_GAMES
            and market not in self.admitted_tennis_set_markets
        )

    @staticmethod
    def load(path: Path | str = DEFAULT_CALIBRATION) -> Calibration:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return Calibration(
            pooled=doc.get("pooled", {}),
            by_market=doc.get("by_market", {}),
            pooled_by_sport=doc.get("pooled_by_sport", {}),
            by_market_direction=doc.get("by_market_direction", {}),
            thin_by_market_direction=doc.get("thin_by_market_direction", {}),
            by_class=doc.get("by_class", {}),
            admitted_player_markets=frozenset(
                doc.get("admitted_player_markets") or ()
            ),
            admitted_tennis_set_markets=frozenset(
                doc.get("admitted_tennis_set_markets") or ()
            ),
            refused_markets=frozenset(doc.get("refused_markets") or ()),
            gap_shrink_k=_gap_shrink_k(doc.get("gap_shrink_k")),
        )

    def for_class(self, klass: str) -> Calibration | None:
        """The class's own curves, with no global pool behind them."""
        section = self.by_class.get(klass)
        if not section:
            return None
        return Calibration(
            pooled={},
            by_market=section.get("by_market", {}),
            pooled_by_sport=section.get("pooled_by_sport", {}),
            by_market_direction=section.get("by_market_direction", {}),
            thin_by_market_direction=section.get("thin_by_market_direction", {}),
            cap_market_by_thin=self.cap_market_by_thin,
        )

    def _direction_entry(
        self, market: str, direction: str | None, p: float
    ) -> tuple[dict[str, Any], str] | None:
        """This direction's own bucket for `p`, if the fit measured one.

        Only a bucket the direction actually has. A direction curve is the
        market's rows split in two, so its top buckets are often under
        MIN_MARKET_BUCKET where the market's are not - that is thinness, not
        a measurement, and must not refuse a leg the market curve describes.
        Back-tested before this was settled: treating the direction's range
        as a ceiling refused goals_2h_total and tiebreaks_total legs on every
        day 22-25.09 on no evidence at all. Where the direction is silent the
        lookup is exactly what it was before 2026-09-26.
        """
        if not direction:
            return None
        key = direction_key(market, direction)
        entry = self._find(self.by_market_direction.get(key, {}), p)
        return (entry, f"market:{key}") if entry is not None else None

    @staticmethod
    def _find(curve: dict[str, dict[str, Any]], p: float) -> dict[str, Any] | None:
        for key, entry in curve.items():
            lo, hi = (float(x) for x in key.split("-"))
            if lo <= p < hi:
                return entry
        return None

    def realised(
        self,
        market: str,
        p: float,
        sport: str | None = None,
        direction: str | None = None,
        klass: str | None = None,
    ) -> tuple[float, str, int] | None:
        """The measured lower bound for this market at this claimed probability.

        Returns (realised_lo95, source, n), or None when neither the market's
        own curve nor the pooled one covers the bucket — in which case the
        caller must refuse the leg rather than fall back to `p`. Falling back
        to the model's own number is precisely the untested claim this module
        exists to stop making.

        `direction` selects the market's per-direction curve where the file
        has a bucket for `p` (see `_direction_entry`); without one the lookup
        is the pooled market curve, as it was before 2026-09-26.
        """
        if klass is not None:
            # A leg of a match class is read from the class's own curves and
            # never from the pool the class was measured to differ from. A
            # file with no section for the class refuses the leg - that is
            # the AWAITING_OWN_CURVE rule applied to a class.
            own_class = self.for_class(klass)
            if own_class is None:
                return None
            hit = own_class.realised(market, p, sport, direction)
            if hit is None:
                return None
            return hit[0], f"{klass}:{hit[1]}", hit[2]
        entry: dict[str, Any] | None
        by_direction = self._direction_entry(market, direction, p)
        if by_direction is not None:
            entry, source = by_direction
            return entry["realised_lo95"], source, entry["n"]
        # A player prop is read from its own direction's curve or not at all.
        # Superbet quotes these OVER only, while the cache replay prices both
        # directions, so the combined market curve is mostly UNDER rows - and
        # the two directions are miscalibrated in opposite ways (2026-10-02
        # replay: OVER >=0.70 claimed 0.798, realised 0.672; UNDER claimed
        # 0.850, realised 0.875). shots_on_target OVER has no bucket above
        # 0.70 and would have read 0.704 off the combined curve against ~0.62
        # realised.
        if market in PLAYER_PROP_MARKETS:
            return None
        own = self.by_market.get(market, {})
        entry = self._find(own, p)
        if entry is not None:
            hit = entry["realised_lo95"], f"market:{market}", entry["n"]
            if self.cap_market_by_thin:
                return self._cap_by_thin(market, direction, p, hit)
            return hit
        # See AWAITING_OWN_CURVE: no pool may stand in for a market that has
        # no measured curve of its own yet.
        if not own and market in AWAITING_OWN_CURVE:
            return None
        # See TENNIS_PER_SET: a per-set market is read from its own curve or
        # not at all - a hole inside its range is not filled from the pool.
        if market in TENNIS_PER_SET:
            return None

        # A market with its own curve may NOT borrow the pooled one above the
        # top of its own measured range.
        #
        # Measured 2026-09-21, and it is the whole reason empirical-frequency
        # metrics were once banned outright. `games_won_for` has 9,286 settled
        # rows and not one bucket above 0.825; its best measured bucket
        # realises 0.756. The pooled curve — 74,574 rows, almost all football
        # counting markets — says 0.905 at p=0.90. Falling through produced 12
        # tennis legs at a claimed 0.905 that this market has never once been
        # observed to deliver, which is the "0.811 against a price of 20.00"
        # failure wearing a calibration curve.
        #
        # Silence above a market's measured range is evidence, not a gap: it
        # says the model never produces a confident prediction here that
        # verifies. A hole *inside* the range is different — that is a thin
        # bucket, and the pooled curve is a reasonable stand-in for it.
        if own:
            ceiling = self._measured_ceiling(own)
            if ceiling is not None and p >= ceiling:
                return None
        elif uses_empirical_frequency(market) or market in NORMAL_NON_COUNT_METRICS:
            # A market with NO curve of its own had no ceiling at all, and
            # borrowed the sport pool to its very top. For an empirical
            # frequency that is the failure above, one step removed: the raw
            # frequency is measured to overclaim at the top (games_won_for:
            # claimed 0.95, realised 0.73), and a market that has never been
            # settled - games_set1_total, games_set2_total, tiebreaks_total on
            # 2026-09-23 - cannot be assumed to be the exception. It may not
            # claim more than the empirical markets that HAVE been measured.
            ceiling = self._unproven_ceiling()
            if p >= ceiling:
                return None

        # The sport's own pool before the global one. `sets_total` has 202
        # settled rows — too few for a market curve — and read 0.856 off a
        # global bucket of 64,790 rows that were almost entirely goals and
        # corners. Tennis has 56,581 settled rows of its own; there is no
        # reason to describe it with football.
        pooled: tuple[float, str, int] | None = None
        if sport:
            entry = self._find(self.pooled_by_sport.get(sport, {}), p)
            if entry is not None:
                pooled = entry["realised_lo95"], f"pooled:{sport}", entry["n"]
        if pooled is None:
            entry = self._find(self.pooled, p)
            if entry is not None:
                pooled = entry["realised_lo95"], "pooled", entry["n"]
        if pooled is None:
            return None
        # The pool stands in for a market's thin bucket, but may not claim
        # more than the market's own rows there bound. goals_1h_total UNDER
        # (no cache-replay rows until 2026-10-04) read pooled:football's
        # 0.8149 at p 0.80-0.825 where its own 232 rows realised 0.810, lo95
        # ~0.755, and six such legs printed on 2026-10-03: the pool's bound is
        # tight because it measures other markets. See fit_confidence.
        # MIN_THIN_BUCKET for the leave-one-day-out measurement.
        return self._cap_by_thin(market, direction, p, pooled)

    def _unproven_ceiling(self) -> float:
        """The lowest measured ceiling among empirical markets with a curve.

        Falls back to UNPROVEN_MARKET_CEILING when no empirical market has a
        curve, so the absence of evidence never widens the range.
        """
        tops = [
            c
            for m, curve in self.by_market.items()
            if uses_empirical_frequency(m)
            and (c := self._measured_ceiling(curve)) is not None
        ]
        return min(tops) if tops else UNPROVEN_MARKET_CEILING

    def measured_ceiling(self, market: str) -> float | None:
        """Top of the range this market has evidence for, or None if no curve.

        Public because the coupon needs the same fact the confidence view
        uses: a row claiming more than its market has ever been observed to
        deliver is making a claim the settled data refuses to describe.
        """
        own = self.by_market.get(market, {})
        return self._measured_ceiling(own) if own else None

    @staticmethod
    def _measured_ceiling(curve: dict[str, dict[str, Any]]) -> float | None:
        """Top of the highest bucket this market actually has evidence for."""
        tops: list[float] = []
        for key in curve:
            _, _, hi = key.partition("-")
            try:
                tops.append(float(hi))
            except ValueError:
                continue
        return max(tops) if tops else None


def combined_probability(legs: list[float]) -> float:
    """Product, because same-match legs were measured independent (lambda 1.009)."""
    out = 1.0
    for p in legs:
        out *= p
    return out


def fair_odds(probability: float) -> float | None:
    """The price a combination would need to be worth its risk, and NOT a
    prediction of Superbet's Bet Builder price.

    Superbet prices a builder with its own correlation adjustment, so
    multiplying the leg prices would invent a number the book never quoted.
    The operator compares this against what the screen actually shows.
    """
    if probability <= 0.0:
        return None
    return round(1.0 / probability, 2)


# Superbet does not price a Bet Builder at the product of its legs: it applies
# its own correlation adjustment, and that adjustment is the whole margin.
# Measured 2026-09-20 from the operator's screenshots — the first time this
# repo ever saw a builder's real price (see reports/sofa_narzut_bet_buildera_
# 2026-09-20.md):
#
#     slip                                  legs   product   screen   markup
#     Inter Miami  goals U5.5 + 1h U2.5        2     1.754     1.60     8.8%
#     Athletico    corners 1h U6.5 + U13.5     2     1.782     1.50    15.8%
#     Flamengo     3 UNDER + corners 2h OVER   4     2.364     1.90    19.6%
#
# 12% is the middle of that range, held flat on purpose: three observations
# cannot fit a curve in leg count, and a per-leg-count table from n=3 would be
# overfitting dressed as precision. Replace with a fitted curve once enough
# screen prices are recorded.
#
# The single leg on the same screen (Londrina corners U12.5) went at exactly
# our quoted 1.37, so the leg prices are faithful. The money is in the join.
BUILDER_CORRELATION_HAIRCUT = 0.12

# Below this the empirical joint is noise, and min()-ing against it would let
# one unlucky decile veto a slip. The builder sample floor is already 10.
MIN_JOINT_SAMPLE = 8


def builder_odds(odds_product: float, screen_odds: float | None = None) -> float:
    """What a builder actually returns, per unit staked.

    `screen_odds` is the price the operator read off Superbet. When it is
    known it wins outright — a measurement beats an estimate. When it is not,
    the product is discounted by the measured correlation markup, because
    selecting on the undiscounted product is selecting on a price the book has
    never quoted.
    """
    if screen_odds is not None:
        return screen_odds
    return odds_product * (1.0 - BUILDER_CORRELATION_HAIRCUT)


def empirical_joint(
    observations: list[dict[int, float]], conditions: list[tuple[float, str]]
) -> tuple[int, int]:
    """How often did every leg of this slip hold in the SAME past match?

    `observations` is one {event_id: value} map per leg, `conditions` the
    matching (line, direction) pairs. Only matches present in every leg's
    sample can be judged, so the count is over the intersection.

    This is the question `combined_probability` cannot ask. The product
    assumes independence; the intersection observes the joint. On 2026-09-20
    the two disagreed in both directions on real slips — 58.3% product against
    4/10 observed where the legs disagreed about tempo, and 64.9% against 5/6
    where one leg nested inside another.

    Returns (hits, n). n == 0 when the samples share no match.
    """
    if not observations or len(observations) != len(conditions):
        return 0, 0
    common = set(observations[0])
    for obs in observations[1:]:
        common &= set(obs)
    hits = 0
    for event_id in common:
        if all(
            (obs[event_id] < line) if direction == "UNDER" else (obs[event_id] > line)
            for obs, (line, direction) in zip(observations, conditions)
        ):
            hits += 1
    return hits, len(common)


def joint_probability(product: float, hits: int, n: int) -> float:
    """The slip's probability, taking the more pessimistic of two estimates.

    The product and the observed joint are both estimates of the same
    quantity, and neither dominates: the product overstates legs that disagree
    about tempo and understates legs that nest. Taking the minimum refuses to
    promote a slip on a noisy ten-match high while still letting that sample
    demote one — which is the asymmetry this repo keeps paying for when it
    gets it backwards.

    The empirical side is Laplace-smoothed, so 10/10 does not assert
    certainty.
    """
    if n < MIN_JOINT_SAMPLE:
        return product
    return min(product, (hits + 1) / (n + 2))


def is_stakeable(builder: Mapping[str, Any]) -> bool:
    """Whether a builder is a bet, as the PDF — the actual coupon — decides it.

    Two conditions, and they are not the same one. `best_for_fixture` keeps a
    fixture from being staked three times over off one opinion; the EV test
    asks whether the position survives Superbet's measured markup for pricing
    a correlated slip.

    This lives here, used by both `run_confidence.py` and
    `build_coupon_pdf.py`, because it was written out twice and the two copies
    disagreed. On 2026-09-21 CONFIDENCE reported `stakeable_builders: 3` for a
    day on which the PDF staked nothing: all three builders were
    `best_for_fixture` and all three had negative EV after the haircut. One
    predicate, one answer.
    """
    if not builder.get("best_for_fixture"):
        return False
    # K10 (stats-only epoch): combined probability x the price after the
    # haircut >= 0.90, the singles' own bar. Written into the builder, so an
    # older artifact is read by the predicate it was built with.
    if builder.get("stakeable_rule") == STAKEABLE_RULE_X:
        p = builder.get("combined_probability")
        odds = builder.get("odds_after_haircut")
        return p is not None and odds is not None and round(
            float(p) * float(odds), 9) >= BUILDER_MIN_X
    # Older artifacts predate the haircut and carry only the product EV.
    key = (
        "ev_after_haircut" if "ev_after_haircut" in builder else "ev_if_product_priced"
    )
    ev = builder.get(key)
    return ev is not None and ev > 0


# How close to the start a position may still be offered. One number for
# COUPON and CONFIDENCE: until 2026-09-23 only COUPON had it, and CONFIDENCE
# built a PDF builder five minutes before its fixture's kickoff.
MIN_MINUTES_TO_KICKOFF = 15


def too_close_to_kickoff(clocks: list[datetime], now: datetime) -> bool:
    """True when the EARLIER clock is inside COUPON's kickoff margin.

    The same margin COUPON keeps (MIN_MINUTES_TO_KICKOFF), not merely "not
    started": without it, on 2026-09-23 a builder was printed five minutes
    before the kickoff in its own artifact. No clock at all is refused too.
    """
    if not clocks:
        return True
    return min(clocks) <= now + timedelta(minutes=MIN_MINUTES_TO_KICKOFF)


def disagrees_with_price(
    p_central: float,
    market_p: float | None,
    confidence: float,
    odds: float,
    sample_frequency: float | None = None,
) -> bool:
    """COUPON's MAX_DISAGREEMENT test, on the quantity it was measured on.

    MAX_DISAGREEMENT was measured as p_central minus the DEVIGGED market
    price. CONFIDENCE applied it as the calibrated lower bound minus 1/odds -
    both sides shifted the lenient way (the lower bound sits below p_central,
    1/odds above the devigged price) - and on 2026-09-23 159 of 216 printed
    singles sat more than 0.10 above their devigged price, the region COUPON
    drops as measured-negative. A rung quoted on one side only has no devigged
    price, and keeps the old comparison.

    `sample_frequency`, where the row has one, replaces p_central: a tennis
    empirical row is priced mostly FROM the price, and its p_central carries a
    quarter of the sample's disagreement (see SheetRow.sample_frequency).
    """
    if market_p is not None:
        claim = sample_frequency if sample_frequency is not None else p_central
        return claim - market_p > MAX_DISAGREEMENT
    return confidence - 1.0 / odds > MAX_DISAGREEMENT
