"""The schedule term (epochs.SCHEDULE_TERM, bet.sofa.schedule_term) as it
rides past SHEET: on CONFIDENCE's legs, on SETTLE's 07_settled.json rows and
as one Polish note on the PDF / HTML / dossier / read set. Display and
record only - nothing here gates, prices or re-ranks a leg.

What travels: ``p_central_no_schedule_term`` (the inverted shadow,
T-SCHEDULE-TERM-FORWARD compares it with ``p_central`` on settled legs) and
``schedule_term`` cut to ``status`` / ``t_home`` / ``t_away``. Both sides'
features (two dataclasses with their indicator lists) stay on the SHEET row
only: copied onto every leg and settled row of a fixture's ~dozens of rungs
they would multiply the artifacts' size for nothing the forward test reads,
and the sheet row keyed by (event, market, subject, line, direction) keeps
them. A row without the fields gives none (old artifacts unchanged).

Kept free of the term's own imports (rating book, calendar, DB) so the
renderers and SETTLE read it cheaply; ``APPLIED`` is
``schedule_term.APPLIED`` (a test holds them equal).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

APPLIED = "APPLIED"
TERM_KEYS = ("status", "t_home", "t_away")
NOTE_PL = "kontekst terminarza w modelu"


def compact(term: object) -> dict[str, Any] | None:
    """A row's ``schedule_term`` without the sides' features; None when the
    row carries none."""
    if not isinstance(term, Mapping):
        return None
    return {k: term.get(k) for k in TERM_KEYS if term.get(k) is not None}


def leg_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """What a leg / settled row takes from its SHEET row: each field only
    when the row carries it."""
    out: dict[str, Any] = {}
    term = compact(row.get("schedule_term"))
    if term is not None:
        out["schedule_term"] = term
    shadow = row.get("p_central_no_schedule_term")
    if shadow is not None:
        out["p_central_no_schedule_term"] = shadow
    return out


def in_model(leg: Mapping[str, Any]) -> tuple[float, float] | None:
    """(t_home, t_away) when the term moved this leg's p: status APPLIED and
    a t not zero. A floor key (EXCLUDED_FLOOR), a national fixture or a side
    without coverage (t = 0) is not "in the model"."""
    term = leg.get("schedule_term")
    if not isinstance(term, Mapping) or term.get("status") != APPLIED:
        return None
    try:
        t_home = float(term.get("t_home") or 0.0)
        t_away = float(term.get("t_away") or 0.0)
    except (TypeError, ValueError):
        return None
    if t_home == 0.0 and t_away == 0.0:
        return None
    return t_home, t_away


def _signed(t: float) -> str:
    """t to 3 decimals, signed; a t that rounds to zero is "0.000" (never
    "-0.000" / "+0.000")."""
    r = round(t, 3)
    return "0.000" if r == 0 else f"{r:+.3f}"


def label(leg: Mapping[str, Any]) -> str:
    """The note the PDF / HTML / dossier / read set show beside the leg."""
    t = in_model(leg)
    if t is None:
        return ""
    return f"{NOTE_PL} (t = {_signed(t[0])} gosp. / {_signed(t[1])} gości)"
