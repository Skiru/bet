"""What every fit writer shares: which settled rows it may read, and the
metadata that says when it read them.

Two defects of 2026-10-02 live here:

* Friendlies were in the fits. SAMPLES and the football rating drop the
  competitions in config/sofa_friendly_competitions.json, but fit_constants
  and fit_confidence read every settled row - about 6% of the global
  goals_for pool - so a prior and a curve described games the sheet never
  samples. `friendly_exclusion_sql` is the one filter both use.
* A fit carried no time. `fit_stamp` gives every output the wall clock of the
  fit and the newest dated `run_date` it read (the cache replay files its rows
  under the literal 'cache-calibration', which sorts after every date and so
  is excluded from the max).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from bet.sofa.samples import FRIENDLY_COMPETITION_IDS

# Keys the operator writes into a fitted file by hand. A fit that rebuilds the
# file from the DB must carry them over, or the next refit silently undoes an
# operator decision (admitted_player_markets: Calibration.player_prop_not_admitted;
# admitted_tennis_set_markets: Calibration.tennis_set_market_not_admitted;
# refused_markets: Calibration.refused_by_operator; gap_shrink_k:
# Calibration.shrink_for_gap - k was measured against one curve, so re-measure
# it after a refit rather than trusting the carried value).
OPERATOR_KEYS: tuple[str, ...] = (
    "admitted_player_markets", "admitted_tennis_set_markets", "refused_markets",
    "gap_shrink_k",
)


def friendly_exclusion_sql(
    prefix: str = "", ids: frozenset[int] = FRIENDLY_COMPETITION_IDS
) -> str:
    """A WHERE term that drops football rows of friendly competitions.

    NULL-safe: a row without a competition id is kept (``x IN (...)`` on a
    NULL would be NULL, and NOT NULL drops the row).
    """
    if not ids:
        return "1"
    listed = ",".join(str(int(c)) for c in sorted(ids))
    return (
        f"NOT ({prefix}sport = 'football' AND "
        f"COALESCE({prefix}competition_id, -1) IN ({listed}))"
    )


def max_settled_run_date(conn: sqlite3.Connection) -> str | None:
    """Newest dated run_date in sofa_settled_row (index-backed), or None."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(sofa_settled_row)")}
    if "run_date" not in columns:
        return None
    row = conn.execute(
        "SELECT MAX(run_date) FROM sofa_settled_row "
        "WHERE run_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
    ).fetchone()
    value = row[0] if row is not None else None
    return str(value) if value is not None else None


def fit_stamp(conn: sqlite3.Connection) -> dict[str, Any]:
    """`fitted_at_utc`, `max_settled_run_date` and the friendly filter size."""
    return {
        "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "max_settled_run_date": max_settled_run_date(conn),
        "friendly_competitions_excluded": len(FRIENDLY_COMPETITION_IDS),
    }


def carry_operator_keys(new: dict[str, Any], prior: dict[str, Any] | None) -> None:
    """Copy every operator-owned key of `prior` into `new`, in place."""
    if not prior:
        return
    for key in OPERATOR_KEYS:
        if key in prior and key not in new:
            new[key] = prior[key]


# Curves fitted by their own scripts and installed apart (not from the replay
# fit_confidence reads): the new-market keys listed in
# `new_market_curves_fitted_from` (scripts/sofa/install_new_market_curves.py)
# and the tennis match winner (`match_won_for`, fit_tennis_winner_curve.py,
# `match_won_for_fitted_from`). A full fit rebuilds the file and would drop
# them silently - every market they price would stop printing (until
# 2026-10-16 each refit carried them by hand, data/refit_2026-10-16/
# carry_over.py). A key the new fit produced itself is never overwritten.
SEPARATE_FIT_META: tuple[str, ...] = (
    "new_market_curves_fitted_from", "match_won_for_fitted_from")


def _section(doc: dict[str, Any], klass: str, field: str) -> dict[str, Any]:
    if not klass:
        out: dict[str, Any] = doc.setdefault(field, {})
        return out
    cls: dict[str, Any] = doc.setdefault("by_class", {}).setdefault(klass, {})
    sec: dict[str, Any] = cls.setdefault(field, {})
    return sec


def _get(doc: dict[str, Any], klass: str, field: str) -> dict[str, Any] | None:
    sec = (doc.get(field) if not klass
           else ((doc.get("by_class") or {}).get(klass) or {}).get(field))
    return sec if isinstance(sec, dict) else None


# Groups of `new_market_curves_fitted_from` whose curve the full fit never
# replaces, even when it holds the key itself (audit 2026-10-21 D6): their
# p comes from an estimator the cache replay does not run (the card-halves
# share model, scripts/sofa/fit_incident_set_curves.py; the footballer fouls
# drawn, scripts/sofa/measure_player_props_v2.py; the shot-detail forecast),
# and each was installed only after the one-sided holdout gate. A full fit
# holds such a key from replayed plain-sample player rows (printed_player_
# ladder lets player_fouls_drawn_for into build_player_rows) or from live
# SETTLE rows alone - another p, never gated - so the installed curve wins.
PRIOR_WINS_GROUPS: frozenset[str] = frozenset(
    {"card_halves", "player_props_v2", "shot_detail"})


def prior_curve_wins(entry: object) -> bool:
    """Does a separately fitted curve (its `new_market_curves_fitted_from`
    entry) replace the full fit's own curve of the key?"""
    return (isinstance(entry, Mapping)
            and entry.get("group") in PRIOR_WINS_GROUPS
            and not entry.get("requires_replay_flags"))


def carry_separately_fitted_curves(
    new: dict[str, Any], prior: dict[str, Any] | None
) -> list[str]:
    """Copy into `new`, in place, every separately fitted curve of `prior`
    (SEPARATE_FIT_META) that `new` lacks - and, for a PRIOR_WINS_GROUPS
    entry, also one `new` holds; returns the carried keys."""
    if not prior:
        return []
    carried: list[str] = []
    for key, entry in (prior.get("new_market_curves_fitted_from") or {}).items():
        klass, _, mk = str(key).rpartition(":")
        # "<market>|<DIR>@<line>"; a score-market slice key
        # ("result_or_over@1@0.5|OVER") has its "@" before the "|"
        market_part, bar, rest = mk.partition("|")
        direction, at, line = rest.partition("@")
        dkey = f"{market_part}{bar}{direction}"
        if at and not klass:
            # a per-line curve "<market>|<DIR>@<line>" (by_market_direction_
            # line, scripts/sofa/fit_joint_curves.py): fit_confidence writes
            # that section only for config/sofa_line_curves.json's keys
            lsrc = (prior.get("by_market_direction_line") or {}).get(dkey) or {}
            if line not in lsrc:
                continue
            ldst = new.setdefault("by_market_direction_line", {}).setdefault(
                dkey, {})
            if line not in ldst or prior_curve_wins(entry):
                ldst[line] = lsrc[line]
                carried.append(str(key))
            continue
        src = _get(prior, klass, "by_market_direction")
        if src is None or mk not in src:
            continue
        dst = _section(new, klass, "by_market_direction")
        if mk not in dst or prior_curve_wins(entry):
            dst[mk] = src[mk]
            carried.append(str(key))
    if prior.get("match_won_for_fitted_from"):
        for klass in ["", *sorted(prior.get("by_class") or {})]:
            src = _get(prior, klass, "by_market")
            if src is None or "match_won_for" not in src:
                continue
            dst = _section(new, klass, "by_market")
            if "match_won_for" not in dst:
                dst["match_won_for"] = src["match_won_for"]
                carried.append(f"{klass + ':' if klass else ''}match_won_for")
    for meta in SEPARATE_FIT_META:
        if meta in prior and meta not in new:
            new[meta] = prior[meta]
    return carried


def carry_sport_new_market_curves(
    section: dict[str, Any], sport: str, prior: dict[str, Any] | None
) -> list[str]:
    """The same for one measured sport's freshly fitted section of
    config/sofa_sport_confidence_calibration.json: every
    `new_market_curves_fitted_from` key "<sport>:<family>|<SIDE>" of `prior`
    the new section lacks is copied in (with its `curve_source`), in place;
    returns the carried keys. fit_sport_confidence replaces a sport's whole
    section, which would otherwise drop the installed new-market curves."""
    if not prior:
        return []
    old = ((prior.get("sports") or {}).get(sport) or {})
    old_curves = old.get("curves") or {}
    carried: list[str] = []
    for key in prior.get("new_market_curves_fitted_from") or {}:
        sp, _, ck = str(key).partition(":")
        if sp != sport or ck not in old_curves:
            continue
        curves = section.setdefault("curves", {})
        if ck in curves:
            continue
        curves[ck] = old_curves[ck]
        src = (old.get("curve_source") or {}).get(ck)
        if src is not None:
            section.setdefault("curve_source", {})[ck] = src
        carried.append(str(key))
    return carried
