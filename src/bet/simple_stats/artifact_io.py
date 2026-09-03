"""Tiny, self-contained atomic JSON writer + SHA256 helper.

Deliberately does not import bet.pipeline.run_evidence: that module lives
under the bet.pipeline package, whose __init__.py pulls in a much larger
dependency graph (state/manifest/contracts/sharding/sports) this package has
no other reason to depend on. The behavior mirrors
bet.pipeline.run_evidence.write_json_atomic/sha256_file exactly (mkstemp in
the same directory, fsync best-effort, atomic os.replace).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(temp_path, path)
    except Exception as exc:
        if temp_path.exists():
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise ValueError(f"Failed atomic write to {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_market_context(path: Path) -> tuple["MarketContextV1", list[str]]:
    """Read a MARKET_CONTEXT_V1 artifact this repo's schema may have moved on from.

    Returns the context and the names of any prediction fields dropped to make
    it readable.

    ``StrictBaseModel`` forbids unknown fields, which is right for a live run
    and wrong for reading one back. On 2026-09-02 bzzoiro-tennis was removed and
    ``ModelPrediction`` lost its seven tennis fields; every
    ``market_context.json`` already on disk became unreadable that instant, and
    the three readers failed three different ways:

    * ``backtest_slate.py`` -- crashed, taking the only instrument that settles
      this repo's arguments against real results with it;
    * ``build_coupons.py`` -- crashed, at the last step before the operator gets
      output;
    * ``run_analyze.py`` -- caught it and continued *without the market column*,
      which is the quietest of the three and not the safest.

    Re-running a finished day is normal here, so a schema change must not turn
    yesterday's artifacts into rubble. Strict first, so a current-shaped file is
    validated exactly as everywhere else; only on failure are unknown prediction
    fields dropped, and they are returned so the caller can say so out loud. A
    field the schema has forgotten is not one a coupon should quietly use.
    """
    from bet.simple_stats.contracts import MarketContextV1, ModelPrediction

    raw_text = Path(path).read_text(encoding="utf-8")
    try:
        return MarketContextV1.model_validate_json(raw_text), []
    except ValueError:
        pass

    known = set(ModelPrediction.model_fields)
    raw = json.loads(raw_text)
    dropped: set[str] = set()
    for event in raw.get("events") or []:
        predictions = event.get("predictions")
        if not isinstance(predictions, dict):
            continue
        dropped |= set(predictions) - known
        event["predictions"] = {k: v for k, v in predictions.items() if k in known}
    # Still strict about everything else: this widens the door for fields the
    # schema *used* to have, not for an artifact that is simply wrong.
    return MarketContextV1.model_validate(raw), sorted(dropped)
