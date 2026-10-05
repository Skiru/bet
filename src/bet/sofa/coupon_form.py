"""The coupon's structure across legs of one match (plan 2026-10-05 production
grade, F4.2 / F4.3): the ladder form and the exposure per match.

**Ladder form** (F4.2). A ladder - two or more legs of one match that are the
same variable (bet.sofa.leg_relations: U2.5 and U3.5 goals, an OVER and an
UNDER of one count) - is one decision, not independent bets. Two forms:

* ``group`` (default): every rung prints, grouped on the PDF under one header
  "ta sama zmienna" that lists the rungs. Nothing is dropped.
* ``one_rung``: one rung per variable, the highest x = confidence x odds
  (leg_relations.one_rung_per_variable); the other rungs go to
  ``removed_by_coupon_form`` in 11_coupon.json, never graded as the coupon.
  The operator's decision (plan section 5, point 1) - OFF by default.

**Exposure** (F4.3): per match, how many positions, what share of the coupon,
the sum of their confidence, and how many positions (plus printed builders)
are lost if every leg of the match loses; and on how many matches the first
30 positions stand. No limit by default (operator decision); the hook is
``max_positions_per_match`` - a number keeps the first N positions of a match
in coupon order and moves the rest to ``removed_by_coupon_form``.

Both dials are read from ``config/sofa_coupon_form.json`` when it exists::

    {"ladder_form": "group", "max_positions_per_match": null}

and default to the constants below. They change WHICH legs print, so they act
only from ``epochs.COUPON_STRUCTURE_FROM_UTC`` on a day >= 2026-10-06 (never
mid-day); a dial set before that is reported in the artifact as not applied.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bet.sofa.config import config_path
from bet.sofa.leg_relations import one_rung_per_variable

LADDER_FORM_GROUP = "group"
LADDER_FORM_ONE_RUNG = "one_rung"
LADDER_FORMS = (LADDER_FORM_GROUP, LADDER_FORM_ONE_RUNG)

# The defaults: every rung prints (grouped), no cap per match.
LADDER_FORM = LADDER_FORM_GROUP
MAX_POSITIONS_PER_MATCH: int | None = None

COUPON_FORM_FILE = "sofa_coupon_form.json"

# "positions 1-30 sit on N matches": the analysts' read set (C3).
TOP_POSITIONS = 30


@dataclass(frozen=True)
class CouponForm:
    ladder_form: str = LADDER_FORM
    max_positions_per_match: int | None = MAX_POSITIONS_PER_MATCH
    source: str = "default"

    def is_default(self) -> bool:
        return (self.ladder_form == LADDER_FORM_GROUP
                and self.max_positions_per_match is None)

    def as_dict(self) -> dict[str, Any]:
        return {"ladder_form": self.ladder_form,
                "max_positions_per_match": self.max_positions_per_match,
                "source": self.source}


def load_coupon_form(path: Path | None = None) -> CouponForm:
    """The coupon-form dials; a missing file is the defaults. An unreadable
    file or a value outside the allowed set raises - a dial that silently
    does nothing reads like one that was honoured."""
    p = path if path is not None else config_path(COUPON_FORM_FILE)
    if not p.exists():
        return CouponForm()
    doc = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{p}: an object expected")
    unknown = set(doc) - {"ladder_form", "max_positions_per_match", "note"}
    if unknown:
        raise ValueError(f"{p}: unknown keys {sorted(unknown)}")
    form = doc.get("ladder_form", LADDER_FORM)
    if form not in LADDER_FORMS:
        raise ValueError(f"{p}: ladder_form must be one of {LADDER_FORMS}: {form!r}")
    cap = doc.get("max_positions_per_match", MAX_POSITIONS_PER_MATCH)
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int)
                            or cap < 1):
        raise ValueError(f"{p}: max_positions_per_match must be null or >= 1: {cap!r}")
    return CouponForm(str(form), cap, str(p.name))


def _group(leg: Mapping[str, Any]) -> str:
    return str(leg.get("group_key") or f"sofa:{int(leg['sofascore_event_id'])}")


def apply_form(
    fresh: Sequence[dict[str, Any]], form: CouponForm, active: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(kept, removed) of the fresh legs under the form; with the defaults
    or before the epoch (`active` False) nothing is removed."""
    from bet.sofa.confidence import coupon_order

    legs = list(fresh)
    if not active or form.is_default():
        return legs, []
    removed: list[dict[str, Any]] = []
    if form.ladder_form == LADDER_FORM_ONE_RUNG:
        legs, dropped = one_rung_per_variable(legs)
        removed.extend(dropped)
    cap = form.max_positions_per_match
    if cap is not None:
        kept_ids: set[int] = set()
        for block in coupon_order(legs):
            kept_ids.update(id(x) for x in block.legs[:cap])
        removed.extend({**x, "refusal": "MAX_POSITIONS_PER_MATCH"}
                       for x in legs if id(x) not in kept_ids)
        legs = [x for x in legs if id(x) in kept_ids]
    return legs, removed


def exposure(
    singles: Sequence[Mapping[str, Any]],
    builders: Sequence[Mapping[str, Any]],
    max_positions_per_match: int | None = None,
    top: int = TOP_POSITIONS,
) -> dict[str, Any]:
    """How much of the coupon stands on each match (F4.3).

    `singles`: the coupon's singles (numbered positions and locked legs);
    `builders`: the printed builders. A position is a numbered single; a
    locked leg is counted apart. `worst_case_lost` is what one match takes if
    every leg on it loses: its positions, locked legs and printed builders.
    """
    numbered = [s for s in singles if s.get("position") is not None]
    total = len(numbered)
    per: dict[str, dict[str, Any]] = {}

    def row(leg: Mapping[str, Any]) -> dict[str, Any]:
        k = _group(leg)
        if k not in per:
            per[k] = {"group_key": k, "match": leg.get("match", ""),
                      "sport": leg.get("sport") or "football",
                      "kickoff_utc": leg.get("kickoff_utc"),
                      "positions": [], "locked": 0, "builders": [],
                      "confidence_sum": 0.0}
        return per[k]

    for s in singles:
        r = row(s)
        if s.get("position") is None:
            r["locked"] += 1
        else:
            r["positions"].append(int(s["position"]))
            r["confidence_sum"] += float(s["confidence"])
    for b in builders:
        row(b)["builders"].append(b.get("builder_no") or "B")
    out_rows = []
    for r in per.values():
        n = len(r["positions"])
        out_rows.append({
            **r,
            "n_positions": n,
            "share_of_positions": round(n / total, 4) if total else 0.0,
            "confidence_sum": round(r["confidence_sum"], 3),
            "worst_case_lost": n + r["locked"] + len(r["builders"]),
            "over_limit": (max_positions_per_match is not None
                           and n > max_positions_per_match),
        })
    out_rows.sort(key=lambda r: (-r["n_positions"], min(r["positions"] or [10**9])))
    top_matches = sorted({_group(s) for s in numbered
                          if int(s["position"]) <= top})
    return {
        "positions": total,
        "matches": sum(1 for r in out_rows if r["n_positions"]),
        "max_positions_per_match": max_positions_per_match,
        "top_positions": top,
        "top_positions_matches": len(top_matches),
        "top_positions_group_keys": top_matches,
        "per_match": out_rows,
    }
