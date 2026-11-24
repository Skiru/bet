"""verify_legs.py: the verifier's deterministic per-leg screen (2026-10-19) -
a missing sheet row, a side the names contradict, a leg printed unlocked
after its start, a clean leg, the candidate NO_BET reads validating as
LegRead, and the --live statuses on a fake fetcher."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa.contracts import LegRead
from bet.sofa.line_evidence import LineEvidence
from scripts.sofa import verify_legs
from scripts.sofa.build_coupon import assemble

DATE = "2026-10-14"
BUILT = "2026-10-14T10:00:00Z"
TEAMS = {1: ("Lech Poznan", "Legia Warszawa"), 2: ("Wisla Krakow", "Cracovia"),
         3: ("Gornik Zabrze", "Piast Gliwice"),
         4: ("Rakow Czestochowa", "Motor Lublin")}


def fixture(eid: int, kickoff: str) -> dict[str, Any]:
    home, away = TEAMS[eid]
    return {
        "sofascore_event_id": eid, "superbet_event_ids": [f"su{eid}"],
        "sport": "football", "kickoff_utc": kickoff, "home_name": home,
        "away_name": away, "home_entity_id": eid * 10, "away_entity_id": eid * 10 + 1,
        "competition_name": "Ekstraklasa", "competition_id": 202, "season_id": 1,
        "category_name": "Poland", "identity": "CONFIRMED", "round_number": 9,
        "round_name": None, "cup_round_type": None, "previous_leg_event_id": None,
        "venue_name": None, "referee": None, "ground_type": None,
        "default_period_count": 2, "superbet_kickoff_utc": kickoff,
        "sofascore_status": "notstarted"}


def leg(eid: int, market: str, subject: str, kickoff: str,
        conf: float = 0.80) -> dict[str, Any]:
    home, away = TEAMS[eid]
    return {"sofascore_event_id": eid, "confidence": conf, "sport": "football",
            "kickoff_utc": kickoff, "market": market, "subject": subject,
            "line": 4.5, "direction": "OVER", "offered_odds": 1.25,
            "match": f"{home} - {away}", "competition": "Ekstraklasa",
            "display_market": market, "sample_size": 10,
            "calibrated_on": f"market:{market}|OVER"}


def sheet_row(x: dict[str, Any]) -> dict[str, Any]:
    return {"sofascore_event_id": x["sofascore_event_id"], "sport": "football",
            "market": x["market"], "subject": x["subject"], "line": x["line"],
            "direction": "OVER", "p_central": 0.80, "notes": []}


def build_day(tmp_path: Path) -> Path:
    """1 clean, 2 without a sheet row, 3 a side leg, 4 started before the build."""
    late, early = "2026-10-14T18:00:00Z", "2026-10-14T08:00:00Z"
    singles = [leg(1, "corners_total", "", late),
               leg(2, "corners_total", "", late),
               leg(3, "corners_for", "Gornik Zabrze", late),
               leg(4, "corners_total", "", early)]
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": BUILT,
            "singles": singles, "legs": singles, "builders": []}
    doc = assemble(conf, None, [], {}, BUILT, DATE, read_events=True,
                   read_value_order=True)
    run = tmp_path / DATE
    run.mkdir()
    (run / "11_coupon.json").write_text(json.dumps(doc))
    (run / "02_fixtures.json").write_text(json.dumps(
        [fixture(e, early if e == 4 else late) for e in TEAMS]))
    (run / "05_sheet.json").write_text(json.dumps(
        [sheet_row(x) for x in singles if x["sofascore_event_id"] != 2]))
    (run / "03_samples.json").write_text(json.dumps(
        [{"sofascore_event_id": e, "metrics": {}} for e in TEAMS]))
    return run


def run_cli(tmp_path: Path, *extra: str) -> tuple[int, dict[int, dict[str, Any]], str]:
    out = tmp_path / "out"
    code = verify_legs.main(["--date", DATE, "--runs-dir", str(tmp_path),
                             "--out-dir", str(out), *extra])
    recs = [json.loads(line) for line in
            (out / "verify_legs.jsonl").read_text().splitlines()]
    return code, {r["sofascore_event_id"]: r for r in recs}, (
        out / "verify_legs.md").read_text()


def checks(rec: dict[str, Any], level: str = "DEFECT") -> set[str]:
    return {f["check"] for f in rec["findings"] if f["level"] == level}


def test_the_screen_finds_each_defect_and_passes_the_clean_leg(
        tmp_path: Path) -> None:
    build_day(tmp_path)
    code, recs, md = run_cli(tmp_path, "--all")
    assert code == 1
    assert recs[1]["findings"] == []
    assert {"sheet_row", "sheet_notes", "clocks"} <= set(recs[1]["checks_run"])
    assert checks(recs[2]) == {"sheet_row"}
    assert recs[3]["side"] == {"code": "side_a", "independent": "side_a"}
    assert recs[3]["findings"] == []
    assert checks(recs[4]) == {"clocks"}
    assert "Day summary" in md


def test_a_side_the_names_contradict_is_a_defect(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_day(tmp_path)
    monkeypatch.setattr(verify_legs, "determine_side", lambda s, f: "side_b")
    _, recs, _ = run_cli(tmp_path, "--all")
    assert checks(recs[3]) == {"side"}
    assert recs[3]["side"] == {"code": "side_b", "independent": "side_a"}


def test_a_simulator_choice_code_is_not_a_side() -> None:
    """11-08: 158 false side DEFECTs read "U2.5/O0.5" / "Nie/Nie" as teams."""
    def name(market: str, subject: str) -> str | None:
        return verify_legs.side_name(verify_legs.Leg(
            raw={"market": market, "subject": subject}, kind="single"))
    assert name("half_goals_combo", "U2.5/O0.5") is None
    assert name("btts_halves", "Nie/Nie") is None
    assert name("htft", "1/X") is None
    assert name("team_scores_both_halves", "1") is None
    assert name("corners_for", "FC Utrecht") == "FC Utrecht"


def test_the_independent_side_match() -> None:
    side = verify_legs.independent_side
    assert side("karagumruk", "Fatih Karagümrük", "Keçiörengücü") == "side_a"
    assert side("Mitsuki Wei K.Leong", "Max Purcell",
                "Mitsuki Wei Kang Leong") == "side_b"
    # a generic word alone decides nothing
    assert side("FC", "FC Utrecht", "FC Twente") is None


def test_the_reads_block_is_no_bet_for_hard_defects_and_validates(
        tmp_path: Path) -> None:
    build_day(tmp_path)
    _, _, md = run_cli(tmp_path)
    block = md.split("```json reads\n", 1)[1].split("```", 1)[0]
    reads = json.loads(block)
    assert {r["sofascore_event_id"] for r in reads} == {2, 4}
    for r in reads:
        LegRead.model_validate(r)
        assert r["verdict"] == "NO_BET" and r["author"] == "verifier"


def test_a_locked_leg_printed_before_its_start_is_clean(tmp_path: Path) -> None:
    run = build_day(tmp_path)
    doc = json.loads((run / "11_coupon.json").read_text())
    for s in doc["singles"]:
        if s["sofascore_event_id"] == 4:
            s.update(locked=True, printed_at_utc="2026-10-14T07:00:00Z")
    (run / "11_coupon.json").write_text(json.dumps(doc))
    _, recs, _ = run_cli(tmp_path, "--all")
    assert checks(recs[4]) == set()
    for s in doc["singles"]:
        if s["sofascore_event_id"] == 4:
            s["printed_at_utc"] = "2026-10-14T08:30:00Z"
    (run / "11_coupon.json").write_text(json.dumps(doc))
    _, recs, md = run_cli(tmp_path, "--all")
    assert checks(recs[4]) == {"clocks"}
    # a locked leg is a fact of the day: never a candidate read
    block = json.loads(md.split("```json reads\n", 1)[1].split("```", 1)[0])
    assert 4 not in {r["sofascore_event_id"] for r in block}


def test_missing_artifacts_exit_2(tmp_path: Path) -> None:
    (tmp_path / DATE).mkdir()
    assert verify_legs.main(["--date", DATE, "--runs-dir", str(tmp_path),
                             "--out-dir", str(tmp_path / "o")]) == 2


def test_live_statuses_on_a_fake_fetcher(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_day(tmp_path)
    from bet.sofa import offer, superbet

    def rung(market: str, odds: float, subject: str = "") -> SimpleNamespace:
        return SimpleNamespace(market=market, subject=subject, line=4.5,
                               over_odds=odds, under_odds=3.0)

    offers = {
        1: [rung("corners_total", 1.25)],                       # OK
        2: [rung("corners_total", 1.05)],                       # CHANGED, x < 0.90
        3: [],                                                  # MISSING
    }

    class FakeFetcher:
        def __init__(self, client: object, **flags: bool) -> None:
            assert "tennis_winner" in flags  # offer.day_flags, as OFFER
            self.errors: list[tuple[str, str]] = []
            self.not_reached: list[int] = []

        def fetch_offers(self, fixtures: list[Any]) -> list[SimpleNamespace]:
            asked = [f.sofascore_event_id for f in fixtures]
            assert sorted(asked) == [1, 2, 3]  # the started match 4 is not asked
            return [SimpleNamespace(sofascore_event_id=e, rungs=offers.get(e, []),
                                    superbet_started_utc=None) for e in asked]

    monkeypatch.setattr(offer, "OfferFetcher", FakeFetcher)
    monkeypatch.setattr(superbet, "SuperbetClient", lambda: object())
    _, recs, _ = run_cli(tmp_path, "--all", "--live", "--limit-fixtures", "3")
    assert recs[1]["live"] == {"status": "OK", "odds": 1.25}
    # a changed price is a NOTE that says what the rebuild does (sofa-verifier
    # 2c, operator 2026-11-19): 1.05 is under the odds floor and x < 0.90
    assert recs[2]["live"]["status"] == "CHANGED"
    assert recs[2]["live"]["x"] == 0.84  # old confidence x new odds, kept
    assert recs[2]["live"]["rebuild"]["drops"] == ["ODDS_TOO_LOW", "NEGATIVE_LEG_EV"]
    assert "live" in checks(recs[2], "NOTE") and "live" not in checks(recs[2])
    assert "the rebuild drops it (ODDS_TOO_LOW" in next(
        f["detail"] for f in recs[2]["findings"] if f["check"] == "live")
    assert recs[3]["live"] == {"status": "MISSING"}
    assert "live" in checks(recs[3])  # a vanished price stays a DEFECT
    assert "live" not in recs[4]


# --- rebuild_at_price: what the rebuild does with a changed price ------------

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)
GAP_EVIDENCE = LineEvidence(
    {"keys": {"football": {}},
     "sport_printable_by_gap": {"football": {"4": {"gap": -0.06}, "3": {"gap": -0.06},
                                             "1": {"gap": 0.0}}}},
    v2=True, price_gap_sports=frozenset({"football"}))


def priced(conf: float, odds: float, **extra: Any) -> dict[str, Any]:
    return {"sport": "football", "market": "corners_total", "subject": "",
            "line": 9.5, "direction": "OVER", "model_p": 0.85,
            "confidence": conf, "offered_odds": odds,
            "calibrated_on": "market:corners_total|OVER", "calibration_n": 900,
            **extra}


def at(raw: dict[str, Any], odds: float,
       ev: LineEvidence | None = GAP_EVIDENCE) -> dict[str, Any]:
    return verify_legs.rebuild_at_price(raw, odds, ev, "2026-11-15", NOW,
                                        0.70, 0.90)


def test_a_shorter_price_re_reads_the_offset_and_keeps_the_leg() -> None:
    """11-15: curve 0.80 at 1.40 (d = +0.086, bucket 4) printed 0.74; at 1.20
    (d = -0.033, bucket 1) the offset is 0 - the rebuild prints 0.80 x 1.20 =
    0.96, where the old check called 0.74 x 1.20 = 0.888 a DEFECT."""
    raw = priced(0.74, 1.40, line_offset=-0.06,
                 calibrated_on="market:corners_total|OVER-0.0600sbd4")
    assert at(raw, 1.40)["confidence"] == 0.74  # its own price: as printed
    assert at(raw, 1.20) == {"confidence": 0.8, "rule": "line_evidence",
                             "x": 0.96, "drops": []}


def test_a_new_price_under_the_odds_floor_is_dropped() -> None:
    """11-15: a leg whose new price was under 1/0.9202 passed as a NOTE on x."""
    got = at(priced(0.86, 1.15), 1.08)
    assert round(0.86 * 1.08, 3) >= 0.90  # the x gate alone would keep it
    assert got["drops"] == ["ODDS_TOO_LOW"]


def test_a_longer_price_that_moves_the_offset_can_drop_the_leg() -> None:
    got = at(priced(0.80, 1.20), 1.40)  # bucket 1 -> 4: offset -0.06
    assert got["confidence"] == 0.74 and got["drops"] == []  # x 1.036
    got = at(priced(0.75, 1.20), 1.40)  # d 0.036, bucket 3
    assert got["confidence"] == 0.69
    assert got["drops"] == ["BELOW_CONFIDENCE_FLOOR"]


def test_no_line_evidence_keeps_the_old_confidence_and_says_so() -> None:
    assert at(priced(0.80, 1.20), 1.10, ev=None) == {
        "confidence": 0.8, "rule": "old_confidence", "x": 0.88,
        "drops": ["NEGATIVE_LEG_EV"]}


def test_a_capped_leg_is_a_lower_bound_under_the_band_cell() -> None:
    cell = {"0.850-0.875": {"n": 40, "k": 28}}  # 0.70 realised
    ev = LineEvidence({"keys": {"football": {}},
                       "bands": {"football": {"corners_total|OVER": {
                           "1.30-1.60": cell}}}})
    raw = priced(0.70, 1.35, price_band_cap=0.70,
                 calibrated_on="market:corners_total|OVER|cap:corners_total|"
                 "OVER@1.30-1.60:0.850-0.875")
    got = at(raw, 1.32, ev)
    assert got["rule"] == "line_evidence:lower_bound"
    assert got["confidence"] == 0.70 and got["drops"] == []
    # out of the band no cell caps it: the curve's lower bound (cap) stands
    assert at(raw, 1.25, ev)["confidence"] == 0.70


def test_a_class_leg_reads_its_class_evidence_and_no_bucket_is_a_drop() -> None:
    raw = priced(0.75, 1.30, calibrated_on="sb:football:women:corners_total|OVER")
    got = at(raw, 1.25, LineEvidence({"keys": {"football": {}}}))
    assert got["drops"] == ["NO_LINE_EVIDENCE"]
    lines = LineEvidence({"keys": {"football": {"women:corners_total|OVER": {
        "buckets": {"0.850-0.875": {"n": 400, "k": 340}}}}}})
    got = at(raw, 1.25, lines)  # no curve: the class key's own bucket
    assert got["rule"] == "line_evidence" and 0.80 < got["confidence"] < 0.85
    ev = LineEvidence({"keys": {"football": {"women:corners_total|OVER": {
        "printable": {"realised_minus_confidence": [-0.05], "n": 500,
                      "games": 400}}}}})
    raw = priced(0.80, 1.30, calibrated_on="women:market:corners_total|OVER")
    assert at(raw, 1.25, ev)["confidence"] == 0.75  # the class key's offset
    raw["calibrated_on"] = "market:corners_total|OVER"
    assert at(raw, 1.25, ev)["confidence"] == 0.80  # not the class key's


def test_a_missing_input_is_cannot_verify_never_a_no_bet(tmp_path: Path) -> None:
    """No 03_samples.json: the own-sample check could not run - CANNOT_VERIFY,
    never a defect and never a candidate NO_BET (final review 2026-10-19)."""
    run = build_day(tmp_path)
    (run / "03_samples.json").unlink()
    code, recs, md = run_cli(tmp_path, "--all")
    assert code == 1
    assert checks(recs[1], "CANNOT_VERIFY") == {"own_sample"}
    assert checks(recs[1]) == set()
    block = md.split("```json reads\n", 1)[1].split("```", 1)[0]
    assert {r["sofascore_event_id"] for r in json.loads(block)} == {2, 4}
