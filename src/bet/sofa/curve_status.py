"""Which confidence curves failed their calibration check (plan
docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md, F2.1).

config/sofa_curve_status.json is written by
`scripts/sofa/measure_calibration.py --write-config --before <d>` - between
days, from settled legs strictly before <d> - and lists the curves (a leg's
`calibrated_on`) whose printed confidence missed the realised rate on at
least MIN_SETTLED legs (bet.sofa.calibration_audit). A leg read off a listed
curve is refused as CURVE_FAILED_CALIBRATION by CONFIDENCE and
SPORT_CONFIDENCE - only while bet.sofa.epochs.curve_status_enforced() is
true, which it is not until the operator sets CURVE_STATUS_FROM_UTC (None =
disabled), and only on a day on or after the file's `applies_from_date`.

A missing file lists nothing. An unreadable one raises: a stage that was told
to refuse failed curves must not silently print them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.sofa import epochs
from bet.sofa.config import config_path

CURVE_STATUS_FILE = "sofa_curve_status.json"
CURVE_FAILED_CALIBRATION = "CURVE_FAILED_CALIBRATION"


@dataclass(frozen=True)
class CurveStatus:
    failed: frozenset[str] = frozenset()
    applies_from_date: str | None = None

    def refuses(self, curve: str | None, date: str) -> bool:
        """Is a leg of `date` calibrated on `curve` refused?"""
        if not curve or curve not in self.failed:
            return False
        return self.applies_from_date is None or date >= self.applies_from_date


def default_path() -> Path:
    return config_path(CURVE_STATUS_FILE)


def from_doc(doc: Mapping[str, Any]) -> CurveStatus:
    failed = doc.get("failed_curves") or {}
    if not isinstance(failed, Mapping):
        raise ValueError("failed_curves must be an object keyed by curve")
    applies = doc.get("applies_from_date")
    return CurveStatus(frozenset(str(k) for k in failed),
                       str(applies) if applies else None)


def load(path: Path | None = None) -> CurveStatus:
    """The file's failed curves; none when the file does not exist."""
    p = path if path is not None else default_path()
    if not p.exists():
        return CurveStatus()
    return from_doc(json.loads(p.read_text(encoding="utf-8")))


def for_build(date: str, build_at: datetime | None = None,
              path: Path | None = None) -> CurveStatus:
    """What a build of `date` refuses: nothing unless the operator enabled
    the rule (epochs.CURVE_STATUS_FROM_UTC); the file is not even read
    before that."""
    if not epochs.curve_status_enforced(date, build_at):
        return CurveStatus()
    return load(path)
