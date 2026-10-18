"""History curves per line (epochs.LINE_CURVES_FROM_UTC).

A football curve is fitted per market x direction over every line the
history replay prices (a ladder around the centre), and Superbet quotes a
few lines near it. The model's p is not calibrated alike across lines: on the
2026-10-17 replay, out of sample on Superbet's quoted lines, the pooled
curve overstated goals_for UNDER 1.5 by 3.9 pp (62k rows at curve >= 0.70)
and understated the far UNDER lines, and so for most count markets - the
"hard" side near the centre over, the trivial far lines under
(`docs/sofa/evidence/line_curves_2026-10-18.md`).

For the keys of `config/sofa_line_curves.json` (chosen where the per-line
curve was better out of sample with the interval below zero) fit_confidence
writes `by_market_direction_line`: {"<market>|<DIR>": {"<line>": curve}}, and
CONFIDENCE reads a leg's own line bucket first (confidence.Calibration.
realised(..., line=)); a line bucket the fit could not fill reads the pooled
curve as before. Men's football only: a class leg (women, season_early...)
reads its class's curves unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import epochs
from bet.sofa.config import config_path

FILE = "sofa_line_curves.json"
SECTION = "by_market_direction_line"
FITTED_FROM = "line_curves_fitted_from"
SPORT = "football"


def line_label(line: float) -> str:
    """The section's key of a line: 1.5 -> "1.5", 10.0 -> "10"."""
    return f"{float(line):g}"


def load_keys(path: Path | None = None) -> frozenset[str]:
    """The `<market>|<DIR>` keys read per line (none when the file is
    absent: no key is read per line)."""
    p = path if path is not None else config_path(FILE)
    if not p.exists():
        return frozenset()
    doc = json.loads(p.read_text(encoding="utf-8"))
    return frozenset(str(k) for k in doc.get("keys") or ())


def leg_line(row: Mapping[str, Any], on: bool) -> float | None:
    """The line a row's curve is read at: its own for a football row with a
    line when the day reads per line (`on`, epochs.line_curves), else None -
    the lookup as before."""
    if not on or row.get("sport") != SPORT or row.get("line") is None:
        return None
    return float(row["line"])


def day_reads_per_line(day: str) -> bool:
    """Does the day's LATEST build read per line - the rule a measurement
    re-deriving that day's confidence, and the line evidence fitted for it
    (--before <day>), follow. A mixed day (the switch inside it) reads per
    line: its legs printed before are locked, the rest is built under it."""
    end = datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(days=1)
    return epochs.line_curves(day, end - timedelta(microseconds=1))
