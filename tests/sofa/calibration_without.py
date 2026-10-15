"""A copy of the installed football / tennis calibration without some markets'
curves - for a test of what CONFIDENCE does with a key that has no curve,
which stays true after an install gives that key one (2026-10-15: the new
markets' curves, scripts/sofa/install_new_market_curves.py)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from bet.sofa.config import config_path


def _strip(node: Any, markets: frozenset[str]) -> Any:
    if not isinstance(node, dict):
        return node
    return {k: _strip(v, markets) for k, v in node.items()
            if k.split(":")[-1].split("|")[0] not in markets}


def calibration_without(tmp_path: Path, markets: Iterable[str]) -> Path:
    doc = json.loads(config_path("sofa_confidence_calibration.json").read_text())
    out = tmp_path / "calibration_without.json"
    out.write_text(json.dumps(_strip(doc, frozenset(markets))))
    return out
