"""The fingerprint of the fitted config files SHEET prices with.

A refit install (`prepare_refit.py install`: engine constants, league
baselines, market reliability; with its flags the count dispersion and the
tennis rating) or a fit of the audit 2026-10-13 tables changes `p_central`
without any switch in `bet.sofa.epochs`, so a rebuild could not tell a sheet
priced on the old constants from one priced on the new (2026-10-13: SHEET was
re-run by hand after the 18:06Z install). SHEET stamps this fingerprint on
every row (`config_sha`); `rebuild_plan` compares it with the files as they
stand and names a difference. It does not re-run SHEET for it: an install is
not dated, and a constants install never goes into a day already built
(CLAUDE.md, hard rules) except under an explicit go, when the operator re-runs
SHEET himself. The history curves are not here: CONFIDENCE reads them on
every rebuild.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from bet.sofa.config import config_dir

# Every fitted file SHEET reads (scripts/sofa/run_sheet.py and the loaders it
# calls). Operator lists (friendlies, women's competitions, ...) are not fits.
SHEET_CONFIG_FILES: tuple[str, ...] = (
    "sofa_engine_constants.json",
    "sofa_league_baselines.json",
    "sofa_market_reliability.json",
    "sofa_tennis_tier_baselines.json",
    "tennis_rating.json",
    "sofa_count_dispersion.json",
    "sofa_side_correlations.json",
    "sofa_game_state.json",
    "sofa_season_phase.json",
    "sofa_rating_weight.json",
)
# Fitted files SHEET reads that enter the fingerprint only once installed, so
# the fingerprint of every sheet priced before one existed is unchanged:
# config/sofa_shot_detail.json (epochs.SHOT_DETAIL_MARKETS, the operator's
# install of scripts/sofa/fit_shot_detail.py), config/sofa_goals_stretch.json
# (epochs.FOOTBALL_GOALS_STRETCH, scripts/sofa/fit_goals_stretch.py),
# config/sofa_count_stretch.json (epochs.FOOTBALL_COUNT_STRETCH,
# scripts/sofa/fit_count_stretch.py), config/sofa_player_stretch.json
# (epochs.FOOTBALL_PLAYER_STRETCH, scripts/sofa/fit_player_stretch.py).
SHEET_OPTIONAL_FILES: tuple[str, ...] = (
    "sofa_shot_detail.json", "sofa_goals_stretch.json",
    "sofa_count_stretch.json", "sofa_player_stretch.json")
DIGEST_CHARS = 16


def fingerprint(directory: Path | None = None) -> str:
    """sha256 over the names and bytes of SHEET_CONFIG_FILES (a missing file
    counts as absent) and of the SHEET_OPTIONAL_FILES present, the first
    DIGEST_CHARS hex characters."""
    base = directory if directory is not None else config_dir()
    h = hashlib.sha256()
    for name in SHEET_CONFIG_FILES:
        path = base / name
        h.update(name.encode())
        h.update(b"\0")
        h.update(path.read_bytes() if path.is_file() else b"<absent>")
        h.update(b"\0")
    for name in SHEET_OPTIONAL_FILES:
        path = base / name
        if path.is_file():
            h.update(name.encode())
            h.update(b"\0")
            h.update(path.read_bytes())
            h.update(b"\0")
    return h.hexdigest()[:DIGEST_CHARS]
