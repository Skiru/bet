"""A market's thin bucket caps what a pool may claim for it (2026-10-04).

goals_1h_total had no cache-replay rows, so its UNDER buckets 0.70-0.875 were
under MIN_MARKET_BUCKET=400 (232-393 rows) and CONFIDENCE read
pooled:football there - 0.8149 at p 0.80-0.825, where the market's own rows
bound it at ~0.755. fit_confidence now writes those buckets (MIN_THIN_BUCKET
..MIN_MARKET_BUCKET rows) to `thin_by_market_direction`, and
Calibration.realised returns min(pool lo95, thin lo95) where it falls to a
pool. A file without the section reads exactly as before.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from bet.sofa.confidence import Calibration
from scripts.sofa.fit_confidence import MIN_MARKET_BUCKET, MIN_THIN_BUCKET

REPO = Path(__file__).resolve().parents[2]

POOL = {"0.800-0.825": {"n": 1_360_517, "realised": 0.8155, "realised_lo95": 0.8149}}
OWN_ELSEWHERE = {"0.600-0.700": {"n": 2104, "realised": 0.6773, "realised_lo95": 0.657},
                 "0.875-0.900": {"n": 410, "realised": 0.8854, "realised_lo95": 0.8509}}


def _cal(thin: dict[str, dict[str, dict[str, float]]]) -> Calibration:
    return Calibration(
        pooled=POOL,
        by_market={"goals_1h_total": OWN_ELSEWHERE},
        pooled_by_sport={"football": POOL},
        thin_by_market_direction=thin,
    )


def test_without_thin_section_the_pool_reads_as_before() -> None:
    hit = _cal({}).realised("goals_1h_total", 0.81, "football", "UNDER")
    assert hit == (0.8149, "pooled:football", 1_360_517)


def test_thin_bucket_below_the_pool_caps_it() -> None:
    thin = {"goals_1h_total|UNDER": {
        "0.800-0.825": {"n": 232, "realised": 0.81, "realised_lo95": 0.7545}}}
    hit = _cal(thin).realised("goals_1h_total", 0.81, "football", "UNDER")
    assert hit == (0.7545, "market_thin:goals_1h_total|UNDER", 232)


def test_thin_bucket_above_the_pool_does_not_raise_it() -> None:
    thin = {"goals_1h_total|UNDER": {
        "0.800-0.825": {"n": 393, "realised": 0.88, "realised_lo95": 0.845}}}
    hit = _cal(thin).realised("goals_1h_total", 0.81, "football", "UNDER")
    assert hit == (0.8149, "pooled:football", 1_360_517)


def test_the_other_direction_thin_bucket_is_not_read() -> None:
    thin = {"goals_1h_total|OVER": {
        "0.800-0.825": {"n": 150, "realised": 0.70, "realised_lo95": 0.62}}}
    hit = _cal(thin).realised("goals_1h_total", 0.81, "football", "UNDER")
    assert hit is not None and hit[1] == "pooled:football"


def test_a_measured_bucket_is_never_capped() -> None:
    # 0.875-0.900 has its own market bucket: the thin section is not consulted.
    thin = {"goals_1h_total|UNDER": {
        "0.875-0.900": {"n": 150, "realised": 0.70, "realised_lo95": 0.62}}}
    hit = _cal(thin).realised("goals_1h_total", 0.88, "football", "UNDER")
    assert hit == (0.8509, "market:goals_1h_total", 410)


def test_load_reads_the_section(tmp_path: Path) -> None:
    thin = {"goals_1h_total|UNDER": {
        "0.800-0.825": {"n": 232, "realised": 0.81, "realised_lo95": 0.7545}}}
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "pooled": POOL, "pooled_by_sport": {"football": POOL},
        "by_market": {"goals_1h_total": OWN_ELSEWHERE},
        "thin_by_market_direction": thin,
    }))
    hit = Calibration.load(path).realised("goals_1h_total", 0.81, "football", "UNDER")
    assert hit is not None and hit[1] == "market_thin:goals_1h_total|UNDER"


def test_class_section_carries_its_thin_buckets() -> None:
    cal = Calibration(
        pooled=POOL, by_market={}, pooled_by_sport={"football": POOL},
        by_class={"women": {
            "by_market": {"goals_1h_total": OWN_ELSEWHERE},
            "pooled_by_sport": {"football": POOL},
            "thin_by_market_direction": {"goals_1h_total|UNDER": {
                "0.800-0.825": {"n": 120, "realised": 0.78, "realised_lo95": 0.70}}},
        }},
    )
    hit = cal.realised("goals_1h_total", 0.81, "football", "UNDER", klass="women")
    assert hit == (0.70, "women:market_thin:goals_1h_total|UNDER", 120)


def test_fit_writes_only_the_thin_band(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    con = sqlite3.connect(db)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.execute("create table sofa_entity_events (kind text, events_json text)")
    rows = []
    eid = 0

    def add(market: str, direction: str, p: float, n: int, wins: int) -> None:
        nonlocal eid
        for i in range(n):
            win = i < wins
            # UNDER 1.5 wins on 1 goal; OVER 1.5 wins on 2.
            if direction == "UNDER":
                actual = 1.0 if win else 2.0
            else:
                actual = 2.0 if win else 1.0
            rows.append(
                (market, 1.5, direction, 10, 1.2, 1.0, actual, p, "football", eid))
            eid += 1

    add("goals_1h_total", "UNDER", 0.81, MIN_THIN_BUCKET + 50, 120)  # thin
    add("goals_1h_total", "UNDER", 0.76, MIN_THIN_BUCKET - 1, 70)  # too thin
    add("goals_1h_total", "UNDER", 0.89, MIN_MARKET_BUCKET, 360)  # measured
    add("player_fouls_for", "OVER", 0.81, MIN_THIN_BUCKET + 50, 90)  # no pool
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    out = tmp_path / "cal.json"
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out)],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text())
    assert doc["min_thin_bucket"] == MIN_THIN_BUCKET
    thin = doc["thin_by_market_direction"]
    assert set(thin) == {"goals_1h_total|UNDER"}
    assert set(thin["goals_1h_total|UNDER"]) == {"0.800-0.825"}
    entry = thin["goals_1h_total|UNDER"]["0.800-0.825"]
    assert entry["n"] == MIN_THIN_BUCKET + 50
    assert entry["realised"] == round(120 / (MIN_THIN_BUCKET + 50), 4)
    assert entry["realised_lo95"] < entry["realised"]
    assert "0.875-0.900" in doc["by_market_direction"]["goals_1h_total|UNDER"]
