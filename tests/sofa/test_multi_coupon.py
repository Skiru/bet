"""WARIANT WSZYSTKIE: an assembly of what each sport's coupon printed."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import multi_coupon as mc
from bet.sofa import sport_coupon as sc
from scripts.sofa import (
    audit_settlement,
    run_multi_coupon,
    run_sport_coupon,
    settle_multi_coupon,
    settle_sport_coupon,
)

DATE = "2026-09-30"
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def official_single(
    eid: int,
    market: str,
    odds: float,
    conf: float,
    kickoff: datetime = AT + timedelta(hours=6),
) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "match": f"H{eid} - A{eid}",
        "competition": "Liga",
        "sport": "football",
        "kickoff_utc": iso(kickoff),
        "market": market,
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "confidence": conf,
        "offered_odds": odds,
        "overround": 0.08,
    }


def builder(eid: int, stakeable: bool) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "match": f"H{eid} - A{eid}",
        "kickoff_utc": iso(AT + timedelta(hours=5)),
        "n_legs": 2,
        "combined_probability": 0.55,
        "odds_if_product": 2.10,
        "odds_after_haircut": 1.85,
        "ev_after_haircut": 0.02 if stakeable else -0.03,
        "best_for_fixture": True,
        "legs": [
            {
                "market": "corners_total",
                "subject": "",
                "line": 7.5,
                "direction": "OVER",
            },
            {"market": "goals_total", "subject": "", "line": 3.5, "direction": "UNDER"},
        ],
    }


def write_official(
    root: Path,
    singles: list[dict[str, Any]],
    builders: list[dict[str, Any]] | None = None,
    pdf: bool = True,
) -> Path:
    run = root / DATE
    run.mkdir(parents=True, exist_ok=True)
    (run / "05_sheet.json").write_text("[]", encoding="utf-8")
    doc = {
        "profile": "standard",
        "created_at_utc": iso(AT - timedelta(hours=1)),
        "pdf_max_singles": 30,
        "prints_builders": True,
        "min_ev": None,
        "singles": singles,
        "builders": builders or [],
        "unfitted_constants": ["K_PRICE"],
    }
    later = (AT - timedelta(minutes=50)).timestamp()
    (run / "08_confidence.json").write_text(json.dumps(doc), encoding="utf-8")
    os.utime(run / "05_sheet.json", (later - 60, later - 60))
    os.utime(run / "08_confidence.json", (later, later))
    if pdf:
        (run / f"KUPON_{DATE}.pdf").write_bytes(b"%PDF official")
        os.utime(run / f"KUPON_{DATE}.pdf", (later + 5, later + 5))
    return run


def sport_leg(
    eid: str, odds: float, fair_p: float, kickoff: datetime = AT + timedelta(hours=4)
) -> dict[str, Any]:
    return {
        "superbet_event_id": eid,
        "market_id": 623,
        "family": "total",
        "period": 0,
        "subject": "",
        "line": 5.5,
        "side": "OVER",
        "odds": odds,
        "fair_p": fair_p,
        "fair_p_x_odds": round(fair_p * odds, 4),
        "overround": 0.07,
        "match_name": f"H{eid}·A{eid}",
        "team1": f"H{eid}",
        "team2": f"A{eid}",
        "tournament": "Liga",
        "kickoff_utc": iso(kickoff),
        "source_date": DATE,
        "label": "liczba goli: powyżej 5.5",
    }


def write_sport(
    root: Path,
    sport: sc.SportKey,
    legs: list[dict[str, Any]],
    created: datetime = AT - timedelta(minutes=30),
    date: str = DATE,
    with_hash: bool = True,
) -> Path:
    d = sc.day_dir(str(root), sport, DATE)
    d.mkdir(parents=True, exist_ok=True)
    pdf = d / sc.pdf_name(sport, DATE)
    pdf.write_bytes(f"%PDF {sport}".encode())
    doc = {
        "kind": "SPORT_COUPON_EXPERIMENT",
        "date": date,
        "sport": sport,
        "created_at_utc": iso(created),
        "legs": legs,
        "UNFITTED_CONSTANTS": list(sc.UNFITTED_CONSTANTS),
        "rule_history": {"n": 0},
    }
    if with_hash:
        doc["pdf_sha256"] = sc.file_sha256(pdf)
    (d / sc.COUPON_FILE).write_text(json.dumps(doc), encoding="utf-8")
    return d


def full_day(root: Path) -> None:
    write_official(
        root,
        [
            official_single(1, "corners_total", 1.30, 0.77),
            official_single(2, "goals_total", 1.50, 0.73),
        ],
        [builder(3, True), builder(4, False)],
    )
    for i, sport in enumerate(sc.SPORT_KEYS):
        write_sport(
            root,
            sport,
            [sport_leg(f"{i}1", 1.20, 0.80), sport_leg(f"{i}2", 1.10, 0.88)],
        )


# --- assembly ---------------------------------------------------------------------


def test_every_position_is_exactly_what_its_coupon_printed(tmp_path: Path) -> None:
    full_day(tmp_path)
    doc = mc.assemble(str(tmp_path), DATE, AT)
    off = doc["sections"]["official"]
    assert [p["source"]["sofascore_event_id"] for p in off["singles"]] == [1, 2]
    assert [p["odds"] for p in off["singles"]] == [1.30, 1.50]
    assert [p["probability"] for p in off["singles"]] == [0.77, 0.73]
    # only the stakeable builder is printed - as the official PDF does
    assert [b["source"]["sofascore_event_id"] for b in off["builders"]] == [3]
    for sport in sc.SPORT_KEYS:
        sec = doc["sections"][sport]
        assert sec["status"] == "OK"
        assert [(p["odds"], p["probability"]) for p in sec["singles"]] == [
            (1.20, 0.80),
            (1.10, 0.88),
        ]
        assert {p["probability_kind"] for p in sec["singles"]} == {"fair_p"}
    assert {p["probability_kind"] for p in off["singles"]} == {"confidence"}
    assert doc["counts"] == {
        "singles": 2 + 8,
        "builders": 1,
        "sections_ok": 5,
        "sections_excluded": [],
    }
    assert doc["not_the_coupon"] is True


def test_the_official_section_is_capped_as_its_pdf_is(tmp_path: Path) -> None:
    singles = [official_single(i, "corners_total", 1.3, 0.77) for i in range(40)]
    write_official(tmp_path, singles)
    doc = mc.assemble(str(tmp_path), DATE, AT)
    assert len(doc["sections"]["official"]["singles"]) == 30  # pdf_max_singles


def test_a_started_position_is_marked_not_dropped(tmp_path: Path) -> None:
    write_official(
        tmp_path,
        [
            official_single(
                1, "corners_total", 1.3, 0.77, kickoff=AT - timedelta(minutes=5)
            )
        ],
    )
    write_sport(
        tmp_path, "hockey", [sport_leg("1", 1.2, 0.8, kickoff=AT - timedelta(hours=1))]
    )
    doc = mc.assemble(str(tmp_path), DATE, AT)
    assert doc["sections"]["official"]["singles"][0]["started"] is True
    assert doc["sections"]["hockey"]["singles"][0]["started"] is True


@pytest.mark.parametrize(
    "breakage, reason",
    [
        ("missing", "MISSING"),
        ("profile", "WRONG_PROFILE"),
        ("sheet_newer", "STALE_CONFIDENCE"),
        ("vetoes_newer", "STALE_CONFIDENCE"),
        ("no_pdf", "NO_PDF"),
        ("pdf_older", "PDF_OLDER_THAN_ARTIFACT"),
    ],
)
def test_an_official_source_that_is_not_the_printed_coupon_is_refused(
    tmp_path: Path, breakage: str, reason: str
) -> None:
    run = write_official(
        tmp_path,
        [official_single(1, "corners_total", 1.3, 0.77)],
        pdf=breakage != "no_pdf",
    )
    conf = run / "08_confidence.json"
    t = conf.stat().st_mtime
    if breakage == "missing":
        conf.unlink()
    elif breakage == "profile":
        conf.write_text(
            json.dumps({"profile": "wariant", "singles": []}), encoding="utf-8"
        )
        os.utime(conf, (t, t))
    elif breakage == "sheet_newer":
        os.utime(run / "05_sheet.json", (t + 100, t + 100))
    elif breakage == "vetoes_newer":
        (run / "vetoes.json").write_text("{}", encoding="utf-8")
        os.utime(run / "vetoes.json", (t + 100, t + 100))
    elif breakage == "pdf_older":
        os.utime(run / f"KUPON_{DATE}.pdf", (t - 100, t - 100))
    sec = mc.assemble(str(tmp_path), DATE, AT)["sections"]["official"]
    assert sec["status"] == "EXCLUDED" and sec["reason"].startswith(reason)
    assert sec["singles"] == [] and sec["builders"] == []


def test_a_sport_source_is_refused_when_wrong_day_stale_or_not_its_pdf(
    tmp_path: Path,
) -> None:
    write_sport(tmp_path, "cs2", [sport_leg("1", 1.2, 0.8)], date="2026-09-29")
    write_sport(
        tmp_path,
        "hockey",
        [sport_leg("1", 1.2, 0.8)],
        created=AT - mc.MAX_SOURCE_AGE - timedelta(minutes=1),
    )
    d = write_sport(tmp_path, "basketball", [sport_leg("1", 1.2, 0.8)])
    (d / sc.pdf_name("basketball", DATE)).write_bytes(b"%PDF another build")
    secs = mc.assemble(str(tmp_path), DATE, AT)["sections"]
    assert secs["cs2"]["reason"].startswith("WRONG_DAY")
    assert secs["hockey"]["reason"].startswith("STALE")
    assert secs["basketball"]["reason"].startswith("PDF_MISMATCH")
    assert secs["volleyball"]["reason"].startswith("MISSING")


def test_a_legacy_sport_coupon_without_a_hash_passes_only_within_the_skew(
    tmp_path: Path,
) -> None:
    d = write_sport(tmp_path, "hockey", [sport_leg("1", 1.2, 0.8)], with_hash=False)
    pdf, js = d / sc.pdf_name("hockey", DATE), d / sc.COUPON_FILE
    t = js.stat().st_mtime
    os.utime(pdf, (t - 1, t - 1))  # rendered just before the JSON, same run
    assert mc.assemble(str(tmp_path), DATE, AT)["sections"]["hockey"]["status"] == "OK"
    os.utime(pdf, (t - sc.LEGACY_PDF_SKEW_S - 10, t - sc.LEGACY_PDF_SKEW_S - 10))
    sec = mc.assemble(str(tmp_path), DATE, AT)["sections"]["hockey"]
    assert sec["reason"].startswith("PDF_NOT_FROM_THIS_BUILD")


def test_the_official_day_directory_is_only_read(tmp_path: Path) -> None:
    full_day(tmp_path)
    run = tmp_path / DATE
    before = {p.name: (p.stat().st_mtime, p.read_bytes()) for p in run.iterdir()}
    assert mc.multi_dir(str(tmp_path), DATE) != run
    mc.assemble(str(tmp_path), DATE, AT)
    after = {p.name: (p.stat().st_mtime, p.read_bytes()) for p in run.iterdir()}
    assert after == before


# --- the script -----------------------------------------------------------------------


def run(monkeypatch: pytest.MonkeyPatch, root: Path, at: datetime, *extra: str) -> int:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(root))
    monkeypatch.setattr(run_multi_coupon, "now", lambda: at)
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE, *extra])
    return run_multi_coupon.main()


def test_script_writes_beside_the_day_and_links_json_to_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_day(tmp_path)
    assert run(monkeypatch, tmp_path, AT) == 0
    out = mc.multi_dir(str(tmp_path), DATE)
    doc = json.loads((out / mc.MULTI_FILE).read_text(encoding="utf-8"))
    assert doc["pdf_sha256"] == sc.file_sha256(out / mc.pdf_name(DATE))
    assert doc["sports_built_unreviewed"] is False
    assert not (tmp_path / DATE / mc.pdf_name(DATE)).exists()
    text = json.dumps(doc)
    assert "odds_if_product" not in json.dumps(
        [p for s in doc["sections"].values() for p in s["singles"]]
    )
    assert "combined_price" not in text


def test_script_is_partial_when_a_section_is_out_and_refuses_a_closed_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_official(tmp_path, [official_single(1, "corners_total", 1.3, 0.77)])
    assert run(monkeypatch, tmp_path, AT) == 1
    assert run(monkeypatch, tmp_path, sc.day_end(DATE)) == 2


def test_a_failed_render_keeps_the_previous_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_day(tmp_path)
    assert run(monkeypatch, tmp_path, AT) == 0
    out = mc.multi_dir(str(tmp_path), DATE)
    before = (out / mc.MULTI_FILE).read_bytes(), (out / mc.pdf_name(DATE)).read_bytes()

    def boom(doc: dict[str, Any], path: Path) -> None:
        path.write_bytes(b"half")
        raise RuntimeError("render")

    monkeypatch.setattr(run_multi_coupon, "render_pdf", boom)
    assert run(monkeypatch, tmp_path, AT + timedelta(minutes=1)) == 2
    assert (
        (out / mc.MULTI_FILE).read_bytes(),
        (out / mc.pdf_name(DATE)).read_bytes(),
    ) == before


def test_sport_coupon_json_names_its_pdf_by_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = {
        "kind": "SPORT_COUPON_EXPERIMENT",
        "sport": "hockey",
        "date": DATE,
        "created_at_utc": iso(AT),
        "rule": sc.Rule().as_dict(),
        "UNFITTED_CONSTANTS": [],
        "counts": {},
        "candidates": 0,
        "vetoed": [],
        "vetoes_unmatched": [],
        "rule_history": {"n": 0, "days": []},
        "legs": [],
        "snapshots": 0,
        "locked": 0,
    }
    pdf = run_sport_coupon.write_outputs("hockey", DATE, str(tmp_path), doc)
    saved = json.loads((pdf.parent / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert saved["pdf_sha256"] == sc.file_sha256(pdf)
    assert sc.pdf_matches(saved, pdf.parent / sc.COUPON_FILE, pdf) is None


# --- settling -------------------------------------------------------------------------


def settled_row(
    eid: int, market: str, outcome: str, line: float = 7.5, direction: str = "OVER"
) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "market": market,
        "subject": "",
        "line": line,
        "direction": direction,
        "outcome": outcome,
    }


def test_settlement_matches_7c_and_the_sport_coupons_and_adds_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_day(tmp_path)
    assert run(monkeypatch, tmp_path, AT) == 0
    run_dir = tmp_path / DATE
    rows = [
        settled_row(1, "corners_total", "WIN"),
        settled_row(2, "goals_total", "LOSS"),
        settled_row(3, "corners_total", "WIN"),
        settled_row(3, "goals_total", "WIN", 3.5, "UNDER"),
    ]
    (run_dir / "07_settled.json").write_text(json.dumps(rows), encoding="utf-8")
    hockey = sc.day_dir(str(tmp_path), "hockey", DATE)
    game = {
        "state": "SETTLED",
        "t1_periods": [2, 2, 2],
        "t2_periods": [0, 0, 1],
        "t1_full": 6,
        "t2_full": 1,
        "overtime": False,
        "graded": [],
    }
    (hockey / "settled.json").write_text(
        json.dumps({"events": {"11": game}}), encoding="utf-8"
    )
    res = settle_multi_coupon.settle_day(str(tmp_path), DATE)
    assert res is not None
    off = res["sections"]["official"]
    # the same answer as audit_settlement 7c on the same rows
    conf = json.loads((run_dir / "08_confidence.json").read_text(encoding="utf-8"))
    by_key = {audit_settlement._key(r): r for r in rows}
    seven_c = audit_settlement.settle_singles(conf["singles"], by_key)
    assert (off["singles"]["won"], off["singles"]["lost"]) == (
        seven_c["won"],
        seven_c["lost"],
    )
    assert off["singles"]["units"] == pytest.approx(seven_c["units"])
    assert off["builders"]["won"] == 1 and off["builders"]["settled"] == 1
    # hockey: 7 goals, both legs over 5.5 win; the same as its own settlement
    h = res["sections"]["hockey"]
    assert (h["singles"]["won"], h["singles"]["not_counted"]) == (1, 1)  # "12" pending
    graded_alone = settle_sport_coupon.settle_day(str(tmp_path), "hockey", DATE)
    assert graded_alone is not None
    assert [g["outcome"] for g in h["rows"]] == [g["outcome"] for g in graded_alone]
    total = res["variant_total"]
    parts = [off["singles"], off["builders"]] + [
        res["sections"][s]["singles"] for s in sc.SPORT_KEYS
    ]
    assert total["units"] == pytest.approx(sum(p["units"] for p in parts))
    assert total["positions"] == sum(p["positions"] for p in parts)
    saved = mc.multi_dir(str(tmp_path), DATE) / mc.MULTI_SETTLED
    assert json.loads(saved.read_text(encoding="utf-8"))["not_the_coupon"] is True


def test_an_excluded_section_settles_to_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_official(tmp_path, [official_single(1, "corners_total", 1.3, 0.77)])
    run(monkeypatch, tmp_path, AT)
    res = settle_multi_coupon.settle_day(str(tmp_path), DATE)
    assert res is not None
    assert res["sections"]["cs2"]["status"] == "EXCLUDED"
    assert res["variant_total"]["positions"] == 1
