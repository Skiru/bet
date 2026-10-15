"""League strength learnt in international club competitions
(epochs.FOOTBALL_CUP_STRENGTH_FROM_UTC).

The list of cups and the step of the per-league correction live in
``config/sofa_cup_strength.json``; ``apply`` sets them on a
``football_rating.RatingBook`` before its first update, so the correction is
learnt inside the book as it replays the history (SHEET's
``football_rating.replay`` and the cache replay alike). The file is an
operator list with one chosen step, not a fit: it is not part of
``sheet_config.fingerprint`` - the row marker ``cup_strength_rule`` is what
makes a rebuild re-run SHEET.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bet.sofa.config import config_dir
from bet.sofa.football_rating import RatingBook

CUP_STRENGTH_FILE = "sofa_cup_strength.json"


@dataclass(frozen=True)
class CupStrength:
    competitions: frozenset[int]
    # metric -> step of the per-league correction; only metrics measured
    # better out of sample (the evidence file) carry one
    eta: dict[str, float]


def load(path: Path | None = None) -> CupStrength:
    """The installed cup list and step; raises when the file is missing or
    malformed (a switched-on rule never silently prices without it)."""
    p = path if path is not None else config_dir() / CUP_STRENGTH_FILE
    data = json.loads(p.read_text(encoding="utf-8"))
    comps = frozenset(int(c) for c in data["competitions"])
    eta = {str(m): float(v) for m, v in data["eta"].items()}
    if not comps or not eta or not all(0.0 < v < 1.0 for v in eta.values()):
        raise ValueError(f"{p}: empty competitions / eta or a step outside (0, 1)")
    return CupStrength(comps, eta)


def apply(book: RatingBook, cup: CupStrength | None) -> RatingBook:
    """The book with the cup correction on (None: unchanged). Before the
    book's first update - a correction switched on mid-replay would read a
    book that never learnt it."""
    if cup is not None:
        if book.last_ts:
            raise ValueError("cup strength applied to a book already updated")
        book.cup_competitions = cup.competitions
        book.cup_eta = dict(cup.eta)
    return book
