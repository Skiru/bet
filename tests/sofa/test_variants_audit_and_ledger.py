"""audit_variants catches every tampering it claims to; the ledger adds up."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import multi_coupon as mc
from bet.sofa import sport_coupon as sc
from scripts.sofa import (
    audit_variants,
    record_results,
    run_multi_coupon,
    run_sport_coupon,
)
from tests.sofa.test_multi_coupon import official_single, write_official
from tests.sofa.test_sport_coupon import snap, total_pair, write_snaps

DATE = "2026-09-30"
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def built_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    d = write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                str(i),
                total_pair(str(i), 1.20 + i / 100, 4.20),
                AT - timedelta(minutes=5),
                kickoff=AT + timedelta(hours=2 + i),
            )
            for i in range(4)
        ],
    )
    monkeypatch.setattr(run_sport_coupon, "now", lambda: AT)
    monkeypatch.setattr(
        "sys.argv", ["x", "--date", DATE, "--sport", "hockey", "--max-legs", "3"]
    )
    assert run_sport_coupon.main() == 0
    write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    monkeypatch.setattr(run_multi_coupon, "now", lambda: AT + timedelta(minutes=1))
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE])
    assert run_multi_coupon.main() == 1  # three sports have no coupon
    return d


def findings(tmp_path: Path) -> list[str]:
    out = audit_variants.audit_sport(str(tmp_path), "hockey", DATE)
    return out + audit_variants.audit_multi(str(tmp_path), DATE)


def edit_coupon(d: Path, fn: Any) -> None:
    path = d / sc.COUPON_FILE
    doc = json.loads(path.read_text(encoding="utf-8"))
    fn(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_a_clean_day_has_no_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built_day(tmp_path, monkeypatch)
    assert findings(tmp_path) == []


def test_a_changed_pdf_is_s1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = built_day(tmp_path, monkeypatch)
    (d / sc.pdf_name("hockey", DATE)).write_bytes(b"%PDF other")
    assert any(f.startswith("S1") for f in findings(tmp_path))


def test_a_price_or_probability_not_in_the_snapshot_is_s3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = built_day(tmp_path, monkeypatch)

    def bump(doc: dict[str, Any]) -> None:
        doc["legs"][0]["fair_p"] += 0.02
        doc["legs"][1]["odds"] = 1.99

    edit_coupon(d, bump)
    got = findings(tmp_path)
    assert any("S3" in f and "fair_p" in f for f in got)
    assert any("S3" in f and "odds" in f for f in got)


def test_a_leg_the_rule_would_refuse_is_s2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = built_day(tmp_path, monkeypatch)

    def refuse(doc: dict[str, Any]) -> None:
        doc["legs"][0]["overround"] = 0.2
        doc["legs"][1]["family"] = "player_points"

    edit_coupon(d, refuse)
    got = [f for f in findings(tmp_path) if f.startswith("S2")]
    assert any("margin" in f for f in got) and any("player" in f for f in got)


def test_a_selection_the_snapshots_do_not_give_is_s5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = built_day(tmp_path, monkeypatch)
    edit_coupon(d, lambda doc: doc["legs"].pop())
    assert any(f.startswith("S5") for f in findings(tmp_path))


def test_a_vetoed_leg_on_the_page_is_s4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = built_day(tmp_path, monkeypatch)
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    eid = doc["legs"][0]["superbet_event_id"]
    (d / sc.VETOES_FILE).write_text(
        json.dumps({"vetoes": [{"superbet_event_id": eid}]}), encoding="utf-8"
    )
    got = findings(tmp_path)
    assert any(f.startswith("S4") and "vetoed" in f for f in got)


def test_a_source_rebuilt_after_the_variant_makes_it_stale_m2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = built_day(tmp_path, monkeypatch)
    edit_coupon(d, lambda doc: doc["legs"][0].update(odds=1.25))
    assert any(f.startswith("M2 hockey") for f in findings(tmp_path))
    conf = tmp_path / DATE / "08_confidence.json"
    cdoc = json.loads(conf.read_text(encoding="utf-8"))
    cdoc["singles"][0]["offered_odds"] = 1.40
    conf.write_text(json.dumps(cdoc), encoding="utf-8")
    assert any(f.startswith("M2 official") for f in findings(tmp_path))


def test_the_multi_pdf_must_match_m1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built_day(tmp_path, monkeypatch)
    (mc.multi_dir(str(tmp_path), DATE) / mc.pdf_name(DATE)).write_bytes(b"%PDF x")
    assert any(f.startswith("M1") for f in findings(tmp_path))


def test_the_ledger_records_every_variant_once_per_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = built_day(tmp_path, monkeypatch)
    run_dir = tmp_path / DATE
    (run_dir / "07_settled.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 1,
                    "market": "corners_total",
                    "subject": "",
                    "line": 7.5,
                    "direction": "OVER",
                    "outcome": "WIN",
                }
            ]
        ),
        encoding="utf-8",
    )
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    events = {
        leg["superbet_event_id"]: {
            "state": "SETTLED",
            "t1_periods": [2, 2, 2],
            "t2_periods": [0, 0, 0],
            "t1_full": 6,
            "t2_full": 0,
            "overtime": False,
            "graded": [
                {
                    **{
                        k: leg[k]
                        for k in (
                            "superbet_event_id",
                            "market_id",
                            "family",
                            "period",
                            "subject",
                            "line",
                            "side",
                            "odds",
                        )
                    },
                    "partner_odds": 4.2,
                    "fair_p": leg["fair_p"],
                    "outcome": "WIN",
                }
            ],
        }
        for leg in doc["legs"]
    }
    (d / "settled.json").write_text(json.dumps({"events": events}), encoding="utf-8")
    rows = record_results.record(str(tmp_path), DATE)
    by = {r["variant"]: r for r in rows}
    assert set(by) == {"official", "sport:hockey", "multi", "measure:hockey"}
    assert by["official"]["total"]["won"] == 1
    assert by["sport:hockey"]["total"]["won"] == 3
    assert by["multi"]["total"]["units"] == pytest.approx(
        by["official"]["total"]["units"] + by["sport:hockey"]["total"]["units"]
    )
    assert by["measure:hockey"]["favourite_side"]["sides"] == 3
    record_results.record(str(tmp_path), DATE)  # idempotent
    lines = (
        record_results.ledger_path(str(tmp_path))
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 4
