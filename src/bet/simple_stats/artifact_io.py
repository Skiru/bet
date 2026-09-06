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


def load_event_dossiers(path: Path) -> tuple["EventDossierListV1", list[str]]:
    """Read an EVENT_DOSSIER_LIST_V1 artifact whose provider vocabulary has moved on.

    Returns the dossiers and the names of any retired providers whose
    observations were dropped to make the file readable.

    Same failure as ``load_market_context``, same removal, one artifact further
    down -- and it went unnoticed for four days because only the ``--rebuilt``
    arm of ``backtest_slate.py`` reads a dossier back. Taking bzzoiro-tennis out
    of ``PROVIDER_NAMES`` on 2026-09-02 made ``runs/2026-08-29``'s dossiers
    unparseable (824 validation errors), so *that slate could not be replayed at
    all*: any measurement of a code change against it silently ran on seven days
    instead of eight, and the run printed "unavailable" to stderr among the
    coverage gaps.

    Dropping the observations rather than the metric is what keeps the replay
    honest. A retired provider's readings are exactly what a rebuild must not
    reuse -- the whole reason the provider was retired -- while the matches the
    surviving providers reported are still evidence, so a metric left with a
    smaller sample is the correct answer and a metric deleted outright is not.
    A metric emptied of every observation is removed, because an empty sample is
    not a sample.

    Widening ``PROVIDER_NAMES`` instead would have been the smaller diff and the
    wrong one: it is the same list a *live* ENRICH validates against, so a name
    re-added for the benefit of a two-week-old artifact is a name a live run can
    write again.
    """
    from bet.simple_stats.contracts import EventDossierListV1, PROVIDER_NAMES
    from typing import get_args

    raw_text = Path(path).read_text(encoding="utf-8")
    try:
        return EventDossierListV1.model_validate_json(raw_text), []
    except ValueError:
        pass

    known = set(get_args(PROVIDER_NAMES))
    raw = json.loads(raw_text)
    dropped: set[str] = set()
    for dossier in raw.get("dossiers") or []:
        for container_key in ("metrics", "player_metrics"):
            container = dossier.get(container_key)
            entries = (
                container.values()
                if isinstance(container, dict)
                else container if isinstance(container, list) else []
            )
            empty: list[object] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                seen_any = False
                for bucket_key, bucket in list(entry.items()):
                    if not isinstance(bucket, list):
                        continue
                    kept = []
                    for observation in bucket:
                        provider = (
                            observation.get("provider")
                            if isinstance(observation, dict)
                            else None
                        )
                        if provider is not None and provider not in known:
                            dropped.add(str(provider))
                            continue
                        kept.append(observation)
                    entry[bucket_key] = kept
                    seen_any = seen_any or bool(kept)
                if not seen_any:
                    empty.append(entry)
            if isinstance(container, dict) and empty:
                for name in [k for k, v in container.items() if v in empty]:
                    del container[name]
            elif isinstance(container, list) and empty:
                dossier[container_key] = [e for e in container if e not in empty]
    return EventDossierListV1.model_validate(raw), sorted(dropped)
