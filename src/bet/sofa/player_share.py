"""The footballer share model (epochs.FOOTBALL_PLAYER_SHARE_FROM_UTC).

A footballer's centre priced off his side instead of off his own short
sample alone:

    centre = share x T
    share  = (his volume over his sampled starts + m x prior_share)
             / (his side's volume in the same matches + m)

T is his side's team centre today for the market's team metric - the
centre SHEET prices the side's row with (the sample shrunk to the league,
the rating blend, game state, the opponent correction), so the player row
inherits the opponent and the game script. For shots on target the volume
is his shots and the centre is multiplied by his accuracy shrunk hard to his
position's (accuracy repeats far less than volume: StatsBomb, striker
shots/90 R^2 0.435 vs SOT/90 0.234). For fouls the volume is his fouls and
T his side's fouls_for centre.

Arithmetic only; SHEET reads ``config/sofa_player_share.json`` (the fitted
m, m_accuracy and the position priors, written by
scripts/sofa/measure_player_share.py) and applies it only from the switch.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.config import config_path

CONFIG_FILE = "sofa_player_share.json"
MARKER = "player_share_v1"
NOTE = "PLAYER_SHARE"

# player market -> the team metric whose centre is T
TEAM_METRIC: dict[str, str] = {
    "player_shots_for": "shots_for",
    "player_shots_on_target_for": "shots_for",
    "player_fouls_for": "fouls_for",
    "player_tackles_for": "tackles_for",
}
# team metric -> its /statistics key (bet.sofa.metrics)
TEAM_METRIC_KEYS: dict[str, str] = {
    "shots_for": "totalShotsOnGoal",
    "fouls_for": "fouls",
    "tackles_for": "totalTackle",
}
# player market -> the player metric whose share of the side is taken
VOLUME_METRIC: dict[str, str] = {
    "player_shots_for": "player_shots_for",
    "player_shots_on_target_for": "player_shots_for",
    "player_fouls_for": "player_fouls_for",
    "player_tackles_for": "player_tackles_for",
}
# markets whose centre is volume x accuracy
ACCURACY_MARKETS: frozenset[str] = frozenset({"player_shots_on_target_for"})
# fewer matched starts than this: the share is not read, the old centre is
MIN_SHARE_MATCHES = 3
ALL_POSITIONS = "*"


def share_centre(
    *,
    his_volume: float,
    team_volume: float,
    team_centre: float,
    prior_share: float,
    m: float,
    his_count: float | None = None,
    prior_accuracy: float | None = None,
    m_accuracy: float | None = None,
) -> float:
    """share x T (x the shrunk accuracy when ``his_count`` is given)."""
    denom = team_volume + m
    share = (his_volume + m * prior_share) / denom if denom > 0 else prior_share
    centre = share * team_centre
    if his_count is not None and prior_accuracy is not None:
        ma = m_accuracy or 0.0
        acc_denom = his_volume + ma
        accuracy = ((his_count + ma * prior_accuracy) / acc_denom
                    if acc_denom > 0 else prior_accuracy)
        centre *= accuracy
    return centre


@dataclass(frozen=True)
class ShareInputs:
    """His volume and his side's over the matches both are known in."""

    his_volume: float
    team_volume: float
    matches: int
    # his count of the market itself over the same matches (accuracy markets)
    his_count: float | None


def share_inputs(
    volume: Sequence[tuple[int, float]],
    team: Sequence[tuple[int, float]],
    own: Sequence[tuple[int, float]] | None = None,
) -> ShareInputs:
    """``volume`` his (event id, volume) over his sampled starts, ``team`` his
    side's (event id, team volume), ``own`` (accuracy markets) his (event id,
    count) - summed over the events present in every list given."""
    team_by = dict(team)
    own_by = dict(own) if own is not None else None
    hv = tv = hc = 0.0
    k = 0
    for event_id, value in volume:
        if event_id not in team_by:
            continue
        if own_by is not None and event_id not in own_by:
            continue
        hv += value
        tv += team_by[event_id]
        if own_by is not None:
            hc += own_by[event_id]
        k += 1
    return ShareInputs(hv, tv, k, hc if own_by is not None else None)


@dataclass(frozen=True)
class ShareCell:
    m: float
    prior_share: dict[str, float]
    m_accuracy: float | None = None
    prior_accuracy: dict[str, float] = field(default_factory=dict)

    def describe(self) -> str:
        text = f"m {self.m:g}"
        if self.m_accuracy is not None:
            text += f", accuracy m {self.m_accuracy:g}"
        return text

    def share_prior(self, position: str | None) -> float:
        return self.prior_share.get(position or "", self.prior_share[ALL_POSITIONS])

    def accuracy_prior(self, position: str | None) -> float | None:
        if not self.prior_accuracy:
            return None
        return self.prior_accuracy.get(position or "",
                                       self.prior_accuracy.get(ALL_POSITIONS))


@dataclass(frozen=True)
class ShareTable:
    markets: dict[str, ShareCell]
    path: str | None = None

    def cell(self, market: str) -> ShareCell | None:
        return self.markets.get(market)


def _positive(value: Any) -> bool:
    return (isinstance(value, int | float) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) >= 0.0)


def _priors(raw: Any, what: str, market: str) -> dict[str, float]:
    if not isinstance(raw, Mapping) or ALL_POSITIONS not in raw:
        raise ValueError(f"{market}: {what} needs a {ALL_POSITIONS!r} entry")
    out: dict[str, float] = {}
    for key, value in raw.items():
        if not _positive(value) or float(value) > 1.0:
            raise ValueError(f"{market}: {what}[{key!r}] = {value!r}")
        out[str(key)] = float(value)
    return out


def parse_table(data: Mapping[str, Any], path: str | None = None) -> ShareTable:
    markets = data.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError("player share file without 'markets'")
    out: dict[str, ShareCell] = {}
    for market, cell in markets.items():
        if market not in TEAM_METRIC:
            raise ValueError(f"not a player share market: {market!r}")
        if not isinstance(cell, Mapping) or not _positive(cell.get("m")):
            raise ValueError(f"{market}: bad cell {cell!r}")
        m_acc = cell.get("m_accuracy")
        if market in ACCURACY_MARKETS:
            if not _positive(m_acc):
                raise ValueError(f"{market}: needs m_accuracy")
            acc = _priors(cell.get("prior_accuracy"), "prior_accuracy", market)
        else:
            m_acc = None
            acc = {}
        out[str(market)] = ShareCell(
            m=float(cell["m"]),
            prior_share=_priors(cell.get("prior_share"), "prior_share", market),
            m_accuracy=None if m_acc is None else float(m_acc),
            prior_accuracy=acc,
        )
    return ShareTable(out, path)


def load_table(path: Path | None = None) -> ShareTable:
    target = path if path is not None else config_path(CONFIG_FILE)
    with open(target, encoding="utf-8") as fh:
        return parse_table(json.load(fh), str(target))
