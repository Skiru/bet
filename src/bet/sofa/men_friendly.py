"""Men's national-team friendlies (Sofascore uniqueTournament 851): the goal
sample and the goals prior of such a fixture, behind two switches that are
off (bet.sofa.epochs.MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC,
MEN_FRIENDLY_BASELINE_FROM_UTC; operator's decision).

851 is on the friendly exclusion list since 2026-10-04
(config/sofa_friendly_competitions.json, comparability.is_friendly_event), so
no 851 match enters any sample, rating or replay. For an 851 FIXTURE that has
two consequences, measured on 2026-10-13
(docs/sofa/evidence/national_friendly_samples_2026-10-13.md,
scripts/sofa/measure_national_friendly_samples.py, 2,209 men's friendlies
2015-01-01..2026-10-12, NB log-loss of the shrunk centre, match bootstrap):

* the goal sample (comparability.SAME_COMPETITION_METRICS) cannot find the
  fixture's own competition in the pool and falls back to the newest ten
  competitive matches (variant D). Variant C - every pool match, friendlies
  and competitive alike, inside the window the newest ten 851 matches span
  (pick_friendly_window) - beat it on both markets with an as-of prior:
  goals_total C - D -0.0071 [-0.0127, -0.0015], goals_for -0.0140
  [-0.0196, -0.0086] (with the global prior -0.0211 / -0.0252);
* 851 has no league baseline (it is excluded from every fit), so the centre
  is shrunk toward the pooled prior - the global goals_total 3.26 - while
  men's friendlies average 2.54 goals (2,365 matches since 2015). The
  baseline here is the as-of mean of 851's own matches before the day
  (FriendlyBaseline), the "asof" prior of the measurement.

Women's friendlies (852) are not touched: on the same measurement their
same-competition sample (A) is the best variant and stays as it is.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.comparability import (
    SAME_COMPETITION_MIN,
    competition_id,
    pick_same_competition,
)
from bet.sofa.metrics import regulation_score

# International Friendly Games (men). 852 (women) is deliberately not here.
MEN_FRIENDLY_COMPETITION_ID = 851

# The markets the measurement covered. The half-match goal markets of
# SAME_COMPETITION_METRICS keep the usual sample (not measured).
MEN_FRIENDLY_GOAL_METRICS: frozenset[str] = frozenset({"goals_total", "goals_for"})

# The as-of prior of the measurement: at least this many 851 matches, from
# BASELINE_HISTORY_FROM, strictly before the day; below it the usual prior.
MIN_FRIENDLY_BASELINE_MATCHES = 30
BASELINE_HISTORY_FROM = datetime(2015, 1, 1, tzinfo=UTC)

# A cheap pre-filter of the listing index before a payload is parsed; the
# competition id of the parsed event decides.
_SLUG_PROBE = '"int-friendly-games"'


def is_men_friendly_fixture(sport: str, competition: int | None) -> bool:
    return sport == "football" and competition == MEN_FRIENDLY_COMPETITION_ID


def pick_friendly_window[T](
    newest_first: Sequence[T],
    competition: int,
    n: int,
    competition_of: Callable[[T], int | None],
    regular: Callable[[T], bool],
    ts_of: Callable[[T], int],
    *,
    knockout: bool = False,
    minimum: int = SAME_COMPETITION_MIN,
) -> list[T]:
    """Variant C of the measurement: every match of ``newest_first`` (a pool
    holding the friendlies) from the oldest of the newest ``n`` REGULAR
    matches of ``competition`` on; when there are fewer than ``minimum`` of
    them, or the fixture is a knockout, the newest ``n`` of the pool (B)."""
    picked = None if knockout else pick_same_competition(
        newest_first, competition, n, competition_of, regular, minimum)
    if picked is None:
        return list(newest_first[:n])
    oldest = min(ts_of(m) for m in picked)
    return [m for m in newest_first if ts_of(m) >= oldest]


@dataclass(frozen=True)
class FriendlyBaseline:
    """The mean regulation goals of a men's friendly over ``n`` 851 matches
    strictly before ``cut_ts`` (None below MIN_FRIENDLY_BASELINE_MATCHES)."""

    mean_total: float | None
    n: int
    cut_ts: int

    def prior(self, metric: str) -> tuple[float, str] | None:
        """(prior, note) for a measured goal metric, else None."""
        if self.mean_total is None or metric not in MEN_FRIENDLY_GOAL_METRICS:
            return None
        value = self.mean_total if metric == "goals_total" else self.mean_total / 2.0
        cut = datetime.fromtimestamp(self.cut_ts, UTC).strftime("%Y-%m-%d")
        return value, (
            f"PRIOR_MEN_FRIENDLY: competition {MEN_FRIENDLY_COMPETITION_ID} "
            f"{metric} {value:.4g} from {self.n} men's national-team friendlies "
            f"before {cut} (epochs.MEN_FRIENDLY_BASELINE; no fitted baseline)")


def baseline_from_events(
    events: Iterable[Mapping[str, Any]],
    cut_ts: int,
    since_ts: int = int(BASELINE_HISTORY_FROM.timestamp()),
    minimum: int = MIN_FRIENDLY_BASELINE_MATCHES,
) -> FriendlyBaseline:
    """The as-of men's friendly baseline from listed events: finished 851
    matches between two national teams, regulation score, since_ts <= start
    < cut_ts, one per event id."""
    seen: set[int] = set()
    total, n = 0.0, 0
    for event in events:
        eid, ts = event.get("id"), event.get("startTimestamp")
        if not isinstance(eid, int) or not isinstance(ts, int) or eid in seen:
            continue
        if not since_ts <= ts < cut_ts:
            continue
        if competition_id(event) != MEN_FRIENDLY_COMPETITION_ID:
            continue
        if (event.get("status") or {}).get("type") != "finished":
            continue
        home, away = event.get("homeTeam") or {}, event.get("awayTeam") or {}
        if not (home.get("national") and away.get("national")):
            continue
        score = regulation_score(dict(event))
        if score is None:
            continue
        seen.add(eid)
        total += score[0] + score[1]
        n += 1
    return FriendlyBaseline(total / n if n >= minimum else None, n, cut_ts)


def load_men_friendly_baseline(db_path: str | Path, cut_ts: int) -> FriendlyBaseline:
    """baseline_from_events over the listed-event index (read-only). ~20 s on
    the full index, so SHEET asks only on a day with an 851 fixture and the
    switch on."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT event_json FROM sofa_listed_event WHERE sport = 'football' "
            "AND start_ts < ? AND instr(event_json, ?) > 0",
            (cut_ts, _SLUG_PROBE),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return baseline_from_events((json.loads(js) for (js,) in rows), cut_ts)
