"""K_CENTRE per football market (switch `epochs.PER_MARKET_K_FROM_UTC`, off
while it is None).

SHEET shrinks a sample's mean toward the league prior with one K per sport
(`K_CENTRE.by_sport.football` = 15). Measured out of sample (track W4,
docs/sofa/evidence/k_under_dispersion_2026-10-08.md; test 2026-06-09..10-07,
the spread already the history-fitted dispersion) the shots and fouls markets
want a much smaller K (the teams differ more than the pooled K allows), a few
others a different one. `K_CENTRE.by_market.football` in
config/sofa_engine_constants.json holds only the markets whose K was chosen on
the train rows' log-loss AND validated on their last third; a market absent
from it reads the sport's K, byte for byte.

One reader for SHEET and the cache replay (calibrate_from_cache), so what is
measured is what ships.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SPORT = "football"


def k_for_market(
    engine_constants: Mapping[str, Any], sport: str | None, market: str,
    sport_k: float,
) -> float:
    """The K of one marketed row: its own `K_CENTRE.by_market.<sport>.<market>`
    when the file has one, else `sport_k` (the K the row would read today).
    Only football is read."""
    if sport != SPORT:
        return sport_k
    entry = engine_constants.get("K_CENTRE")
    if not isinstance(entry, Mapping):
        return sport_k
    by_market = entry.get("by_market")
    if not isinstance(by_market, Mapping):
        return sport_k
    cell = by_market.get(sport)
    if not isinstance(cell, Mapping):
        return sport_k
    value = cell.get(market)
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return sport_k
