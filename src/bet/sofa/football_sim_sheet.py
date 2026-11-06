"""SHEET's reading of the football minute-by-minute simulator
(epochs.FOOTBALL_SIM_FROM_UTC; the model: bet.sofa.football_sim, measured in
docs/sofa/evidence/football_sim_2026-11-06.md; the wiring:
docs/sofa/evidence/football_sim_wiring_2026-11-06.md).

For a football row of ``epochs.FOOTBALL_SIM_MARKETS`` (the path markets,
bet.sofa.football_sim_markets) SHEET takes its p_central from here. The
centres are the ones SHEET already computes for the fixture: the pure rating
(``FootballForecast.centre``) goals centre of each side and its card-points
centre (the red-card process' base). A side with no goals centre gives no
price: SHEET refuses the row (NOT_RATED), never falls back to another
estimator - the curves of these keys describe this simulator only.

Simulation: SIMS = 4,000 matches per fixture, seeded by the event id (the
measurement's ``simulate(params, centres, n=4000, seed=eid % 2**31)``), so a
re-run prices the same. Only the goal / red-card paths are read: the per-half
counts are drawn after them from the same generator and change no path, so
they are not simulated here (``Centres.halves`` empty).

The fitted constants (``SimParams``) are config/sofa_football_sim_params.json
- the measurement's params.json (fitted on the history 2025-01-01 ..
2026-05-31, hyper-parameters chosen on 2026-03 .. 05), never refitted here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from bet.sofa.config import config_path
from bet.sofa.football_sim import (
    Centres,
    MarketSim,
    SimParams,
    path_outcomes,
    simulate,
)
from bet.sofa.football_sim_markets import MARKETS, describe, path_spec

SIMS = 4000
NOTE = "FOOTBALL_SIM"
PARAMS_FILE = "sofa_football_sim_params.json"


class _Rated(Protocol):
    def centre(self, market: str, side: str | None) -> tuple[float, str] | None:
        ...


def in_scope(sport: object, market: str) -> bool:
    return sport == "football" and market in MARKETS


def seed_of(event_id: int) -> int:
    return event_id % (2 ** 31)


def load_params(path: Path | None = None) -> SimParams | None:
    """The simulator's fitted constants; None when the file is absent."""
    p = path if path is not None else config_path(PARAMS_FILE)
    if not p.exists():
        return None
    return SimParams.from_json(json.loads(p.read_text(encoding="utf-8")))


def centres_of(football: _Rated | None) -> Centres | None:
    """The fixture's goals (and card-points) centres from SHEET's rating
    forecast; None without a goals centre for either side."""
    if football is None:
        return None
    home = football.centre("goals_for", "side_a")
    away = football.centre("goals_for", "side_b")
    if home is None or away is None or home[0] <= 0 or away[0] <= 0:
        return None
    ch = football.centre("cards_points_for", "side_a")
    ca = football.centre("cards_points_for", "side_b")
    cards = (None if ch is None or ca is None or min(ch[0], ca[0]) <= 0
             else (float(ch[0]), float(ca[0])))
    return Centres(goals=(float(home[0]), float(away[0])), halves={}, cards=cards)


@dataclass
class SimPricer:
    """One simulation per fixture (cached), every path market read off it."""

    params: SimParams
    sims: int = SIMS
    _sims: dict[int, MarketSim] = field(default_factory=dict)
    _centres: dict[int, Centres] = field(default_factory=dict)
    _outcomes: dict[tuple[int, str, Any], dict[str, float]] = field(
        default_factory=dict)

    def market_sim(self, event_id: int, centres: Centres) -> MarketSim:
        got = self._sims.get(event_id)
        if got is None or self._centres.get(event_id) != centres:
            got = MarketSim(simulate(self.params, centres, n=self.sims,
                                     seed=seed_of(event_id)))
            self._sims[event_id] = got
            self._centres[event_id] = centres
            for key in [k for k in self._outcomes if k[0] == event_id]:
                del self._outcomes[key]
        return got

    def outcomes(self, event_id: int, centres: Centres, kind: str,
                 param: Any) -> dict[str, float]:
        ms = self.market_sim(event_id, centres)
        key = (event_id, kind, param)
        got = self._outcomes.get(key)
        if got is None:
            got = {k: float(v.mean())
                   for k, v in path_outcomes(ms, kind, param).items()}
            self._outcomes[key] = got
        return got

    def p(self, event_id: int, centres: Centres, market: str, subject: str,
          direction: str) -> float | None:
        """P of the row's selection; None when the simulator does not read it."""
        spec = path_spec(market, subject, direction)
        if spec is None:
            return None
        kind, param, outcome = spec
        return self.outcomes(event_id, centres, kind, param).get(outcome)

    def forget(self, event_id: int) -> None:
        self._sims.pop(event_id, None)
        self._centres.pop(event_id, None)
        for key in [k for k in self._outcomes if k[0] == event_id]:
            del self._outcomes[key]


def note(market: str, subject: str, direction: str, p: float,
         centres: Centres, sims: int = SIMS) -> str:
    cards = ("default" if centres.cards is None
             else f"{centres.cards[0]:.2f} / {centres.cards[1]:.2f}")
    return (f"{NOTE}: {describe(market, subject, direction)} p {p:.4f} from "
            f"{sims} simulated matches (bet.sofa.football_sim; pure rating "
            f"goals centres home {centres.goals[0]:.3f} / away "
            f"{centres.goals[1]:.3f}, card points {cards}); no sample, no "
            "price - the confidence is the key's own history curve "
            "(epochs.FOOTBALL_SIM)")


def describe_params(params: SimParams) -> Mapping[str, Any]:
    return {"fitted_to": params.fitted_to, "goal_frailty": params.goal_frailty,
            "match_mean": params.match_mean}
