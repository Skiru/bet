"""bet.sofa.slip_builder and scripts/sofa/build_slip.py: a chat slip to a
target price from the day's coupon - fewest legs, one per match, each leg on
its own statistics (min(confidence, 1/odds for a price_gap leg)), one search
over every leg, "say no first" (the operator 2026-10-31 removed the families
on the plus)."""

from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import slip_builder as sb
from scripts.sofa import build_slip

NOW = datetime.datetime(2026, 10, 20, 8, 0, tzinfo=datetime.UTC)
LATER = "2026-10-20T18:00:00Z"


def _leg(
    eid: int,
    odds: float,
    conf: float,
    market: str = "corners_total",
    direction: str = "OVER",
    kickoff: str = LATER,
    line: float = 7.5,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "group_key": f"sofa:{eid}",
        "sport": "football",
        "market": market,
        "direction": direction,
        "line": line,
        "offered_odds": odds,
        "confidence": conf,
        "kickoff_utc": kickoff,
        "match": f"A{eid} - B{eid}",
        "superbet_market": "Liczba rzutów rożnych",
        "superbet_selection": f"powyżej {line}",
        **extra,
    }


def test_measured_chance_is_the_legs_own_confidence() -> None:
    """Operator 2026-10-31: no family, sport or tier shortfall - the leg's
    confidence (it carries the line evidence) is its measured chance, even
    within `price_gap.GAP` of its price."""
    chance, source = sb.measured_chance(
        _leg(1, 1.25, 0.82, market="goals_total", direction="UNDER"), 1.25)
    assert chance == pytest.approx(0.82) and source == "pewność"
    tennis = dict(_leg(2, 1.25, 0.6), sport="tennis")
    assert sb.measured_chance(tennis, 1.25) == (pytest.approx(0.6), "pewność")


def test_price_gap_leg_is_read_at_its_price_and_confidence_bounds_from_above() -> None:
    leg = _leg(1, 1.25, 0.95, price_gap={"flag": "CONFIDENCE_ABOVE_PRICE"})
    chance, source = sb.measured_chance(leg, 1.25)
    assert chance == pytest.approx(0.80) and source == "cena (price_gap)"
    low = _leg(2, 1.25, 0.70, price_gap={"flag": "CONFIDENCE_ABOVE_PRICE"})
    assert sb.measured_chance(low, 1.25) == (pytest.approx(0.70), "pewność")


def test_any_sport_leg_above_its_price_is_read_at_its_price() -> None:
    """2026-10-31 smoke: unflagged volleyball set handicaps at 82% against
    57% at the price topped a ~3 slip; a measured sport carries no
    `price_gap`, so the gap itself caps it."""
    vb = dict(_leg(1, 1.75, 0.82, market="set_handicap"), sport="volleyball")
    chance, source = sb.measured_chance(vb, 1.75)
    assert chance == pytest.approx(1 / 1.75)
    assert source == "cena (pewność ponad cenę)"
    near = dict(_leg(2, 1.75, 0.59, market="set_handicap"), sport="hockey")
    assert sb.measured_chance(near, 1.75) == (pytest.approx(0.59), "pewność")


def test_no_family_record_is_left() -> None:
    import importlib.util

    assert importlib.util.find_spec("bet.sofa.family_record") is None
    for name in ("shortfalls", "tier", "family_text", "TIER_SHORTFALL",
                 "TIER_NAMES", "TIER_REST"):
        assert not hasattr(sb, name), name


def test_fewer_longer_legs_win_at_the_same_target() -> None:
    short = [_leg(i, 1.25, 0.80) for i in range(1, 7)]  # x = 1.00
    long_ = [_leg(i, 1.50, 0.70) for i in range(11, 14)]  # x = 1.05
    res = sb.build(short + long_, NOW, target=2.2)
    (slip,) = res.slips
    assert len(slip.legs) == 2
    assert all(x.odds == 1.50 for x in slip.legs)
    assert slip.price_product >= 2.2


def test_one_leg_per_match_and_disjoint_slips() -> None:
    legs = [_leg(i, 1.5, 0.7, line=line) for i in range(1, 7) for line in (6.5, 7.5)]
    res = sb.build(legs, NOW, target=2.2, slips=3)
    keys = [x.match_key for s in res.slips for x in s.legs]
    assert len(res.slips) == 3 and len(keys) == len(set(keys))


def test_started_and_out_of_band_legs_are_refused() -> None:
    soon = (NOW + datetime.timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    legs = [_leg(1, 1.5, 0.7, kickoff=soon), _leg(2, 3.5, 0.3), _leg(3, 1.5, 0.7)]
    pool, refused = sb.candidates(legs, NOW)
    assert [x.leg["sofascore_event_id"] for x in pool] == [3]
    assert refused == {"rozpoczęty lub za chwilę": 1, "kurs poza przedziałem": 1}


def test_say_no_first_counts_the_slips_found_never_families() -> None:
    """The first line says how many of the requested slips the day's legs
    give; no family on the plus is counted (operator 2026-10-31)."""
    one = [_leg(1, 1.5, 0.7, market="goals_total", direction="UNDER")]
    res = sb.build(one, NOW, target=2.2)
    assert res.slips == [] and res.candidates == 1
    text = sb.render(res, day="2026-10-20", target=2.2, now=NOW)
    assert text.startswith("**Dziś żadnego kuponu na ~2.2** (iloczyn kursów "
                           "najlepszych nóg sięga ~1.50")
    legs = [_leg(i, 1.5, 0.7, market="goals_total", direction="UNDER")
            for i in range(1, 4)]
    res = sb.build(legs, NOW, target=2.2, slips=2)
    assert len(res.slips) == 1
    text = sb.render(res, day="2026-10-20", target=2.2, now=NOW)
    assert text.startswith("**Dzień cienki - masz 1 z 2 kuponów na ~2.2**")
    assert "rodzin" not in text and "poparci" not in text
    assert "Nogi w puli: 3" in text


def test_render_names_superbet_words_and_never_a_slip_price() -> None:
    res = sb.build([_leg(1, 1.5, 0.69), _leg(2, 1.5, 0.69)], NOW, target=2.2)
    text = sb.render(res, day="2026-10-20", target=2.2, now=NOW)
    assert text.startswith("**Dzień daje 1 z 1")
    assert "Liczba rzutów rożnych: powyżej 7.5" in text
    assert "sprawdź na ekranie Superbetu" in text
    assert "Cel ~2.2 osiągnięty" in text and "2.25" not in text
    assert "2 nogi" in text
    # each leg at its own confidence (0.69 within GAP of 1/1.5)
    assert math.isclose(res.slips[0].chance, 0.69**2)
    assert "rodzin" not in text and "| grupa |" not in text


def test_script_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    day = "2026-10-20"
    assert (
        build_slip.main(
            [
                "--date",
                day,
                "--target",
                "2",
                "--runs-dir",
                str(tmp_path),
            ]
        )
        == 2
    )
    run = tmp_path / day
    run.mkdir()
    (run / "11_coupon.json").write_text(
        json.dumps(
            {
                "singles": [
                    _leg(1, 1.5, 0.7, kickoff="2099-01-01T00:00:00Z"),
                    _leg(2, 1.5, 0.7, kickoff="2099-01-01T00:00:00Z"),
                ]
            }
        ),
        encoding="utf-8",
    )
    assert (
        build_slip.main(
            [
                "--date",
                day,
                "--target",
                "2",
                "--runs-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert (
        build_slip.main(
            [
                "--date",
                day,
                "--target",
                "2",
                "--slips",
                "2",
                "--runs-dir",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert "Dzień cienki - masz 1 z 2" in capsys.readouterr().out


def test_kickoff_window_is_local_time_and_half_open() -> None:
    lo, hi = build_slip.window("2026-10-20", "10:00", "12:00") or (NOW, NOW)
    assert lo == datetime.datetime(2026, 10, 20, 8, 0, tzinfo=datetime.UTC)
    assert hi == datetime.datetime(2026, 10, 20, 10, 0, tzinfo=datetime.UTC)
    assert build_slip.window("2026-10-20", None, None) is None
    early = datetime.datetime(2026, 10, 20, 7, 0, tzinfo=datetime.UTC)
    legs = [
        _leg(1, 1.5, 0.7, kickoff="2026-10-20T08:00:00Z"),
        _leg(2, 1.5, 0.7, kickoff="2026-10-20T10:00:00Z"),
    ]
    pool, refused = sb.candidates(legs, early, window=(lo, hi))
    assert [x.leg["sofascore_event_id"] for x in pool] == [1]
    assert refused == {"start poza oknem": 1}


def test_competition_filter_keeps_only_named_competitions() -> None:
    legs = [
        _leg(1, 1.5, 0.7, competition="UEFA Champions League"),
        _leg(2, 1.5, 0.7, competition="League One"),
        _leg(3, 1.5, 0.7),
    ]
    pool, refused = sb.candidates(legs, NOW, competitions=["champions league"])
    assert [x.leg["sofascore_event_id"] for x in pool] == [1]
    assert refused == {"poza wybranymi rozgrywkami": 2}
    pool, _ = sb.candidates(legs, NOW)
    assert len(pool) == 3


def test_search_is_exact_against_brute_force() -> None:
    import itertools
    import random

    rnd = random.Random(5)
    for _ in range(300):
        legs = [
            sb.Leg(
                _leg(m, 1.0, 0.0),
                round(rnd.uniform(1.10, 2.00), 2),
                rnd.uniform(0.45, 0.88),
                "t",
            )
            for m in range(1, 9)
            for _ in range(rnd.randint(1, 3))
        ]
        legs = [
            sb.Leg(dict(x.leg, line=i), x.odds, min(x.chance, 1 / x.odds), "t")
            for i, x in enumerate(legs)
        ]
        target = rnd.uniform(1.8, 5.0)
        best = None
        for k in range(1, 5):
            for combo in itertools.combinations(legs, k):
                if len({x.match_key for x in combo}) < k:
                    continue
                # the only miss allowed: a combo inside the target's own STEP band
                if sum(math.log(x.odds) for x in combo) < math.log(target) + sb.STEP:
                    continue
                score = sum(math.log(x.chance) for x in combo)
                best = score if best is None else max(best, score)
        got = sb.best_slip(legs, target, max_legs=4)
        if best is None:
            continue
        assert got is not None
        assert got.price_product >= target
        assert len({x.match_key for x in got.legs}) == len(got.legs)
        assert math.log(got.chance) >= best - 1e-9


def test_a_refused_read_drops_the_leg_and_the_next_best_takes_its_place() -> None:
    from bet.sofa.contracts import LegRead

    legs = [_leg(1, 1.6, 0.66), _leg(2, 1.55, 0.68), _leg(3, 1.5, 0.70)]
    first = sb.build(legs, NOW, target=2.3)
    chosen = {x.leg["sofascore_event_id"] for x in first.slips[0].legs}
    assert all(x.read == sb.READ_NONE for x in first.slips[0].legs)
    out = min(chosen)
    reads = [
        LegRead(
            sofascore_event_id=out,
            market="corners_total",
            subject="",
            line=7.5,
            direction="OVER",
            verdict="WATCH",
            author="analyst",
            reason="test",
        ),
        LegRead(
            sofascore_event_id=max(chosen),
            market="corners_total",
            subject="",
            line=7.5,
            direction="OVER",
            verdict="KEEP",
            author="analyst",
            reason="test",
        ),
    ]
    second = sb.build(legs, NOW, target=2.3, reads=reads[:1], slip_reads=reads[1:])
    again = {x.leg["sofascore_event_id"]: x.read for x in second.slips[0].legs}
    assert out not in again and again[max(chosen)] == sb.READ_KEEP
    assert second.refused["odrzucona przez analityka (WATCH / NO_BET / weto)"] == 1
    carried = [dict(legs[0], reads=[{"verdict": "NO_BET", "author": "verifier"}])]
    assert sb.read_status(carried[0]) is None


def test_reserve_slips_and_the_slip_read_set(tmp_path: Path) -> None:
    legs = [_leg(i, 1.5, 0.7) for i in range(1, 7)]
    res = sb.build(legs, NOW, target=2.2, reserve=1)
    assert len(res.slips) == 1 and len(res.reserve) == 1
    keys = [x.match_key for s in res.slips + res.reserve for x in s.legs]
    assert len(keys) == len(set(keys)) == 4
    written = build_slip.write_read_set(tmp_path, res)
    assert written == {"football": 4}
    rows = json.loads((tmp_path / "read_set_slip_football.json").read_text())
    assert sorted(r["in_set"] for r in rows) == ["slip"] * 2 + ["slip_reserve"] * 2
    assert rows[0]["superbet_market"] == "Liczba rzutów rożnych"
    text = sb.render(res, day="2026-10-20", target=2.2, now=NOW)
    assert "Nieczytane nogi w kuponach: 2" in text and "Zapas do czytania" in text


def test_a_slip_exactly_at_the_target_is_found() -> None:
    legs = [sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.45, "t") for i in (1, 2)]
    got = sb.best_slip(legs, 4.0)
    assert got is not None and got.price_product == pytest.approx(4.0)


def test_a_slip_at_the_target_is_not_lost_to_one_just_below_it() -> None:
    # 1.25 x 1.6 x 2.0 = 4 exactly; 2.0 x 1.11 x 1.82 = 4.04 is the runner-up
    # (review 4: the exact-target state shared a bucket with a richer one
    # just under the target and was dropped)
    spec = [(1.25, 0.79), (1.6, 0.60), (2.0, 0.48), (1.11, 0.88), (1.82, 0.53)]
    spec.append((1.98, 0.49))
    legs = [
        sb.Leg(_leg(i, o, c), o, c, "t") for i, (o, c) in enumerate(spec)
    ]
    got = sb.best_slip(legs, 4.0, 3)
    assert got is not None
    assert sorted(x.odds for x in got.legs) == [1.25, 1.6, 2.0]
    one = [
        sb.Leg(_leg(1, 2.0, 0.4), 2.0, 0.4, "t"),
        sb.Leg(_leg(2, 1.99995, 0.45), 1.99995, 0.45, "t"),
    ]
    got = sb.best_slip(one, 2.0, 1)
    assert got is not None and got.legs[0].odds == 2.0


def test_round_targets_with_two_decimal_odds_are_exact() -> None:
    import itertools
    import random

    rnd = random.Random(11)
    grid = [1.10, 1.11, 1.2, 1.25, 1.3, 1.4, 1.5, 1.6, 1.8, 1.82, 1.9, 2.0]
    for _ in range(300):
        legs = [
            sb.Leg(
                _leg(m, 1.0, 0.0, line=i),
                o,
                min(rnd.uniform(0.45, 0.9), 1 / o),
                "t",
            )
            for i, (m, o) in enumerate(
                (m, rnd.choice(grid))
                for m in range(1, 8)
                for _ in range(rnd.randint(1, 2))
            )
        ]
        target = float(rnd.choice([2, 2.5, 3, 4, 5]))
        best = None
        for k in range(1, 4):
            for combo in itertools.combinations(legs, k):
                if len({x.match_key for x in combo}) < k:
                    continue
                if math.prod(x.odds for x in combo) < target - 1e-9:
                    continue
                score = sum(math.log(x.chance) for x in combo)
                best = score if best is None else max(best, score)
        got = sb.best_slip(legs, target, max_legs=3)
        if best is None:
            assert got is None
            continue
        assert got is not None and math.log(got.chance) >= best - 1e-9


def test_a_leg_with_a_non_finite_confidence_is_refused() -> None:
    legs = [_leg(1, 1.5, float("nan")), _leg(2, 1.5, 0.7), _leg(3, 1.5, None)]
    got, refused = sb.candidates(legs, NOW)
    assert [x.leg["sofascore_event_id"] for x in got] == [2]
    assert refused["brak ceny lub pewności"] == 2


def test_one_family_slip_is_named_never_gated() -> None:
    legs = [sb.Leg(_leg(i, 1.6, 0.6), 1.6, 0.55, "t") for i in (1, 2, 3)]
    slip = sb.Slip(legs)
    assert sb.concentration(slip) == ("football|corners_total|OVER", 3)
    mixed = sb.Slip(
        [
            legs[0],
            sb.Leg(_leg(4, 1.6, 0.6, direction="UNDER"), 1.6, 0.55, "t"),
        ]
    )
    assert sb.concentration(mixed) is None
    assert sb.concentration(sb.Slip(legs[:2])) == ("football|corners_total|OVER", 2)
    result = sb.Result([slip], 1, 3)
    text = sb.render(result, day="2026-10-20", target=4, now=NOW)
    assert "3 z 3 nóg jednego rynku (football|corners_total|OVER)" in text


def test_an_earlier_requests_slip_keep_shows_its_time(tmp_path: Path) -> None:
    from scripts.sofa import merge_reads

    run = tmp_path / "2026-10-20"
    run.mkdir()
    read = {
        "sofascore_event_id": 1,
        "market": "corners_total",
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "verdict": "KEEP",
        "author": "analyst",
        "reason": "test",
    }
    report = tmp_path / "r.md"
    report.write_text("```json reads\n" + json.dumps([read]) + "\n```\n")
    assert merge_reads.merge(run, [report], "analyst", False, slip=True) == 0
    assert merge_reads.merge(run, [report], "analyst", False, slip=True) == 0
    stored = json.loads((run / merge_reads.SLIP_READS).read_text())
    assert len(stored) == 1 and stored[0]["read_at_utc"]  # the latest replaced
    keep = [
        _read(1, 7.5, "KEEP").model_copy(
            update={"read_at_utc": "2026-10-20T08:00:00+00:00"}
        )
    ]
    leg = _leg(1, 1.5, 0.7)
    at = datetime.datetime(2026, 10, 20, 10, 0, tzinfo=datetime.UTC)
    assert sb.read_status(leg, slip_reads=keep, now=at) == sb.READ_KEEP
    later = at + datetime.timedelta(hours=8)
    assert sb.read_status(leg, slip_reads=keep, now=later) == "KEEP (10:00)"
    assert (
        sb.read_status(leg, slip_reads=[_read(1, 7.5, "KEEP")], now=later)
        == sb.READ_KEEP
    )


def test_window_parsing_midnight_and_the_next_day() -> None:
    utc = datetime.UTC
    lo, hi = build_slip.window("2026-10-20", "20", "24") or (NOW, NOW)
    assert (lo, hi) == (
        datetime.datetime(2026, 10, 20, 18, 0, tzinfo=utc),
        datetime.datetime(2026, 10, 20, 22, 0, tzinfo=utc),
    )
    lo, hi = build_slip.window("2026-10-20", "22:00", "2:00") or (NOW, NOW)
    assert hi == datetime.datetime(2026, 10, 21, 0, 0, tzinfo=utc)
    late = datetime.datetime(2026, 10, 20, 23, 30, tzinfo=utc)  # 01:30 local, 10-21
    lo, hi = build_slip.window("2026-10-20", "2", "4", late) or (NOW, NOW)
    assert lo == datetime.datetime(2026, 10, 21, 0, 0, tzinfo=utc)
    for bad in ("25", "9:61", "x"):
        with pytest.raises(ValueError):
            build_slip.window("2026-10-20", bad, "12")


def test_script_refuses_bad_arguments_and_reads_no_family_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    day = "2026-10-20"
    base = ["--date", day, "--target", "2", "--runs-dir", str(tmp_path)]
    for extra in (
        ["--reserve", "-1"],
        ["--min-odds", "2", "--max-odds", "1.5"],
        ["--start-from", "25", "--start-to", "12"],
    ):
        with pytest.raises(SystemExit) as exc:
            build_slip.main(base + extra)
        assert exc.value.code == 2
    run = tmp_path / day
    run.mkdir()
    (run / "11_coupon.json").write_text(json.dumps({"singles": []}), encoding="utf-8")
    # no family_record.json is needed, and the old flags are accepted no-ops
    # (a session that loaded the old /kupon contract still runs)
    assert build_slip.main(
        base + ["--any-family", "--allow-rest", "--no-refresh-record"]) == 1
    out = capsys.readouterr()
    assert out.out.startswith("**Dziś żadnego kuponu na ~2**")
    assert "family_record" not in out.err
    assert sorted(p.name for p in run.iterdir()) == ["11_coupon.json"]


def test_a_leg_without_a_fixture_id_is_counted_not_fatal() -> None:
    bare = dict(_leg(1, 1.5, 0.7))
    del bare["sofascore_event_id"]
    pool, refused = sb.candidates([bare, _leg(2, 1.5, 0.7)], NOW)
    assert len(pool) == 1 and refused == {"brak id meczu": 1}


def test_stale_prices_are_flagged_by_the_pipelines_own_limits() -> None:
    old = (NOW - datetime.timedelta(minutes=50)).isoformat().replace("+00:00", "Z")
    fresh = (NOW - datetime.timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    legs = [
        _leg(1, 1.5, 0.7, price_fetched_at_utc=old),
        _leg(2, 1.5, 0.7, price_fetched_at_utc=fresh),
        dict(_leg(3, 1.5, 0.7, price_fetched_at_utc=old), sport="hockey"),
    ]
    pool, _ = sb.candidates(legs, NOW)
    stale = {x.leg["sofascore_event_id"]: x.stale for x in pool}
    assert stale == {1: True, 2: False, 3: False}  # hockey: 3 h
    res = sb.build(legs[:2], NOW, target=2.2)
    text = sb.render(
        res,
        day="2026-10-20",
        target=2.2,
        now=NOW,
        built_at="2026-10-20T07:00:00Z",
    )
    assert "Cena starsza niż limit pipeline'u: 1 noga" in text
    assert "zbudowany 20.10 09:00" in text and "| 20.10 20:00 |" in text


def test_merge_reads_slip_goes_to_the_slip_files_only(tmp_path: Path) -> None:
    from scripts.sofa import merge_reads

    run = tmp_path / "2026-10-20"
    run.mkdir()
    report = tmp_path / "r.md"
    read = {
        "sofascore_event_id": 1,
        "market": "corners_total",
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "verdict": "WATCH",
        "author": "analyst",
        "reason": "test",
    }
    report.write_text("```json reads\n" + json.dumps([read]) + "\n```\n")
    assert merge_reads.merge(run, [report], "analyst", False, slip=True) == 0
    assert not (run / "reads.json").exists()
    assert (
        json.loads((run / merge_reads.SLIP_READS).read_text())[0]["verdict"] == "WATCH"
    )


def _read(eid: int, line: float, verdict: str, direction: str = "OVER") -> Any:
    from bet.sofa.contracts import LegRead

    return LegRead(
        sofascore_event_id=eid,
        market="corners_total",
        subject="",
        line=line,
        direction=direction,
        verdict=verdict,
        author="analyst",
        reason="test",
    )


def test_kept_legs_reach_the_target_before_an_unread_leg_enters() -> None:
    # operator 2026-10-21: each round swapped read legs for unread ones
    legs = [_leg(1, 1.5, 0.70), _leg(2, 1.5, 0.70), _leg(3, 1.6, 0.66)]
    first = sb.build(legs, NOW, target=2.2)
    assert {x.leg["sofascore_event_id"] for x in first.slips[0].legs} == {1, 2}
    keep = [_read(1, 7.5, "KEEP"), _read(3, 7.5, "KEEP")]
    kept = sb.build(legs, NOW, target=2.2, slip_reads=keep)
    assert {x.leg["sofascore_event_id"] for x in kept.slips[0].legs} == {1, 3}
    short = sb.build(legs, NOW, target=3.0, slip_reads=keep)
    assert {x.leg["sofascore_event_id"] for x in short.slips[0].legs} == {1, 2, 3}


def test_a_refused_rung_refuses_its_harder_rungs_not_the_easier() -> None:
    watch = [_read(1, 7.5, "WATCH")]
    assert sb.read_status(_leg(1, 1.5, 0.7, line=8.5), watch) is None
    assert sb.read_status(_leg(1, 1.5, 0.7, line=7.5), watch) is None
    assert sb.read_status(_leg(1, 1.3, 0.8, line=6.5), watch) == sb.READ_NONE
    under = [_read(1, 9.5, "NO_BET", "UNDER")]
    assert sb.read_status(_leg(1, 1.5, 0.7, line=8.5, direction="UNDER"), under) is None
    assert sb.read_status(_leg(1, 1.5, 0.7, line=10.5, direction="UNDER"), under) == (
        sb.READ_NONE
    )


def test_the_days_read_is_labelled_apart_from_the_slips_own() -> None:
    keep = [_read(1, 7.5, "KEEP")]
    leg = _leg(1, 1.5, 0.7)
    assert sb.read_status(leg, reads=keep) == sb.READ_KEEP_DAY
    assert sb.read_status(leg, slip_reads=keep) == sb.READ_KEEP
    day = sb.Leg(leg, 1.5, 0.6, "t", sb.READ_KEEP_DAY)
    old = sb.Leg(_leg(2, 1.5, 0.7), 1.5, 0.6, "t", f"{sb.READ_KEEP} (10:42)")
    fresh = sb.Leg(_leg(3, 1.5, 0.7), 1.5, 0.6, "t", sb.READ_KEEP)
    # operator 2026-10-21: a morning or an earlier slip's KEEP is read again
    assert sb.unread_legs([sb.Slip([day, old, fresh])]) == [day, old]


def test_merge_reads_checks_the_slip_read_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.sofa import merge_reads

    run = tmp_path / "2026-10-20"
    run.mkdir()
    rs = tmp_path / "read_set_slip_football.json"
    rs.write_text(json.dumps([_leg(1, 1.5, 0.7), _leg(2, 1.5, 0.7)]))
    report = tmp_path / "r.md"
    typo = _read(3, 7.5, "KEEP").model_dump()
    report.write_text("```json reads\n" + json.dumps([typo]) + "\n```\n")
    assert (
        merge_reads.merge(run, [report], "analyst", True, slip=True, read_sets=[rs])
        == 1
    )
    out = capsys.readouterr().out
    assert "UNMATCHED_READ: 3" in out and out.count("LEG_WITHOUT_READ") == 2
    good = [_read(1, 7.5, "KEEP").model_dump(), _read(2, 7.5, "WATCH").model_dump()]
    report.write_text("```json reads\n" + json.dumps(good) + "\n```\n")
    assert (
        merge_reads.merge(run, [report], "analyst", True, slip=True, read_sets=[rs])
        == 0
    )


def test_a_later_keep_never_erases_a_slip_watch(tmp_path: Path) -> None:
    from scripts.sofa import merge_reads

    run = tmp_path / "2026-10-20"
    run.mkdir()
    base = {
        "sofascore_event_id": 1,
        "market": "corners_total",
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "author": "analyst",
        "reason": "t",
    }
    for verdict in ("WATCH", "KEEP"):
        report = tmp_path / f"{verdict}.md"
        body = json.dumps([{**base, "verdict": verdict}])
        report.write_text("```json reads\n" + body + "\n```\n")
        assert merge_reads.merge(run, [report], "analyst", False, slip=True) == 0
    stored = json.loads((run / merge_reads.SLIP_READS).read_text())
    assert sorted(r["verdict"] for r in stored) == ["KEEP", "WATCH"]
    from bet.sofa.veto import load_reads

    assert (
        sb.read_status(
            _leg(1, 1.5, 0.7), slip_reads=load_reads(run / merge_reads.SLIP_READS)
        )
        is None
    )


def test_read_legs_are_kept_over_unread_ones_on_a_hair_of_chance() -> None:
    read = [
        sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.4884, "t", sb.READ_KEEP)
        for i in (1, 2)
    ]
    unread = [sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.4887, "t") for i in (3, 4)]
    got = sb.best_slip(read + unread, 4.0, 2)
    assert got is not None
    assert {x.leg["sofascore_event_id"] for x in got.legs} == {1, 2}
    clearly = [sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.52, "t") for i in (3, 4)]
    got = sb.best_slip(read + clearly, 4.0, 2)
    assert got is not None
    assert {x.leg["sofascore_event_id"] for x in got.legs} == {3, 4}


def test_every_leg_is_searched_in_one_pass() -> None:
    """Operator 2026-10-31: no preference by market family - the leg with
    the better chance of its own wins its slot."""
    singles = [
        _leg(1, 2.0, 0.40),
        _leg(2, 2.0, 0.60, market="goals_total", direction="UNDER"),
    ]
    one = sb.build(singles, NOW, 1.9)
    assert [x.leg["sofascore_event_id"] for x in one.slips[0].legs] == [2]
    assert one.candidates == 2
    text = sb.render(one, day="2026-10-20", target=1.9, now=NOW)
    assert text.startswith("**Dzień daje 1 z 1 kuponów na ~1.9.**")


def _builder(eid: int, *legs: dict[str, Any], p: float = 0.5) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "match": f"A{eid} - B{eid}",
        "competition": "X",
        "kickoff_utc": LATER,
        "combined_probability": p,
        "odds_if_product": 9.99,
        "legs": [
            {k: g[k] for k in ("market", "direction", "line", "confidence",
                               "superbet_market", "superbet_selection")}
            | {"odds": g["offered_odds"]}
            for g in legs
        ],
    }


def test_builder_is_one_option_of_its_match_priced_as_the_product() -> None:
    """A builder's odds are its legs' product (the operator's rule), its
    chance the combined probability lowered by each leg's own price cap (a
    price_gap leg at its price), and it shares the match with that match's
    singles."""
    # the artifact's builder legs carry no price_gap: b (0.75 at 1.40, 3.6 pp
    # above its price) is marked by bet.sofa.price_gap's own rule, a (0.68 at
    # 1.50, 1.3 pp) is not
    a = _leg(1, 1.5, 0.68)
    b = _leg(1, 1.4, 0.75, line=8.5)
    pool, _ = sb.builder_candidates([_builder(1, a, b, p=0.6)], NOW,
                                    max_odds=5.0)
    (x,) = pool
    assert x.odds == pytest.approx(1.5 * 1.4)
    assert x.match_key == "sofa:1"
    assert x.chance == pytest.approx(0.6 * (1 / 1.4) / 0.75)
    assert len(sb.leg_rows(x)) == 2
    res = sb.build([], NOW, 2.0, max_odds=5.0,
                   builders=[_builder(1, a, b, p=0.6)])
    assert res.slips and res.slips[0].legs[0].leg["market"] == sb.BUILDER_MARKET
    text = sb.render(res, day="2026-10-20", target=2.0, now=NOW)
    assert "iloczynem kursów nóg (zasada operatora 26.10)" in text
    # the product, labelled, never a builder price of ours (CLAUDE.md)
    assert "2.10 iloczyn |" in text and "ekran ~" not in text
    assert "zwrot wg naszych liczb najwyżej" in text


def test_builder_with_a_refused_leg_never_enters() -> None:
    from bet.sofa.contracts import LegRead

    a = _leg(1, 1.5, 0.70)
    b = _leg(1, 1.4, 0.75, line=8.5)
    watch = LegRead(sofascore_event_id=1, market="corners_total", subject="",
                    line=8.5, direction="OVER", verdict="WATCH",
                    author="analyst", reason="test")
    pool, refused = sb.builder_candidates([_builder(1, a, b)], NOW,
                                          max_odds=5.0, slip_reads=[watch])
    assert pool == []
    assert refused == {"builder: noga odrzucona przez analityka": 1}


def test_check_reads_the_operators_own_builder_leg_by_leg() -> None:
    # A builder from the screen: two legs on the day's coupon, one not. The
    # check names the legs below price by the measured chance (the leg's own
    # confidence, a price_gap leg at its price), says what the missing leg's
    # match offers, and never calls the product a joint chance.
    singles = [
        _leg(1, 1.12, 0.84),
        _leg(1, 1.31, 0.78, market="cards_total", direction="UNDER", line=6.5,
             superbet_market="Liczba kartek", superbet_selection="poniżej 6.5"),
    ]
    assert sb.find_leg(singles, "a1|LICZBA KARTEK|poniżej 6.5")[0] is singles[1]
    missing, near = sb.find_leg(singles, "A1|Liczba goli|poniżej 4.5")
    assert missing is None and len(near) == 2
    with pytest.raises(ValueError):
        sb.find_leg(singles, "A1|Liczba goli")
    text = sb.render_check(
        ["A1|Liczba rzutów rożnych|powyżej 7.5", "A1|Liczba kartek|poniżej 6.5",
         "A1|Liczba goli|poniżej 4.5"],
        singles, 1.62, {},
        {"k": 9, "n": 20, "legs_read": 2, "legs_without_history": []})
    assert text.startswith("**Builder: 2 z 3 nóg na kuponie dnia, 1 z szansą "
                           "zmierzoną poniżej ceny.**")
    assert "Liczba goli|poniżej 4.5 - nie ma na kuponie dnia" in text
    assert "razem w 9 z 20 ostatnich meczów" in text
    assert "Iloczyn" not in text  # never the product of chances (skill rule)
    # the column and the headline read one rule: measured chance vs 1/odds
    # (E2E 2026-10-29); no family column (operator 2026-10-31)
    assert "| szansa zmierzona < 1/kurs | zestawienie |" in text
    assert "rodzina" not in text
    rows = {x.split(" | ")[0]: x for x in text.splitlines()
            if x.startswith("| Liczba ")}
    assert "| **tak** |" in rows["| Liczba rzutów rożnych: powyżej 7.5"]
    assert "| 78,0% | 78,0% | nie |" in rows["| Liczba kartek: poniżej 6.5"]
    assert "1/kurs 61,7%" in text
    # a leg refused or removed says why it is not on the coupon
    why = sb.render_check(
        ["A1|Liczba goli|poniżej 4.5"], singles, None, {}, None,
        [{"match": "A1 - B1", "superbet_market": "Liczba goli",
          "superbet_selection": "poniżej 4.5", "why": "odrzucona: ODDS_TOO_LOW"}])
    assert "poniżej 4.5 - nie na kuponie: odrzucona: ODDS_TOO_LOW" in why
