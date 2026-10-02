"""Fit outputs keep the operator's keys, say when they were fitted, and read no
friendly (2026-10-02).

* fit_confidence's full writer rebuilt the calibration file from the DB and
  dropped `admitted_player_markets`, the operator's admission list - the next
  refit would have refused every admitted player prop again.
* No fit output carried a timestamp or the newest settled day it read.
* SAMPLES and the rating exclude friendlies; the fits did not (~6% of the
  global goals_for pool).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import Calibration
from bet.sofa.db import get_connection, migrate
from bet.sofa.fit_meta import friendly_exclusion_sql, max_settled_run_date
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS
from scripts.sofa.run_sheet import get_calibration_correction

FRIENDLY = 853  # Club Friendly Games
assert FRIENDLY in FRIENDLY_COMPETITION_IDS


def _row(i: int, **over: Any) -> dict[str, Any]:
    row = {
        "run_date": "2026-09-28", "sofascore_event_id": i, "sport": "football",
        "competition_id": 17, "market": "goals_total", "subject": "",
        "line": 2.5, "direction": "OVER", "sample_size": 10,
        "sample_mean": 2.6, "sample_sd": 1.2, "p_central": 0.55,
        "p_bar": 0.55, "market_p": None, "actual_value": 3.0 + (i % 2),
        "outcome": "WIN", "settled_at": "2026-09-29T00:00:00+00:00",
        "ladder_sigma": None,
    }
    row.update(over)
    return row


def _seed(db: str, rows: list[dict[str, Any]]) -> None:
    migrate(db)
    with get_connection(db) as conn:
        cols = list(rows[0])
        conn.executemany(
            f"INSERT INTO sofa_settled_row ({','.join(cols)}) "
            f"VALUES ({','.join(':' + c for c in cols)})",
            rows,
        )
        conn.commit()


@pytest.fixture()
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "sofa.db")
    rows = [_row(i) for i in range(1, 41)]
    rows += [_row(100 + i, competition_id=FRIENDLY, actual_value=9.0)
             for i in range(10)]
    rows += [_row(200, run_date="2026-09-30"),
             _row(201, run_date="cache-calibration")]
    # A tennis row in a competition whose id happens to be a football
    # friendly's is not a friendly.
    rows += [_row(300, sport="tennis", competition_id=FRIENDLY,
                  market="games_total", line=20.5, sample_mean=21.0,
                  sample_sd=3.0, actual_value=22.0)]
    _seed(path, rows)
    return path


def test_friendly_term_is_null_safe_and_football_only(db: str) -> None:
    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport,"
            " competition_id, market, subject, line, direction, sample_size,"
            " sample_mean, sample_sd, p_central, p_bar, actual_value, outcome,"
            " settled_at) VALUES ('2026-09-28', 999, 'football', NULL,"
            " 'goals_total', '', 2.5, 'OVER', 10, 2.6, 1.2, 0.5, 0.5, 3, 'WIN', 'x')"
        )
        kept = {r[0] for r in conn.execute(
            f"SELECT sofascore_event_id FROM sofa_settled_row "
            f"WHERE {friendly_exclusion_sql()}")}
        assert 999 in kept, "a row without a competition id is kept"
        assert 300 in kept, "tennis is never a friendly"
        assert not kept & set(range(100, 110))
        assert max_settled_run_date(conn) == "2026-09-30"
    assert friendly_exclusion_sql(ids=frozenset()) == "1"


def _fit_confidence(monkeypatch: pytest.MonkeyPatch, db: str, out: Path,
                    *flags: str) -> dict[str, Any]:
    from scripts.sofa import fit_confidence

    monkeypatch.setattr(
        sys, "argv", ["fit", "--db-path", db, "--out", str(out), *flags])
    assert fit_confidence.main() == 0
    doc: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return doc


def test_full_confidence_fit_keeps_admitted_player_markets(
    db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "cal.json"
    out.write_text(json.dumps({
        "pooled": {}, "admitted_player_markets": ["player_shots_for"]}))
    doc = _fit_confidence(monkeypatch, db, out)
    assert doc["admitted_player_markets"] == ["player_shots_for"]
    assert not Calibration.load(out).player_prop_not_admitted("player_shots_for")
    meta = doc["fitted_from"]
    assert meta["fitted_at_utc"].endswith("+00:00")
    assert meta["max_settled_run_date"] == "2026-09-30"
    # 40 + 2 football league rows + 1 tennis; the 10 friendlies are out.
    assert meta["scored_rows"] == 43


def test_classes_only_keeps_admitted_player_markets_and_stamps(
    db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "cal.json"
    out.write_text(json.dumps({
        "pooled": {"0.600-0.700": {"n": 1}},
        "admitted_player_markets": ["player_shots_for"]}))
    doc = _fit_confidence(monkeypatch, db, out, "--classes-only")
    assert doc["admitted_player_markets"] == ["player_shots_for"]
    assert doc["pooled"] == {"0.600-0.700": {"n": 1}}
    assert "fitted_at_utc" in doc["by_class_fitted_from"]


def test_fit_constants_stamps_every_output_and_drops_friendlies(
    db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa import fit_constants

    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        sys, "argv",
        ["fit", "--db-path", db, "--config-dir", str(config_dir)])
    fit_constants.main()
    baselines = json.loads(
        (config_dir / "sofa_league_baselines.json").read_text(encoding="utf-8"))
    reliability = json.loads(
        (config_dir / "sofa_market_reliability.json").read_text(encoding="utf-8"))
    constants = json.loads(
        (config_dir / "sofa_engine_constants.json").read_text(encoding="utf-8"))
    for meta in (baselines["fitted_from"], constants["fitted_from"],
                 reliability[fit_constants.RELIABILITY_META_KEY]):
        assert meta["fitted_at_utc"].endswith("+00:00")
        assert meta["max_settled_run_date"] == "2026-09-30"
    # Friendlies: no league baseline, and out of the global mean (9.0 each).
    goals = baselines["goals_total"]
    assert str(FRIENDLY) not in goals
    assert goals["global"]["mean"] < 4.0
    assert constants["fitted_from"]["settled_rows"] == 43

    # The reliability reader looks markets up by name: the metadata key can
    # never be read as a market's curve.
    assert get_calibration_correction(
        reliability, fit_constants.RELIABILITY_META_KEY, 0.85, "OVER"
    ) == get_calibration_correction(reliability, "no_such_market", 0.85, "OVER")
