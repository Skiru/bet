"""scripts/sofa/measure_disagreement.py - CONFIDENCE's disagreement gate, re-measured.

A temp DB built by bet.sofa.db.migrate and a tiny calibration file: the split
must be the one `disagrees_with_price` makes, each profile's floor and price
rule must hold, halves are event-id parity, an interval below --min-clusters
is "-", and derived / player-prop / friendly / undated rows never enter.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from bet.sofa.confidence import COUPON_PROFILE, Calibration
from bet.sofa.db import migrate
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS
from scripts.sofa.measure_disagreement import (
    DayArtifacts,
    GatedRow,
    SettledRow,
    connect_ro,
    gate_rows,
    load_rows,
    main,
    measure_profile,
)

FRIENDLY_ID = min(FRIENDLY_COMPETITION_IDS)
LEAGUE_ID = 17  # not a friendly, not a women's competition

# p in [0.60, 0.70) -> 0.67, p in [0.70, 1.00) -> 0.75.
CURVE = {
    "0.600-0.700": {"n": 500, "realised": 0.68, "realised_lo95": 0.67},
    "0.700-1.000": {"n": 500, "realised": 0.76, "realised_lo95": 0.75},
}


def _calibration(tmp_path: Path) -> Path:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "pooled": {},
        "by_market": {"corners_total": CURVE},
        "pooled_by_sport": {"tennis": CURVE},
    }), encoding="utf-8")
    return path


def _insert(conn: sqlite3.Connection, **kw: object) -> None:
    row = {
        "run_date": "2026-09-25", "sofascore_event_id": 1, "sport": "football",
        "competition_id": LEAGUE_ID, "market": "corners_total", "subject": "",
        "line": 9.5, "direction": "OVER", "sample_size": 10, "sample_mean": 10.0,
        "sample_sd": 2.0, "p_central": 0.80, "p_bar": 0.7, "market_p": 0.75,
        "actual_value": 11.0, "outcome": "WIN", "settled_at": "2026-09-26T08:00:00Z",
        "offered_odds": 1.40,
    }
    row.update(kw)
    cols = ",".join(row)
    conn.execute(
        f"INSERT INTO sofa_settled_row ({cols}) VALUES ({','.join('?' * len(row))})",
        tuple(row.values()),
    )


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "sofa.db"
    migrate(str(path))
    return path


def _fill(db: Path, rows: list[dict[str, object]]) -> None:
    conn = sqlite3.connect(db)
    for i, kw in enumerate(rows):
        kw.setdefault("line", 9.5 + i)  # UNIQUE(event, market, subject, line, dir)
        _insert(conn, **kw)
    conn.commit()
    conn.close()


def _gated(db: Path, tmp_path: Path, sports: tuple[str, ...] = ("football",),
           artifacts: dict[str, DayArtifacts] | None = None,
           ) -> tuple[list[SettledRow], Counter[str], list[GatedRow], Counter[str]]:
    conn = connect_ro(db)
    rows, dropped = load_rows(conn, "2026-09-18", "2026-10-01", sports)
    conn.close()
    cal = Calibration.load(_calibration(tmp_path))
    gated, skipped = gate_rows(rows, cal, artifacts)
    return rows, dropped, gated, skipped


def test_the_split_is_disagrees_with_price(db: Path, tmp_path: Path) -> None:
    _fill(db, [
        # claim 0.80 vs market 0.62: gap 0.18 -> refused
        {"sofascore_event_id": 2, "p_central": 0.80, "market_p": 0.62},
        # gap 0.03 -> admitted
        {"sofascore_event_id": 3, "p_central": 0.80, "market_p": 0.77},
        # gap 0.08 -> admitted
        {"sofascore_event_id": 5, "p_central": 0.78, "market_p": 0.70},
    ])
    _, _, gated, _ = _gated(db, tmp_path)
    by_id = {g.row.sofascore_event_id: g for g in gated}
    assert by_id[2].refused and not by_id[3].refused and not by_id[5].refused
    cells = measure_profile(gated, COUPON_PROFILE, 7, 50, 20)
    assert cells["refused"].n == 1 and cells["admitted"].n == 2
    assert cells[">=0.15"].n == 1 and cells["0.10-0.15"].n == 0
    assert cells["0-0.05"].n == 1 and cells["0.05-0.10"].n == 1


def test_profile_floor_and_price_rule(db: Path, tmp_path: Path) -> None:
    _fill(db, [
        # confidence 0.75 x 1.40 = 1.05: admitted
        {"sofascore_event_id": 2, "p_central": 0.80, "offered_odds": 1.40},
        # confidence 0.67, under the 0.70 floor
        {"sofascore_event_id": 4, "p_central": 0.65, "market_p": 0.62},
        # confidence 0.75 x 1.25 = 0.9375: admitted since 10-05 (x >= 0.90)
        {"sofascore_event_id": 6, "p_central": 0.80, "offered_odds": 1.25},
        # confidence 0.75 x 1.15 = 0.8625: refused by the price
        {"sofascore_event_id": 8, "p_central": 0.80, "offered_odds": 1.15},
    ])
    _, _, gated, _ = _gated(db, tmp_path)
    std = measure_profile(gated, COUPON_PROFILE, 7, 50, 20)
    assert std["admitted"].n + std["refused"].n == 2


def test_halves_are_event_id_parity(db: Path, tmp_path: Path) -> None:
    _fill(db, [
        {"sofascore_event_id": 10, "outcome": "WIN"},
        {"sofascore_event_id": 12, "outcome": "WIN"},
        {"sofascore_event_id": 11, "outcome": "LOSS"},
    ])
    _, _, gated, _ = _gated(db, tmp_path)
    cell = measure_profile(gated, COUPON_PROFILE, 7, 50, 20)["admitted"]
    assert (cell.n_even, cell.n_odd) == (2, 1)
    assert cell.roi_even == pytest.approx(0.40)
    assert cell.roi_odd == pytest.approx(-1.0)
    assert cell.roi == pytest.approx((0.4 + 0.4 - 1.0) / 3)


def test_interval_is_dash_below_min_clusters(db: Path, tmp_path: Path) -> None:
    _fill(db, [{"sofascore_event_id": 100 + i,
                "outcome": "WIN" if i % 3 else "LOSS"} for i in range(6)])
    _, _, gated, _ = _gated(db, tmp_path)
    thin = measure_profile(gated, COUPON_PROFILE, 7, 50, 20)["admitted"]
    assert thin.roi_ci is None and thin.edge_ci is None and thin.roi_odd_ci is None
    wide = measure_profile(gated, COUPON_PROFILE, 7, 50, 3)["admitted"]
    assert wide.roi_ci is not None and wide.roi is not None
    assert wide.roi_ci[0] <= wide.roi <= wide.roi_ci[1]
    assert wide.roi_even_ci is not None and wide.roi_odd_ci is not None


def test_excluded_rows_never_enter(db: Path, tmp_path: Path) -> None:
    _fill(db, [
        {"sofascore_event_id": 2},  # the one row that stays
        {"sofascore_event_id": 3, "market": "handicap_corners"},
        {"sofascore_event_id": 4, "market": "player_shots_for", "subject": "X"},
        {"sofascore_event_id": 6, "competition_id": FRIENDLY_ID},
        {"sofascore_event_id": 8, "run_date": "cache-calibration"},
        {"sofascore_event_id": 10, "outcome": "VOID"},
        {"sofascore_event_id": 12, "market_p": None},
        {"sofascore_event_id": 14, "offered_odds": None},
        {"sofascore_event_id": 16, "offered_odds": 1.05},  # under MIN_ODDS
    ])
    rows, dropped, gated, _ = _gated(db, tmp_path)
    assert [r.sofascore_event_id for r in rows] == [2]
    assert dropped["DERIVED_NOT_CALIBRATABLE"] == 1
    assert dropped["PLAYER_PROP"] == 1
    assert dropped["FRIENDLY_FIXTURE"] == 1
    assert dropped["ODDS_TOO_LOW"] == 1


def test_class_without_curve_is_refused_and_counted(db: Path, tmp_path: Path) -> None:
    _fill(db, [{"sofascore_event_id": 2}, {"sofascore_event_id": 4}])
    art = DayArtifacts(classes={4: "women"}, fixtures_found=True)
    _, _, gated, skipped = _gated(db, tmp_path, artifacts={"2026-09-25": art})
    assert [g.row.sofascore_event_id for g in gated] == [2]
    assert skipped["NO_CLASS_CURVE"] == 1


def test_tennis_sample_frequency_replaces_p_central(db: Path, tmp_path: Path) -> None:
    _fill(db, [{"sofascore_event_id": 2, "sport": "tennis", "market": "games_total",
                "competition_id": None, "line": 21.5, "p_central": 0.78,
                "market_p": 0.72}])
    key = (2, "games_total", "", 21.5, "OVER")
    plain = _gated(db, tmp_path, ("tennis",))[2]
    assert not plain[0].refused  # 0.78 - 0.72 = 0.06
    art = DayArtifacts(sample_frequency={key: 0.90}, sheet_found=True)
    with_freq = _gated(db, tmp_path, ("tennis",), {"2026-09-25": art})[2]
    assert with_freq[0].refused and with_freq[0].claim == 0.90  # 0.18 > 0.10


def test_main_end_to_end_and_refuses_protected_output(
    db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fill(db, [{"sofascore_event_id": 2 + i, "p_central": 0.80,
                "market_p": 0.65 if i % 2 else 0.77} for i in range(4)])
    out = tmp_path / "m.json"
    rc = main(["--from", "2026-09-24", "--to", "2026-10-01", "--db-path", str(db),
               "--calibration", str(_calibration(tmp_path)), "--no-artifacts",
               "--boot", "50", "--json-out", str(out)])
    assert rc == 0
    text = capsys.readouterr().out
    assert "profile standard" in text and "wariant" not in text
    assert "verdict (facts)" in text and "operator's" in text
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["profiles"]["standard"]["cells"]["refused"]["n"] == 2
    protected = Path(__file__).resolve().parents[2] / "runs" / "x.json"
    with pytest.raises(SystemExit):
        main(["--from", "2026-09-24", "--to", "2026-10-01", "--db-path", str(db),
              "--json-out", str(protected)])
    assert not protected.exists()
    with pytest.raises(SystemExit):
        main(["--from", "cache-calibration", "--to", "2026-10-01",
              "--db-path", str(db)])
