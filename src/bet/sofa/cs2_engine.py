"""CS2 engine: a model probability for each CS2 line, from pre-match history.

The measurement's second half. CS2_SETTLE grades Superbet's price; this puts
a number of our own beside it, computed only from the cs2_* history that
existed before the series started, so the audit can ask the question every
sofa sport has to answer before it may reach a coupon: does the history beat
the devigged price, or only add noise to it? (In football it does not; see
the memory note sofa-model-loses-to-the-price.)

Leakage is the failure mode that would make the answer worthless, so it is
closed twice: history is cut at the EARLIER of Superbet's kickoff and
Sofascore's start (Sofascore routinely lists a series minutes before
Superbet's time), and the series being graded is excluded by id as well.

Models, by family (anything else returns None - never a guessed number):

- map_winner, match_winner: a map-level Elo (K = ELO_K), calibrated by a
  logistic fit with a home term on its own walk-forward predictions
  (RatingModel); the series from p(map) held constant, exact for best-of-
  1/2/3/5. Beats a constant only barely (match_winner 0.2423 vs 0.2462).
- maps_total, maps_handicap, team_maps: NO number - the constant-p series
  overpredicts three-map series (see ELO_FAMILIES).
- player_kills / _deaths / _assists / _headshots, team_kills: the player's
  (team's) last MAX_SAMPLE maps; a negative binomial (`engine.nb_survival`)
  when the predictive variance exceeds the mean, a continuity-corrected normal
  when it does not.
- map_rounds_total: the history's own base rate at the line - the teams'
  samples carried nothing about the next map's length.
- map_team_rounds: the team's frequency above the line, shrunk toward the
  base rate with K_ROUNDS pseudo-maps (beat a constant: 0.2380 vs 0.2417).
  Round totals are bounded and lumpy (13-x, then 16-14 / 19-17 in overtime).

An integer line's push is voided by grade(), so every family reports
P(side | no push). Every probability is clamped to engine's
[P_FLOOR, P_CEILING]. The constants in UNFITTED are chosen, not fitted, and
are reported as such beside every number they produce.

Measured on the stored history at review (2026-09-28, 2,084 series): raw Elo
per-map Brier 0.2446 (0.25 is a coin), favourites 7-10 pp overrated - which
the calibration exists to take out; kills near the player's own mean
calibrated but nearly uninformative (Brier 0.2485). The model is expected to
lose to the price; the audit is where that is measured, not assumed.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from bet.sofa.cs2 import Cs2Line, esports_name
from bet.sofa.engine import (
    P_CEILING,
    P_FLOOR,
    nb_survival,
    normal_cdf,
    predictive_sd,
)

ELO_START = 1500.0
ELO_K = 24.0
MIN_MAPS_RATED = 10  # both teams, before a winner-family number is given
MIN_SAMPLE = 8  # maps, for a count or round model
MAX_SAMPLE = 20  # most recent maps used for counts and rounds
MIN_FIT = 200  # walk-forward predictions (or maps) before a fit or base rate
K_ROUNDS = 20  # pseudo-maps of base rate behind a team's rounds frequency
MIN_VAR_RATIO = 0.5  # floor on predictive variance / mean for the normal branch
LOOKBACK_DAYS = 365
UNFITTED = (
    "ELO_K",
    "ELO_START",
    "MIN_MAPS_RATED",
    "MIN_SAMPLE",
    "MAX_SAMPLE",
    "MIN_FIT",
    "K_ROUNDS",
    "MIN_VAR_RATIO",
)

# Only the winner families. maps_total, team_maps and maps_handicap were
# modelled from the same p held constant through the series, and on the stored
# history that overpredicted a three-map series (0.482 against 0.424 on 876
# best-of-threes, 0.376 against 0.222 in the 0.3 band) - real series are more
# lopsided than any constant p allows, and the per-map calibration pushed it
# further the wrong way. Losing to a constant (0.2479 vs 0.2442) is a guess,
# not a model, so those families get no number until a series-level term
# earns one (review 2026-09-28, round 2).
ELO_FAMILIES = {"map_winner", "match_winner"}
COUNT_FAMILIES = {
    "player_kills",
    "player_deaths",
    "player_assists",
    "player_headshots",
    "team_kills",
}
ROUND_FAMILIES = {"map_rounds_total", "map_team_rounds"}
MODELLED = ELO_FAMILIES | COUNT_FAMILIES | ROUND_FAMILIES


def clamp(p: float) -> float:
    return max(P_FLOOR, min(P_CEILING, p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


# --- the series -------------------------------------------------------------------


@cache
def series_distribution(p_map: float, best_of: int) -> dict[tuple[int, int], float]:
    """Exact final-score distribution of a best-of-n with constant p per map.

    Keys are (team1 maps, team2 maps). Best-of-2 is not a race: both maps are
    played and 1-1 is a result. Anything else must be odd.
    """
    if not 0.0 <= p_map <= 1.0:
        raise ValueError(f"p_map {p_map} outside [0, 1]")
    q = 1.0 - p_map
    if best_of == 2:
        return {(2, 0): p_map * p_map, (1, 1): 2 * p_map * q, (0, 2): q * q}
    if best_of < 1 or best_of % 2 == 0:
        raise ValueError(f"best_of {best_of} is not 1, 2, 3 or 5")
    need = best_of // 2 + 1
    out: dict[tuple[int, int], float] = {}
    for losses in range(need):
        # The winner takes the last map: C(need - 1 + losses, losses) orders.
        orders = math.comb(need - 1 + losses, losses)
        out[(need, losses)] = orders * p_map**need * q**losses
        out[(losses, need)] = orders * q**need * p_map**losses
    return out


# --- ratings ----------------------------------------------------------------------


def elo_expected(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (r_b - r_a) / 400.0))


@dataclass
class EloBook:
    """Raw map-level Elo, replayed in time order."""

    ratings: dict[int, float] = field(default_factory=dict)
    played: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    def rating(self, team: int) -> float:
        return self.ratings.get(team, ELO_START)

    def rated(self, *teams: int) -> bool:
        return all(self.played[t] >= MIN_MAPS_RATED for t in teams)

    def update(self, winner: int, loser: int) -> None:
        r_w, r_l = self.rating(winner), self.rating(loser)
        delta = ELO_K * (1.0 - elo_expected(r_w, r_l))
        self.ratings[winner] = r_w + delta
        self.ratings[loser] = r_l - delta
        self.played[winner] += 1
        self.played[loser] += 1


def logit_diff(book: EloBook, home: int, away: int) -> float:
    """The rating gap on the logit scale: raw Elo is exactly sigmoid of it."""
    return (book.rating(home) - book.rating(away)) * math.log(10.0) / 400.0


def fit_logistic(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """(a, b) of P(y = 1) = sigmoid(a + b x), by Newton's method, ridged
    lightly toward raw Elo (a = 0, b = 1) so a short history cannot run away."""
    a, b, ridge = 0.0, 1.0, 1.0
    for _ in range(50):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys, strict=True):
            p = _sigmoid(a + b * x)
            w = p * (1.0 - p)
            ga += p - y
            gb += (p - y) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        ga += ridge * a
        gb += ridge * (b - 1.0)
        haa += ridge
        hbb += ridge
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-10:
            break
    return a, b


@dataclass
class RatingModel:
    """Map-level Elo, calibrated on its own pre-match history.

    Raw Elo overrated favourites on the stored history (predicted 0.743 for
    maps that went 0.673) and knew nothing of Sofascore's home side, which
    wins 54.0% of 3,591 maps. So P(home wins the map) = sigmoid(a + b d), d
    the rating gap in logits, with (a, b) fitted on walk-forward predictions -
    each series predicted from the ratings frozen at its start, as production
    uses them - and only on maps before the cut. Under MIN_FIT predictions it
    stays raw Elo (a = 0, b = 1).
    """

    book: EloBook
    a: float = 0.0
    b: float = 1.0
    n_fit: int = 0

    def p_map(self, team1: int, team2: int, team1_is_home: bool) -> float | None:
        if not self.book.rated(team1, team2):
            return None
        home, away = (team1, team2) if team1_is_home else (team2, team1)
        p_home = _sigmoid(self.a + self.b * logit_diff(self.book, home, away))
        return p_home if team1_is_home else 1.0 - p_home


# --- the history ------------------------------------------------------------------


StatRow = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class MapRow:
    event_id: int
    start_ts: int
    order: int
    home_id: int
    away_id: int
    home_rounds: int | None  # None when Sofascore has the winner but no rounds
    away_rounds: int | None
    home_won: bool
    # (team id, player id, folded name, stat -> value)
    players: tuple[tuple[int, int, str, StatRow], ...]


def load_history(
    conn: sqlite3.Connection, before_ts: int, exclude_event: int | None
) -> list[MapRow]:
    """Every finished map of a finished series that started before `before_ts`
    (and within LOOKBACK_DAYS), oldest first. `exclude_event` is dropped even
    if its start is earlier - it is the series being graded.

    A map with a winner but no rounds - 19% of the stored maps at review -
    is kept for the ratings and skipped by the rounds models.
    """
    since = before_ts - LOOKBACK_DAYS * 86400
    rows = conn.execute(
        """SELECT m.game_id, s.sofascore_event_id, s.start_ts, m.map_order,
                  s.home_id, s.away_id, m.home_rounds, m.away_rounds, m.winner_code
           FROM cs2_map m JOIN cs2_series s USING (sofascore_event_id)
           WHERE s.status_type = 'finished' AND m.status_type = 'finished'
             AND s.start_ts < ? AND s.start_ts >= ?
             AND ((m.home_rounds IS NOT NULL AND m.away_rounds IS NOT NULL
                   AND m.home_rounds != m.away_rounds)
                  OR m.winner_code IN (1, 2))
           ORDER BY s.start_ts, s.sofascore_event_id, m.map_order""",
        (before_ts, since),
    ).fetchall()
    players: dict[int, list[tuple[str, int, str, StatRow]]] = defaultdict(list)
    ids = [r[0] for r in rows]
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for gid, side, pid, name, k, d, a, h in conn.execute(
            f"SELECT game_id, side, player_id, player_name, kills, deaths, assists, "
            f"headshots FROM cs2_player_map WHERE game_id IN ({marks})",
            chunk,
        ):
            stats = tuple(
                (stat, v)
                for stat, v in (
                    ("kills", k),
                    ("deaths", d),
                    ("assists", a),
                    ("headshots", h),
                )
                if isinstance(v, int)
            )
            players[gid].append((str(side), int(pid), esports_name(str(name)), stats))
    out: list[MapRow] = []
    for gid, eid, ts, order, home_id, away_id, hr, ar, winner in rows:
        if exclude_event is not None and eid == exclude_event:
            continue
        has_rounds = hr is not None and ar is not None and hr != ar
        home_won = bool(hr > ar) if has_rounds else winner == 1
        rows_for_map = tuple(
            (home_id if side == "home" else away_id, pid, name, stats)
            for side, pid, name, stats in players.get(gid, [])
        )
        out.append(
            MapRow(
                eid,
                ts,
                order,
                home_id,
                away_id,
                hr if has_rounds else None,
                ar if has_rounds else None,
                home_won,
                rows_for_map,
            )
        )
    return out


def walk_forward(history: list[MapRow]) -> tuple[EloBook, list[tuple[float, float]]]:
    """Replay the history series by series: predict each series' maps from the
    ratings at its start as (logit gap home - away, home won), then update."""
    book = EloBook()
    points: list[tuple[float, float]] = []
    by_series: dict[int, list[MapRow]] = {}
    for m in history:
        by_series.setdefault(m.event_id, []).append(m)
    for maps in by_series.values():  # insertion order is chronological
        home, away = maps[0].home_id, maps[0].away_id
        if book.rated(home, away):
            d = logit_diff(book, home, away)
            points.extend((d, 1.0 if m.home_won else 0.0) for m in maps)
        for m in maps:
            winner, loser = (
                (m.home_id, m.away_id) if m.home_won else (m.away_id, m.home_id)
            )
            book.update(winner, loser)
    return book, points


def build_ratings(history: list[MapRow]) -> RatingModel:
    book, points = walk_forward(history)
    if len(points) < MIN_FIT:
        return RatingModel(book, n_fit=len(points))
    a, b = fit_logistic([x for x, _ in points], [y for _, y in points])
    return RatingModel(book, a, max(0.0, min(2.0, b)), len(points))


# --- the models ---------------------------------------------------------------------


@dataclass(frozen=True)
class ModelP:
    p: float  # for the line's own side, given no push
    n: int  # maps behind the number
    model: str


def side_given_no_push(p_over: float, p_under: float, over: bool) -> float | None:
    """P(side | not a push). grade() voids a push, so its mass belongs to
    neither side - an integer line would otherwise pour it all into UNDER."""
    total = p_over + p_under
    if total <= 1e-12:
        return None
    return (p_over if over else p_under) / total


def count_p(values: list[int], line: float, over: bool) -> ModelP | None:
    """P(OVER / UNDER the line) for a count, from a sample of it.

    Negative binomial when the predictive variance exceeds the mean; a
    continuity-corrected normal when it does not - deaths are bounded by the
    rounds played and were under-dispersed for a third of players, and a
    Poisson floor would widen them.
    """
    n = len(values)
    if n < MIN_SAMPLE:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    var_pred = predictive_sd(var, mean, n, apply_poisson_floor=False) ** 2
    lo, hi = math.floor(line), math.ceil(line)  # equal on an integer line
    if var_pred > mean:
        # nb_survival(m, v, k) = P(X > k). OVER 19.5 and OVER 20 both ask for
        # X > floor(line); UNDER 20 asks for X <= 19, i.e. 1 - P(X > 19).
        p_over = nb_survival(mean, var_pred, lo)
        p_under = 1.0 - nb_survival(mean, var_pred, lo - 1) if lo == hi else 1 - p_over
        model = "negative_binomial"
    else:
        # Floored: a constant sample ([5] * 8) otherwise has sd ~ 0 and claims
        # the clamp at once (round 2 review) - eight maps prove less than that.
        sd = math.sqrt(max(var_pred, MIN_VAR_RATIO * mean, 1e-9))
        p_over = 1.0 - normal_cdf((math.floor(line) + 0.5 - mean) / sd)
        p_under = normal_cdf((lo - 0.5 - mean) / sd) if lo == hi else 1 - p_over
        model = "normal"
    side = side_given_no_push(p_over, p_under, over)
    return None if side is None else ModelP(clamp(side), n, model)


def base_rate(values: list[int], line: float) -> float | None:
    """The history's own share above the line, pushes left out."""
    decided = [v for v in values if v != line]
    if len(decided) < MIN_FIT:
        return None
    return sum(1 for v in decided if v > line) / len(decided)


def shrunk_frequency(
    values: list[int], line: float, over: bool, base: float | None
) -> ModelP | None:
    """The sample's share on this side, shrunk toward the base rate with
    K_ROUNDS pseudo-maps; pushes left out of both, as grade() leaves them out.

    At review the plain Laplace frequency scored Brier 0.2587 against 0.2485
    for a constant rate on 1,356 first maps: a team's last twenty maps carry
    little of the next map's length, so the base rate has to carry the rest.
    """
    decided = [v for v in values if v != line]
    n = len(decided)
    if n < MIN_SAMPLE or base is None:
        return None
    hits = sum(1 for v in decided if (v > line) == over)
    prior = base if over else 1.0 - base
    p = (hits + K_ROUNDS * prior) / (n + K_ROUNDS)
    return ModelP(clamp(p), n, "shrunk_frequency")


def _team_maps(history: list[MapRow], team: int) -> list[MapRow]:
    return [m for m in history if team in (m.home_id, m.away_id)][-MAX_SAMPLE:]


def _rounds_maps(history: list[MapRow], team: int) -> list[MapRow]:
    """The team's last MAX_SAMPLE maps that carry rounds."""
    with_rounds = [
        m
        for m in history
        if team in (m.home_id, m.away_id) and m.home_rounds is not None
    ]
    return with_rounds[-MAX_SAMPLE:]


def total_rounds(maps: list[MapRow]) -> list[int]:
    return [
        m.home_rounds + m.away_rounds
        for m in maps
        if m.home_rounds is not None and m.away_rounds is not None
    ]


def own_rounds(maps: list[MapRow], team: int) -> list[int]:
    out: list[int] = []
    for m in maps:
        own = m.home_rounds if m.home_id == team else m.away_rounds
        if own is not None:
            out.append(own)
    return out


def both_sides_rounds(maps: list[MapRow]) -> list[int]:
    out: list[int] = []
    for m in maps:
        if m.home_rounds is not None and m.away_rounds is not None:
            out += [m.home_rounds, m.away_rounds]
    return out


def player_values(history: list[MapRow], team: int, name: str, stat: str) -> list[int]:
    """The player's last maps: found by his nickname on this team's recent maps,
    then followed by his Sofascore player id - across teams, since players
    move - so the sample is his, not a namesake's."""
    folded = esports_name(name)
    ids = {
        pid
        for m in _team_maps(history, team)
        for t, pid, nick, _ in m.players
        if t == team and nick == folded
    }
    if len(ids) != 1:
        return []
    (pid,) = ids
    values: list[int] = []
    for m in reversed(history):
        for _, p, _, stats in m.players:
            if p == pid:
                value = dict(stats).get(stat)
                if value is not None:
                    values.append(value)
        if len(values) >= MAX_SAMPLE:
            break
    return values


def team_kills(history: list[MapRow], team: int) -> list[int]:
    out: list[int] = []
    for m in _team_maps(history, team):
        kills = [dict(s).get("kills") for t, _, _, s in m.players if t == team]
        if len(kills) >= 5 and all(k is not None for k in kills):
            out.append(sum(k for k in kills if k is not None))
    return out


def model_probability(
    line: Cs2Line,
    team1_id: int,
    team2_id: int,
    team1: str,
    team2: str,
    best_of: int,
    history: list[MapRow],
    ratings: RatingModel,
    team1_is_home: bool,
) -> ModelP | None:
    """The model's probability for this side of this line, or None."""
    fam = line.family
    if fam not in MODELLED:
        return None
    subject = line.subject.strip()
    side_team = team1_id if subject == team1 else team2_id if subject == team2 else None

    if fam in ELO_FAMILIES:
        p = ratings.p_map(team1_id, team2_id, team1_is_home)
        if p is None:
            return None
        n = min(ratings.book.played[team1_id], ratings.book.played[team2_id])
        if fam == "map_winner":
            return ModelP(clamp(p if line.side == "T1" else 1.0 - p), n, "elo")
        try:
            dist = series_distribution(round(p, 6), best_of)
        except ValueError:
            return None
        if fam in ("match_winner", "maps_handicap"):
            hcp = line.line or 0.0
            p_t1 = sum(q for (a, b), q in dist.items() if a - b + hcp > 0)
            p_t2 = sum(q for (a, b), q in dist.items() if a - b + hcp < 0)
            side = side_given_no_push(p_t1, p_t2, line.side == "T1")
            return None if side is None else ModelP(clamp(side), n, "elo_series")
        if line.line is None or line.side not in ("OVER", "UNDER"):
            return None
        if fam == "maps_total":
            count = {score: score[0] + score[1] for score in dist}
        else:  # team_maps
            if side_team is None:
                return None
            idx = 0 if side_team == team1_id else 1
            count = {score: score[idx] for score in dist}
        p_over = sum(q for score, q in dist.items() if count[score] > line.line)
        p_under = sum(q for score, q in dist.items() if count[score] < line.line)
        side = side_given_no_push(p_over, p_under, line.side == "OVER")
        return None if side is None else ModelP(clamp(side), n, "elo_series")

    if line.line is None or line.side not in ("OVER", "UNDER"):
        return None
    over = line.side == "OVER"
    if fam == "map_rounds_total":
        # The history's base rate alone. With the two teams' own last maps
        # shrunk toward it, the score only ever approached the base rate as the
        # shrinkage grew (lines 19.5-23.5, K = 20/50/100, 1,326 first maps):
        # the teams' sample carried nothing about the next map's length.
        decided = [v for v in total_rounds(history) if v != line.line]
        base = base_rate(decided, line.line)
        if base is None:
            return None
        return ModelP(clamp(base if over else 1.0 - base), len(decided), "base_rate")
    if side_team is None:
        return None
    if fam == "map_team_rounds":
        base = base_rate(both_sides_rounds(history), line.line)
        values = own_rounds(_rounds_maps(history, side_team), side_team)
        return shrunk_frequency(values, line.line, over, base)
    if fam == "team_kills":
        return count_p(team_kills(history, side_team), line.line, over)
    stat = fam.removeprefix("player_")
    for team in (team1_id, team2_id):
        values = player_values(history, team, line.subject, stat)
        if values:
            return count_p(values, line.line, over)
    return None


# --- checking the engine against history --------------------------------------------


def _brier(ps: list[float], ys: list[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys, strict=True)) / len(ys)


def elo_backtest(history: list[MapRow], train_share: float = 0.7) -> dict[str, Any]:
    """Out-of-sample check of the rating model, the way production uses it.

    Each series is predicted from the ratings frozen at its start. The
    calibration is fitted on the first `train_share` of those predictions and
    scored on the rest; raw Elo is scored on the same held-out maps, so the two
    held-out figures are comparable. A sanity check on the engine, not a claim
    of edge - only CS2_SETTLE compares with the price.
    """
    _, points = walk_forward(history)
    cut = int(len(points) * train_share)
    train, test = points[:cut], points[cut:]
    result: dict[str, Any] = {
        "maps_predicted": len(points),
        "maps_held_out": len(test),
        "brier_raw_held_out": None,
        "brier_calibrated_held_out": None,
    }
    if not test:
        return result
    ys = [y for _, y in test]
    result["brier_raw_held_out"] = _brier([_sigmoid(x) for x, _ in test], ys)
    if len(train) >= MIN_FIT:
        a, b = fit_logistic([x for x, _ in train], [y for _, y in train])
        b = max(0.0, min(2.0, b))
        result["brier_calibrated_held_out"] = _brier(
            [_sigmoid(a + b * x) for x, _ in test], ys
        )
    return result


# --- model against price ---------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    family: str
    series: int
    sides: int
    brier_price: float
    brier_model: float
    brier_blend: float  # the plain average of the two probabilities

    @property
    def model_beats_price(self) -> bool:
        return self.brier_model < self.brier_price


def compare_to_price(rows: list[dict[str, Any]], label: str) -> Comparison | None:
    """Brier of the devigged price, of the model and of their average, on the
    graded sides that carry both. Lower is better; the same sides for all
    three, so the three numbers are comparable and nothing else is."""
    rs = [
        r for r in rows if r.get("fair_p") is not None and r.get("model_p") is not None
    ]
    if not rs:
        return None
    ys = [1.0 if r["outcome"] == "WIN" else 0.0 for r in rs]
    price = [float(r["fair_p"]) for r in rs]
    model = [float(r["model_p"]) for r in rs]
    return Comparison(
        family=label,
        series=len({r.get("superbet_event_id") for r in rs}),
        sides=len(rs),
        brier_price=_brier(price, ys),
        brier_model=_brier(model, ys),
        brier_blend=_brier(
            [(a + b) / 2 for a, b in zip(price, model, strict=True)], ys
        ),
    )
