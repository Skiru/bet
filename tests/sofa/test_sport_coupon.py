"""The experimental per-sport coupon: price-only, singles, beside the measurement."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2, shadow
from bet.sofa import sport_coupon as sc
from scripts.sofa import run_sport_coupon, settle_sport_coupon

AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
DATE = "2026-09-30"


def iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def hline(
    eid: str,
    market_id: int,
    family: str,
    side: str,
    odds: float,
    line: float | None = None,
    period: int = 0,
    subject: str = "",
) -> dict[str, Any]:
    return {
        "superbet_event_id": eid,
        "market_id": market_id,
        "family": family,
        "period": period,
        "subject": subject,
        "line": line,
        "side": side,
        "odds": odds,
    }


def snap(
    eid: str,
    lines: list[dict[str, Any]],
    fetched: datetime,
    kickoff: datetime = AT + timedelta(hours=6),
) -> dict[str, Any]:
    return {
        "fetched_at_utc": iso(fetched),
        "superbet_event_id": eid,
        "match_name": f"Home {eid}·Away {eid}",
        "team1": f"Home {eid}",
        "team2": f"Away {eid}",
        "kickoff_utc": iso(kickoff),
        "tournament": "Liga",
        "lines": lines,
    }


def total_pair(
    eid: str, over: float, under: float, line: float = 5.5
) -> list[dict[str, Any]]:
    return [
        hline(eid, 623, "total", "OVER", over, line),
        hline(eid, 623, "total", "UNDER", under, line),
    ]


def build_cands(
    snaps: list[dict[str, Any]], at: datetime = AT, sport: sc.SportKey = "hockey"
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts: dict[str, int] = {}
    events = sc.latest_events(sport, snaps)
    return sc.candidates(sport, events, at, sc.Rule(), counts), counts


def write_snaps(
    root: Path, sport: sc.SportKey, date: str, snaps: list[dict[str, Any]]
) -> Path:
    d = sc.day_dir(str(root), sport, date)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in snaps))
    return d


# --- the rule -------------------------------------------------------------------------


def test_a_side_below_the_floor_or_on_a_dear_line_is_not_a_leg() -> None:
    fresh = AT - timedelta(minutes=10)
    cands, counts = build_cands(
        [
            snap("1", total_pair("1", 1.20, 4.20), fresh),  # ~0.78 fair, 7% margin
            snap("2", total_pair("2", 1.50, 2.50), fresh),  # favourite ~0.62
            snap("3", total_pair("3", 1.10, 3.80), fresh),  # ~0.78 but 17% margin
        ]
    )
    assert [(c["superbet_event_id"], c["side"]) for c in cands] == [("1", "OVER")]
    # every other side, by name: 1 UNDER, 2 OVER, 2 UNDER, 3 UNDER below the
    # floor; 3 OVER on a dear line
    assert counts == {"BELOW_FLOOR": 4, "MARGIN_TOO_HIGH": 1}


def test_fair_p_and_margin_are_the_pipelines_devig_of_the_whole_group() -> None:
    [c], _ = build_cands([snap("1", total_pair("1", 1.20, 4.20), AT)])
    assert c["fair_p"] == pytest.approx(cs2.fair_probability(1.20, 4.20), abs=1e-4)
    assert c["overround"] == pytest.approx(1 / 1.20 + 1 / 4.20 - 1, abs=1e-4)
    assert c["fair_p_x_odds"] == pytest.approx(c["fair_p"] * 1.20, abs=1e-3)
    assert c["group_odds"] == {"OVER": 1.20, "UNDER": 4.20}


def test_a_1x2_needs_its_draw_and_is_devigged_over_three() -> None:
    fresh = AT - timedelta(minutes=5)
    whole = [
        hline("1", 640, "result_1x2", "T1", 1.20),
        hline("1", 640, "result_1x2", "DRAW", 7.5),
        hline("1", 640, "result_1x2", "T2", 12.0),
    ]
    cands, _ = build_cands([snap("1", whole, fresh)])
    [c] = cands
    fair = cs2.group_fair({"T1": 1.20, "DRAW": 7.5, "T2": 12.0}, "three")
    assert fair is not None and c["fair_p"] == pytest.approx(fair["T1"], abs=1e-4)
    # the draw suspended: {T1, T2} is NOT a two-way market (it would devig to
    # 0.72 at a negative margin)
    cands, counts = build_cands([snap("2", [whole[0], whole[2]], fresh)])
    assert cands == [] and counts["incomplete_group"] == 2


def test_only_the_newest_snapshot_is_read_and_it_must_be_fresh() -> None:
    old, new = AT - timedelta(hours=2), AT - timedelta(minutes=5)
    cands, _ = build_cands(
        [
            snap("1", total_pair("1", 1.20, 4.20, 5.5), old),
            snap("1", total_pair("1", 1.22, 4.00, 6.5), new),
        ]
    )
    assert {c["line"] for c in cands} == {6.5}
    stale = AT - sc.MAX_PRICE_AGE - timedelta(minutes=1)
    cands, counts = build_cands([snap("2", total_pair("2", 1.20, 4.20), stale)])
    assert cands == [] and counts["stale_price_event"] == 1


def test_cs2_reads_only_the_newest_snapshot_too() -> None:
    def pair(line: float, over: float, under: float) -> list[dict[str, Any]]:
        return [
            cs2.Cs2Line("9", "maps_total", 0, "", line, "OVER", over).as_dict(),
            cs2.Cs2Line("9", "maps_total", 0, "", line, "UNDER", under).as_dict(),
        ]

    cands, _ = build_cands(
        [
            snap("9", pair(2.5, 1.20, 4.20), AT - timedelta(hours=1)),
            snap("9", pair(3.5, 1.25, 3.80), AT - timedelta(minutes=5)),
        ],
        sport="cs2",
    )
    assert {c["line"] for c in cands} == {3.5}


def test_microsecond_less_timestamps_order_as_times_not_strings() -> None:
    # "…:00Z" sorts after "…:00.5Z" as a string; it is the EARLIER time.
    early = snap("1", total_pair("1", 1.20, 4.20, 5.5), AT - timedelta(minutes=5))
    late = snap("1", total_pair("1", 1.22, 4.00, 6.5), AT - timedelta(minutes=5))
    late["fetched_at_utc"] = iso(AT - timedelta(minutes=5)).replace("Z", ".500000Z")
    cands, _ = build_cands([early, late])
    assert {c["line"] for c in cands} == {6.5}


def test_a_started_or_imminent_event_is_skipped() -> None:
    cands, counts = build_cands(
        [
            snap(
                "1",
                total_pair("1", 1.20, 4.20),
                AT - timedelta(minutes=30),
                kickoff=AT + timedelta(minutes=10),
            )
        ]
    )
    assert cands == [] and counts["started_or_too_close"] == 1


def test_player_lines_never_reach_the_coupon() -> None:
    lines = [
        hline("1", 236265, "player_points", "OVER", 1.20, 0.5, subject="A B"),
        hline("1", 236265, "player_points", "UNDER", 4.20, 0.5, subject="A B"),
    ]
    cands, counts = build_cands([snap("1", lines, AT - timedelta(minutes=5))])
    assert cands == [] and counts["player_line"] == 2


def test_one_leg_per_event_the_cheapest_side_and_at_most_max_legs() -> None:
    fresh = AT - timedelta(minutes=5)
    snaps = [
        snap(
            "1",
            [*total_pair("1", 1.20, 4.20, 5.5), *total_pair("1", 1.25, 3.60, 4.5)],
            fresh,
        )
    ]
    # a lower fair_p x odds than event 1's best (0.9657 against 0.9718)
    snaps += [snap(str(i), total_pair(str(i), 1.25, 3.6), fresh) for i in range(2, 15)]
    cands, _ = build_cands(snaps)
    legs, vetoed = sc.select("hockey", cands, [], sc.Rule())
    assert len(legs) == sc.MAX_LEGS and vetoed == []
    assert len({leg["superbet_event_id"] for leg in legs}) == len(legs)
    ev1 = [c for c in cands if c["superbet_event_id"] == "1"]
    best = max(ev1, key=lambda c: c["fair_p"] * c["odds"])
    [chosen] = [leg for leg in legs if leg["superbet_event_id"] == "1"]
    assert chosen["line"] == best["line"]
    assert legs == sorted(legs, key=lambda leg: (leg["kickoff_utc"], leg["match_name"]))
    assert not any(k in leg for leg in legs for k in ("_x", "_p"))


def test_a_tie_at_the_cut_is_decided_by_kickoff_then_id_and_flagged() -> None:
    fresh = AT - timedelta(minutes=5)
    snaps = [
        snap(
            str(i),
            total_pair(str(i), 1.20, 4.20),
            fresh,
            kickoff=AT + timedelta(hours=6 - i),
        )  # later id, earlier kickoff
        for i in range(1, 4)
    ]
    cands, _ = build_cands(snaps)
    legs, _ = sc.select("hockey", cands, [], sc.Rule(max_legs=2))
    assert sorted(leg["superbet_event_id"] for leg in legs) == ["2", "3"]
    assert all(leg.get("tie_at_cut") for leg in legs)
    again, _ = sc.select("hockey", list(reversed(cands)), [], sc.Rule(max_legs=2))
    assert [x["superbet_event_id"] for x in again] == [
        x["superbet_event_id"] for x in legs
    ]


def test_vetoes_remove_what_they_name_and_report_what_matched_nothing() -> None:
    fresh = AT - timedelta(minutes=5)
    lines = [
        *total_pair("1", 1.20, 4.20, 5.5),
        *total_pair("1", 1.22, 4.00, 6.5),
        hline("1", 630, "winner", "T1", 1.22, None),
        hline("1", 630, "winner", "T2", 4.00, None),
    ]
    cands, _ = build_cands([snap("1", lines, fresh)])
    legs, vetoed = sc.select("hockey", cands, [{"superbet_event_id": "1"}], sc.Rule())
    assert legs == [] and len(vetoed) == len(cands)
    by_line = [{"superbet_event_id": "1", "family": "total", "line": 5.5}]
    legs, vetoed = sc.select("hockey", cands, by_line, sc.Rule())
    assert {v["line"] for v in vetoed} == {5.5}
    assert legs[0]["line"] != 5.5
    wrong = [
        {"superbet_event_id": "999", "reason": "x"},
        {"superbet_event_id": "1", "family": "handicap"},
    ]
    spent = [{"superbet_event_id": "7", "reason": "started since"}]
    assert sc.unmatched_vetoes(wrong + spent, cands, {"1", "7"}) == wrong


# --- the day's window, and what a rebuild keeps ---------------------------------------


def test_the_day_runs_to_six_in_the_morning_warsaw_and_reads_d_plus_1(
    tmp_path: Path,
) -> None:
    night = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)  # 01:30 Warsaw
    morning = datetime(2026, 10, 1, 5, 0, tzinfo=UTC)  # 07:00 Warsaw: tomorrow's
    write_snaps(tmp_path, "hockey", DATE, [snap("1", total_pair("1", 1.20, 4.20), AT)])
    write_snaps(
        tmp_path,
        "hockey",
        "2026-10-01",
        [
            snap("2", total_pair("2", 1.20, 4.20), AT, kickoff=night),
            snap("3", total_pair("3", 1.20, 4.20), AT, kickoff=morning),
        ],
    )
    events, read = sc.day_events(str(tmp_path), "hockey", DATE)
    assert read == 3
    counts: dict[str, int] = {}
    cands = sc.candidates(
        "hockey", events, AT, sc.Rule(), counts, until=sc.day_end(DATE)
    )
    got = {(c["superbet_event_id"], c["source_date"]) for c in cands}
    assert got == {("1", DATE), ("2", "2026-10-01")}
    assert counts["after_day_end"] == 1
    assert sc.day_end(DATE) == datetime(2026, 10, 1, 4, 0, tzinfo=UTC)  # CEST


def test_a_started_leg_stays_on_a_rebuilt_coupon() -> None:
    printed = {
        "legs": [
            {
                **hline("1", 623, "total", "OVER", 1.2, 5.5),
                "fair_p": 0.78,
                "kickoff_utc": iso(AT - timedelta(minutes=30)),
                "match_name": "a",
            },
            {
                **hline("2", 623, "total", "OVER", 1.2, 5.5),
                "fair_p": 0.78,
                "kickoff_utc": iso(AT + timedelta(hours=3)),
                "match_name": "b",
            },
        ]
    }
    locked = sc.locked_legs(printed, AT)
    assert [leg["superbet_event_id"] for leg in locked] == ["1"] and locked[0]["locked"]
    fresh = AT - timedelta(minutes=5)
    cands, _ = build_cands(
        [snap(str(i), total_pair(str(i), 1.20, 4.20), fresh) for i in range(2, 6)]
    )
    legs, _ = sc.select("hockey", cands, [], sc.Rule(max_legs=3), locked)
    assert len(legs) == 3 and legs[0]["superbet_event_id"] == "1"
    assert sum(1 for leg in legs if leg.get("locked")) == 1


# --- grading --------------------------------------------------------------------------


def hockey_event(state: str = "SETTLED", **kw: Any) -> dict[str, Any]:
    return {
        "state": state,
        "t1_periods": [1, 2, 1],
        "t2_periods": [0, 1, 1],
        "t1_full": 4,
        "t2_full": 2,
        "overtime": False,
        "graded": [],
        **kw,
    }


def leg(side: str = "OVER", line: float | None = 5.5, **kw: Any) -> dict[str, Any]:
    return {
        **hline("1", 623, "total", side, 1.30, line),
        "fair_p": 0.75,
        "team1": "A",
        "team2": "B",
        "kickoff_utc": iso(AT),
        **kw,
    }


def coupon(*legs: dict[str, Any], sport: str = "hockey") -> dict[str, Any]:
    return {"sport": sport, "date": DATE, "legs": list(legs)}


def test_a_leg_is_graded_from_the_result_even_when_its_line_was_taken_down() -> None:
    # 4-2: six goals. The 5.5 line is not among the measurement's graded rows
    # (Superbet recentred the ladder before the start) - it is still graded.
    [g] = sc.grade_coupon(coupon(leg()), {DATE: {"events": {"1": hockey_event()}}})
    assert g["outcome"] == "WIN" and g["odds"] == 1.30
    assert sc.summarize([g])["roi"] == pytest.approx(0.30)
    [g] = sc.grade_coupon(
        coupon(leg(line=6.0)), {DATE: {"events": {"1": hockey_event()}}}
    )
    assert g["outcome"] == "VOID"  # a push


def test_a_disagreement_with_the_measurements_own_grade_is_a_mismatch() -> None:
    measured = [{**hline("1", 623, "total", "OVER", 1.2, 5.5), "outcome": "LOSS"}]
    ev = hockey_event(graded=measured)
    [g] = sc.grade_coupon(coupon(leg()), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "MISMATCH"
    assert sc.summarize([g]) == {"n": 0}


def test_states_other_than_settled_are_named_not_guessed() -> None:
    cases = {
        None: "PENDING",
        "VOID": "VOID",
        "GAVE_UP": "NOT_GRADED:GAVE_UP",
        "NOT_ON_SOFASCORE": "PENDING:NOT_ON_SOFASCORE",
    }
    for state, want in cases.items():
        events = {} if state is None else {"1": {"state": state}}
        [g] = sc.grade_coupon(coupon(leg()), {DATE: {"events": events}})
        assert g["outcome"] == want


def test_a_leg_settles_in_the_file_of_its_source_date() -> None:
    night = leg(source_date="2026-10-01")
    settled = {DATE: {"events": {}}, "2026-10-01": {"events": {"1": hockey_event()}}}
    [g] = sc.grade_coupon(coupon(night), settled)
    assert g["outcome"] == "WIN"


def test_a_shootout_winner_is_never_read_from_the_score() -> None:
    ev = hockey_event(
        t1_periods=[1, 1, 0],
        t2_periods=[0, 1, 1],
        t1_full=2,
        t2_full=2,
        overtime=True,
        status="AP",
    )
    win = {**leg(side="T1", line=None), "market_id": 630, "family": "winner"}
    [g] = sc.grade_coupon(coupon(win), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "UNGRADEABLE"
    ev["winner"] = "T1"
    [g] = sc.grade_coupon(coupon(win), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "WIN"


def test_an_unclear_orientation_grades_only_orientation_free_legs() -> None:
    ev = hockey_event(orientation_unclear=True)
    handicap = {**leg(side="T1", line=-1.5), "market_id": 604, "family": "handicap"}
    [t, h] = sc.grade_coupon(coupon(leg(), handicap), {DATE: {"events": {"1": ev}}})
    assert (t["outcome"], h["outcome"]) == ("WIN", "UNGRADEABLE")


def test_a_cs2_leg_is_graded_from_the_stored_maps() -> None:
    cleg = {
        **cs2.Cs2Line("1", "maps_handicap", 0, "", -1.5, "T1", 1.9).as_dict(),
        "fair_p": 0.7,
        "team1": "A",
        "team2": "B",
        "kickoff_utc": iso(AT),
    }
    ev = {"state": "SETTLED", "maps": [[13, 7], [13, 10]], "graded": []}
    [g] = sc.grade_coupon(coupon(cleg, sport="cs2"), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "WIN"  # 2-0 covers -1.5


def test_rule_history_chooses_before_the_outcome_and_keeps_a_push_void(
    tmp_path: Path,
) -> None:
    d = write_snaps(
        tmp_path,
        "hockey",
        "2026-09-29",
        [
            snap(
                "1",
                [*total_pair("1", 1.20, 4.20, 6.0), *total_pair("1", 1.12, 5.0, 3.5)],
                AT - timedelta(days=1, hours=1),
                kickoff=AT - timedelta(days=1),
            )
        ],
    )
    # 4-2 = 6 goals: the rule's pick (the cheaper 6.0 line) pushes. Choosing
    # among the measurement's graded rows would take the 3.5 line and win.
    settled = {"date": "2026-09-29", "events": {"1": hockey_event()}}
    (d / "settled.json").write_text(json.dumps(settled), encoding="utf-8")
    h = sc.rule_history(str(tmp_path), "hockey", ["2026-09-29"], sc.Rule())
    assert h["n"] == 0 and h["void"] == 1 and h["days"] == ["2026-09-29"]


# --- labels ---------------------------------------------------------------------------


def test_every_market_family_has_a_polish_label() -> None:
    for sport, table in shadow.MARKETS.items():
        assert {s.family for s in table.values()} <= set(sc.FAMILY_PL[sport]), sport
    team_level = {f for f in cs2.FAMILIES if not f.startswith("player_")}
    assert team_level <= set(sc.FAMILY_PL["cs2"])


def test_describe_names_the_team_and_the_handicap_from_its_own_side() -> None:
    base = {"team1": "Kladno", "team2": "Trinec", "subject": "", "period": 0}
    hcp_t2 = {**base, "family": "handicap", "side": "T2", "line": -1.5}
    assert sc.describe("hockey", hcp_t2).endswith("Trinec (+1.5)")
    tt = {
        **base,
        "family": "period_team_total",
        "side": "UNDER",
        "line": 1.5,
        "subject": "T1",
        "period": 2,
    }
    assert (
        sc.describe("hockey", tt)
        == "Kladno - 2. tercja - liczba goli drużyny: poniżej 1.5"
    )
    cs = {
        "team1": "NiP",
        "team2": "BIG",
        "subject": "",
        "family": "map_winner",
        "map_nr": 2,
        "side": "T2",
        "line": None,
    }
    assert sc.describe("cs2", cs) == "2. mapa - zwycięzca mapy: BIG"
    draw = {**base, "family": "result_1x2", "side": "DRAW", "line": None}
    assert sc.describe("hockey", draw) == "1X2 (czas podstawowy): remis"
    exact = {**base, "family": "exact_sets", "side": "3:1", "line": None}
    assert sc.describe("volleyball", exact).endswith("Kladno 3:1 Trinec")
    odd = {**base, "family": "odd_even", "side": "ODD", "line": None}
    assert sc.describe("basketball", odd).endswith(": nieparzysta")


def test_files_live_beside_the_measurement_never_in_the_coupon_day(
    tmp_path: Path,
) -> None:
    for sport in sc.SPORT_KEYS:
        d = sc.day_dir(str(tmp_path), sport, DATE)
        assert d != tmp_path / DATE
        assert d.parent.name in ("cs2", sport)
        assert sc.pdf_name(sport, DATE) != f"KUPON_{DATE}.pdf"


# --- the scripts end to end -----------------------------------------------------------


def run_build(monkeypatch: pytest.MonkeyPatch, root: Path, at: datetime) -> int:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(root))
    monkeypatch.setattr(run_sport_coupon, "now", lambda: at)
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE, "--sport", "hockey"])
    return run_sport_coupon.main()


def test_build_writes_singles_only_keeps_started_legs_and_settles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                str(i),
                total_pair(str(i), 1.20, 4.20),
                AT - timedelta(minutes=5),
                kickoff=AT + timedelta(hours=1 + i),
            )
            for i in range(3)
        ],
    )
    (d / sc.VETOES_FILE).write_text(
        json.dumps({"vetoes": [{"superbet_event_id": "0", "reason": "lineup"}]}),
        encoding="utf-8",
    )
    assert run_build(monkeypatch, tmp_path, AT) == 0
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert doc["not_the_coupon"] is True and doc["UNFITTED_CONSTANTS"]
    assert [leg["superbet_event_id"] for leg in doc["legs"]] == ["1", "2"]
    assert [v["veto"] for v in doc["vetoed"]] == ["lineup"]
    text = json.dumps(doc)
    assert "odds_if_product" not in text and "combined" not in text
    assert (d / sc.pdf_name("hockey", DATE)).exists()
    assert not (tmp_path / DATE).exists()

    # two hours later event 1 has started: a rebuild keeps it as printed,
    # and event 2 is re-priced
    later = AT + timedelta(hours=2)
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                "2",
                total_pair("2", 1.25, 3.80),
                later - timedelta(minutes=5),
                kickoff=AT + timedelta(hours=3),
            )
        ],
    )
    assert run_build(monkeypatch, tmp_path, later) == 0
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    by = {leg["superbet_event_id"]: leg for leg in doc["legs"]}
    assert by["1"]["locked"] and by["1"]["odds"] == 1.20
    assert by["2"]["odds"] == 1.25
    builds = (d / sc.BUILDS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(builds) == 2

    (d / "settled.json").write_text(
        json.dumps({"events": {"1": hockey_event(), "2": {"state": "VOID"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv", ["x", "--from", DATE, "--to", DATE, "--sport", "hockey"]
    )
    assert settle_sport_coupon.main() == 0
    out = json.loads((d / settle_sport_coupon.SETTLED_OUT).read_text(encoding="utf-8"))
    assert {g["superbet_event_id"]: g["outcome"] for g in out["legs"]} == {
        "1": "WIN",
        "2": "VOID",
    }


def test_a_closed_day_is_never_rebuilt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_build(monkeypatch, tmp_path, sc.day_end(DATE)) == 2
    assert not sc.day_dir(str(tmp_path), "hockey", DATE).exists()


def test_a_failed_pdf_leaves_the_previous_json_and_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    assert run_build(monkeypatch, tmp_path, AT) == 0
    d = sc.day_dir(str(tmp_path), "hockey", DATE)
    before = (
        (d / sc.COUPON_FILE).read_bytes(),
        (d / sc.pdf_name("hockey", DATE)).read_bytes(),
    )

    def boom(doc: dict[str, Any], path: Path) -> None:
        path.write_bytes(b"half")
        raise RuntimeError("render")

    monkeypatch.setattr(run_sport_coupon, "render_pdf", boom)
    assert run_build(monkeypatch, tmp_path, AT + timedelta(minutes=1)) == 2
    after = (
        (d / sc.COUPON_FILE).read_bytes(),
        (d / sc.pdf_name("hockey", DATE)).read_bytes(),
    )
    assert after == before


def test_a_torn_build_log_line_is_repaired_before_the_next_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5),
              kickoff=AT + timedelta(hours=2))],
    )
    assert run_build(monkeypatch, tmp_path, AT) == 0
    with (d / sc.BUILDS_FILE).open("a", encoding="utf-8") as fh:
        fh.write('{"created_at_utc": "torn')  # a crash mid-append
    assert run_build(monkeypatch, tmp_path, AT + timedelta(minutes=10)) == 0
    lines = (d / sc.BUILDS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["legs"] and json.loads(lines[2])["legs"]
