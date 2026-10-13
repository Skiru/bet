"""Season phase: a multiplier of the football goals centre by where the match
sits in its league season (audit 2026-10-13 C1; switch
``epochs.SEASON_PHASE_FROM_UTC``, off while None).

Measured 2026-10-05 against the raw sample mean (model_defects_2026-10-05.md
section 5): the last two rounds of a league season score ~11% more goals than
the sample says, the last 20% ~5% more, rounds 1-3 2-4% fewer. Neither half of
SHEET's centre knows the phase: the shrunk sample and the rating both average
over every phase of the matches they were earned in.

The phase must be known before the match, so it is read from the history as
of the kickoff, never from the season's own end:

  * a side's round = 1 + its matches of (competition, season) before the
    kickoff; the match's round is the mean of the two sides';
  * the season's length = the median per-team match count of the
    competition's PREVIOUS season (the latest season of the competition whose
    first match is before the current one's), counted on matches before the
    kickoff - the current season's own count would call the newest rounds
    "the last" (the leak model_defects_2026-10-05 rejected);
  * a season shorter than MIN_SEASON_ROUNDS (a cup, a group stage) or a
    round beyond the previous season's length (a changed format) has no
    phase, and its centre is left as it is.

``SeasonPhaseIndex`` is that as-of state: SHEET fills it with the history
before the day's cut and asks it about each fixture; a history replay asks it
about a match BEFORE ``add``-ing that match. With the switch on the centre of
a market of SEASON_PHASE_MARKETS is ``centre x exp(c[market][phase])``, the
coefficients fitted on the history by ``scripts/sofa/fit_season_phase.py``
(``fit_coefficients``: per phase the Poisson MLE log(sum y / sum centre)
minus the same of mid-season - a phase term, never a level correction) into
config/sofa_season_phase.json. Evidence:
docs/sofa/evidence/season_phase_2026-10-13.md.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from bet.sofa.config import config_path

CONFIG_FILE = "sofa_season_phase.json"

PHASE_EARLY = "early"  # rounds 1..EARLY_ROUNDS
PHASE_MID = "mid"
PHASE_LATE = "late"  # round / length >= LATE_SHARE
PHASE_FINAL = "final"  # the last FINAL_ROUNDS rounds
PHASES: tuple[str, ...] = (PHASE_EARLY, PHASE_MID, PHASE_LATE, PHASE_FINAL)

# The cut points of the 2026-10-05 measurement (round_label in
# scripts/sofa/measure_model_defects.py). Chosen there, not fitted.
EARLY_ROUNDS = 3.0
FINAL_ROUNDS = 2.0
LATE_SHARE = 0.8
MIN_SEASON_ROUNDS = 10
SEASON_PHASE_UNFITTED: tuple[str, ...] = (
    "SEASON_PHASE_EARLY_ROUNDS", "SEASON_PHASE_FINAL_ROUNDS",
    "SEASON_PHASE_LATE_SHARE", "SEASON_PHASE_MIN_SEASON_ROUNDS")

SEASON_PHASE_MARKETS: tuple[str, ...] = (
    "goals_for", "goals_total",
    "goals_1h_for", "goals_1h_total",
    "goals_2h_for", "goals_2h_total",
)
# a phase cell's coefficient is fitted only from this many centres; fewer
# leave the phase without one (its centre unchanged)
MIN_FIT_ROWS = 500
# |c| above this is a unit slip, never a phase effect (+-0.5 = x1.65)
MAX_ABS_COEFFICIENT = 0.5


def phase_label(round_no: float, season_rounds: float) -> str | None:
    """The phase of a match at `round_no` (1-based, may be a half: the mean of
    the two sides') of a season `season_rounds` long; None without one."""
    if season_rounds < MIN_SEASON_ROUNDS or round_no < 1:
        return None
    if round_no > season_rounds:
        return None  # longer than last season: a changed format, no reading
    if round_no <= EARLY_ROUNDS:
        return PHASE_EARLY
    if round_no > season_rounds - FINAL_ROUNDS:
        return PHASE_FINAL
    if round_no / season_rounds >= LATE_SHARE:
        return PHASE_LATE
    return PHASE_MID


class _Match(Protocol):
    @property
    def event_id(self) -> int: ...
    @property
    def ts(self) -> int: ...
    @property
    def competition_id(self) -> int: ...
    @property
    def season_id(self) -> int | None: ...
    @property
    def home_id(self) -> int: ...
    @property
    def away_id(self) -> int: ...


@dataclass
class SeasonPhaseIndex:
    """Per (competition, season): each team's match count and the season's
    first kickoff, from the matches `add`-ed so far (time order)."""

    counts: dict[tuple[int, int], Counter[int]] = field(
        default_factory=lambda: defaultdict(Counter))
    first_ts: dict[tuple[int, int], int] = field(default_factory=dict)
    seasons: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))

    def add(self, competition_id: int, season_id: int | None, ts: int,
            home_id: int, away_id: int) -> None:
        if season_id is None:
            return
        key = (competition_id, season_id)
        c = self.counts[key]
        c[home_id] += 1
        c[away_id] += 1
        if key not in self.first_ts or ts < self.first_ts[key]:
            self.first_ts[key] = ts
        self.seasons[competition_id].add(season_id)

    def add_result(self, r: _Match) -> None:
        self.add(r.competition_id, r.season_id, r.ts, r.home_id, r.away_id)

    def previous_season(self, competition_id: int, season_id: int,
                        ts: int) -> int | None:
        """The latest other season of the competition that started before the
        current one (before `ts` when the current one has no match yet)."""
        start = self.first_ts.get((competition_id, season_id), ts)
        best: tuple[int, int] | None = None
        for s in self.seasons.get(competition_id, ()):
            if s == season_id:
                continue
            f = self.first_ts[(competition_id, s)]
            if f < start and (best is None or f > best[0]):
                best = (f, s)
        return None if best is None else best[1]

    def season_rounds(self, competition_id: int, season_id: int,
                      ts: int) -> float | None:
        prev = self.previous_season(competition_id, season_id, ts)
        if prev is None:
            return None
        per_team = list(self.counts[(competition_id, prev)].values())
        if len(per_team) < 4:
            return None
        return float(statistics.median(per_team))

    def match_round(self, competition_id: int, season_id: int,
                    home_id: int, away_id: int) -> float:
        c = self.counts.get((competition_id, season_id))
        played = (c[home_id] + c[away_id]) / 2.0 if c is not None else 0.0
        return 1.0 + played

    def phase(self, competition_id: int, season_id: int | None, ts: int,
              home_id: int, away_id: int) -> str | None:
        """The match's phase from what was `add`-ed before it; None without
        one (no season id, no previous season, a short or changed season)."""
        if season_id is None:
            return None
        length = self.season_rounds(competition_id, season_id, ts)
        if length is None:
            return None
        return phase_label(
            self.match_round(competition_id, season_id, home_id, away_id), length)


def index_from_history(history: Iterable[_Match], cut_ts: int) -> SeasonPhaseIndex:
    """The index of every match strictly before `cut_ts` (SHEET: the day's
    00:00Z, the same cut its rating book is replayed to)."""
    idx = SeasonPhaseIndex()
    for r in history:
        if r.ts >= cut_ts:
            continue
        idx.add_result(r)
    return idx


def phases_by_event(history: Iterable[_Match]) -> dict[int, str | None]:
    """event id -> its phase as of its kickoff (asked before it is added):
    the replay's reading, for a measurement or a history replay."""
    idx = SeasonPhaseIndex()
    out: dict[int, str | None] = {}
    for r in history:
        out[r.event_id] = idx.phase(
            r.competition_id, r.season_id, r.ts, r.home_id, r.away_id)
        idx.add_result(r)
    return out


@dataclass(frozen=True)
class SeasonPhaseTable:
    coefficients: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    path: str | None = None

    def multiplier(self, market: str, phase: str | None) -> float | None:
        """exp(c) of the market in the phase; None when the market or the
        phase has no coefficient (the centre is then left as it is)."""
        if phase is None:
            return None
        c = self.coefficients.get(market, {}).get(phase)
        return None if c is None else math.exp(c)


def apply(centre: float, market: str, phase: str | None,
          table: SeasonPhaseTable | None) -> tuple[float, float | None]:
    """(centre x the phase multiplier, the multiplier or None) - the one
    function SHEET and a history replay both call."""
    if table is None:
        return centre, None
    mult = table.multiplier(market, phase)
    return (centre if mult is None else centre * mult), mult


def parse_table(data: Mapping[str, Any], path: str | None = None) -> SeasonPhaseTable:
    markets = data.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError(f"{path}: no 'markets' object")
    out: dict[str, dict[str, float]] = {}
    for market, cell in markets.items():
        if market not in SEASON_PHASE_MARKETS:
            raise ValueError(f"{path}: {market} is not a season-phase market")
        coefs = cell.get("coefficients") if isinstance(cell, Mapping) else None
        if not isinstance(coefs, Mapping):
            raise ValueError(f"{path}: {market} has no 'coefficients'")
        row: dict[str, float] = {}
        for phase, c in coefs.items():
            if phase not in PHASES or phase == PHASE_MID:
                raise ValueError(f"{path}: {market} phase {phase!r} is not fitted")
            if not isinstance(c, int | float) or isinstance(c, bool) or not (
                    math.isfinite(c) and abs(c) <= MAX_ABS_COEFFICIENT):
                raise ValueError(f"{path}: {market} {phase} {c!r} is not sane")
            row[str(phase)] = float(c)
        out[str(market)] = row
    return SeasonPhaseTable(out, path)


def load_table(path: Path | None = None) -> SeasonPhaseTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent identity would claim a rule the sheet did not use."""
    target = path if path is not None else config_path(CONFIG_FILE)
    return parse_table(json.loads(target.read_text()), str(target))


def fit_coefficients(
    centres: Sequence[float], ys: Sequence[float], phases: Sequence[str | None],
    min_rows: int = MIN_FIT_ROWS,
) -> dict[str, float]:
    """Per phase other than mid: log(sum y / sum centre) of the phase minus
    the same of mid-season (the Poisson MLE of a log-link model with offset
    log centre and one indicator per phase, its intercept left out). A phase
    (or mid) with fewer than `min_rows` centres gives nothing."""
    sy: dict[str, float] = defaultdict(float)
    sc: dict[str, float] = defaultdict(float)
    n: dict[str, int] = defaultdict(int)
    for c, y, p in zip(centres, ys, phases, strict=True):
        if p is None:
            continue
        sy[p] += y
        sc[p] += c
        n[p] += 1
    if n[PHASE_MID] < min_rows or sy[PHASE_MID] <= 0 or sc[PHASE_MID] <= 0:
        return {}
    mid = math.log(sy[PHASE_MID] / sc[PHASE_MID])
    out: dict[str, float] = {}
    for p in PHASES:
        if p == PHASE_MID or n[p] < min_rows or sy[p] <= 0 or sc[p] <= 0:
            continue
        c = math.log(sy[p] / sc[p]) - mid
        out[p] = max(-MAX_ABS_COEFFICIENT, min(MAX_ABS_COEFFICIENT, c))
    return out
