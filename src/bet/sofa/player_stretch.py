"""Player shots stretch: the supremacy term of a footballer's shots centre
(switch ``epochs.FOOTBALL_PLAYER_STRETCH_FROM_UTC``, off while None).

A footballer's centre is the mean of his starts in his team's recent
matches - matches of every kind of opponent, so a striker of today's
favourite is priced as if the match were average. With the switch on, the
centre of a market of PLAYER_STRETCH_MARKETS is

    centre x exp(beta x s),  s = his own side's expected goal difference
                             (FootballForecast.supremacy(the side his
                             sample was matched in), clamped)

(bet.sofa.supremacy_stretch), in SHEET and in the cache replay of the
player rows (calibrate_from_cache --player-stretch). beta is fitted by
``scripts/sofa/fit_player_stretch.py`` on the starts-only player rows of the
history (Poisson pseudo-likelihood, offset log centre) into
config/sofa_player_stretch.json. Not the shot-detail markets (their own
estimator, bet.sofa.shot_detail), nor fouls / tackles / offsides / assists
(measured no gain, or the OVER curve not significant).

Measured 2026-10-17 (starts-only player rows, fit before 2026, tested on
2026; s today, the team's expected goal difference): player_shots_for beta
0.126, player_shots_on_target_for 0.117, log-loss on the ladder lines better
before and after the bucket curve. A covariate of s relative to the
sample's matches measured a larger beta and is not used (it needs the
sample's own past supremacies, which SHEET does not hold). Evidence:
EVIDENCE.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bet.sofa import supremacy_stretch as ss

CONFIG_FILE = "sofa_player_stretch.json"
EVIDENCE = "docs/sofa/evidence/player_stretch_2026-10-17.md"
PLAYER_STRETCH_MARKETS: tuple[str, ...] = (
    "player_shots_for", "player_shots_on_target_for")
PLAYER_STRETCH_UNFITTED = ss.STRETCH_UNFITTED
SPEC = ss.StretchSpec("player-stretch", PLAYER_STRETCH_MARKETS)


class PlayerStretchTable(ss.StretchTable):
    SPEC = SPEC


def parse_table(data: Mapping[str, Any], path: str | None = None) -> PlayerStretchTable:
    single, phased = ss.parse_cells(SPEC, data, path)
    return PlayerStretchTable(single, path, phased)


def load_table(path: Path | None = None) -> PlayerStretchTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent identity would claim a rule the sheet did not use."""
    data, where = ss.read_file(CONFIG_FILE, path)
    return parse_table(data, where)
