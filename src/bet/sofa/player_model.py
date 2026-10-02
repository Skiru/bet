"""A player-prop model for the measured sports' player lines (basketball, hockey).

A MEASUREMENT. SHADOW_SETTLE writes its probability beside each graded player
line (settle_shadow.attach_player_model) and measure_player_props.py scores it
against Superbet's devigged price. Nothing here feeds or gates the football /
tennis coupon, and the per-sport experimental coupons (sport_coupon.py) are
price-only and do not read it.

The sample. For a line on player P in game G (teams A and B), the history is
each team's own `last` listing (sofa_listing_event) strictly before the
earlier of Superbet's kickoff and Sofascore's start, minus a margin, with G
itself excluded by id; for each of those games the stored `/lineups`
(sofa_event_stats.lineups_json) gives that team's players. P is found by name
among the players the two teams fielded (players.match_player, the grade's own
matcher; a name two different player ids share is nobody's), and his sample
is his appearances in his team's games - the grade's own gate,
shadow.has_played (secondsPlayed > 0), and the grade's own reading of the
statistics, shadow.player_stat_value, so a combined line (points + rebounds)
is the sum in each game, modelled directly. A game whose box lacks the stat
is left out of that family's sample, never read as a zero.

The count model (every family but plus-minus), per second on the court / ice:

    rate  = (sum x + K * pool_rate) / (sum s + K),  K = PRIOR_GAMES * mean s
    mean  = rate * E[s],  E[s] = mean seconds of his last N_MINUTES appearances
    var   = phi * mean,   phi = (n * phi_own + K_PHI * phi_pool) / (n + K_PHI)

pool_rate is the same family's rate over every other player of his position
group in the same two teams' games (the "league" each line sits in, read off
the history actually loaded, never a fitted table); phi_own is the sample's
variance-to-mean ratio (it carries the minutes' own variation), phi_pool the
median of the pool players' ratios; phi < 1 is Poisson. The pmf is
joint.count_pmf (Poisson / negative binomial). Hockey publishes time on ice
as `secondsPlayed` for the games that carry it (measured 2026-10-02 on the
400 newest hockey boxes: 4,128 appearances with it, and 7,099 entries with
non-zero statistics but no `secondsPlayed` - those are DNP to the grade and
so outside the sample too).

Plus-minus is signed: a per-game normal with mean and variance shrunk toward
the pool's by PRIOR_GAMES pseudo-games, discretised onto the integers.

P(side) grades every integer outcome with shadow.grade, the settlement's own
function, and conditions on a settled result: P(win) / (P(win) + P(loss)) -
a push is VOID and never graded, and a DNP voids the line, so the model is
conditional on an appearance as the grade is.

Fewer than MIN_APPEARANCES usable games gives no probability, with a reason.
Every constant in UNFITTED was chosen, not fitted, and is written beside every
number it produces.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.sofa.joint import count_pmf, normal_cdf
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

MODEL_NAME = "player_rate_v1"

# Team games read from each side's listing, newest first.
HISTORY_GAMES = 60
# The player's newest appearances kept in his sample.
MAX_SAMPLE = 20
# Below this many usable appearances the model gives no probability.
MIN_APPEARANCES = 5
# Expected seconds = mean of this many most recent appearances.
N_MINUTES = 5
# Pseudo-games of the pool's rate (and plus-minus mean / variance) added to
# the player's own.
PRIOR_GAMES = 3.0
# Pseudo-games of the pool's dispersion ratio added to the player's own.
K_PHI = 5.0
# Plus-minus: the predictive spread never goes below this.
MIN_SD_SIGNED = 0.75
# History is cut this long before the earlier of the two kickoffs.
CUTOFF_MARGIN_S = 60

UNFITTED = (
    "HISTORY_GAMES",
    "MAX_SAMPLE",
    "MIN_APPEARANCES",
    "N_MINUTES",
    "PRIOR_GAMES",
    "K_PHI",
    "MIN_SD_SIGNED",
    "CUTOFF_MARGIN_S",
)

SIGNED_FAMILIES = frozenset({"player_plus_minus"})
# Keys this module writes on a graded line; grading never reads them.
MODEL_KEYS = (
    "model_source",
    "model_fetched_at_utc",
    "model_p",
    "model_n",
    "model",
    "model_reason",
    "model_mean",
    "unfitted_constants",
)


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
class PlayerProbability:
    """The model's P(this side), or None with the reason."""

    p: float | None
    n: int
    model: str = MODEL_NAME
    reason: str | None = None
    mean: float | None = None


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
        listed = conn.execute(
            "SELECT event_id, start_ts FROM sofa_listing_event "
            "WHERE entity_id = ? AND kind = 'last' AND start_ts < ? "
            "ORDER BY start_ts DESC LIMIT ?",
            (int(team_id), int(before_ts), int(history_games) + 1),
        ).fetchall()
        games = [
            (int(eid), int(ts))
            for eid, ts in listed
            if exclude_event_id is None or int(eid) != int(exclude_event_id)
        ][:history_games]
        for eid, ts in games:
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


def find_player(subject: str, appearances: Sequence[Appearance]) -> int | None:
    """The player id Superbet's subject names, among the players fielded.

    players.match_player on normalised names; a normalised name two player
    ids share is removed first, as build_player_box removes a homonym.
    """
    ids: dict[str, set[int]] = {}
    for a in appearances:
        ids.setdefault(normalize_name(a.name), set()).add(a.player_id)
    candidates: dict[str, dict[str, Any]] = {
        name: {"id": next(iter(pids))} for name, pids in ids.items() if len(pids) == 1
    }
    matched = match_player(subject, candidates)
    return None if matched is None else int(candidates[matched]["id"])


def _values(
    apps: Iterable[Appearance], spec: PlayerSpec
) -> list[tuple[Appearance, float]]:
    out = []
    for a in apps:
        v = player_stat_value(a.stats, spec)
        if isinstance(v, float):
            out.append((a, v))
    return out


def _side_probability(line: ShadowLine, pmf: dict[int, float]) -> float | None:
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


def _dispersion(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean <= 0.0:
        return None
    return statistics.variance(values) / mean


def _count_pmf_for(
    own: Sequence[tuple[Appearance, float]],
    pool: Sequence[tuple[Appearance, float]],
) -> tuple[dict[int, float], float]:
    n = len(own)
    seconds = sum(a.seconds for a, _ in own)
    total = sum(v for _, v in own)
    mean_s = seconds / n
    pool_s = sum(a.seconds for a, _ in pool)
    pool_rate = sum(v for _, v in pool) / pool_s if pool_s > 0 else total / seconds
    k = PRIOR_GAMES * mean_s
    rate = (total + k * pool_rate) / (seconds + k)
    expected_s = statistics.fmean(a.seconds for a, _ in own[:N_MINUTES])
    mean = rate * expected_s
    by_player: dict[int, list[float]] = {}
    for a, v in pool:
        by_player.setdefault(a.player_id, []).append(v)
    pool_phis = [
        phi
        for vs in by_player.values()
        if len(vs) >= MIN_APPEARANCES and (phi := _dispersion(vs)) is not None
    ]
    phi_pool = statistics.median(pool_phis) if pool_phis else 1.0
    phi_own = _dispersion([v for _, v in own])
    phi = (n * (phi_own if phi_own is not None else phi_pool) + K_PHI * phi_pool) / (
        n + K_PHI
    )
    variance = max(phi, 1.0) * mean
    kmax = int(mean + 12.0 * math.sqrt(max(variance, 1.0)) + 12)
    pmf = count_pmf(mean, variance, kmax)
    return dict(enumerate(pmf)), mean


def _signed_pmf_for(
    own: Sequence[tuple[Appearance, float]],
    pool: Sequence[tuple[Appearance, float]],
) -> tuple[dict[int, float], float]:
    xs = [v for _, v in own]
    n = len(xs)
    pool_xs = [v for _, v in pool]
    pool_mean = statistics.fmean(pool_xs) if pool_xs else 0.0
    pool_var = (
        statistics.variance(pool_xs) if len(pool_xs) >= 2 else statistics.variance(xs)
    )
    mean = (sum(xs) + PRIOR_GAMES * pool_mean) / (n + PRIOR_GAMES)
    var = (n * statistics.pvariance(xs) + PRIOR_GAMES * pool_var) / (n + PRIOR_GAMES)
    sd = max(math.sqrt(var), MIN_SD_SIGNED)
    lo, hi = math.floor(mean - 10 * sd) - 1, math.ceil(mean + 10 * sd) + 1
    pmf = {
        k: normal_cdf((k + 0.5 - mean) / sd) - normal_cdf((k - 0.5 - mean) / sd)
        for k in range(lo, hi + 1)
    }
    return pmf, mean


def line_probability(
    line: ShadowLine, sport: SportKey, appearances: Sequence[Appearance]
) -> PlayerProbability:
    """P(this side settles a win | it settles), or None with a reason."""
    spec = PLAYER_MARKETS[sport].get(line.market_id)
    if spec is None:
        return PlayerProbability(None, 0, reason="NOT_A_PLAYER_MARKET")
    pid = find_player(line.subject, appearances)
    if pid is None:
        return PlayerProbability(None, 0, reason="NOT_IN_HISTORY")
    mine = sorted(
        (a for a in appearances if a.player_id == pid),
        key=lambda a: (-a.ts, a.event_id),
    )
    # A head-to-head game is on both teams' listings: one appearance per game.
    unique: list[Appearance] = []
    seen: set[int] = set()
    for a in mine:
        if a.event_id not in seen:
            seen.add(a.event_id)
            unique.append(a)
    own = _values(unique, spec)[:MAX_SAMPLE]
    if len(own) < MIN_APPEARANCES:
        return PlayerProbability(None, len(own), reason="THIN_SAMPLE")
    group = own[0][0].group
    pool = _values(
        (a for a in appearances if a.player_id != pid and a.group == group), spec
    )
    if spec.family in SIGNED_FAMILIES:
        pmf, mean = _signed_pmf_for(own, pool)
    else:
        pmf, mean = _count_pmf_for(own, pool)
    p = _side_probability(line, pmf)
    if p is None:
        return PlayerProbability(None, len(own), reason="DEGENERATE")
    return PlayerProbability(p, len(own), mean=mean)


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


def model_fields(mp: PlayerProbability) -> dict[str, Any]:
    """What a graded line carries: the model's number and its provenance."""
    return {
        "model_p": None if mp.p is None else round(mp.p, 4),
        "model_n": mp.n,
        "model": mp.model,
        "model_reason": mp.reason,
        "model_mean": None if mp.mean is None else round(mp.mean, 3),
        "unfitted_constants": list(UNFITTED),
    }


def score_rows(
    rows: Sequence[dict[str, Any]],
    sport: SportKey,
    appearances: Sequence[Appearance],
) -> list[PlayerProbability]:
    """One PlayerProbability per row, player lines only (others: None p)."""
    return [
        line_probability(line_from_row(r), sport, appearances)
        if int(r["market_id"]) in PLAYER_MARKETS[sport]
        else PlayerProbability(None, 0, reason="NOT_A_PLAYER_MARKET")
        for r in rows
    ]


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


def read_forecasts(path: Path) -> list[dict[str, Any]]:
    """The day's pre-game rows; a torn line is skipped."""
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
        if isinstance(row, dict) and "superbet_event_id" in row:
            out.append(row)
    return out


def _women_key(name: str, women: bool) -> str:
    key = normalize_name(name)
    return f"{key} (w)" if women and not key.endswith("(w)") else key


def team_name_index(
    conn: sqlite3.Connection, slug: str, now_ts: int
) -> dict[str, set[int]]:
    """Normalised Sofascore team name -> team ids, from the sport's listed
    games of the last TEAM_NAME_WINDOW_S. A women's side is keyed with the
    "(w)" marker normalize_name gives Superbet's "(K)"."""
    from bet.sofa.resolve import sofascore_gender

    index: dict[str, set[int]] = {}
    for (text,) in conn.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport = ? AND start_ts > ?",
        (slug, int(now_ts) - TEAM_NAME_WINDOW_S),
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
) -> list[dict[str, Any]]:
    """The pre-game rows for one sport's new snapshot records.

    Per record: both teams tied to Sofascore ids offline (resolve_team), the
    history cut before Superbet's kickoff (history_cutoff), each player side
    scored by line_probability, its pair devigged as the grade devigs it. A
    key already in `done` is not written again.
    """
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
        if ckey not in cache:
            cache[ckey] = load_appearances(conn, sport, teams, before, None)
        apps = cache[ckey]
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
            if not teams:
                mp = PlayerProbability(None, 0, reason="TEAM_UNRESOLVED")
            else:
                mp = line_probability(line_from_row(base), sport, apps)
            out.append(
                {
                    **base,
                    "fair_p": None if fair is None else fair.get(str(ln["side"])),
                    "teams_resolved": len(teams),
                    **model_fields(mp),
                    "unfitted_constants": list(UNFITTED) + list(UNFITTED_PREGAME),
                    "computed_at_utc": computed_at,
                }
            )
    return out


def last_pregame(
    forecasts: Sequence[dict[str, Any]], superbet_event_id: str, clock: datetime
) -> dict[tuple[int, str, str, str], dict[str, Any]]:
    """Per (market, subject, line, side) of one game: the newest pre-game row
    whose snapshot was taken before `clock` (the game's pre-match clock) and
    that carries a p."""
    best: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    for row in forecasts:
        if str(row.get("superbet_event_id")) != str(superbet_event_id):
            continue
        if row.get("model_p") is None:
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
    return best


def line_key(row: dict[str, Any]) -> tuple[int, str, str, str]:
    return (
        int(row["market_id"]),
        str(row.get("subject") or ""),
        repr(row.get("line")),
        str(row["side"]),
    )
