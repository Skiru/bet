from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.tennis_score import match_tiebreak_sets, set_games

# Finished after extra time (110 = AET) or penalties (120 = AP). 366 such
# matches sat in the cache, all rejected. Rejecting them is *right* for the
# counting metrics — a 120-minute match has a third more corners, cards and
# fouls, and letting it into the sample shifts the mean up, which is the F28
# error with the sign flipped. But the goals are recoverable, because Sofascore
# records the 90-minute score separately in homeScore.normaltime, and 90
# minutes is what Superbet's goal markets settle on.
#
# So these events are admitted to the sample and refused per metric in
# extract_metric: goals read normaltime, everything else gets
# EVENT_NOT_FINISHED.
EXTRA_TIME_STATUS_CODES = frozenset({110, 120})


def is_extra_time_event(event: dict[str, Any]) -> bool:
    status = event.get("status")
    if not isinstance(status, dict):
        return False
    return status.get("code") in EXTRA_TIME_STATUS_CODES


def goal_score_inconsistent(event: dict[str, Any]) -> bool:
    """The listing's goal fields disagree with each other, on either side.

    period1 + period2 must be normaltime, and with no extra time current must
    be normaltime. Review 2026-10-04: Buxton - South Shields (17160371) lists
    the away side current 2, period1 1, period2 0, normaltime 1 (incidents:
    goals at 7' and 64'); the old check looked at the home side only and the
    settle graded goals_2h_total 0.5 OVER a loss. ~1% of cached league
    matches carry such a score; a goal count read from it is no count.
    """
    extra_time = is_extra_time_event(event)
    for side in ("homeScore", "awayScore"):
        score = event.get(side)
        if not isinstance(score, dict):
            continue
        p1, p2, nt, cur = (score.get(k) for k in
                           ("period1", "period2", "normaltime", "current"))
        if isinstance(p1, int) and isinstance(p2, int) and isinstance(nt, int):
            if p1 + p2 != nt:
                return True
        if not extra_time and isinstance(nt, int) and isinstance(cur, int):
            if cur != nt:
                return True
    return False


def regulation_score(event: dict[str, Any]) -> tuple[float, float] | None:
    """Home and away goals at 90 minutes - the quantity Superbet settles on.

    ``current`` carries extra time AND the shootout: a J.League 2 cup tie that
    was 2-2 at 90 minutes reads current 7-5 after penalties. SAMPLES always
    used this rule; the cache replay read ``current`` and fitted J2's
    goals_total baseline at 3.87 against a real ~2.46 (2026-09-26).
    """
    field = "normaltime" if is_extra_time_event(event) else "current"
    home = (event.get("homeScore") or {}).get(field)
    away = (event.get("awayScore") or {}).get(field)
    if home is None or away is None:
        return None
    return float(home), float(away)


FOOTBALL_METRICS = {
    "goals_total": {"sofascore": "goals_from_listing", "is_total": True},
    "goals_for": {"sofascore": "goals_from_listing", "is_total": False},
    "goals_1h_total": {"sofascore": "goals_1h_from_listing", "is_total": True},
    "goals_1h_for": {"sofascore": "goals_1h_from_listing", "is_total": False},
    "goals_2h_total": {"sofascore": "goals_2h_from_listing", "is_total": True},
    "goals_2h_for": {"sofascore": "goals_2h_from_listing", "is_total": False},
    "corners_total": {"sofascore": "cornerKicks", "is_total": True},
    "corners_for": {"sofascore": "cornerKicks", "is_total": False},
    # cards_total / cards_for are deliberately absent.
    #
    # They measured yellowCards only, and Superbet prices no yellow-only
    # market. Enumerated against the live board on 2026-09-18 for
    # Brentford-Chelsea, which carries the full card screen: every countable
    # card market is "liczba kartek" — match, per team, per half — and Superbet
    # settles those in booking *points*, counting a red as more than a yellow.
    # The only red-specific markets are "liczba czerwonych kartek", which is a
    # different quantity again, not a yellow count.
    #
    # So there is no market to build for a yellow-only metric, and a metric
    # nothing can price is a number that looks like coverage without being any.
    # cards_points_total / cards_points_for are the right pair and are below.
    # This also takes the declared-metric count from 30 to 28, which makes
    # "15 of 30 metrics never materialised" an honest denominator.
    "cards_points_total": {
        "sofascore": "cards_points_from_incidents",
        "is_total": True,
    },
    "cards_points_for": {"sofascore": "cards_points_from_incidents", "is_total": False},
    "fouls_total": {"sofascore": "fouls", "is_total": True},
    "fouls_for": {"sofascore": "fouls", "is_total": False},
    "offsides_total": {"sofascore": "offsides", "is_total": True},
    "offsides_for": {"sofascore": "offsides", "is_total": False},
    "shots_total": {"sofascore": "totalShotsOnGoal", "is_total": True},
    "shots_for": {"sofascore": "totalShotsOnGoal", "is_total": False},
    "shots_on_target_total": {"sofascore": "shotsOnGoal", "is_total": True},
    "shots_on_target_for": {"sofascore": "shotsOnGoal", "is_total": False},
    "xg_total": {"sofascore": "expectedGoals", "is_total": True},
    "xg_for": {"sofascore": "expectedGoals", "is_total": False},
    # Per-half counting metrics (F43). Sofascore keys /statistics by period —
    # "1ST", "2ND", "ALL" — and the flattener has always preserved that, but
    # extract_metric read `flat_stats["ALL"]` unconditionally, so the only
    # per-half metrics that existed were the three goal pairs, which come from
    # the listing score and never touch /statistics. Live-verified on
    # 2026-09-18 against event 16950627: cornerKicks ALL=(5,7), 1ST=(2,2),
    # 2ND=(3,5); fouls, offsides, shots and shots on target likewise.
    #
    # Superbet prices these: "1. polowa - liczba rzutow roznych" appeared on
    # 92 fixtures of the 2026-09-18 board and its per-team form on ~100 more,
    # every one of them landing in unmapped_markets.
    #
    # Cards are deliberately absent from this block. cards_points comes from
    # /incidents, not /statistics, and scoping it to a half means deciding
    # what a second-yellow dismissal is worth when the first yellow was in the
    # other half. That is a real modelling question, not a period key, and
    # guessing it would fabricate the number this pipeline exists to refuse.
    "corners_1h_total": {
        "sofascore": "cornerKicks",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "corners_1h_for": {
        "sofascore": "cornerKicks",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "corners_2h_total": {
        "sofascore": "cornerKicks",
        "is_total": True,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "corners_2h_for": {
        "sofascore": "cornerKicks",
        "is_total": False,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "fouls_1h_total": {
        "sofascore": "fouls",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "fouls_1h_for": {
        "sofascore": "fouls",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "shots_1h_total": {
        "sofascore": "totalShotsOnGoal",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "shots_1h_for": {
        "sofascore": "totalShotsOnGoal",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "shots_on_target_1h_total": {
        "sofascore": "shotsOnGoal",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "shots_on_target_1h_for": {
        "sofascore": "shotsOnGoal",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    # Second halves and the remaining /statistics counts Superbet prices
    # (2026-09-25 coverage audit over the 09-22..25 offers: "2. polowa -
    # liczba fauli/strzalow/celnych strzalow/spalonych", "liczba obronionych
    # strzalow przez bramkarza", "liczba rzutow z autu", "liczba wybic od
    # bramki", "liczba odbiorow", each with its per-team form). Every one of
    # them was already in the cached /statistics payload - SAMPLES stores the
    # whole response - and nothing read it. Measured over 22,433 cached
    # football events with statistics: goalkeeperSaves ALL on 60%, 1ST/2ND on
    # 7,330; throwIns 78%; goalKicks 82%; totalTackle 60%. A missing key is
    # not a zero (2,494 events lack goalkeeperSaves while the opponent put 3+
    # shots on target), and extract_metric already reads it as a gap. Some
    # zeros are not zeros either - see ZERO_MEANS_UNTRACKED.
    "fouls_2h_total": {
        "sofascore": "fouls",
        "is_total": True,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "fouls_2h_for": {
        "sofascore": "fouls",
        "is_total": False,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "shots_2h_total": {
        "sofascore": "totalShotsOnGoal",
        "is_total": True,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "shots_2h_for": {
        "sofascore": "totalShotsOnGoal",
        "is_total": False,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "shots_on_target_2h_total": {
        "sofascore": "shotsOnGoal",
        "is_total": True,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "shots_on_target_2h_for": {
        "sofascore": "shotsOnGoal",
        "is_total": False,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "offsides_1h_total": {
        "sofascore": "offsides",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "offsides_1h_for": {
        "sofascore": "offsides",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "offsides_2h_total": {
        "sofascore": "offsides",
        "is_total": True,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "offsides_2h_for": {
        "sofascore": "offsides",
        "is_total": False,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "saves_total": {"sofascore": "goalkeeperSaves", "is_total": True},
    "saves_for": {"sofascore": "goalkeeperSaves", "is_total": False},
    "saves_1h_total": {
        "sofascore": "goalkeeperSaves",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "saves_1h_for": {
        "sofascore": "goalkeeperSaves",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "throw_ins_total": {"sofascore": "throwIns", "is_total": True},
    "throw_ins_for": {"sofascore": "throwIns", "is_total": False},
    "throw_ins_1h_total": {
        "sofascore": "throwIns",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "throw_ins_1h_for": {
        "sofascore": "throwIns",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "throw_ins_2h_total": {
        "sofascore": "throwIns",
        "is_total": True,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "throw_ins_2h_for": {
        "sofascore": "throwIns",
        "is_total": False,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "goal_kicks_total": {"sofascore": "goalKicks", "is_total": True},
    "goal_kicks_for": {"sofascore": "goalKicks", "is_total": False},
    "goal_kicks_1h_total": {
        "sofascore": "goalKicks",
        "is_total": True,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "goal_kicks_1h_for": {
        "sofascore": "goalKicks",
        "is_total": False,
        "period": "1ST",
        "period_complement": "2ND",
    },
    "goal_kicks_2h_total": {
        "sofascore": "goalKicks",
        "is_total": True,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "goal_kicks_2h_for": {
        "sofascore": "goalKicks",
        "is_total": False,
        "period": "2ND",
        "period_complement": "1ST",
    },
    "tackles_total": {"sofascore": "totalTackle", "is_total": True},
    "tackles_for": {"sofascore": "totalTackle", "is_total": False},
}

# /statistics keys whose zero is sometimes "not tracked" rather than nothing.
# A football match has ~40 throw-ins and ~18 tackles; measured over the 22,433
# cached events with statistics, 756 carry throwIns 0-0, 1,696 goalKicks 0-0
# and 416 totalTackle 0-0, with p50 20 / 7 / 9 per side elsewhere - the
# provider publishing a placeholder, the same trap as L1 ("a zero that means
# unknown"). "either": one side at zero is already impossible in a real match
# (283 throwIns and 1,587 totalTackle events). "both": a single zero can
# happen (a side that concedes no shot off target takes no goal kick), so only
# 0-0 is refused. Judged on the full-match pair, and the halves inherit it:
# an untracked match has no trustworthy half either.
ZERO_MEANS_UNTRACKED: dict[str, str] = {
    "throwIns": "either",
    "totalTackle": "either",
    "goalKicks": "both",
}


def stat_is_untracked(key: str, whole: tuple[float, float] | None) -> bool:
    """True when this full-match pair is the provider's placeholder zero."""
    rule = ZERO_MEANS_UNTRACKED.get(key)
    if rule is None or whole is None:
        return False
    zeros = (whole[0] == 0) + (whole[1] == 0)
    return zeros == 2 if rule == "both" else zeros >= 1


# A zero that means "not recorded" (2026-10-03, event 16494320 Wealdstone -
# Halifax: corners 0-0 beside total tackles 0/1). Measured over the 111,606
# cached football /statistics payloads (data/night_2026-10-03/guards/): the
# full data feed - the one that publishes `passes` - and the partial feeds
# (a handful of keys, no `passes`; mostly lower leagues) have similar means
# (corners 9.54 vs 8.36 a match, fouls 24.7 vs 24.9, shots on target 8.6 vs
# 8.6) and 0-0 rates 115-140 times apart: corners 0.02% vs 2.87%,
# fouls 0.01% vs 1.15%, shots on target 0.02% vs 2.61%. The full feed's
# rate is the genuine tail (a negative binomial on its corner totals predicts
# 11 nil-nil matches in 63,452; 13 are there); the partial feed's excess is
# the provider's placeholder. Three clauses (c, below, since 2026-10-04),
# all on the full-match pair (the halves inherit it, as with
# ZERO_MEANS_UNTRACKED):
#
#   a) NEED_FULL_FEED: a 0-0 on one of these keys in a payload without the
#      full-feed marker is refused outright. Expected genuine losses at the
#      full-feed rate: ~7 corner, ~2 foul and ~4 shots-on-target matches in
#      the whole history.
#   b) a 0-0 on a GUARDED key beside a companion that is itself a
#      placeholder (stat_is_untracked, or a 0-0 on a PLACEHOLDER_COMPANIONS
#      key) is refused: the payload has shown it was not counting. In the
#      full feed only for NEED_FULL_FEED keys (the 16494320 shape: corners
#      0-0 beside tackles 0/1; 2 such corner matches in the history).
#      Measured lift on partial feeds: offsides 0-0 is 95% when
#      free kicks read 0-0, 94% beside fouls 0-0, 88% beside a throw-in
#      placeholder, against 10% otherwise. A companion that a genuine 0-0
#      of the key itself would imply (no shot at all, so no shot on target)
#      is no evidence and is skipped. goalkeeperSaves is not guarded: a
#      keeper can make no save, saves live almost only in the full feed (56
#      partial payloads carry them), and a placeholder companion barely
#      moves their 0-0 rate there (0.3% vs 0.18%).
FULL_FEED_MARKER = "passes"
NEED_FULL_FEED = frozenset({"cornerKicks", "fouls", "shotsOnGoal", "totalShotsOnGoal"})
ZERO_PAIR_GUARDED = NEED_FULL_FEED | {"offsides"}
PLACEHOLDER_COMPANIONS = frozenset(
    {
        "cornerKicks",
        "fouls",
        "freeKicks",
        "shotsOnGoal",
        "shotsOffGoal",
        "totalShotsOnGoal",
    }
)
# c) (2026-10-04, data/night_2026-10-03/guards2/) a partial feed's corner
#    pair totalling exactly one. The full feed has 79 such matches in 64,299
#    (0.12%), and a Poisson on both teams' corner rates in their other
#    matches predicts 75 of its 77 measured ones; the partial feeds have
#    1,646 in 36,254 (4.54%) where the same model predicts 70 of 970. The
#    payloads look half-counted (where they carry them, median throw-ins 1
#    and goal kicks 0 a match, against 38 and 14 beside five or more
#    corners). Expected genuine
#    losses: ~70 matches. Total 2 is also high there (1.68% vs 0.57%) but
#    that is about two thirds placeholder at most, so it is not refused.
PARTIAL_FEED_MIN_TOTAL: dict[str, float] = {"cornerKicks": 1.0}
IMPLIED_BY_ZERO: dict[str, frozenset[str]] = {
    # No shot at all means none of its parts.
    "totalShotsOnGoal": frozenset({"shotsOnGoal", "shotsOffGoal"}),
}


def zero_pair_not_recorded(
    key: str, all_stats: dict[str, tuple[float, float]] | None
) -> str | None:
    """Why this full-match pair is the provider not counting, or None.

    A 0-0 (clauses a and b), or a partial feed's total at or under
    PARTIAL_FEED_MIN_TOTAL (clause c: a single corner).

    ``all_stats`` is the payload's ALL period. Returns a short note naming
    the evidence (the clause and the companion), so a gap can say why.
    """
    if key not in ZERO_PAIR_GUARDED or not all_stats:
        return None
    pair = all_stats.get(key)
    if pair is None:
        return None
    full_feed = FULL_FEED_MARKER in all_stats
    floor = PARTIAL_FEED_MIN_TOTAL.get(key)
    if not full_feed and floor is not None and 0 < pair[0] + pair[1] <= floor:
        return (
            f"{key} {pair[0]:g}-{pair[1]:g} in a partial feed (no {FULL_FEED_MARKER}):"
            f" a total of {floor:g} or less is not a count"
        )
    if pair[0] != 0 or pair[1] != 0:
        return None
    if full_feed and key not in NEED_FULL_FEED:
        # Offsides 0-0 is a common genuine result in the full feed (2.46%
        # as sent; 4.82% once the per-half shape's omitted 0-0s are restored,
        # fill_omitted_zero_pairs), and a placeholder companion only doubles
        # it there (tackles 4.7% vs 2.1%): about half of what clause b would
        # refuse would be real. In the partial feeds the 0-0s clause b keeps
        # are 8.18%, ~3.4 points over that genuine rate, and no companion
        # measured on 2026-10-04 separates them cleanly: a half-counted
        # companion (corners total 1, throw-ins under 15, free kicks under
        # 10) catches 251 at an expected 60 genuine; a competition-level
        # cut at a 25% 0-0 rate 285 at 39 (data/night_2026-10-03/guards2/).
        return None
    implied = IMPLIED_BY_ZERO.get(key, frozenset())
    for other in sorted(all_stats):
        if other == key or other in implied:
            continue
        companion = all_stats[other]
        if stat_is_untracked(other, companion):
            seen = f"{companion[0]:g}-{companion[1]:g}"
            return f"{key} 0-0 beside placeholder {other} {seen}"
        if other in PLACEHOLDER_COMPANIONS and companion[0] == 0 and companion[1] == 0:
            return f"{key} 0-0 beside {other} 0-0"
    if key in NEED_FULL_FEED and not full_feed:
        return f"{key} 0-0 in a partial feed (no {FULL_FEED_MARKER})"
    return None

TENNIS_METRICS = {
    "games_total": {"sofascore": "gamesWon", "is_total": True},
    "games_won_for": {"sofascore": "gamesWon", "is_total": False},
    "sets_total": {"sofascore": "sets_from_listing", "is_total": True},
    "aces_total": {"sofascore": "aces", "is_total": True},
    "aces_for": {"sofascore": "aces", "is_total": False},
    "double_faults_total": {"sofascore": "doubleFaults", "is_total": True},
    "double_faults_for": {"sofascore": "doubleFaults", "is_total": False},
    "tiebreaks_total": {"sofascore": "tiebreaks", "is_total": True},
    # F45 — the serve markets Superbet prices and this pipeline could not read.
    #
    # "Liczba asow + podwojnych bledow" is a market in its own right, match and
    # per player, and it is NOT the sum of an aces row and a double-faults row:
    # those are two separate claims with two separate ladders, while this is one
    # quantity with one. Summing the two metrics per observation is the only way
    # to get its sample.
    "serve_points_total": {"sofascore": "aces_plus_double_faults", "is_total": True},
    "serve_points_for": {"sofascore": "aces_plus_double_faults", "is_total": False},
    # Per set. Sofascore keys /statistics by set for every serve statistic —
    # 1,291 of the 1,992 cached tennis events carry both "1ST" and "2ND", and
    # 434 reach "3RD". No `period_complement` is declared on purpose: sets do
    # not partition a match the way halves do, so the 1ST + 2ND == ALL check
    # that guards the football metrics would refuse every three-set match.
    "aces_set1_total": {"sofascore": "aces", "is_total": True, "period": "1ST"},
    "aces_set1_for": {"sofascore": "aces", "is_total": False, "period": "1ST"},
    "aces_set2_total": {"sofascore": "aces", "is_total": True, "period": "2ND"},
    "aces_set2_for": {"sofascore": "aces", "is_total": False, "period": "2ND"},
    "double_faults_set1_total": {
        "sofascore": "doubleFaults",
        "is_total": True,
        "period": "1ST",
    },
    "double_faults_set1_for": {
        "sofascore": "doubleFaults",
        "is_total": False,
        "period": "1ST",
    },
    "double_faults_set2_total": {
        "sofascore": "doubleFaults",
        "is_total": True,
        "period": "2ND",
    },
    "double_faults_set2_for": {
        "sofascore": "doubleFaults",
        "is_total": False,
        "period": "2ND",
    },
    "serve_points_set1_total": {
        "sofascore": "aces_plus_double_faults",
        "is_total": True,
        "period": "1ST",
    },
    "serve_points_set1_for": {
        "sofascore": "aces_plus_double_faults",
        "is_total": False,
        "period": "1ST",
    },
    "serve_points_set2_total": {
        "sofascore": "aces_plus_double_faults",
        "is_total": True,
        "period": "2ND",
    },
    "serve_points_set2_for": {
        "sofascore": "aces_plus_double_faults",
        "is_total": False,
        "period": "2ND",
    },
    # F54 — a player's games in one set. THE per-player tennis market, and the
    # largest single family this pipeline was not reading: 827 priced markets
    # across 166 of 2026-09-22's tennis fixtures, every one of them dropped.
    #
    # They were not dropped for want of a mapping. `classify_market` matched
    # "1. set - Kenta Kawada liczba gemow" on the no-dash games pattern (F38),
    # read the subject as "1. set - Kenta Kawada", and `_SUBJECT_IS_SCOPE`
    # then refused it — correctly, because at that point the only metric on
    # offer was the whole-match `games_won_for` and pricing a set line off a
    # whole-match sample is F29's defect. The guard was right and the metric
    # was missing; this is the metric.
    #
    # The source is NOT /statistics. `gamesWon` is absent there on 35% of
    # cached tennis events (F46) and is never keyed by set — checked over the
    # cache, tennis periods carry `aces` and `doubleFaults` and nothing else.
    # The set score in the listing *is* the quantity: `homeScore.periodN` is
    # how many games that player won in set N, and `check_identities` has
    # always asserted sum(period1..5) == gamesWon, so the per-set figure is a
    # term of an invariant this pipeline already enforces.
    #
    # A set that was not played has no `periodN` key, so it produces no
    # observation rather than a zero (L1/L2) — which is also what Superbet
    # does with the bet: an unplayed third set voids, it does not settle at 0.
    "games_won_set1_for": {
        "sofascore": "games_from_listing",
        "is_total": False,
        "set_index": 1,
    },
    "games_won_set2_for": {
        "sofascore": "games_from_listing",
        "is_total": False,
        "set_index": 2,
    },
    "games_won_set3_for": {
        "sofascore": "games_from_listing",
        "is_total": False,
        "set_index": 3,
    },
    # Both players' games in one set — Superbet's "1. set - liczba gemow",
    # quoted on 246 of 2026-09-23's tennis fixtures and sent to
    # unmapped_markets on every one. The same listing field as the per-player
    # metric above, summed: the set score IS the games, so the value is one of
    # 6, 7, 8, 9, 10, 12, 13 and never 11 (rarely 14+: an advantage set with no
    # tiebreak at 6-6 - an 8-6 set is in the cache, event 15324486).
    "games_set1_total": {
        "sofascore": "games_from_listing",
        "is_total": True,
        "set_index": 1,
    },
    "games_set2_total": {
        "sofascore": "games_from_listing",
        "is_total": True,
        "set_index": 2,
    },
}


def extract_flat_statistics(
    statistics: dict[str, Any] | None,
) -> dict[str, dict[str, tuple[float, float]]]:
    """Flatten /statistics into ``{period: {key: (home, away)}}``.

    Search is flat across every group of a period (PULAPKA #2): ``offsides``
    lives under ``Attack``, ``shotsOnGoal`` under ``Shots``, and filtering on
    ``groupName == "Match overview"`` loses half the table in silence.

    A key whose value is missing or non-numeric is **omitted**, never defaulted
    to 0.0 — a zero the provider never sent is the fabrication this pipeline
    exists to avoid (L1/L2).
    """
    flat: dict[str, dict[str, tuple[float, float]]] = {}
    if not statistics:
        return flat
    for period in statistics.get("statistics", []):
        period_name = period.get("period", "ALL")
        bucket = flat.setdefault(period_name, {})
        for group in period.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                if not key:
                    continue
                raw_home = item.get("homeValue")
                raw_away = item.get("awayValue")
                if raw_home is None or raw_away is None:
                    continue
                try:
                    bucket[key] = (float(raw_home), float(raw_away))
                except (TypeError, ValueError):
                    continue
    fill_omitted_zero_pairs(flat)
    return flat


# A zero the provider omits (2026-10-04, data/night_2026-10-03/guards2/).
# Sofascore's full football feed (the payload carrying `passes`) comes in two
# shapes: with a per-half breakdown (1ST/2ND) and without. The per-half shape
# drops an item whose full-match pair is 0-0 - measured over the 31,116 cached
# per-half full-feed payloads: redCards 0-0 is present 129 times and absent
# 25,268, offsides 0-0 present 2 times and absent 1,554 (4.99%, against a 0-0
# rate of 4.65% in the 33,188 payloads without halves, which keep the item),
# yellowCards 0-0 present 2 and absent 943. Independent checks: the per-player
# lineups of all 205 offsides-absent events that have them sum totalOffside
# to 0; of the yellowCards-absent events with card incidents, all 84 carry
# only red cards or cards to staff, never a yellow. Read as "absent" these
# were STAT_KEY_ABSENT and every genuine nil-nil left the offsides sample and
# the card sample - only the zeros, so both read high. Only the keys measured
# here are filled, only in that payload shape, and a key the payload sends
# is never touched. (fouls absent there, 166 times, is untracked - a match
# has ~25 - and is not filled.)
OMITTED_ZERO_KEYS = ("offsides", "yellowCards")


def fill_omitted_zero_pairs(flat: dict[str, dict[str, tuple[float, float]]]) -> None:
    """Restore the 0-0 the per-half full feed omitted (in place)."""
    whole = flat.get("ALL")
    if not whole or FULL_FEED_MARKER not in whole or "1ST" not in flat:
        return
    for key in OMITTED_ZERO_KEYS:
        if key in whole:
            continue
        if any(key in flat.get(p, {}) for p in ("1ST", "2ND")):
            # A half carries it, so the match is not 0-0: not this shape.
            continue
        for period in ("ALL", "1ST", "2ND"):
            if period in flat:
                flat[period][key] = (0.0, 0.0)


def infer_best_of(event: dict[str, Any]) -> int | None:
    """Match format (3 or 5) for a *completed* tennis match, from the listing.

    ``defaultPeriodCount`` is the field that states the format, but it lives on
    ``/event/{id}`` only — it is absent from all 30 events of the recorded
    listing ``evidence/team_275923_events_last_0.json``. Filtering a sample on
    it against a listing therefore rejects every historical match and leaves
    tennis with no sample at all, which looks exactly like missing data (L14).

    The listing does decide the question, though, without another call: the
    winner's ``current`` is the number of sets they won, and that number is
    unambiguous.

        3 sets won -> best of 5   (a best-of-3 cannot reach three)
        2 sets won -> best of 3   (a best-of-5 winner needs three)

    Anything else (a retirement, an abandoned match) returns None, and the
    caller must not guess. Verified against the recorded listing: event
    15345277 (Australian Open) reads 3 -> BO5, event 15543167 (Doha) reads
    2 -> BO3.
    """
    home = event.get("homeScore")
    away = event.get("awayScore")
    if not isinstance(home, dict) or not isinstance(away, dict):
        return None
    home_sets = home.get("current")
    away_sets = away.get("current")
    if not isinstance(home_sets, int) or not isinstance(away_sets, int):
        return None

    sets_won = max(home_sets, away_sets)
    if sets_won == 3:
        return 5
    if sets_won == 2:
        return 3
    return None


def _incident_player_key(incident: dict[str, Any]) -> str | None:
    """Stable identity for the player an incident belongs to."""
    player = incident.get("player")
    if isinstance(player, dict) and player.get("id") is not None:
        return f"id:{player['id']}"
    name = incident.get("playerName")
    if isinstance(name, dict):
        name = name.get("name")
    if name:
        return f"name:{name}"
    return None


def _is_staff_card(incident: dict[str, Any]) -> bool:
    """A card to the coaching staff: Sofascore sets ``manager``, not ``player``."""
    return bool(incident.get("manager")) and not incident.get("player")


# An incident list that is no card record (2026-10-04,
# data/night_2026-10-03/guards2/). Sofascore's lower-league incident feeds
# carry goals and dismissals only: no substitution, and a yellow card only
# sometimes. Measured over the cache: of the 25,256 partial-statistics events
# whose incident list has no substitution, 22,063 show yellowCards > 0 and
# 17,079 of those carry no card incident at all; of the 4,098 that carry
# cards but no yellow, 3,671 have yellowCards > 0 (red cards listed, the
# yellows not). Where the list has substitutions the incident yellows equal
# the statistic on 93% of full-feed and 83% of partial-feed events. In the
# full feed a match with a red card and no yellow is 0.22% of matches; a
# no-substitution list with red cards and no yellow is 58% of the 8,102
# carded no-substitution lists of events without statistics. Read as card
# points such a list counts the red cards and nothing else - a 7-card match
# reads 2.
#
# So a list without a single substitution is a card record only when it
# shows a yellow card. Without one:
#   - a red / second-yellow / staff card: CARDS_NOT_RECORDED (5,908 events
#     without statistics, 4,098 with; genuine red-only matches expected at
#     ~0.22%, i.e. ~140 + ~55);
#   - no card at all beside yellowCards 0-0: ZERO_NOT_RECORDED. Those 0-0s
#     are 9.97% of such events against ~3% of full-feed matches with no card
#     (genuine: ~760 of the 2,518 refused would be real). They are refused
#     anyway because their inclusion depends on their value: in this feed a
#     carded match yields a card value only when the list happens to carry a
#     card (about one in four), a 0-0 always - so even the genuine zeros
#     entered the sample at four times the weight of everything else (32% of
#     the feed's card values were 0-0).
INCIDENT_FEED_DETAIL = "substitution"


def cards_not_recorded(
    incidents: dict[str, Any], all_stats: dict[str, tuple[float, float]] | None
) -> GapReason | None:
    """Why this incident list cannot be read as card points, or None."""
    listed = incidents.get("incidents", [])
    if any(inc.get("incidentType") == INCIDENT_FEED_DETAIL for inc in listed):
        return None
    card_incidents = [inc for inc in listed if inc.get("incidentType") == "card"]
    if any(
        inc.get("incidentClass") == "yellow"
        and not inc.get("rescinded", False)
        and not _is_staff_card(inc)
        for inc in card_incidents
    ):
        return None
    if card_incidents:
        return GapReason.CARDS_NOT_RECORDED
    yellow = (all_stats or {}).get("yellowCards")
    if yellow is not None and sum(yellow) == 0:
        return GapReason.ZERO_NOT_RECORDED
    return None


def calculate_cards_points(
    incidents: dict[str, Any] | None,
    all_stats: dict[str, tuple[float, float]] | None = None,
) -> tuple[float, float] | GapReason:
    """Superbet card points from /incidents (PLAN §5.4).

    Scoring: yellow = 1, straight red = 2, and a dismissal for a second yellow
    is worth 3 in total.

    §5.4a asked for one number to be measured: is ``yellowRed`` worth +1 (because
    Sofascore already emitted both yellows) or +3 (because it emitted none)?
    We do not answer it with a constant. The payload answers it per match: count
    how many ``yellow`` incidents that same player already carries and pay the
    remainder up to 3. That is correct under either convention — including a
    third one nobody predicted, where Sofascore emits exactly one yellow — so
    the family is right without a measurement, and stays right if Sofascore
    changes its mind.

    ``rescinded`` cards are dropped unconditionally (PULAPKA #4); a rescinded
    yellow also stops counting toward the second-yellow arithmetic, which is
    what the disciplinary record says happened.

    Cards shown to the coaching staff are dropped too. Superbet's football
    rules (Oficjalny Komunikat nr 06/2022, version of 16.12.2025, sections 1,
    2 and 4): "Kartki pokazane sztabowi szkoleniowemu oraz zawodnikom na
    ławce rezerwowych nie będą brane pod uwagę." Sofascore marks such a card
    with ``manager`` and no ``player`` (3,339 of them in the cache on
    2026-10-02; all 895 sampled had ``time`` -5); its own ``yellowCards`` statistic
    leaves them out on 87% of the events that carry one. A card with neither
    key is kept: that is a player Sofascore did not name, not a coach. A card
    to an unused substitute carries ``player`` and is still counted - telling
    it apart needs the lineups, which this function does not read.
    """
    # `not`, not `is None`: {} is the cache's "asked, got 404" (samples.py),
    # and read as a payload it graded a match as 0 cards in SETTLE and fed
    # 0:0 into calibration and the rating (review 2026-10-01).
    if not incidents:
        # A missing payload is not a zero (L3).
        return GapReason.NO_INCIDENTS

    not_recorded = cards_not_recorded(incidents, all_stats)
    if not_recorded is not None:
        return not_recorded

    cards = [
        inc
        for inc in incidents.get("incidents", [])
        if inc.get("incidentType") == "card"
        and not inc.get("rescinded", False)
        and not _is_staff_card(inc)
    ]

    # An incident list with no card in it is only a zero when /statistics
    # says so. Measured on the cache 2026-09-26: of the finished events whose
    # incidents carry no card, 8,490 had yellowCards > 0 in /statistics and
    # 25,295 had no statistics at all (goal-only coverage), against 1,791
    # with yellowCards 0:0 - a 4.3% zero rate among tracked matches, which is
    # what football looks like. Reading the absence as zero cards had pulled
    # the cards_points_total prior from ~4.5 to 2.63.
    if not any(
        inc.get("incidentType") == "card" for inc in incidents.get("incidents", [])
    ):
        yellow = (all_stats or {}).get("yellowCards")
        if yellow is None or sum(yellow) > 0:
            return GapReason.STAT_KEY_ABSENT
        return 0.0, 0.0

    yellows_by_player: dict[str, int] = {}
    for inc in cards:
        if inc.get("incidentClass") == "yellow":
            key = _incident_player_key(inc)
            if key:
                yellows_by_player[key] = yellows_by_player.get(key, 0) + 1

    home = 0.0
    away = 0.0
    for inc in cards:
        cls = inc.get("incidentClass")
        if cls == "yellow":
            pts = 1.0
        elif cls == "red":
            pts = 2.0
        elif cls == "yellowRed":
            key = _incident_player_key(inc)
            already = yellows_by_player.get(key, 0) if key else 0
            # A second-yellow dismissal is 3 points in total; pay only the part
            # the separate yellow incidents have not already paid.
            pts = float(max(0, 3 - already))
        else:
            continue

        if inc.get("isHome", False):
            home += pts
        else:
            away += pts

    return home, away


# Counting statistics whose halves must add up to the full-match figure.
# Reported, never blocking: 0.9-2.2% divergence is the normal noise floor for
# this class of data, so rejecting on it would throw away good observations.
HALVES_CHECKED_KEYS = (
    "cornerKicks",
    "yellowCards",
    "fouls",
    "offsides",
    "totalShotsOnGoal",
    "shotsOnGoal",
)


def check_halves_identity(
    flat_stats: dict[str, dict[str, tuple[float, float]]],
) -> list[str]:
    """1ST + 2ND == ALL for counting keys (PLAN §5.5, reported not blocking)."""
    divergences: list[str] = []
    all_stats = flat_stats.get("ALL")
    first = flat_stats.get("1ST")
    second = flat_stats.get("2ND")
    if not all_stats or not first or not second:
        return divergences

    for key in HALVES_CHECKED_KEYS:
        if key not in all_stats or key not in first or key not in second:
            continue
        for side in (0, 1):
            halves = first[key][side] + second[key][side]
            whole = all_stats[key][side]
            if abs(halves - whole) > 1e-6:
                divergences.append(
                    f"{key}[{'home' if side == 0 else 'away'}]: "
                    f"1ST+2ND={halves:g} != ALL={whole:g}"
                )
    return divergences


def check_identities(
    flat_stats: dict[str, dict[str, tuple[float, float]]],
    incidents: dict[str, Any] | None,
    listing_event: dict[str, Any],
    sport: str,
) -> GapReason | None:
    """The four blocking internal identities of PLAN §5.5.

    With one provider there is nobody to disagree with, so the payload has to
    disagree with itself. A divergence here is a transcription signal, not
    noise: the observation is rejected, never averaged.
    """
    if "ALL" in flat_stats:
        stats = flat_stats["ALL"]
        if (
            "totalShotsOnGoal" in stats
            and "shotsOnGoal" in stats
            and "shotsOffGoal" in stats
            and "blockedScoringAttempt" in stats
        ):
            # Shots in the woodwork are a fourth category this sum omitted, and
            # the gate blocked 30.5% of matches where the real transcription
            # error rate is 1.4% — 22 times more than it should (F28). Worse,
            # it blocked them *directionally*: a shot off the post correlates
            # with shooting a lot, so the rejected matches had median shots 25
            # against 23 and median corners 10 against 9. The sample lost
            # attacking matches systematically, and a one-way shift is exactly
            # the kind that does not come out in the wash.
            #
            # "base + hitWoodwork == total" is the obvious repair and it is
            # also wrong: it still blocks 70 matches, and their residuals are
            # *negative* (-1 in 62 cases, -2 in 11), meaning the woodwork shot
            # is already counted inside one of the three categories there.
            # Sofascore is not consistent about double-counting, so no exact
            # identity is universally true. Bounding the discrepancy by the
            # number of woodwork shots admits both conventions and still
            # catches the genuine 1.4%.
            woodwork = stats.get("hitWoodwork", (0.0, 0.0))
            for side in (0, 1):
                s_on = stats["shotsOnGoal"][side]
                s_off = stats["shotsOffGoal"][side]
                s_blk = stats["blockedScoringAttempt"][side]
                s_tot = stats["totalShotsOnGoal"][side]
                if abs(s_tot - (s_on + s_off + s_blk)) > woodwork[side]:
                    return GapReason.INTERNAL_INCONSISTENT

    # {} ("asked, got 404") checks nothing: as a payload it read as zero goals
    # and failed every match with a goal.
    if sport == "football" and incidents:
        goal_incs = sum(
            1
            for i in incidents.get("incidents", [])
            if i.get("incidentType") == "goal" and not i.get("rescinded", False)
        )
        hs = listing_event.get("homeScore", {})
        as_ = listing_event.get("awayScore", {})

        c_h = hs.get("current")
        c_a = as_.get("current")

        if c_h is not None and c_a is not None:
            # Extra time / penalties goals might be excluded or included.
            # In regular matches without ET, current = normaltime.
            if hs.get("normaltime") is not None and hs.get("normaltime") == c_h:
                if goal_incs != c_h + c_a:
                    return GapReason.INTERNAL_INCONSISTENT

    if sport == "football":
        hs = listing_event.get("homeScore", {})
        if "period1" in hs and "period2" in hs and "normaltime" in hs:
            if hs["period1"] + hs["period2"] != hs["normaltime"]:
                return GapReason.INTERNAL_INCONSISTENT

    if sport == "tennis":
        if "ALL" in flat_stats and "gamesWon" in flat_stats["ALL"]:
            hs = listing_event.get("homeScore", {})
            as_ = listing_event.get("awayScore", {})
            # A 10-point match tiebreak sits in periodN as points (10-5), and
            # gamesWon counts it as NO game (266 of 270 cached cases: 6-2 1-6
            # 10-8 has gamesWon 7:8). Summing the raw periods made every such
            # match INTERNAL_INCONSISTENT - see tennis_score. The identity is
            # checked in gamesWon's own convention, the tiebreak set left out.
            games = set_games(hs, as_)
            if games is None:
                return GapReason.INTERNAL_INCONSISTENT
            tiebreaks = match_tiebreak_sets(hs, as_)
            counted = [g for i, g in enumerate(games, 1) if i not in tiebreaks]
            home_sets = sum(h for h, _ in counted)
            away_sets = sum(a for _, a in counted)

            # tiebreak games might need to be included?
            # The rule says: "suma gamesWon obu stron == suma gemów z wyniku setowego"
            # periodNTieBreak holds points, not games; the set score (7-6)
            # already counts the tie-break game itself.

            home_stat = flat_stats["ALL"]["gamesWon"][0]
            away_stat = flat_stats["ALL"]["gamesWon"][1]
            if home_sets != home_stat or away_sets != away_stat:
                return GapReason.INTERNAL_INCONSISTENT

    return None


def extract_metric(
    metric_name: str,
    sport: str,
    flat_stats: dict[str, dict[str, tuple[float, float]]],
    incidents: dict[str, Any] | None,
    listing_event: dict[str, Any],
    is_home: bool,
) -> float | GapReason:
    metrics_map = FOOTBALL_METRICS if sport == "football" else TENNIS_METRICS
    if metric_name not in metrics_map:
        return GapReason.STAT_KEY_ABSENT

    config = metrics_map[metric_name]
    sofascore_key = config["sofascore"]
    is_total = config["is_total"]

    # A match that went to extra time or penalties lasted 120 minutes, so its
    # corners, cards, fouls and shots describe a different game and must not
    # join a 90-minute sample. Its *goals* are recoverable: Sofascore records
    # the 90-minute score in homeScore.normaltime, which is what Superbet's
    # goal markets settle on. Admitted in the sample, refused here.
    if is_extra_time_event(listing_event) and not str(sofascore_key).startswith(
        "goals"
    ):
        return GapReason.EVENT_NOT_FINISHED

    if str(sofascore_key).startswith("goals") and goal_score_inconsistent(
        listing_event
    ):
        return GapReason.INTERNAL_INCONSISTENT

    if sofascore_key == "goals_from_listing":
        # normaltime for an extra-time match, current otherwise. A 2-1 after
        # extra time that was 1-1 at 90 minutes contributes 2, not 3.
        score = regulation_score(listing_event)
        if score is None:
            return GapReason.STAT_KEY_ABSENT
        h, a = score
        return h + a if is_total else h if is_home else a

    if sofascore_key == "goals_1h_from_listing":
        h = listing_event.get("homeScore", {}).get("period1")
        a = listing_event.get("awayScore", {}).get("period1")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        if h < 0 or a < 0:
            # A corrected score: event 8344189 lists period1 5, period2 -5,
            # current 10 (18 such halves in 913k cached matches, 2026-09-30).
            # A negative count is no count, and it crashed the rating's log.
            return GapReason.INTERNAL_INCONSISTENT
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "goals_2h_from_listing":
        h = listing_event.get("homeScore", {}).get("period2")
        a = listing_event.get("awayScore", {}).get("period2")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        if h < 0 or a < 0:
            # A corrected score: event 8344189 lists period1 5, period2 -5,
            # current 10 (18 such halves in 913k cached matches, 2026-09-30).
            # A negative count is no count, and it crashed the rating's log.
            return GapReason.INTERNAL_INCONSISTENT
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "cards_points_from_incidents":
        pts = calculate_cards_points(incidents, flat_stats.get("ALL"))
        if isinstance(pts, GapReason):
            return pts
        h, a = pts
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "gamesWon":
        # F46. `gamesWon` is missing from /statistics on **689 of the 1,992**
        # cached tennis events — 35% — while the set scores that define it sit
        # in the listing on every one of them. The old code read the statistic
        # or nothing, so a third of every games sample was burnt on slots that
        # produced no observation and were never refilled.
        #
        # The listing is not a second-best source here, it is the *same*
        # number: check_internal_consistency has always asserted
        # sum(period1..5) == gamesWon and refuses the event when they disagree,
        # so this branch is the quantity that invariant validates. Prefer the
        # statistic when present, so nothing that worked before changes.
        stats_all = flat_stats.get("ALL", {})
        hs_ = listing_event.get("homeScore", {})
        as_ = listing_event.get("awayScore", {})
        # One convention for every observation: a match tiebreak is ONE game
        # to its winner (bet365's rule; Superbet's is unverified). gamesWon
        # counts it as none and the raw periods as ten (6-4 6-7 10-5 read as
        # 22), so a match that had one is always read from the normalised
        # set score, whichever source is present - see tennis_score.
        #
        # The set score wins whenever it is readable (review 2026-10-04): it is
        # what Superbet settles on, and gamesWon can contradict it - event
        # 17149657, 6-7(9) 2-6, gamesWon 8:11 against 8:13 on the sets, graded
        # games_total 19 and flipped eight settled rows. Where the two agree
        # nothing changes; gamesWon is read only when the sets are unreadable.
        games = set_games(hs_, as_)
        if games:
            h = float(sum(g for g, _ in games))
            a = float(sum(g for _, g in games))
        elif "gamesWon" in stats_all and not match_tiebreak_sets(hs_, as_):
            h, a = stats_all["gamesWon"]
        else:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "games_from_listing":
        # See games_won_set{1,2,3}_for. The set score is the games, and a set
        # with no score in the listing was not played — that is missing data,
        # not a nil set.
        set_index = config.get("set_index")
        if not isinstance(set_index, int):
            return GapReason.STAT_KEY_ABSENT
        key = f"period{set_index}"
        hs_ = listing_event.get("homeScore", {})
        as_ = listing_event.get("awayScore", {})
        h = hs_.get(key)
        a = as_.get(key)
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        # A match tiebreak is not a set of games (10-5 is points), and a
        # score that is no set score at all (UTS) is no observation.
        if set_index in match_tiebreak_sets(hs_, as_) or set_games(hs_, as_) is None:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "sets_from_listing":
        # Both players contest the same sets, so "sets played" is the count of
        # period keys either score carries — not a per-side figure.
        home_score = listing_event.get("homeScore", {})
        away_score = listing_event.get("awayScore", {})
        set_keys = [f"period{i}" for i in range(1, 6)]
        played_sets = sum(1 for k in set_keys if k in home_score or k in away_score)
        if played_sets == 0:
            return GapReason.STAT_KEY_ABSENT
        return float(played_sets)

    if sofascore_key == "expectedGoals" and not listing_event.get("hasXg", False):
        return GapReason.STAT_KEY_ABSENT

    # Default stats lookup, in the period the metric declares. "ALL" for
    # everything that does not say otherwise, which is how it always behaved.
    period = str(config.get("period", "ALL"))

    if sofascore_key == "aces_plus_double_faults":
        if period not in flat_stats:
            return GapReason.NO_STATISTICS
        bucket = flat_stats[period]
        # Both halves of the sum, or none of it. Defaulting the missing one to
        # zero would invent a serve statistic (L1/L2), and it would do it in
        # the direction that makes UNDER look good.
        if "aces" not in bucket or "doubleFaults" not in bucket:
            return GapReason.STAT_KEY_ABSENT
        ace_h, ace_a = bucket["aces"]
        df_h, df_a = bucket["doubleFaults"]
        h, a = ace_h + df_h, ace_a + df_a
        return float(h + a) if is_total else float(h if is_home else a)
    if period not in flat_stats:
        # A half nobody reported is missing data, not a nil first half.
        return GapReason.NO_STATISTICS

    stats = flat_stats[period]
    if sofascore_key not in stats:
        return GapReason.STAT_KEY_ABSENT
    if stat_is_untracked(sofascore_key, flat_stats.get("ALL", {}).get(sofascore_key)):
        return GapReason.NO_STATISTICS
    if zero_pair_not_recorded(sofascore_key, flat_stats.get("ALL")):
        return GapReason.ZERO_NOT_RECORDED

    if period != "ALL":
        # The halves must add up to the match. Sofascore mostly agrees with
        # itself — measured across 2,174 cached events carrying all three
        # periods, 1ST + 2ND == ALL held for 1757/1766 corner sides, 1746/1766
        # total shots, 1731/1742 fouls, 1735/1766 shots on target, 1693/1710
        # yellow cards, 1657/1680 offsides — but on 1-2% it does not, and
        # there is no way to tell which of the two figures is the wrong one.
        #
        # Refuse that single observation rather than the event: the same
        # match's ALL-period metrics are unaffected and keep their sample.
        # This is the per-statistic twin of the period1 + period2 ==
        # normaltime check in check_internal_consistency, which has guarded
        # the *score* since before any per-half statistic existed.
        # Only when the declared periods actually partition the match.
        # Football's two halves do. Tennis sets do NOT: set 1 + set 2 is the
        # whole match only when the match went two sets, so applying this to
        # aces_set1 would refuse every three-set match — 434 of the 1,992
        # cached tennis events reach a third set. A metric that cannot name
        # its complement is not checked.
        complement = config.get("period_complement")
        whole = flat_stats.get("ALL", {}).get(sofascore_key)
        other = (
            flat_stats.get(str(complement), {}).get(sofascore_key)
            if complement
            else None
        )
        if whole is not None and other is not None:
            this = stats[sofascore_key]
            for side in (0, 1):
                if abs(whole[side] - (this[side] + other[side])) > 1e-9:
                    return GapReason.INTERNAL_INCONSISTENT

    h, a = stats[sofascore_key]
    return float(h + a) if is_total else float(h if is_home else a)
