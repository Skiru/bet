"""A copy of the installed line evidence without some markets' keys and price
bands, read by every LineEvidence.load of the test - for a test of what
CONFIDENCE does with a key that has no settled Superbet lines, which stays
true after the morning refresh gives that key its own (2026-10-18:
refresh_line_evidence.py wrote double_chance / penalties / player band
cells and tests that read the installed file stopped holding)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.line_evidence import DEFAULT_EVIDENCE, LineEvidence


def _market(key: str) -> str:
    # "women:double_chance|OVER", "cap:x|OVER@1.00-1.30" -> the market
    return key.split("|")[0].split(":")[-1]


def evidence_without(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                     markets: Iterable[str]) -> Path:
    drop = frozenset(markets)
    doc: dict[str, Any] = json.loads(Path(DEFAULT_EVIDENCE).read_text())
    for section in ("keys", "bands"):
        by_sport = doc.get(section)
        if not isinstance(by_sport, dict):
            continue
        for sport, keys in by_sport.items():
            if isinstance(keys, dict):
                by_sport[sport] = {k: v for k, v in keys.items()
                                   if _market(k) not in drop}
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / "evidence_without.json"
    out.write_text(json.dumps(doc))
    real_load = LineEvidence.load

    def load(path: Path | str = out, **kw: Any) -> LineEvidence:
        return real_load(path, **kw)

    monkeypatch.setattr(LineEvidence, "load", staticmethod(load))
    return out
