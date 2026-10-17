"""The supremacy stretch: one multiplier of a football centre by the rating's
expected goal difference, shared by the goals stretch
(bet.sofa.goals_stretch, epochs.FOOTBALL_GOALS_STRETCH), the count stretch
(bet.sofa.count_stretch, epochs.FOOTBALL_COUNT_STRETCH) and the player
shots stretch (bet.sofa.player_stretch, epochs.FOOTBALL_PLAYER_STRETCH).
Each keeps its own switch, config file, marker and market list (its
``StretchSpec``); only the arithmetic, the file grammar and the fit live
here.

With a table loaded, the centre of one of the spec's markets is

    side  : centre x exp(beta x s + beta2 x s^2),  s = the side's expected
                                                   goal difference
    total : centre x exp(g1 x |s| + g2 x s^2),     s = the home side's

where s comes from the rating's own goals book as of the match
(``FootballForecast.supremacy``, the covariate of bet.sofa.game_state),
clamped at game_state.MAX_SUPREMACY. ``beta2`` is optional (absent = a
linear side term); a total gives both g1 and g2 (g2 0 = |s| alone). A spec
that is ``phased`` may also give a market one coefficient set per season
phase (bet.sofa.season_phase's labels, a match with no phase reading
``none``): a phase the table lacks reads the market's single set, else the
centre is left as it is. A market absent from the table, or a fixture with
no goals rating, keeps its centre byte for byte.

The file (``markets`` object; extra keys such as n_rows are carried):

    "goals_for":   {"beta": 0.062, "by_phase": {"early": {"beta": 0.018}}}
    "goals_total": {"g1": -0.015, "g2": 0.023}
    "throw_ins_for": {"beta": 0.0457, "beta2": -0.0171}

The coefficients are fitted by Poisson pseudo-likelihood, log link, offset
log centre (``fit_terms``: consistent for the mean whatever the count's
dispersion).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

import numpy as np

from bet.sofa.config import config_path
from bet.sofa.game_state import clamp_supremacy
from bet.sofa.season_phase import PHASES

# the label of a match with no season phase (season_phase returns None)
PHASE_NONE = "none"
STRETCH_PHASES: tuple[str, ...] = (*PHASES, PHASE_NONE)
# s is capped as in game_state (chosen, not fitted)
STRETCH_UNFITTED: tuple[str, ...] = ("MAX_SUPREMACY",)
# A coefficient at or beyond this is a broken fit, not a football effect: at
# MAX_SUPREMACY it would multiply a centre by e^3 (side) or more (total).
MAX_ABS_COEFFICIENT = 1.0
SIDE_NAMES: tuple[str, ...] = ("beta", "beta2")
TOTAL_NAMES: tuple[str, ...] = ("g1", "g2")


class _Supremacy(Protocol):
    def supremacy(self, side: str) -> float | None: ...


def phase_key(phase: str | None) -> str:
    """The table's label of a season phase (None: ``none``)."""
    return PHASE_NONE if phase is None else phase


@dataclass(frozen=True)
class StretchSpec:
    """Which markets one stretch covers and what its file may say."""

    label: str  # "goals-stretch", in error messages
    side_markets: tuple[str, ...]
    total_markets: tuple[str, ...] = ()
    # may a market carry one coefficient set per season phase
    phased: bool = False
    # may a side market carry an s^2 term (beta2)
    side_quadratic: bool = False

    @property
    def markets(self) -> tuple[str, ...]:
        return self.side_markets + self.total_markets

    def is_total(self, market: str) -> bool:
        return market in self.total_markets


def features(total: bool, supremacy: float) -> tuple[float, float]:
    """The covariates of the clamped s: (s, s^2) for a side market, (|s|,
    s^2) for a total; a coefficient set uses as many as it has."""
    s = clamp_supremacy(supremacy)
    return (abs(s), s * s) if total else (s, s * s)


def stretch_supremacy(forecast: _Supremacy, side: str | None,
                      total: bool) -> float | None:
    """The s a market's term reads: the side's own for a side market (None
    without a side), the home side's for a total; None when the goals rating
    gives no centre."""
    if total:
        return forecast.supremacy("side_a")
    if side not in ("side_a", "side_b"):
        return None
    return forecast.supremacy(side)


@dataclass(frozen=True)
class StretchTable:
    """A fitted stretch. Subclasses name their ``SPEC``."""

    SPEC: ClassVar[StretchSpec]
    # market -> (beta[, beta2]) for a side market, (g1, g2) for a total
    coefficients: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    path: str | None = None
    # market -> phase label -> coefficients (a phased spec only)
    by_phase: Mapping[str, Mapping[str, tuple[float, ...]]] = field(
        default_factory=dict)

    def coefficients_for(self, market: str,
                         phase: str | None = None) -> tuple[float, ...] | None:
        """The phase's own set, else the market's single set, else None."""
        cell = self.by_phase.get(market)
        if cell is not None:
            coefs = cell.get(phase_key(phase))
            if coefs is not None:
                return coefs
        return self.coefficients.get(market)

    def multiplier(self, market: str, supremacy: float | None,
                   phase: str | None = None) -> float | None:
        """exp(coefficients . features) for the market (in the phase), None
        when it has no coefficients or the fixture no supremacy (the centre
        is then left as it is)."""
        coefs = self.coefficients_for(market, phase)
        if coefs is None or supremacy is None:
            return None
        x = features(self.SPEC.is_total(market), supremacy)
        return math.exp(sum(c * v for c, v in zip(coefs, x, strict=False)))

    def describe(self, market: str, phase: str | None = None) -> str:
        coefs = self.coefficients_for(market, phase)
        if coefs is None:
            return "no coefficients"
        names = TOTAL_NAMES if self.SPEC.is_total(market) else SIDE_NAMES
        text = ", ".join(f"{n} {c:+.4f}" for n, c in zip(names, coefs, strict=False))
        own = self.by_phase.get(market, {}).get(phase_key(phase))
        return f"{text} (phase {phase_key(phase)})" if own is not None else text


def _coefficient(path: str | None, market: str, name: str, raw: Any) -> float:
    if not isinstance(raw, int | float) or isinstance(raw, bool) or not (
            math.isfinite(raw) and abs(raw) < MAX_ABS_COEFFICIENT):
        raise ValueError(f"{path}: {market} {name} {raw!r} is not a sane number")
    return float(raw)


def _coefficient_set(spec: StretchSpec, path: str | None, market: str,
                     total: bool, cell: Mapping[str, Any]) -> tuple[float, ...]:
    if total:
        if "beta" in cell or "beta2" in cell:
            raise ValueError(f"{path}: {market} is a total (g1 / g2, not beta)")
        return tuple(_coefficient(path, market, n, cell.get(n)) for n in TOTAL_NAMES)
    if "g1" in cell or "g2" in cell:
        raise ValueError(f"{path}: {market} is a side market (beta, not g1 / g2)")
    coefs = [_coefficient(path, market, "beta", cell.get("beta"))]
    if "beta2" in cell:
        if not spec.side_quadratic:
            raise ValueError(f"{path}: {market}: {spec.label} has no s^2 side term")
        coefs.append(_coefficient(path, market, "beta2", cell.get("beta2")))
    return tuple(coefs)


def _has_single(cell: Mapping[str, Any]) -> bool:
    return any(n in cell for n in (*SIDE_NAMES, *TOTAL_NAMES))


def parse_cells(
    spec: StretchSpec, data: Mapping[str, Any], path: str | None = None,
) -> tuple[dict[str, tuple[float, ...]], dict[str, dict[str, tuple[float, ...]]]]:
    """(single coefficients, per-phase coefficients) of a stretch file;
    anything the spec does not allow raises."""
    markets = data.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError(f"{path}: no 'markets' object")
    single: dict[str, tuple[float, ...]] = {}
    phased: dict[str, dict[str, tuple[float, ...]]] = {}
    for market, cell in markets.items():
        if market not in spec.markets:
            raise ValueError(f"{path}: {market} is not a {spec.label} market")
        if not isinstance(cell, Mapping):
            raise ValueError(f"{path}: {market} is not an object")
        total = spec.is_total(market)
        phases = cell.get("by_phase")
        if phases is None and not _has_single(cell):
            raise ValueError(f"{path}: {market} has no coefficients")
        if _has_single(cell):
            single[str(market)] = _coefficient_set(spec, path, market, total, cell)
        if phases is None:
            continue
        if not spec.phased:
            raise ValueError(f"{path}: {spec.label} has no per-phase terms "
                             f"({market})")
        if not isinstance(phases, Mapping) or not phases:
            raise ValueError(f"{path}: {market} by_phase is not a non-empty object")
        row: dict[str, tuple[float, ...]] = {}
        for phase, pcell in phases.items():
            if phase not in STRETCH_PHASES:
                raise ValueError(f"{path}: {market} phase {phase!r} is not one "
                                 f"of {list(STRETCH_PHASES)}")
            if not isinstance(pcell, Mapping):
                raise ValueError(f"{path}: {market} {phase} is not an object")
            row[str(phase)] = _coefficient_set(
                spec, path, f"{market} [{phase}]", total, pcell)
        phased[str(market)] = row
    return single, phased


def read_file(name: str, path: Path | None = None) -> tuple[dict[str, Any], str]:
    """(the file's JSON, its path). Missing or unreadable raises: with a
    switch on a silent identity would claim a rule the sheet did not use."""
    target = path if path is not None else config_path(name)
    data = json.loads(target.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{target}: not a JSON object")
    return data, str(target)


def fit_terms(
    total: bool, centres: Sequence[float], supremacy: Sequence[float],
    y: Sequence[float], terms: int = 1, iterations: int = 60,
) -> tuple[float, ...]:
    """The first ``terms`` coefficients maximising sum(y x b.x - c x
    exp(b.x)) (Poisson pseudo-likelihood with offset log c), x =
    features(total, s). Newton from 0, as game_state.fit_beta; zeros when
    the Hessian is singular."""
    if terms not in (1, 2):
        raise ValueError(f"terms {terms}: 1 or 2")
    c = np.asarray(centres, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    x = np.asarray([features(total, s)[:terms] for s in supremacy],
                   dtype=np.float64).reshape(len(c), terms)
    b = np.zeros(terms)
    if len(c) == 0:
        return tuple(float(v) for v in b)
    for _ in range(iterations):
        mu = c * np.exp(x @ b)
        grad = x.T @ (yy - mu)
        hess = (x * mu[:, None]).T @ x
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            return tuple(0.0 for _ in range(terms))
        b = b + step
        if float(np.abs(step).max()) < 1e-10:
            break
    return tuple(float(v) for v in b)


def cell_json(total: bool, coefs: Sequence[float]) -> dict[str, float]:
    """A coefficient set as the file writes it (a total always both g1 and
    g2; a side beta, and beta2 when fitted)."""
    if total:
        full = (list(coefs) + [0.0, 0.0])[:2]
        return {n: round(float(v), 6) for n, v in zip(TOTAL_NAMES, full, strict=True)}
    return {n: round(float(v), 6) for n, v in zip(SIDE_NAMES, coefs, strict=False)}
