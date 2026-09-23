"""A rating forecast for one tennis match, and every score market read off it.

Why this exists. SHEET priced a tennis game or set market from the two
players' last ten matches, counted as they came: a Grand Slam qualifier, two
Challengers and an ITF week pooled as if they were one quantity, and nobody
asking who the opponents in those ten matches were. On the five settled days
2026-09-18..22 (251 matches, 7,781 priced rows) that estimator scored a Brier
of 0.2552; a rating forecast built from the same Sofascore cache scored 0.2372
on the same rows, and Superbet's devigged price 0.2212. The rating does not
beat the price and is not claimed to; it is the better forecast of the two we
have.

What it is, in order:

  1. A surface-blended Elo (half overall, half the surface family), run in
     time order over every cached singles result, so a match is always rated
     only from the matches before it. K = 250 / (n + 5) ** 0.4, the
     FiveThirtyEight tennis schedule.
  2. A calibration layer per tier group (ITF / CH / TOUR) that re-weights the
     Elo logit and adds the context the Elo cannot see. Each term was measured
     on 30,421 matches with both players rated (z against zero):
       - hours on court in the previous 78 h, relative to the opponent (-6.7);
       - back from more than 21 days without a match (-4.1);
       - matches in the previous 7 days (-2.6);
       - recent Elo change - "form" - which *reverses* slightly once the
         rating is known (-2.0).
     Raw Elo is overconfident, least at ITF (slope 0.88) and most at
     Challenger (0.59); this layer is what corrects it. The coefficients are
     fitted by ``scripts/sofa/fit_tennis_rating.py`` into
     ``config/tennis_rating.json`` and never inside a pipeline run.
  3. The score distribution given that probability, read empirically: the
     player-perspective results of the ``NEIGHBOURS`` historical matches whose
     calibrated probability was closest. Games, sets, per-set games and
     tiebreaks all come off the same neighbours, so the markets of one match
     can never contradict each other, and the straight-sets / three-sets
     bimodality is in the data rather than assumed away. Scoping the
     neighbours by tier or by surface was measured and did not help
     (Brier 0.2372 all / 0.2377 tier / 0.2378 tier + surface), so it is global.

Best-of-five is not modelled - no neighbour is a five-setter - and a player
with fewer than ``MIN_RATED`` rated matches gets no forecast at all.
"""

from __future__ import annotations

import bisect
import json
import math
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("config/tennis_rating.json")

MIN_RATED = 10
NEIGHBOURS = 600
FEATURES: tuple[str, ...] = ("lp", "lps", "dmin78", "drest", "dn7", "dform")
REST_DAYS = 21.0

# The rating's weight against the devigged price, the same weight the sample
# carried before it (n / (n + K_TENNIS_LADDER_CENTRE) at n = 10). Chosen on
# the five settled days 2026-09-18..22, where Brier was flat from 0.10 to 0.30
# (0.2281-0.2283), so the choice barely matters; it is not fitted and rows
# priced through it say so.
W_TENNIS_RATING = 0.25

# Markets the rating prices, each measured against the settled record on the
# five days above (price + rating vs price + sample, 179 matches):
#   games_total     0.2418 vs 0.2460     games_won_for  0.2147 vs 0.2175
#   handicap_games  0.2405 vs 0.2501     sets_total     0.2268 vs 0.2309
# Out, and only for want of evidence: tiebreaks_total was WORSE on its 52 rows
# (0.2310 vs 0.2238), and the per-set games and most_games have no settled
# rows yet. ``probability`` can read all of them off the same neighbours; the
# gate is here so that no market is re-priced before it has been measured.
RATED_MARKETS = frozenset(
    {"games_total", "games_won_for", "sets_total", "handicap_games"}
)
_READABLE_MARKETS = RATED_MARKETS | {
    "tiebreaks_total",
    "games_set1_total",
    "games_set2_total",
    "games_won_set1_for",
    "games_won_set2_for",
    "most_games",
}
# A per-subject market: the probability is read from the subject's side.
_SUBJECT_MARKETS = frozenset(
    {"games_won_for", "games_won_set1_for", "games_won_set2_for",
     "handicap_games", "most_games"}
)


def blend_with_price(p_rating: float, market_p: float | None) -> float:
    """What SHEET publishes as p_central for a rated row."""
    if market_p is None:
        return p_rating
    return W_TENNIS_RATING * p_rating + (1.0 - W_TENNIS_RATING) * market_p


def tier_group(category_name: str) -> str:
    """ITF / CH / TOUR - the three levels whose Elo calibration differs."""
    name = category_name.strip()
    if name.startswith("ITF") or name.startswith("UTR") or name == "Juniors":
        return "ITF"
    if name in ("Challenger", "WTA 125"):
        return "CH"
    return "TOUR"


def surface_family(ground_type: str | None) -> str:
    """Sofascore labels one surface several ways (Clay / Red clay, Hard /
    Hardcourt outdoor); the rating needs the family, not the label."""
    g = (ground_type or "").lower()
    if "clay" in g:
        return "clay"
    if "grass" in g:
        return "grass"
    return "hard"


@dataclass(frozen=True)
class TennisResult:
    """One finished singles match, as the history carries it."""

    event_id: int
    ts: int
    tier: str
    surface: str
    home_id: int
    away_id: int
    home_won: bool
    sets: tuple[tuple[int, int], ...]
    minutes: float | None
    # Retired matches count as time on court but neither update the rating
    # nor enter the score distribution: their score is not a match score.
    completed: bool


def parse_event(event: Mapping[str, Any]) -> TennisResult | None:
    """A Sofascore listing event -> TennisResult, or None if it is not a
    finished singles result the model can use."""
    try:
        if event["tournament"]["category"]["sport"]["slug"] != "tennis":
            return None
        home, away = event["homeTeam"], event["awayTeam"]
    except (KeyError, TypeError):
        return None
    if home.get("type") != 1 or away.get("type") != 1:
        return None  # doubles
    status = event.get("status") or {}
    if status.get("type") != "finished":
        return None
    description = status.get("description")
    if description not in ("Ended", "Retired"):
        return None  # walkovers and removals have no match in them
    winner = event.get("winnerCode")
    if winner not in (1, 2):
        return None
    hs, as_ = event.get("homeScore") or {}, event.get("awayScore") or {}
    sets: list[tuple[int, int]] = []
    for i in range(1, 6):
        key = f"period{i}"
        if key in hs and key in as_:
            try:
                sets.append((int(hs[key]), int(as_[key])))
            except (TypeError, ValueError):
                return None
    if len(sets) < 1:
        return None
    timing = event.get("time") or {}
    durations = [timing.get(f"period{i}") for i in range(1, len(sets) + 1)]
    seconds = [float(d) for d in durations if isinstance(d, (int, float))]
    minutes = sum(seconds) / 60.0 if len(seconds) == len(durations) else None
    ts = event.get("startTimestamp")
    if not isinstance(ts, int):
        return None
    return TennisResult(
        event_id=int(event["id"]),
        ts=ts,
        tier=tier_group(str(event["tournament"]["category"].get("name", ""))),
        surface=surface_family(event.get("groundType")),
        home_id=int(home["id"]),
        away_id=int(away["id"]),
        home_won=winner == 1,
        sets=tuple(sets),
        minutes=minutes,
        completed=description == "Ended" and len(sets) >= 2,
    )


def load_history(db_path: str | Path) -> list[TennisResult]:
    """Every distinct finished singles match in the cached player listings,
    in time order."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        seen: dict[int, TennisResult] = {}
        for (events_json,) in conn.execute(
            "SELECT events_json FROM sofa_entity_events WHERE kind = 'last' "
            "AND events_json LIKE '%\"slug\": \"tennis\"%'"
        ):
            for event in json.loads(events_json).get("events", []):
                result = parse_event(event)
                if result is not None:
                    seen[result.event_id] = result
    finally:
        conn.close()
    return sorted(seen.values(), key=lambda r: (r.ts, r.event_id))


def _k(n: int) -> float:
    return 250.0 / float((n + 5) ** 0.4)


def _logit(p: float) -> float:
    p = min(max(p, 1e-3), 1.0 - 1e-3)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


@dataclass
class _PlayerLog:
    # (ts, elo_before, minutes) of every match, newest last.
    matches: list[tuple[int, float, float | None]] = field(default_factory=list)


class RatingBook:
    """Sequential Elo plus the per-player log the context terms are read from."""

    def __init__(self) -> None:
        self.overall: dict[int, float] = defaultdict(lambda: 1500.0)
        self.by_surface: dict[tuple[int, str], float] = defaultdict(lambda: 1500.0)
        self.n: dict[int, int] = defaultdict(int)
        self.n_surface: dict[tuple[int, str], int] = defaultdict(int)
        self.log: dict[int, _PlayerLog] = defaultdict(_PlayerLog)

    def rated(self, player: int) -> int:
        return self.n[player]

    def _context(self, player: int, ts: int) -> tuple[float, float, int, float]:
        """(minutes in 78 h, 1 if back from > REST_DAYS, matches in 7 d, form)."""
        entries = self.log[player].matches
        minutes = 0.0
        recent = 0
        for when, _, mins in reversed(entries):
            age = ts - when
            if age <= 0:
                continue
            if age > 7 * 86400:
                break
            recent += 1
            if age <= 78 * 3600 and mins is not None:
                minutes += mins
        rest = 0.0
        past = [e for e in entries if e[0] < ts]
        if past and (ts - past[-1][0]) / 86400.0 > REST_DAYS:
            rest = 1.0
        form = self.overall[player] - past[-5][1] if len(past) >= 5 else 0.0
        return minutes, rest, recent, form

    def features(self, home: int, away: int, surface: str, ts: int) -> dict[str, float]:
        eh = 0.5 * self.overall[home] + 0.5 * self.by_surface[(home, surface)]
        ea = 0.5 * self.overall[away] + 0.5 * self.by_surface[(away, surface)]
        p_blend = 1.0 / (1.0 + 10 ** ((ea - eh) / 400.0))
        gap = self.overall[away] - self.overall[home]
        p_overall = 1.0 / (1.0 + 10 ** (gap / 400.0))
        mh, rh, nh, fh = self._context(home, ts)
        ma, ra, na, fa = self._context(away, ts)
        return {
            "lp": _logit(p_overall),
            "lps": _logit(p_blend),
            "dmin78": (mh - ma) / 60.0,
            "drest": rh - ra,
            "dn7": float(nh - na),
            "dform": (fh - fa) / 100.0,
        }

    def update(self, r: TennisResult) -> None:
        for player in (r.home_id, r.away_id):
            self.log[player].matches.append((r.ts, self.overall[player], r.minutes))
        if not r.completed:
            return
        y = 1.0 if r.home_won else 0.0
        h, a, s = r.home_id, r.away_id, r.surface
        p = 1.0 / (1.0 + 10 ** ((self.overall[a] - self.overall[h]) / 400.0))
        kh, ka = _k(self.n[h]), _k(self.n[a])
        self.overall[h] += kh * (y - p)
        self.overall[a] -= ka * (y - p)
        gap = self.by_surface[(a, s)] - self.by_surface[(h, s)]
        ps = 1.0 / (1.0 + 10 ** (gap / 400.0))
        self.by_surface[(h, s)] += _k(self.n_surface[(h, s)]) * (y - ps)
        self.by_surface[(a, s)] -= _k(self.n_surface[(a, s)]) * (y - ps)
        self.n[h] += 1
        self.n[a] += 1
        self.n_surface[(h, s)] += 1
        self.n_surface[(a, s)] += 1


def calibrated_p(coefficients: Sequence[float], features: Mapping[str, float]) -> float:
    z = coefficients[0] + sum(
        c * features[name] for c, name in zip(coefficients[1:], FEATURES, strict=True)
    )
    return _sigmoid(z)


def fit_logistic(rows: Sequence[Sequence[float]], ys: Sequence[float]) -> list[float]:
    """Plain Newton-Raphson logistic regression with an intercept."""
    k = len(rows[0]) + 1
    w = [0.0] * k
    for _ in range(30):
        grad = [0.0] * k
        hess = [[0.0] * k for _ in range(k)]
        for x, y in zip(rows, ys, strict=True):
            xs = (1.0, *x)
            p = _sigmoid(sum(wi * xi for wi, xi in zip(w, xs, strict=True)))
            g = y - p
            v = p * (1.0 - p)
            for i in range(k):
                grad[i] += g * xs[i]
                for j in range(i, k):
                    hess[i][j] += v * xs[i] * xs[j]
        for i in range(k):
            hess[i][i] += 1e-6
            for j in range(i):
                hess[i][j] = hess[j][i]
        step = _solve(hess, grad)
        w = [wi + si for wi, si in zip(w, step, strict=True)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return w


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col and m[col][col] != 0.0:
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


@dataclass(frozen=True)
class Outcome:
    """One historical match from one player's side."""

    p: float
    games_for: int
    games_against: int
    sets: int
    tiebreaks: int
    set1: tuple[int, int]
    set2: tuple[int, int]


def _outcomes(r: TennisResult, p_home: float) -> list[Outcome]:
    home_sets = sum(1 for a, b in r.sets if a > b)
    away_sets = sum(1 for a, b in r.sets if b > a)
    if not r.completed or max(home_sets, away_sets) != 2 or len(r.sets) > 3:
        return []  # best-of-three only
    gh = sum(a for a, _ in r.sets)
    ga = sum(b for _, b in r.sets)
    tb = sum(1 for a, b in r.sets if (a, b) in ((7, 6), (6, 7)))
    s1, s2 = r.sets[0], r.sets[1]
    return [
        Outcome(p_home, gh, ga, len(r.sets), tb, s1, s2),
        Outcome(1.0 - p_home, ga, gh, len(r.sets), tb, (s1[1], s1[0]), (s2[1], s2[0])),
    ]


@dataclass(frozen=True)
class MatchForecast:
    """The rating's view of one match from the home player's side."""

    p_home: float
    neighbours_home: tuple[Outcome, ...]
    neighbours_away: tuple[Outcome, ...]
    rated_home: int
    rated_away: int

    def p_side_wins(self, side: str) -> float:
        return self.p_home if side == "side_a" else 1.0 - self.p_home

    def probability(
        self, market: str, side: str | None, line: float, direction: str
    ) -> float | None:
        """The rating's P(selection wins) for a market SHEET lets it price."""
        if market not in RATED_MARKETS:
            return None
        return self.read(market, side, line, direction)

    def read(
        self, market: str, side: str | None, line: float, direction: str
    ) -> float | None:
        """P(selection wins) read off the neighbours, for any score market -
        including the ones not yet measured well enough to be priced.

        A push (an integer line landing exactly) counts as not winning either
        side, so OVER + UNDER can sum to less than one on an integer line."""
        if market not in _READABLE_MARKETS:
            return None
        if market == "most_games" and side == "draw":
            level = sum(
                1 for o in self.neighbours_home if o.games_for == o.games_against
            )
            return level / len(self.neighbours_home) if self.neighbours_home else None
        if market in _SUBJECT_MARKETS:
            if side not in ("side_a", "side_b"):
                return None
            pool = self.neighbours_home if side == "side_a" else self.neighbours_away
        else:
            pool = self.neighbours_home
        if not pool:
            return None

        def value(o: Outcome) -> float:
            if market == "games_total":
                return o.games_for + o.games_against
            if market == "games_won_for":
                return o.games_for
            if market == "sets_total":
                return o.sets
            if market == "tiebreaks_total":
                return o.tiebreaks
            if market == "games_set1_total":
                return sum(o.set1)
            if market == "games_set2_total":
                return sum(o.set2)
            if market == "games_won_set1_for":
                return o.set1[0]
            if market == "games_won_set2_for":
                return o.set2[0]
            # handicap_games and most_games: the subject's margin.
            return o.games_for - o.games_against

        if market == "handicap_games":
            # "X (+5.5)" wins when X's margin exceeds -5.5 (derived.probability).
            wins = sum(1 for o in pool if value(o) > -line)
            return wins / len(pool) if direction == "OVER" else None
        if market == "most_games":
            wins = sum(1 for o in pool if value(o) > 0)
            return wins / len(pool) if direction == "OVER" else None
        over = sum(1 for o in pool if value(o) > line)
        under = sum(1 for o in pool if value(o) < line)
        return (over if direction == "OVER" else under) / len(pool)

    def p_side_wins_a_set(self, side: str) -> float:
        pool = self.neighbours_home if side == "side_a" else self.neighbours_away
        return sum(1 for o in pool if won_a_set(o)) / len(pool)


def won_a_set(o: Outcome) -> bool:
    # In best of three a deciding set means both players won one; otherwise
    # the player won a set only by winning set one or set two.
    return o.sets == 3 or o.set1[0] > o.set1[1] or o.set2[0] > o.set2[1]


class TennisRatingModel:
    """Ratings and the neighbour table, built from history before a cut."""

    def __init__(
        self,
        book: RatingBook,
        coefficients: Mapping[str, Sequence[float]],
        table: list[Outcome],
    ) -> None:
        self.book = book
        self.coefficients = coefficients
        self._table = sorted(table, key=lambda o: o.p)
        self._keys = [o.p for o in self._table]

    @property
    def table_size(self) -> int:
        return len(self._table)

    def _neighbours(self, p: float) -> tuple[Outcome, ...]:
        if len(self._table) < NEIGHBOURS:
            return ()
        i = bisect.bisect_left(self._keys, p)
        lo, hi = i, i
        while hi - lo < NEIGHBOURS:
            left = p - self._keys[lo - 1] if lo > 0 else math.inf
            right = self._keys[hi] - p if hi < len(self._keys) else math.inf
            if left <= right:
                lo -= 1
            else:
                hi += 1
        return tuple(self._table[lo:hi])

    def forecast(
        self,
        home_id: int,
        away_id: int,
        category_name: str,
        ground_type: str | None,
        kickoff: datetime,
    ) -> MatchForecast | None:
        rh, ra = self.book.rated(home_id), self.book.rated(away_id)
        if rh < MIN_RATED or ra < MIN_RATED:
            return None
        coefficients = self.coefficients.get(tier_group(category_name))
        if coefficients is None:
            return None
        feats = self.book.features(
            home_id, away_id, surface_family(ground_type), int(kickoff.timestamp())
        )
        p_home = calibrated_p(coefficients, feats)
        return MatchForecast(
            p_home=p_home,
            neighbours_home=self._neighbours(p_home),
            neighbours_away=self._neighbours(1.0 - p_home),
            rated_home=rh,
            rated_away=ra,
        )


def replay(
    history: Iterable[TennisResult], cut_ts: int
) -> tuple[RatingBook, list[tuple[TennisResult, dict[str, float]]]]:
    """Run the ratings over every match before ``cut_ts``; return the book and
    each rated match with the features it had BEFORE it was played."""
    book = RatingBook()
    rated: list[tuple[TennisResult, dict[str, float]]] = []
    for r in history:
        if r.ts >= cut_ts:
            break
        if (
            r.completed
            and book.rated(r.home_id) >= MIN_RATED
            and book.rated(r.away_id) >= MIN_RATED
        ):
            rated.append((r, book.features(r.home_id, r.away_id, r.surface, r.ts)))
        book.update(r)
    return book, rated


def fit_coefficients(
    rated: Sequence[tuple[TennisResult, Mapping[str, float]]],
) -> dict[str, dict[str, Any]]:
    """One logistic calibration per tier group, with the evidence it came from."""
    out: dict[str, dict[str, Any]] = {}
    by_tier: dict[str, list[tuple[TennisResult, Mapping[str, float]]]] = (
        defaultdict(list)
    )
    for r, f in rated:
        if len(r.sets) <= 3:
            by_tier[r.tier].append((r, f))
    for tier, rows in sorted(by_tier.items()):
        xs = [[f[name] for name in FEATURES] for _, f in rows]
        ys = [1.0 if r.home_won else 0.0 for r, _ in rows]
        out[tier] = {"coefficients": fit_logistic(xs, ys), "n": len(rows)}
    return out


def load_coefficients(
    path: Path = DEFAULT_CONFIG,
) -> tuple[dict[str, list[float]], dict[str, Any]] | None:
    """(coefficients by tier group, metadata) or None if never fitted."""
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if data.get("features") != list(FEATURES):
        # A config fitted on another feature list would be applied to the
        # wrong columns without a word.
        raise ValueError(
            f"{path}: features {data.get('features')} != {list(FEATURES)}"
        )
    coefficients = {
        tier: [float(c) for c in entry["coefficients"]]
        for tier, entry in data["tiers"].items()
    }
    return coefficients, {k: v for k, v in data.items() if k != "tiers"}


def build_model(
    history: Sequence[TennisResult],
    coefficients: Mapping[str, Sequence[float]],
    cut_ts: int,
) -> TennisRatingModel:
    """Ratings before the cut and the neighbour table from rated matches."""
    book, rated = replay(history, cut_ts)
    table: list[Outcome] = []
    for r, feats in rated:
        c = coefficients.get(r.tier)
        if c is None:
            continue
        table.extend(_outcomes(r, calibrated_p(c, feats)))
    return TennisRatingModel(book, coefficients, table)
