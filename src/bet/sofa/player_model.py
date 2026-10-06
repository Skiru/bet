"""A player-prop model for the measured sports' player lines (basketball, hockey).

A MEASUREMENT. SHADOW_SETTLE writes its probability beside each graded player
line (settle_shadow.attach_player_model) and measure_player_props.py scores it
against Superbet's devigged price. Nothing here feeds or gates the coupon.

The sample. For a line on player P in game G (teams A and B), the history is
each team's own `last` listing (sofa_listing_event) strictly before the
earlier of Superbet's kickoff and Sofascore's start, minus a margin, with G
itself excluded by id; for each of those games the stored `/lineups`
(sofa_event_stats.lineups_json) gives that team's players. P is the player
the grade reads: at settle, the subject matched in the graded game's own box
by the grade's own matcher (match_in_box -> players.match_player) and his
history read by that id; before the game, where there is no box, the one
player the two teams fielded whose name agrees on a strict rule (find_player,
names_agree: same surname, agreeing forenames or initials) - the grade's
threshold over 60 games of two squads priced namesakes ("Williams, Jalen" ->
"Jaylin Williams", 2026-10-03); a name two player ids share is nobody's. His
sample is his newest `max_sample` appearances in his team's games - the grade's own
gate, shadow.has_played (secondsPlayed > 0), and the grade's own reading of
the statistics, shadow.player_stat_value, so a combined line (points +
rebounds) is the sum in each game, modelled directly. A game whose box lacks
the stat is left out of that family's sample, never read as a zero.

`player_rate_v3` is v2's count model below with that player rule, pre-game
numbers only for games with both teams resolved, and the fitted file's
identity (model_config = fitted_at_utc, model_cut_utc) on every row; its
constants were refitted on wider grids (fit_player_model.GRID).

The count model (every family but plus-minus), per second on
the court / ice, the sample newest first (i = 0, 1, ...):

    rate  = (sum x + K * pool_rate) / (sum s + K),  K = prior_games * mean s
    w_i   = 0.5 ** (i / hl_minutes)
    E[s]  = sum w_i s_i / sum w_i,   cv = the same weights' sd(s) / mean(s)
    s     = E[s] * exp(sigma Z - sigma^2 / 2),  sigma^2 = sig_a^2 + cv^2
    X | s ~ NB(rate * s, phi * rate * s)
    phi   = (n * phi_own + k_phi * phi_pool) / (n + k_phi),  at least 1

so the minutes the player will get are a distribution, not a number: his own
recent spread of minutes (cv) plus a drift every player has (sig_a), averaged
over a five-point Gauss-Hermite rule. phi is the dispersion GIVEN the minutes
- the Pearson ratio sum (x - r s)^2 / sum r s of the sample about its own
per-second rate - so minutes' variation is counted once, in the mixture.
pool_rate is the same family's rate over the other players in the two teams'
loaded games (position group for hockey, every player for basketball:
`pool`), phi_pool the median of their Pearson ratios.

Why (measured 2026-10-02 on the stored history, scripts/sofa/
fit_player_model.py): player_rate_v1 took E[s] as the mean of the last five
appearances and a variance phi * mean with phi from raw counts. Given the
minutes the player actually got, its basketball variance was right or wide
(standardised squared error 0.73-0.97 per family); without them it was
1.24-1.36, and the excess sat where the minutes moved (3.75 when the player
got 1.5x his expected minutes). Next-game minutes over the last five's mean
ran 0.37 at the 5th percentile and 1.72 at the 95th. The five-game mean was
also too short a memory (an older window predicted minutes better). So v1
was overconfident because minutes are volatile and it priced them as known.

Plus-minus is signed: a per-game normal with mean and variance shrunk toward
the pool's by `prior_games_signed` pseudo-games, discretised onto the
integers.

P(side) grades every integer outcome with shadow.grade, the settlement's own
function, and conditions on a settled result: P(win) / (P(win) + P(loss)) -
a push is VOID and never graded, and a DNP voids the line, so the model is
conditional on an appearance as the grade is. A count family's P(side) then
goes through the sport's calibration slope, p' = sigmoid(b * logit p),
fitted on the training split (calibrate_side; symmetric, so the two sides of
a line still sum to one); plus-minus is not mapped.

The fitted constants live in config/sofa_player_model.json with their
provenance (fitted_from, n, criterion, the curve each was read off). Fewer
than MIN_APPEARANCES usable games gives no probability, with a reason. Every
constant still in UNFITTED was chosen, not fitted, and is written beside
every number it produces.
"""

from __future__ import annotations

import functools
import json
import math
import sqlite3
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.sofa.comparability import is_friendly_event
from bet.sofa.config import config_path
from bet.sofa.joint import normal_cdf
from bet.sofa.names import normalize_name
from bet.sofa.players import match_player
from bet.sofa.shadow import (
    PLAYER_MARKETS,
    PlayerSpec,
    ShadowLine,
    SportKey,
    grade,
    has_played,
    player_stat_value,
)

MODEL_NAME = "player_rate_v3"
PARAMS_FILE = "sofa_player_model.json"

# Team games read from each side's listing, newest first.
HISTORY_GAMES = 60
# Below this many usable appearances the model gives no probability.
MIN_APPEARANCES = 5
# Plus-minus: the predictive spread never goes below this.
MIN_SD_SIGNED = 0.75
# History is cut this long before the earlier of the two kickoffs.
CUTOFF_MARGIN_S = 60

UNFITTED = (
    "HISTORY_GAMES",
    "MIN_APPEARANCES",
    "MIN_SD_SIGNED",
    "CUTOFF_MARGIN_S",
)

SIGNED_FAMILIES = frozenset({"player_plus_minus"})
POOL_KINDS = ("group", "all")
# Keys this module writes on a graded line; grading never reads them.
MODEL_KEYS = (
    "model_source",
    "model_fetched_at_utc",
    "model_p",
    "model_n",
    "model",
    "model_reason",
    "model_mean",
    "model_player_id",
    "model_match",
    "model_config",
    "model_cut_utc",
    "model_teams_resolved",
    "model_pregame_rejected",
    "unfitted_constants",
)

# Five-point Gauss-Hermite rule (physicists'): nodes x, weights w;
# E[f(Z)] = sum w f(sqrt(2) x) / sqrt(pi) for a standard normal Z.
_GH_NODES = (
    -2.0201828704560856,
    -0.9585724646138185,
    0.0,
    0.9585724646138185,
    2.0201828704560856,
)
_GH_WEIGHTS = (
    0.019953242059045913,
    0.39361932315224116,
    0.9453087204829419,
    0.39361932315224116,
    0.019953242059045913,
)


@dataclass(frozen=True)
class SportParams:
    """One sport's constants (config/sofa_player_model.json)."""

    pool: str
    max_sample: int
    hl_minutes: float
    k_phi: float
    prior_games: float
    sig_a: float
    prior_games_signed: float
    calibration_b: float | None


@dataclass(frozen=True)
class Appearance:
    """One player's game for his team: an appearance (has_played) only."""

    event_id: int
    ts: int
    team_id: int
    player_id: int
    name: str
    group: str
    seconds: float
    stats: dict[str, Any]


@dataclass(frozen=True)
class Pool:
    """What the model reads of the other players: the family's sums over
    their appearances and the median of their own dispersion ratios."""

    sum_v: float
    sum_s: float
    sum_sq: float
    n: int
    phi: float | None


@dataclass(frozen=True)
class PlayerProbability:
    """The model's P(this side), or None with the reason."""

    p: float | None
    n: int
    model: str = MODEL_NAME
    reason: str | None = None
    mean: float | None = None
    player_id: int | None = None
    # How the player was found: "box" (the graded game's box, the grade's
    # own matcher) or "name" (the strict name rule over the history).
    match: str | None = None


def parse_params(doc: dict[str, Any]) -> dict[str, SportParams]:
    """The fitted file's constants per sport; a missing key raises."""
    if doc.get("model") != MODEL_NAME:
        raise ValueError(f"{PARAMS_FILE}: model {doc.get('model')!r} != {MODEL_NAME}")
    for key in ("fitted_from", "criterion"):
        if not doc.get(key):
            raise ValueError(f"{PARAMS_FILE}: no {key}")
    shared = doc["shared"]
    out: dict[str, SportParams] = {}
    for sport, entry in doc["sports"].items():

        def value(name: str, entry: dict[str, Any] = entry) -> Any:
            node = entry[name] if name in entry else shared[name]
            return node["value"] if isinstance(node, dict) else node

        pool = str(value("pool"))
        if pool not in POOL_KINDS:
            raise ValueError(f"{PARAMS_FILE}: {sport} pool {pool!r}")
        b = value("calibration_b")
        out[sport] = SportParams(
            pool=pool,
            max_sample=int(value("max_sample")),
            hl_minutes=float(value("hl_minutes")),
            k_phi=float(value("k_phi")),
            prior_games=float(value("prior_games")),
            sig_a=float(value("sig_a")),
            prior_games_signed=float(value("prior_games_signed")),
            calibration_b=None if b is None else float(b),
        )
    return out


@functools.lru_cache(maxsize=4)
def _load(path: str) -> tuple[dict[str, SportParams], dict[str, Any]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_params(doc), doc


def load_params(path: Path | None = None) -> dict[str, SportParams]:
    """The fitted constants per sport (config/sofa_player_model.json)."""
    return _load(str(path or config_path(PARAMS_FILE)))[0]


def params_provenance(path: Path | None = None) -> dict[str, Any]:
    """The file's provenance block: fitted_from and criterion."""
    doc = _load(str(path or config_path(PARAMS_FILE)))[1]
    return {k: doc[k] for k in ("fitted_from", "criterion")}


def sport_params(sport: SportKey) -> SportParams:
    return load_params()[sport]


def position_group(sport: SportKey, raw: object) -> str:
    """Basketball G / F / C (first letter of "GF", "FC"...); hockey G (goalie),
    D, else F. Unknown is its own group."""
    text = str(raw or "").strip().upper()
    if not text:
        return "?"
    if sport == "hockey":
        return text if text in ("G", "D") else "F"
    return text[0]


def appearances_from_lineups(
    sport: SportKey, lineups: dict[str, Any], event_id: int, ts: int, team_id: int
) -> list[Appearance]:
    """Team `team_id`'s appearances in one stored /lineups payload.

    The squad is read by the entry's `teamId` (present on every entry of the
    400 newest boxes of each sport, 2026-10-02); an entry without one is not
    attributed to anybody.
    """
    out: list[Appearance] = []
    for side in ("home", "away"):
        for entry in (lineups.get(side) or {}).get("players") or []:
            if not isinstance(entry, dict) or entry.get("teamId") != team_id:
                continue
            player = entry.get("player")
            stats = entry.get("statistics")
            if not isinstance(player, dict) or not isinstance(stats, dict):
                continue
            pid, name = player.get("id"), player.get("name")
            if not isinstance(pid, int) or not isinstance(name, str) or not name:
                continue
            if not has_played(stats):
                continue
            out.append(
                Appearance(
                    event_id,
                    ts,
                    team_id,
                    pid,
                    name,
                    position_group(
                        sport, entry.get("position") or player.get("position")
                    ),
                    float(stats["secondsPlayed"]),
                    stats,
                )
            )
    return out


def listed_games(
    conn: sqlite3.Connection,
    team_id: int,
    before_ts: int,
    exclude_event_id: int | None,
    history_games: int = HISTORY_GAMES,
) -> list[tuple[int, int]]:
    """(event id, start) of a team's newest listed games before `before_ts`.

    A pre-season game, a friendly or an exhibition is not a game the player
    model may learn from (comparability.is_friendly_event, 2026-10-04: NHL /
    AHL / WNBA / NBA preseason were read as regular games). A listed game
    whose payload is not in the index is kept - nothing says what it was.
    """
    listed = conn.execute(
        "SELECT l.event_id, l.start_ts, e.event_json FROM sofa_listing_event l "
        "LEFT JOIN sofa_listed_event e ON e.event_id = l.event_id "
        "WHERE l.entity_id = ? AND l.kind = 'last' AND l.start_ts < ? "
        "ORDER BY l.start_ts DESC LIMIT ?",
        (int(team_id), int(before_ts), 3 * (int(history_games) + 1)),
    ).fetchall()
    out: list[tuple[int, int]] = []
    for eid, ts, event_json in listed:
        if exclude_event_id is not None and int(eid) == int(exclude_event_id):
            continue
        if event_json:
            try:
                event = json.loads(event_json)
            except ValueError:
                event = None
            if isinstance(event, dict) and is_friendly_event(event):
                continue
        out.append((int(eid), int(ts)))
    return out[:history_games]


def load_appearances(
    conn: sqlite3.Connection,
    sport: SportKey,
    team_ids: Iterable[int],
    before_ts: int,
    exclude_event_id: int | None,
    history_games: int = HISTORY_GAMES,
) -> list[Appearance]:
    """Every appearance for these teams in their own listed games before
    `before_ts` (sofa_listing_event, the index every `last` page feeds), from
    the stored lineups. Read-only."""
    out: list[Appearance] = []
    for team_id in team_ids:
        for eid, ts in listed_games(
            conn, team_id, before_ts, exclude_event_id, history_games
        ):
            row = conn.execute(
                "SELECT lineups_json FROM sofa_event_stats "
                "WHERE sofascore_event_id = ?",
                (eid,),
            ).fetchone()
            if not row or not row[0]:
                continue
            try:
                lineups = json.loads(row[0])
            except ValueError:
                continue
            if isinstance(lineups, dict):
                out.extend(
                    appearances_from_lineups(sport, lineups, eid, ts, int(team_id))
                )
    return out


# Name tokens that are not part of who a player is: generational suffixes
# ("Jr.", "II" - which normalize_name turns into the reserves marker "(r)").
_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v", "r"})
# token_sort_ratio at or above which two names are taken as one without the
# structural check (a spelling variant normalize_name does not fold).
STRICT_NAME_RATIO = 97.0


def name_tokens(text: str) -> list[str]:
    """normalize_name's tokens with punctuation and generational suffixes
    removed ("P.J." -> "pj", "Trent II" -> "trent")."""
    out = []
    for raw in normalize_name(text).split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if tok and tok not in _NAME_SUFFIXES:
            out.append(tok)
    return out


def _given_agree(a: Sequence[str], b: Sequence[str]) -> bool:
    """Given names agree pairwise: equal, an initial of the other, or a
    prefix of at least three letters (Mitch / Mitchell)."""
    if len(a) != len(b) or not a:
        return False
    for x, y in zip(a, b, strict=True):
        short, long_ = (x, y) if len(x) <= len(y) else (y, x)
        if x == y or (len(short) == 1 and long_.startswith(short)):
            continue
        if len(short) >= 3 and long_.startswith(short):
            continue
        return False
    return True


def names_agree(subject: str, candidate: str) -> bool:
    """Whether Superbet's `subject` ("Williams, Jalen") names Sofascore's
    `candidate` ("Jalen Williams") on the strict rule the pre-game forecast
    needs: the same surname tokens and agreeing given names, or a
    token_sort_ratio of at least STRICT_NAME_RATIO. "Williams, Jalen" is not
    "Jaylin Williams" (89.7, which players.match_player accepts)."""
    from rapidfuzz import fuzz

    cand = name_tokens(candidate)
    if not cand:
        return False
    if "," in subject:
        sur_text, _, given_text = subject.partition(",")
        subj = name_tokens(sur_text) + name_tokens(given_text)
        readings = [(name_tokens(sur_text), name_tokens(given_text))]
    else:
        subj = name_tokens(subject)
        readings = [(subj[k:], subj[:k]) for k in range(1, len(subj))] + [
            (subj[:k], subj[k:]) for k in range(1, len(subj))
        ]
    if not subj:
        return False
    if sorted(subj) == sorted(cand):
        return True
    if fuzz.token_sort_ratio(" ".join(subj), " ".join(cand)) >= STRICT_NAME_RATIO:
        return True
    for sur, given in readings:
        if not sur or len(sur) >= len(cand) or cand[-len(sur) :] != sur:
            continue
        if _given_agree(given, cand[: len(cand) - len(sur)]):
            return True
    return False


def _unique_ids(appearances: Sequence[Appearance]) -> dict[str, int]:
    """Normalised name -> player id; a name two ids share is nobody's (as
    build_player_box removes a homonym)."""
    ids: dict[str, set[int]] = {}
    for a in appearances:
        ids.setdefault(normalize_name(a.name), set()).add(a.player_id)
    return {name: next(iter(p)) for name, p in ids.items() if len(p) == 1}


def find_player(
    subject: str, appearances: Sequence[Appearance]
) -> tuple[int | None, str | None]:
    """(player id, None) for the one player fielded whose name agrees with
    Superbet's subject on the strict rule (names_agree), else (None, reason):
    NAME_UNCERTAIN when the grade's looser matcher would pick somebody or two
    players agree; NOT_IN_HISTORY when nobody comes close.

    Used where the graded game's box is not available (the pre-game
    forecast): the history holds every player two teams fielded in up to
    HISTORY_GAMES games, a far larger field than the box the grade matches
    in, so the grade's own threshold would price a namesake (2026-10-03:
    "Williams, Jalen" matched "Jaylin Williams" at 89.7).
    """
    candidates = _unique_ids(appearances)
    agreed = {pid for name, pid in candidates.items() if names_agree(subject, name)}
    if len(agreed) == 1:
        return next(iter(agreed)), None
    if agreed:
        return None, "NAME_UNCERTAIN"
    loose = match_player(subject, {n: {} for n in candidates})
    return None, ("NAME_UNCERTAIN" if loose is not None else "NOT_IN_HISTORY")


def box_player_ids(lineups: dict[str, Any] | None) -> dict[str, int | None] | None:
    """The graded game's box keyed as the grade keys it (shadow.
    build_player_box: every named entry of both squads by normalised name, a
    name seen twice removed), each name with its player id (None when the
    entry carries none). None when either squad is empty or absent - then no
    player line is graded either."""
    if not isinstance(lineups, dict):
        return None
    out: dict[str, int | None] = {}
    homonyms: set[str] = set()
    for side in ("home", "away"):
        size = 0
        for entry in (lineups.get(side) or {}).get("players") or []:
            if not isinstance(entry, dict):
                continue
            player = entry.get("player")
            if not isinstance(player, dict):
                continue
            name = player.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            size += 1
            key = normalize_name(name)
            if key in out:
                homonyms.add(key)
            pid = player.get("id")
            out[key] = (
                pid if isinstance(pid, int) and not isinstance(pid, bool) else None
            )
        if not size:
            return None
    for key in homonyms:
        del out[key]
    return out


def match_in_box(
    subject: str, box_ids: dict[str, int | None]
) -> tuple[int | None, str | None]:
    """The player the GRADE reads for this subject - players.match_player
    over the graded game's own box, shadow.player_value's call - and his id;
    else (None, NOT_IN_BOX / NO_PLAYER_ID)."""
    matched = match_player(subject, {k: {} for k in box_ids})
    if matched is None:
        return None, "NOT_IN_BOX"
    pid = box_ids[matched]
    return (pid, None) if pid is not None else (None, "NO_PLAYER_ID")


def _values(
    apps: Iterable[Appearance], spec: PlayerSpec
) -> list[tuple[Appearance, float]]:
    out = []
    for a in apps:
        v = player_stat_value(a.stats, spec)
        if isinstance(v, float):
            out.append((a, v))
    return out


def own_sample(
    pid: int, appearances: Sequence[Appearance], spec: PlayerSpec, max_sample: int
) -> list[tuple[Appearance, float]]:
    """The player's newest appearances with the family's value, one per game
    (a head-to-head game is on both teams' listings)."""
    mine = sorted(
        (a for a in appearances if a.player_id == pid),
        key=lambda a: (-a.ts, a.event_id),
    )
    unique: list[Appearance] = []
    seen: set[int] = set()
    for a in mine:
        if a.event_id not in seen:
            seen.add(a.event_id)
            unique.append(a)
    return _values(unique, spec)[:max_sample]


def pearson_dispersion(pairs: Sequence[tuple[float, float]]) -> float | None:
    """sum (x - r s)^2 / sum r s * n / (n - 1), r = sum x / sum s: the
    dispersion of (seconds, value) pairs about their own per-second rate -
    the spread left once the minutes are known. None below two games or with
    no count at all."""
    n = len(pairs)
    total = sum(v for _, v in pairs)
    seconds = sum(s for s, _ in pairs)
    if n < 2 or total <= 0.0 or seconds <= 0.0:
        return None
    rate = total / seconds
    return sum((v - rate * s) ** 2 for s, v in pairs) / total * n / (n - 1)


def pool_of(pairs: Sequence[tuple[Appearance, float]]) -> Pool:
    """The Pool of the other players' (appearance, value) pairs."""
    by_player: dict[int, list[tuple[float, float]]] = {}
    for a, v in pairs:
        by_player.setdefault(a.player_id, []).append((a.seconds, v))
    phis = [
        phi
        for ps in by_player.values()
        if len(ps) >= MIN_APPEARANCES and (phi := pearson_dispersion(ps)) is not None
    ]
    return Pool(
        sum(v for _, v in pairs),
        sum(a.seconds for a, _ in pairs),
        sum(v * v for _, v in pairs),
        len(pairs),
        statistics.median(phis) if phis else None,
    )


def nb_pmf(mean: float, variance: float, kmax: int) -> list[float]:
    """PMF on 0..kmax, renormalised: Poisson when variance <= mean, else the
    negative binomial with that mean and variance. joint.count_pmf by
    recurrence instead of one lgamma per point (the replay prices millions)."""
    if mean <= 0.0:
        return [1.0] + [0.0] * kmax
    if variance <= mean * 1.0000001:
        log_p0 = -mean
        ratio_a, ratio_b = 0.0, mean  # p(k) = p(k-1) * mean / k
    else:
        r = mean * mean / (variance - mean)
        q = mean / (r + mean)
        log_p0 = r * math.log1p(-q)
        ratio_a, ratio_b = q, q * r  # p(k) = p(k-1) * q (k - 1 + r) / k
    pmf = [0.0] * (kmax + 1)
    pmf[0] = math.exp(log_p0)
    if pmf[0] == 0.0:
        # Far tail start: build in log space once, then exponentiate.
        logs = [log_p0]
        for k in range(1, kmax + 1):
            logs.append(logs[-1] + math.log((ratio_a * (k - 1) + ratio_b) / k))
        top = max(logs)
        pmf = [math.exp(v - top) for v in logs]
    else:
        for k in range(1, kmax + 1):
            pmf[k] = pmf[k - 1] * (ratio_a * (k - 1) + ratio_b) / k
    total = sum(pmf)
    return [v / total for v in pmf] if total > 0.0 else [1.0] + [0.0] * kmax


def count_distribution(
    sample: Sequence[tuple[float, float]], pool: Pool, params: SportParams
) -> tuple[list[float], float]:
    """(pmf on 0..kmax, mean) of a count family from the player's
    (seconds, value) sample, newest first, and the pool."""
    n = len(sample)
    seconds = sum(s for s, _ in sample)
    total = sum(v for _, v in sample)
    mean_s = seconds / n
    pool_rate = pool.sum_v / pool.sum_s if pool.sum_s > 0 else total / seconds
    k = params.prior_games * mean_s
    rate = (total + k * pool_rate) / (seconds + k)
    weights = [0.5 ** (i / params.hl_minutes) for i in range(n)]
    w_total = sum(weights)
    expected_s = sum(w * s for w, (s, _) in zip(weights, sample, strict=True)) / w_total
    spread = (
        sum(
            w * (s - expected_s) ** 2 for w, (s, _) in zip(weights, sample, strict=True)
        )
        / w_total
    )
    cv = math.sqrt(spread) / max(expected_s, 1.0)
    sigma = math.sqrt(params.sig_a**2 + cv**2)
    # No invented dispersion (review 2026-10-03): a pool that cannot measure
    # one gets no weight, and with neither measured the count is at the
    # model's structural floor, Poisson (phi >= 1 below) - not a guessed 1.0
    # shrunk toward as if it had been measured.
    phi_own = pearson_dispersion(sample)
    parts = [(float(n), phi_own)] if phi_own is not None else []
    if pool.phi is not None:
        parts.append((float(params.k_phi), pool.phi))
    weight = sum(w for w, _ in parts)
    phi = sum(w * v for w, v in parts) / weight if weight > 0 else 1.0
    phi = max(phi, 1.0)
    norm = sum(_GH_WEIGHTS)
    mus = [
        rate * expected_s * math.exp(sigma * math.sqrt(2.0) * x - 0.5 * sigma * sigma)
        for x in _GH_NODES
    ]
    kmax = int(max(mus) + 12.0 * math.sqrt(max(phi * max(mus), 1.0)) + 12)
    pmf = [0.0] * (kmax + 1)
    for w, mu in zip(_GH_WEIGHTS, mus, strict=True):
        for i, v in enumerate(nb_pmf(mu, phi * mu, kmax)):
            pmf[i] += w / norm * v
    mean = sum(w / norm * mu for w, mu in zip(_GH_WEIGHTS, mus, strict=True))
    return pmf, mean


def signed_distribution(
    values: Sequence[float], pool: Pool, params: SportParams
) -> tuple[dict[int, float], float]:
    """(pmf on the integers, mean) of plus-minus: a normal with the player's
    mean and variance shrunk toward the pool's."""
    xs = list(values)
    n = len(xs)
    # An empty pool is no prior: the player's own sample alone, never a
    # shrink toward an invented 0.0 (review 2026-10-03).
    pool_mean = pool.sum_v / pool.n if pool.n else 0.0
    pool_var = (
        (pool.sum_sq - pool.n * pool_mean**2) / (pool.n - 1)
        if pool.n >= 2
        else statistics.variance(xs)
    )
    k = params.prior_games_signed if pool.n else 0.0
    mean = (sum(xs) + k * pool_mean) / (n + k)
    var = (n * statistics.pvariance(xs) + k * pool_var) / (n + k)
    sd = max(math.sqrt(max(var, 0.0)), MIN_SD_SIGNED)
    lo, hi = math.floor(mean - 10 * sd) - 1, math.ceil(mean + 10 * sd) + 1
    pmf = {
        k_: normal_cdf((k_ + 0.5 - mean) / sd) - normal_cdf((k_ - 0.5 - mean) / sd)
        for k_ in range(lo, hi + 1)
    }
    return pmf, mean


def calibrate_side(p: float, b: float | None) -> float:
    """sigmoid(b * logit p): the sport's fitted calibration slope (None: p).
    Monotone in p for b > 0 and symmetric, so complementary sides stay
    complementary."""
    if b is None or p <= 0.0 or p >= 1.0:
        return p
    z = b * math.log(p / (1.0 - p))
    return 1.0 / (1.0 + math.exp(-z))


def side_probability(line: ShadowLine, pmf: dict[int, float]) -> float | None:
    """P(win) / (P(win) + P(loss)) over the integer outcomes, graded by the
    settlement's own function; None when no outcome settles."""
    win = loss = 0.0
    for k, mass in pmf.items():
        outcome = grade(line, float(k))
        if outcome == "WIN":
            win += mass
        elif outcome == "LOSS":
            loss += mass
    if win + loss <= 0.0:
        return None
    return win / (win + loss)


def line_probability(
    line: ShadowLine,
    sport: SportKey,
    appearances: Sequence[Appearance],
    params: SportParams | None = None,
    player_id: int | None = None,
) -> PlayerProbability:
    """P(this side settles a win | it settles), or None with a reason.

    `player_id` is the player the grade reads (match_in_box, at settle);
    without it the subject is found by the strict name rule (find_player)."""
    spec = PLAYER_MARKETS[sport].get(line.market_id)
    if spec is None:
        return PlayerProbability(None, 0, reason="NOT_A_PLAYER_MARKET")
    match = "box" if player_id is not None else "name"
    pid = player_id
    if pid is None:
        pid, why = find_player(line.subject, appearances)
        if pid is None:
            return PlayerProbability(None, 0, reason=why, match=match)
    prm = params or sport_params(sport)
    own = own_sample(pid, appearances, spec, prm.max_sample)
    if not own and not any(a.player_id == pid for a in appearances):
        return PlayerProbability(
            None, 0, reason="NOT_IN_HISTORY", player_id=pid, match=match
        )
    if len(own) < MIN_APPEARANCES:
        return PlayerProbability(
            None, len(own), reason="THIN_SAMPLE", player_id=pid, match=match
        )
    group = own[0][0].group
    pool = pool_of(
        _values(
            (
                a
                for a in appearances
                if a.player_id != pid and (prm.pool == "all" or a.group == group)
            ),
            spec,
        )
    )
    signed = spec.family in SIGNED_FAMILIES
    if signed:
        pmf, mean = signed_distribution([v for _, v in own], pool, prm)
    else:
        counts, mean = count_distribution([(a.seconds, v) for a, v in own], pool, prm)
        pmf = dict(enumerate(counts))
    p = side_probability(line, pmf)
    if p is None:
        return PlayerProbability(
            None, len(own), reason="DEGENERATE", player_id=pid, match=match
        )
    if not signed:
        p = calibrate_side(p, prm.calibration_b)
    return PlayerProbability(p, len(own), mean=mean, player_id=pid, match=match)


def line_from_row(row: dict[str, Any]) -> ShadowLine:
    """The graded row's line, as SHADOW parsed it."""
    return ShadowLine(
        str(row["superbet_event_id"]),
        int(row["market_id"]),
        str(row["family"]),
        int(row.get("period") or 0),
        str(row.get("subject") or ""),
        row.get("line"),
        str(row["side"]),
        float(row["odds"]),
    )


def config_identity(path: Path | None = None) -> dict[str, Any]:
    """Which fitted file produced a number: its fitted_at_utc and its
    training cut (config/sofa_player_model.json, fitted_from)."""
    fitted = params_provenance(path)["fitted_from"]
    return {
        "model_config": fitted.get("fitted_at_utc"),
        "model_cut_utc": fitted.get("cut_utc"),
    }


def model_fields(mp: PlayerProbability) -> dict[str, Any]:
    """What a graded line carries: the model's number and its provenance -
    the model, the fitted file it read (config_identity), the player it
    priced and how he was found."""
    return {
        "model_p": None if mp.p is None else round(mp.p, 4),
        "model_n": mp.n,
        "model": mp.model,
        "model_reason": mp.reason,
        "model_mean": None if mp.mean is None else round(mp.mean, 3),
        "model_player_id": mp.player_id,
        "model_match": mp.match,
        **config_identity(),
        "unfitted_constants": list(UNFITTED),
    }


def score_rows(
    rows: Sequence[dict[str, Any]],
    sport: SportKey,
    appearances: Sequence[Appearance],
    box_ids: dict[str, int | None] | None = None,
) -> list[PlayerProbability]:
    """One PlayerProbability per row, player lines only (others: None p).

    With `box_ids` (box_player_ids of the graded game) each subject is the
    player the grade read (match_in_box), and a subject the box does not
    resolve gets no p; without it, the strict name rule (find_player)."""
    out = []
    for r in rows:
        if int(r["market_id"]) not in PLAYER_MARKETS[sport]:
            out.append(PlayerProbability(None, 0, reason="NOT_A_PLAYER_MARKET"))
            continue
        ln = line_from_row(r)
        if box_ids is None:
            out.append(line_probability(ln, sport, appearances))
            continue
        pid, why = match_in_box(ln.subject, box_ids)
        if pid is None:
            out.append(PlayerProbability(None, 0, reason=why, match="box"))
            continue
        out.append(line_probability(ln, sport, appearances, player_id=pid))
    return out


def history_cutoff(kickoff_ts: int, sofa_start_ts: int | None) -> int:
    """Strictly before the earlier of the two clocks, minus the margin."""
    start = min(kickoff_ts, sofa_start_ts) if sofa_start_ts else kickoff_ts
    return int(start) - CUTOFF_MARGIN_S


# --- the pre-game forecast (SHADOW) ------------------------------------------------

PLAYER_MODEL_FILE = "player_model.jsonl"
# Sports with player markets the model reads.
MODEL_SPORTS: frozenset[SportKey] = frozenset({"basketball", "hockey"})
# How far back the listed games are read to tie a Superbet team name to a
# Sofascore team id when RESOLVE's entity cache does not hold it.
TEAM_NAME_WINDOW_S = 120 * 86400
UNFITTED_PREGAME = ("TEAM_NAME_WINDOW_S",)

ForecastKey = tuple[str, str, int, str, str, str]


def forecast_key(row: dict[str, Any]) -> ForecastKey:
    """Idempotency key of one pre-game row: the snapshot, the line, the side."""
    return (
        str(row["fetched_at_utc"]),
        str(row["superbet_event_id"]),
        int(row["market_id"]),
        str(row.get("subject") or ""),
        repr(row.get("line")),
        str(row["side"]),
    )


LineIdentity = tuple[str, int, str, str, str]


def forecast_line(row: dict[str, Any]) -> LineIdentity:
    """One line's side across snapshots: forecast_key without the snapshot."""
    return forecast_key(row)[1:]


def forecast_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    """What a pre-game row says about its line: the model, its number, the
    fitted file it read and the teams it found. Two snapshots with one
    signature say the same thing, and only the first is written."""
    return (
        row.get("model"),
        row.get("model_p"),
        row.get("model_n"),
        row.get("model_reason"),
        row.get("model_config"),
        row.get("teams_resolved"),
    )


def last_signatures(rows: Sequence[dict[str, Any]]) -> dict[LineIdentity, Any]:
    """Per line side: the signature of the newest row written (the file is
    append-only and in snapshot order; ties go to the later line)."""
    newest: dict[LineIdentity, tuple[str, tuple[Any, ...]]] = {}
    for row in rows:
        key = forecast_line(row)
        at = str(row.get("fetched_at_utc"))
        prev = newest.get(key)
        if prev is None or at >= prev[0]:
            newest[key] = (at, forecast_signature(row))
    return {k: v[1] for k, v in newest.items()}


def read_forecasts(path: Path) -> list[dict[str, Any]]:
    """The day's pre-game rows; a torn line, or a row without the keys every
    reader indexes (forecast_key, line_key), is skipped - one bad row must
    not stop the day's forecasts or a game's attach (review 2026-10-03)."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for text in path.read_text(encoding="utf-8").splitlines():
        if not text.strip():
            continue
        try:
            row = json.loads(text)
        except ValueError:
            continue
        if not isinstance(row, dict) or not all(
            k in row for k in FORECAST_REQUIRED_KEYS
        ):
            continue
        try:
            int(row["market_id"])
        except (TypeError, ValueError):
            continue
        out.append(row)
    return out


FORECAST_REQUIRED_KEYS = (
    "superbet_event_id", "fetched_at_utc", "market_id", "side",
)


def _women_key(name: str, women: bool) -> str:
    key = normalize_name(name)
    return f"{key} (w)" if women and not key.endswith("(w)") else key


def team_name_index(
    conn: sqlite3.Connection, slug: str, now_ts: int,
    window_s: int = TEAM_NAME_WINDOW_S,
) -> dict[str, set[int]]:
    """Normalised Sofascore team name -> team ids, from the sport's listed
    games of the last `window_s` (TEAM_NAME_WINDOW_S). A women's side is
    keyed with the "(w)" marker normalize_name gives Superbet's "(K)"."""
    from bet.sofa.resolve import sofascore_gender

    index: dict[str, set[int]] = {}
    for (text,) in conn.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport = ? AND start_ts > ?",
        (slug, int(now_ts) - int(window_s)),
    ):
        try:
            event = json.loads(text)
        except ValueError:
            continue
        women = sofascore_gender(event) == "W"
        for side in ("homeTeam", "awayTeam"):
            team = event.get(side) or {}
            if isinstance(team.get("id"), int) and isinstance(team.get("name"), str):
                index.setdefault(_women_key(team["name"], women), set()).add(
                    int(team["id"])
                )
    return index


def resolve_team(
    conn: sqlite3.Connection, slug: str, name: str, index: dict[str, set[int]]
) -> int | None:
    """A Superbet team name's Sofascore id, offline: RESOLVE's verified
    entity first (read-only, no hit counter), else an exact normalised name
    in the listed games that names one team only. No fuzzy guess."""
    key = normalize_name(name)
    row = conn.execute(
        "SELECT sofascore_id, status FROM sofa_entity "
        "WHERE sport = ? AND query_key = ?",
        (slug, key),
    ).fetchone()
    if row and row[1] == "verified" and row[0] is not None:
        return int(row[0])
    ids = index.get(key) or set()
    return next(iter(ids)) if len(ids) == 1 else None


def forecast_records(
    conn: sqlite3.Connection,
    sport: SportKey,
    slug: str,
    records: Sequence[dict[str, Any]],
    computed_at: str,
    done: set[ForecastKey],
    now_ts: int,
    last: dict[LineIdentity, Any] | None = None,
) -> list[dict[str, Any]]:
    """The pre-game rows for one sport's new snapshot records.

    Per record: both teams tied to Sofascore ids offline (resolve_team), the
    history cut before Superbet's kickoff (history_cutoff), each player side
    scored by line_probability, its pair devigged as the grade devigs it. A
    key already in `done` is not written again, and neither is a row whose
    forecast_signature equals the last one written for its line side
    (`last`, last_signatures of the file; updated here): every 30-minute
    snapshot used to re-write every line. The last row before the start is
    still the number that held at the start - only its odds / fair_p are
    those of the snapshot that first said it.

    Only a game with BOTH teams resolved is priced: one team's history is
    half the pool and, for an opponent's player, no sample at all (10-02
    hockey: 332 of 584 rows had one team); such a line is computed at settle,
    where Sofascore names both teams.
    """
    if last is None:
        last = {}
    from bet.sofa.cs2 import group_fair
    from bet.sofa.shadow import group_shape

    index: dict[str, set[int]] | None = None
    cache: dict[tuple[tuple[int, ...], int], list[Appearance]] = {}
    out: list[dict[str, Any]] = []
    for rec in records:
        raw_lines = [
            ln
            for ln in rec.get("lines") or []
            if int(ln.get("market_id", 0)) in PLAYER_MARKETS[sport]
        ]
        if not raw_lines:
            continue
        kickoff = datetime.fromisoformat(str(rec["kickoff_utc"]).replace("Z", "+00:00"))
        before = history_cutoff(int(kickoff.timestamp()), None)
        teams: list[int] = []
        for name in (rec.get("team1"), rec.get("team2")):
            if not isinstance(name, str):
                continue
            tid = resolve_team(conn, slug, name, {})
            if tid is None:
                if index is None:
                    index = team_name_index(conn, slug, now_ts)
                tid = resolve_team(conn, slug, name, index)
            if tid is not None:
                teams.append(tid)
        ckey = (tuple(sorted(teams)), before)
        if len(teams) == 2 and ckey not in cache:
            cache[ckey] = load_appearances(conn, sport, teams, before, None)
        apps = cache.get(ckey, [])
        groups: dict[tuple[Any, ...], dict[str, float]] = {}
        for ln in raw_lines:
            gkey = (
                ln["market_id"],
                ln.get("period"),
                ln.get("subject"),
                ln.get("line"),
            )
            groups.setdefault(gkey, {})[str(ln["side"])] = float(ln["odds"])
        for ln in raw_lines:
            base: dict[str, Any] = {
                "fetched_at_utc": rec["fetched_at_utc"],
                "superbet_event_id": str(rec["superbet_event_id"]),
                "kickoff_utc": rec["kickoff_utc"],
                "market_id": int(ln["market_id"]),
                "family": ln["family"],
                "period": int(ln.get("period") or 0),
                "subject": ln.get("subject") or "",
                "line": ln.get("line"),
                "side": ln["side"],
                "odds": ln["odds"],
            }
            key = forecast_key(base)
            if key in done:
                continue
            done.add(key)
            gkey = (
                ln["market_id"],
                ln.get("period"),
                ln.get("subject"),
                ln.get("line"),
            )
            fair = group_fair(groups[gkey], group_shape(sport, int(ln["market_id"])))
            if len(teams) < 2:
                mp = PlayerProbability(None, 0, reason="TEAM_UNRESOLVED")
            else:
                mp = line_probability(line_from_row(base), sport, apps)
            row = {
                **base,
                "fair_p": None if fair is None else fair.get(str(ln["side"])),
                "teams_resolved": len(teams),
                **model_fields(mp),
                "unfitted_constants": list(UNFITTED) + list(UNFITTED_PREGAME),
                "computed_at_utc": computed_at,
            }
            ident, sig = forecast_line(row), forecast_signature(row)
            if last.get(ident) == sig:
                continue
            last[ident] = sig
            out.append(row)
    return out


def last_pregame(
    forecasts: Sequence[dict[str, Any]], superbet_event_id: str, clock: datetime
) -> dict[tuple[int, str, str, str], dict[str, Any]]:
    """Per (market, subject, line, side) of one game: the newest pre-game row
    whose snapshot was taken before `clock` (the game's pre-match clock),
    when that newest row carries a p (a withdrawn number is no forecast),
    that this model wrote (`model` == MODEL_NAME) and that
    resolved both teams (`teams_resolved` == 2): a row an older model wrote
    - a loop started before the code changed - is never attached as this
    model's number, and a one-team row (a player_rate_v2 loop priced those)
    is not preferred to the two-team number settle computes; the line is
    computed at settle instead."""
    best: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    for row in forecasts:
        if str(row.get("superbet_event_id")) != str(superbet_event_id):
            continue
        # A row without a p still counts as the model's latest word: a number
        # it withdrew before the start (NAME_UNCERTAIN, THIN_SAMPLE...) is not
        # attached from an earlier snapshot (review 2026-10-03).
        if row.get("model") != MODEL_NAME:
            continue
        if row.get("teams_resolved") != 2:
            continue
        try:
            fetched = datetime.fromisoformat(
                str(row["fetched_at_utc"]).replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            continue
        if fetched >= clock:
            continue
        key = line_key(row)
        prev = best.get(key)
        if prev is None or str(row["fetched_at_utc"]) > str(prev["fetched_at_utc"]):
            best[key] = row
    return {k: r for k, r in best.items() if r.get("model_p") is not None}


def line_key(row: dict[str, Any]) -> tuple[int, str, str, str]:
    return (
        int(row["market_id"]),
        str(row.get("subject") or ""),
        repr(row.get("line")),
        str(row["side"]),
    )
