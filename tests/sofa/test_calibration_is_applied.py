"""F48 — the calibration curve was measured, written, and never read.

`get_calibration_correction` only honours a bucket that says
``"status": "MEASURED"``. `fit_constants.fit_reliability` never wrote that
field. Every correction ever fitted — 39 non-zero ones in the shipped config —
came back as 0.0, so the curve landed in commit f544ad28 and has never moved a
single row.

It survived because the reader's own tests build their fixtures by hand and
type `"status": "MEASURED"` into them, so they check the reader against a shape
the writer does not produce. This file checks the two against **each other**,
and against the artifact that actually ships.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.db import get_connection, migrate
from scripts.sofa.fit_constants import fit_reliability
from scripts.sofa.run_sheet import get_calibration_correction

REPO = Path(__file__).resolve().parents[2]


def _seed(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        conn.execute(
            """
            INSERT INTO sofa_settled_row (
                run_date, sofascore_event_id, sport, competition_id, market,
                subject, line, direction, sample_size, sample_mean, sample_sd,
                p_central, p_bar, market_p, actual_value, outcome, settled_at
            ) VALUES (
                '2026-09-01', :eid, :sport, 1, :market, '', 2.5, :direction,
                10, 2.6, 1.2, :p_central, :p_central, NULL, 3.0, :outcome,
                '2026-09-02T00:00:00+00:00'
            )
            """,
            row,
        )
    conn.commit()


def _rows(
    market: str, direction: str, p: float, n: int, win_rate: float, sport: str
) -> list[dict[str, Any]]:
    wins = int(n * win_rate)
    return [
        {
            "eid": i,
            "sport": sport,
            "market": market,
            "direction": direction,
            "p_central": p,
            "outcome": "WIN" if i < wins else "LOSS",
        }
        for i in range(n)
    ]


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "sofa.db")
    migrate(path)
    return path


def test_what_the_fit_writes_is_what_the_reader_can_read(db: str) -> None:
    """The whole point: no hand-written fixture anywhere in this test."""
    with get_connection(db) as conn:
        _seed(conn, _rows("goals_total", "OVER", 0.85, 400, 0.50, "football"))
        reliability = fit_reliability(conn)

    # Declared 0.85, realised 0.50 — a gap no interval can call noise.
    assert get_calibration_correction(reliability, "goals_total", 0.85, "OVER") > 0.3


def test_every_bucket_the_fit_emits_is_reachable(db: str) -> None:
    with get_connection(db) as conn:
        _seed(conn, _rows("goals_total", "OVER", 0.85, 400, 0.50, "football"))
        _seed(conn, _rows("corners_total", "UNDER", 0.35, 400, 0.10, "football"))
        reliability = fit_reliability(conn)

    unreachable = []
    for key, buckets in reliability.items():
        if not isinstance(buckets, dict):
            continue
        market, _, direction = key.partition("|")
        for bucket, entry in buckets.items():
            if not isinstance(entry, dict) or entry.get("correction", 0.0) <= 0:
                continue
            midpoint = float(bucket.split("-")[0]) + 0.05
            got = get_calibration_correction(
                reliability, market if market != "_pooled" else "nothing", midpoint,
                direction,
            )
            if got <= 0:
                unreachable.append((key, bucket))
    assert not unreachable, unreachable


def test_a_bias_toward_one_direction_survives_pooling(db: str) -> None:
    """OVER and UNDER are exact complements, so pooling cancels the bias.

    600 rows declaring 0.5 for OVER that win only 30% of the time are the same
    600 rows declaring 0.5 for UNDER that win 70%. Pooled, the market looks
    perfectly calibrated; split, one side is badly overconfident. (600, not
    400, so the direction layer clears MIN_DIRECTION_BUCKET_ROWS.)
    """
    with get_connection(db) as conn:
        _seed(conn, _rows("games_total", "OVER", 0.5, 600, 0.30, "tennis"))
        _seed(conn, _rows("games_total", "UNDER", 0.5, 600, 0.70, "tennis"))
        reliability = fit_reliability(conn)

    pooled_entry = reliability["games_total"]["0.5-0.6"]
    assert pooled_entry["correction"] == 0.0, "pooled must see nothing"

    over = get_calibration_correction(reliability, "games_total", 0.55, "OVER")
    under = get_calibration_correction(reliability, "games_total", 0.55, "UNDER")
    assert over > 0.15, over
    assert under == 0.0, "only the overstated side is corrected"


def test_the_direction_layer_does_not_double_count_the_pooled_one(db: str) -> None:
    """`market|DIRECTION` holds the same rows again. Pooling those too would
    count every row twice and halve every confidence interval."""
    with get_connection(db) as conn:
        _seed(conn, _rows("goals_total", "OVER", 0.85, 400, 0.50, "football"))
        reliability = fit_reliability(conn)
    assert reliability["_pooled"]["0.8-0.9"]["n"] == 400


def test_direction_falls_back_to_the_market_then_to_pooled(db: str) -> None:
    with get_connection(db) as conn:
        _seed(conn, _rows("goals_total", "OVER", 0.85, 400, 0.50, "football"))
        reliability = fit_reliability(conn)
    # A market with no curve of its own still gets the pooled correction.
    assert get_calibration_correction(reliability, "never_seen", 0.85, "OVER") > 0.3
    # And a row with no direction still resolves.
    assert get_calibration_correction(reliability, "goals_total", 0.85) > 0.3


def test_the_shipped_config_is_actually_applied() -> None:
    """The end-to-end check the reader's unit tests could not make."""
    path = REPO / "config/sofa_market_reliability.json"
    if not path.exists():
        pytest.skip("no fitted reliability in this checkout")
    reliability = json.loads(path.read_text(encoding="utf-8"))

    non_zero = [
        (key, bucket, entry["correction"])
        for key, buckets in reliability.items()
        if isinstance(buckets, dict)
        for bucket, entry in buckets.items()
        if isinstance(entry, dict) and entry.get("correction", 0.0) > 0
    ]
    if not non_zero:
        pytest.skip("nothing measured to correct")

    dead = []
    for key, bucket, _ in non_zero:
        market, _, direction = key.partition("|")
        if market == "_pooled":
            continue
        midpoint = float(bucket.split("-")[0]) + 0.05
        if get_calibration_correction(reliability, market, midpoint, direction) <= 0:
            dead.append((key, bucket))
    assert not dead, f"{len(dead)} of {len(non_zero)} shipped corrections are dead"


def test_a_direction_bucket_must_be_better_evidenced_than_a_market_one(
    db: str,
) -> None:
    """A narrower claim needs more evidence, not less.

    At the market-layer minimum the direction layer emitted its two largest
    corrections — 0.176 on 86 rows and 0.140 on 45 — out of ~120 buckets, all
    gated on a 95% interval that clears zero by chance often enough at that
    width.
    """
    from scripts.sofa.fit_constants import (
        MIN_BUCKET_ROWS,
        MIN_DIRECTION_BUCKET_ROWS,
    )

    assert MIN_DIRECTION_BUCKET_ROWS > MIN_BUCKET_ROWS

    thin = MIN_DIRECTION_BUCKET_ROWS - 10
    with get_connection(db) as conn:
        _seed(conn, _rows("goals_total", "OVER", 0.85, thin, 0.10, "football"))
        reliability = fit_reliability(conn)

    # The market layer measures it; the direction layer refuses to.
    assert "goals_total" in reliability
    assert "goals_total|OVER" not in reliability


def test_no_thin_direction_bucket_ships() -> None:
    path = REPO / "config/sofa_market_reliability.json"
    if not path.exists():
        pytest.skip("no fitted reliability in this checkout")
    from scripts.sofa.fit_constants import MIN_DIRECTION_BUCKET_ROWS

    reliability = json.loads(path.read_text(encoding="utf-8"))
    thin = [
        (key, bucket, entry["n"])
        for key, buckets in reliability.items()
        if "|" in key and isinstance(buckets, dict)
        for bucket, entry in buckets.items()
        if isinstance(entry, dict) and entry["n"] < MIN_DIRECTION_BUCKET_ROWS
    ]
    assert not thin, thin


def test_a_row_describes_its_own_arithmetic() -> None:
    """p_bar must be re-derivable from the fields the row publishes.

    The correction is subtracted from p_central *before* the price blend, so a
    row that publishes only p_central and market_p does not determine its own
    p_bar. That went unnoticed for as long as the correction was dead: the
    term was always zero, the identity held by accident, and the first sheet
    where calibration actually fired produced two ARITHMETIC findings on rows
    whose arithmetic was right.
    """
    from bet.sofa.contracts import SheetRow
    from bet.sofa.engine import K_PRICE, bar_probability

    assert "calibration_correction" in SheetRow.model_fields

    p_central, market_p, n, correction = 0.62, 0.30, 10, 0.08
    p_bar, reason = bar_probability(
        p_central=p_central,
        hits=4,
        n=n,
        p_low_val=0.99,
        market_p=market_p,
        correction=correction,
    )
    assert reason == "none"

    w = n / (n + K_PRICE)
    naive = w * p_central + (1 - w) * market_p
    published = w * max(0.01, p_central - correction) + (1 - w) * market_p
    assert abs(published - p_bar) < 1e-9
    assert abs(naive - p_bar) > 1e-3, "without the term the identity is wrong"
