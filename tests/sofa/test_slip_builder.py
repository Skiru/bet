"""bet.sofa.slip_builder and scripts/sofa/build_slip.py: a chat slip to a
target price from the day's coupon - fewest legs, one per match, measured
chance never above the price, "say no first"."""

from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import family_record as fr
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


def _fam(legs: int, hit: float, implied: float) -> dict[str, Any]:
    units = legs * (hit - implied)  # sign is what on_plus reads
    return {
        "legs": legs,
        "matches": legs,
        "won": int(hit * legs),
        "units": units,
        "roi": units / legs,
        "hit": hit,
        "implied": implied,
    }


def _record(
    families: dict[str, dict[str, Any]], day: str = "2026-10-20"
) -> dict[str, Any]:
    return {
        "before": day,
        "days": ["2026-10-09", "2026-10-19"],
        "variant": fr.VARIANT,
        "min_legs": fr.MIN_LEGS,
        "window_days": fr.WINDOW_DAYS,
        "families": families,
    }


PLUS = "football|corners_total|OVER"
MINUS = "football|goals_total|UNDER"


def test_rest_leg_reads_its_family_shortfall_and_never_its_confidence() -> None:
    fam, sport = sb.shortfalls(_record({MINUS: _fam(200, 0.76, 0.80)}))
    chance, source = sb.measured_chance(
        _leg(1, 1.25, 0.85, market="goals_total", direction="UNDER"), 1.25, fam, sport
    ) or (0, "")
    assert chance == pytest.approx(0.80 - 0.04)
    assert source == "rodzina"


def test_family_surplus_never_lifts_a_leg_above_its_price() -> None:
    fam, sport = sb.shortfalls(_record({PLUS: _fam(200, 0.85, 0.80)}))
    leg = _leg(1, 1.25, 0.90)
    chance, source = sb.measured_chance(leg, 1.25, fam, sport, sb.TIER_SELECTION) or (
        0,
        "",
    )
    assert chance == pytest.approx(0.80 + sb.TIER_SHORTFALL[sb.TIER_SELECTION])
    assert chance < 1 / 1.25
    assert source.startswith("selekcja")


def test_price_gap_leg_is_read_at_its_price_and_confidence_bounds_from_above() -> None:
    fam, sport = sb.shortfalls(_record({MINUS: _fam(200, 0.80, 0.80)}))
    leg = _leg(
        1,
        1.25,
        0.95,
        market="goals_total",
        direction="UNDER",
        price_gap={"flag": "CONFIDENCE_ABOVE_PRICE"},
    )
    got = sb.measured_chance(leg, 1.25, fam, sport)
    assert got is not None and got[1] == "rodzina"
    # a family off the plus never reads better than the plus tier's -1.6 pp
    assert got[0] == pytest.approx(0.80 + sb.TIER_SHORTFALL[sb.TIER_FAMILY_PLUS])
    low = _leg(2, 1.25, 0.70, market="goals_total", direction="UNDER")
    got = sb.measured_chance(low, 1.25, fam, sport)
    assert got is not None and got[1] == "pewność"
    assert got[0] == pytest.approx(0.70)


def test_thin_family_reads_the_sport_and_no_measurement_is_no_leg() -> None:
    fam, sport = sb.shortfalls(
        _record({MINUS: _fam(10, 0.70, 0.80), PLUS: _fam(100, 0.78, 0.80)})
    )
    assert MINUS not in fam
    chance, source = sb.measured_chance(
        _leg(1, 1.25, 0.9, market="goals_total", direction="UNDER"), 1.25, fam, sport
    ) or (0, "")
    assert source == "sport" and chance < 0.80
    tennis = dict(_leg(2, 1.25, 0.9), sport="tennis")
    assert sb.measured_chance(tennis, 1.25, fam, sport) is None


def test_fewer_longer_legs_win_at_the_same_target() -> None:
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    short = [_leg(i, 1.25, 0.85) for i in range(1, 7)]  # x = 1.06
    long_ = [_leg(i, 1.50, 0.70) for i in range(11, 14)]  # x = 1.05
    res = sb.build(short + long_, rec, NOW, target=2.2)
    (slip,) = res.slips
    assert len(slip.legs) == 2
    assert all(x.odds == 1.50 for x in slip.legs)
    assert slip.price_product >= 2.2


def test_one_leg_per_match_and_disjoint_slips() -> None:
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    legs = [_leg(i, 1.5, 0.7, line=line) for i in range(1, 7) for line in (6.5, 7.5)]
    res = sb.build(legs, rec, NOW, target=2.2, slips=3)
    keys = [x.match_key for s in res.slips for x in s.legs]
    assert len(res.slips) == 3 and len(keys) == len(set(keys))


def test_started_and_out_of_band_legs_are_refused() -> None:
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    soon = (NOW + datetime.timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    legs = [_leg(1, 1.5, 0.7, kickoff=soon), _leg(2, 3.5, 0.3), _leg(3, 1.5, 0.7)]
    pool, refused = sb.candidates(legs, rec, NOW)
    assert [x.leg["sofascore_event_id"] for x in pool] == [3]
    assert refused == {"rozpoczęty lub za chwilę": 1, "kurs poza przedziałem": 1}


def test_say_no_first_and_rest_only_on_request() -> None:
    rec = _record({MINUS: _fam(300, 0.76, 0.80)})
    legs = [
        _leg(i, 1.5, 0.7, market="goals_total", direction="UNDER") for i in range(1, 5)
    ]
    res = sb.build(legs, rec, NOW, target=2.2)
    assert res.slips == [] and res.supported == 0
    text = sb.render(res, day="2026-10-20", target=2.2, record=rec, now=NOW)
    assert text.startswith("**Dziś żadnego kuponu")
    res = sb.build(legs, rec, NOW, target=2.2, allow_rest=True)
    assert len(res.slips) == 1 and not res.slips[0].supported and res.supported == 0
    text = sb.render(res, day="2026-10-20", target=2.2, record=rec, now=NOW)
    assert text.startswith("**Dziś żadnego") and "poza poparciem" in text


def test_render_names_superbet_words_and_never_a_slip_price() -> None:
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    res = sb.build([_leg(1, 1.5, 0.7), _leg(2, 1.5, 0.7)], rec, NOW, target=2.2)
    text = sb.render(res, day="2026-10-20", target=2.2, record=rec, now=NOW)
    assert text.startswith("**Dzień daje 1 z 1")
    assert "Liczba rzutów rożnych: powyżej 7.5" in text
    assert "sprawdź na ekranie Superbetu" in text
    assert "Cel ~2.2 osiągnięty" in text and "2.25" not in text
    assert "2 nogi" in text
    assert math.isclose(res.slips[0].chance, (1 / 1.5 - 0.008) ** 2)


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
                "--no-refresh-record",
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
    (run / fr.FILE).write_text(
        json.dumps(_record({PLUS: _fam(300, 0.82, 0.80)})), encoding="utf-8"
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
                "--no-refresh-record",
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
                "--no-refresh-record",
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
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    early = datetime.datetime(2026, 10, 20, 7, 0, tzinfo=datetime.UTC)
    legs = [
        _leg(1, 1.5, 0.7, kickoff="2026-10-20T08:00:00Z"),
        _leg(2, 1.5, 0.7, kickoff="2026-10-20T10:00:00Z"),
    ]
    pool, refused = sb.candidates(legs, rec, early, window=(lo, hi))
    assert [x.leg["sofascore_event_id"] for x in pool] == [1]
    assert refused == {"start poza oknem": 1}


def test_competition_filter_keeps_only_named_competitions() -> None:
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    legs = [
        _leg(1, 1.5, 0.7, competition="UEFA Champions League"),
        _leg(2, 1.5, 0.7, competition="League One"),
        _leg(3, 1.5, 0.7),
    ]
    pool, refused = sb.candidates(legs, rec, NOW, competitions=["champions league"])
    assert [x.leg["sofascore_event_id"] for x in pool] == [1]
    assert refused == {"poza wybranymi rozgrywkami": 2}
    pool, _ = sb.candidates(legs, rec, NOW)
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
                sb.TIER_REST,
            )
            for m in range(1, 9)
            for _ in range(rnd.randint(1, 3))
        ]
        legs = [
            sb.Leg(dict(x.leg, line=i), x.odds, min(x.chance, 1 / x.odds), "t", x.tier)
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

    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    legs = [_leg(1, 1.6, 0.66), _leg(2, 1.55, 0.68), _leg(3, 1.5, 0.70)]
    first = sb.build(legs, rec, NOW, target=2.3)
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
    second = sb.build(legs, rec, NOW, target=2.3, reads=reads[:1], slip_reads=reads[1:])
    again = {x.leg["sofascore_event_id"]: x.read for x in second.slips[0].legs}
    assert out not in again and again[max(chosen)] == sb.READ_KEEP
    assert second.refused["odrzucona przez analityka (WATCH / NO_BET / weto)"] == 1
    carried = [dict(legs[0], reads=[{"verdict": "NO_BET", "author": "verifier"}])]
    assert sb.read_status(carried[0]) is None


def test_reserve_slips_and_the_slip_read_set(tmp_path: Path) -> None:
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    legs = [_leg(i, 1.5, 0.7) for i in range(1, 7)]
    res = sb.build(legs, rec, NOW, target=2.2, reserve=1)
    assert len(res.slips) == 1 and len(res.reserve) == 1 and res.supported == 1
    keys = [x.match_key for s in res.slips + res.reserve for x in s.legs]
    assert len(keys) == len(set(keys)) == 4
    written = build_slip.write_read_set(tmp_path, res)
    assert written == {"football": 4}
    rows = json.loads((tmp_path / "read_set_slip_football.json").read_text())
    assert sorted(r["in_set"] for r in rows) == ["slip"] * 2 + ["slip_reserve"] * 2
    assert rows[0]["superbet_market"] == "Liczba rzutów rożnych"
    text = sb.render(res, day="2026-10-20", target=2.2, record=rec, now=NOW)
    assert "Nieczytane nogi w kuponach: 2" in text and "Zapas do czytania" in text


def test_a_slip_exactly_at_the_target_is_found() -> None:
    legs = [sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.45, "t", sb.TIER_REST) for i in (1, 2)]
    got = sb.best_slip(legs, 4.0)
    assert got is not None and got.price_product == pytest.approx(4.0)


def test_a_slip_at_the_target_is_not_lost_to_one_just_below_it() -> None:
    # 1.25 x 1.6 x 2.0 = 4 exactly; 2.0 x 1.11 x 1.82 = 4.04 is the runner-up
    # (review 4: the exact-target state shared a bucket with a richer one
    # just under the target and was dropped)
    spec = [(1.25, 0.79), (1.6, 0.60), (2.0, 0.48), (1.11, 0.88), (1.82, 0.53)]
    spec.append((1.98, 0.49))
    legs = [
        sb.Leg(_leg(i, o, c), o, c, "t", sb.TIER_REST) for i, (o, c) in enumerate(spec)
    ]
    got = sb.best_slip(legs, 4.0, 3)
    assert got is not None
    assert sorted(x.odds for x in got.legs) == [1.25, 1.6, 2.0]
    one = [
        sb.Leg(_leg(1, 2.0, 0.4), 2.0, 0.4, "t", sb.TIER_REST),
        sb.Leg(_leg(2, 1.99995, 0.45), 1.99995, 0.45, "t", sb.TIER_REST),
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
                sb.TIER_REST,
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
    record = _record({"football|corners_total|OVER": _fam(100, 0.5, 0.55)})
    got, refused = sb.candidates(legs, record, NOW)
    assert [x.leg["sofascore_event_id"] for x in got] == [2]
    assert refused["brak ceny lub pewności"] == 2


def test_one_family_slip_is_named_never_gated() -> None:
    legs = [sb.Leg(_leg(i, 1.6, 0.6), 1.6, 0.55, "t", sb.TIER_REST) for i in (1, 2, 3)]
    slip = sb.Slip(legs)
    assert sb.concentration(slip) == ("football|corners_total|OVER", 3)
    mixed = sb.Slip(
        [
            legs[0],
            sb.Leg(_leg(4, 1.6, 0.6, direction="UNDER"), 1.6, 0.55, "t", sb.TIER_REST),
        ]
    )
    assert sb.concentration(mixed) is None
    assert sb.concentration(sb.Slip(legs[:2])) == ("football|corners_total|OVER", 2)
    result = sb.Result([slip], 1, 0, {}, {})
    text = sb.render(result, day="2026-10-20", target=4, record=None, now=NOW)
    assert "3 z 3 nóg z jednej rodziny (football|corners_total|OVER)" in text


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


def test_script_refuses_bad_arguments_and_a_missing_family_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    day = "2026-10-20"
    base = [
        "--date",
        day,
        "--target",
        "2",
        "--runs-dir",
        str(tmp_path),
        "--no-refresh-record",
    ]
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
    assert build_slip.main(base) == 2
    assert "build_family_record.py" in capsys.readouterr().err


def test_a_leg_without_a_fixture_id_is_counted_not_fatal() -> None:
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    bare = dict(_leg(1, 1.5, 0.7))
    del bare["sofascore_event_id"]
    pool, refused = sb.candidates([bare, _leg(2, 1.5, 0.7)], rec, NOW)
    assert len(pool) == 1 and refused == {"brak id meczu": 1}


def test_stale_prices_are_flagged_by_the_pipelines_own_limits() -> None:
    rec = _record(
        {PLUS: _fam(300, 0.82, 0.80), "hockey|corners_total|OVER": _fam(300, 0.82, 0.8)}
    )
    old = (NOW - datetime.timedelta(minutes=50)).isoformat().replace("+00:00", "Z")
    fresh = (NOW - datetime.timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    legs = [
        _leg(1, 1.5, 0.7, price_fetched_at_utc=old),
        _leg(2, 1.5, 0.7, price_fetched_at_utc=fresh),
        dict(_leg(3, 1.5, 0.7, price_fetched_at_utc=old), sport="hockey"),
    ]
    pool, _ = sb.candidates(legs, rec, NOW)
    stale = {x.leg["sofascore_event_id"]: x.stale for x in pool}
    assert stale == {1: True, 2: False, 3: False}  # hockey: 3 h
    res = sb.build(legs[:2], rec, NOW, target=2.2)
    text = sb.render(
        res,
        day="2026-10-20",
        target=2.2,
        record=rec,
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
    rec = _record({PLUS: _fam(300, 0.82, 0.80)})
    legs = [_leg(1, 1.5, 0.70), _leg(2, 1.5, 0.70), _leg(3, 1.6, 0.74)]
    first = sb.build(legs, rec, NOW, target=2.2)
    assert {x.leg["sofascore_event_id"] for x in first.slips[0].legs} == {1, 2}
    keep = [_read(1, 7.5, "KEEP"), _read(3, 7.5, "KEEP")]
    kept = sb.build(legs, rec, NOW, target=2.2, slip_reads=keep)
    assert {x.leg["sofascore_event_id"] for x in kept.slips[0].legs} == {1, 3}
    short = sb.build(legs, rec, NOW, target=3.0, slip_reads=keep)
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
    day = sb.Leg(leg, 1.5, 0.6, "t", 3, sb.READ_KEEP_DAY)
    old = sb.Leg(_leg(2, 1.5, 0.7), 1.5, 0.6, "t", 3, f"{sb.READ_KEEP} (10:42)")
    fresh = sb.Leg(_leg(3, 1.5, 0.7), 1.5, 0.6, "t", 3, sb.READ_KEEP)
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
        sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.4884, "t", sb.TIER_REST, sb.READ_KEEP)
        for i in (1, 2)
    ]
    unread = [sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.4887, "t", sb.TIER_REST) for i in (3, 4)]
    got = sb.best_slip(read + unread, 4.0, 2)
    assert got is not None
    assert {x.leg["sofascore_event_id"] for x in got.legs} == {1, 2}
    clearly = [sb.Leg(_leg(i, 2.0, 0.5), 2.0, 0.52, "t", sb.TIER_REST) for i in (3, 4)]
    got = sb.best_slip(read + clearly, 4.0, 2)
    assert got is not None
    assert {x.leg["sofascore_event_id"] for x in got.legs} == {3, 4}


def test_any_family_searches_every_leg_in_one_pass() -> None:
    """Operator 2026-10-26: no preference for families on the plus - one pass
    over every leg, so a rest leg with the better chance wins its slot."""
    record = _record({PLUS: _fam(80, 0.82, 0.80), MINUS: _fam(80, 0.70, 0.72)})
    singles = [
        _leg(1, 2.0, 0.40),  # plus family, weak
        _leg(2, 2.0, 0.60, market="goals_total", direction="UNDER"),
    ]
    tiered = sb.build(singles, record, NOW, 1.9, allow_rest=True)
    one = sb.build(singles, record, NOW, 1.9, any_family=True)
    assert [x.leg["sofascore_event_id"] for x in tiered.slips[0].legs] == [1]
    assert [x.leg["sofascore_event_id"] for x in one.slips[0].legs] == [2]
    assert one.any_family
    assert "nie stoi na samych rodzinach na plusie" in sb.render(
        one, day="2026-10-20", target=1.9, record=record, now=NOW
    )


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
    chance the combined probability lowered by each leg's shortfall, and it
    shares the match with that match's singles."""
    record = _record({PLUS: _fam(80, 0.80, 0.80)})
    a = _leg(1, 1.5, 0.70)
    b = _leg(1, 1.4, 0.75, line=8.5)
    pool, _ = sb.builder_candidates([_builder(1, a, b, p=0.6)], record, NOW,
                                    max_odds=5.0)
    (x,) = pool
    assert x.odds == pytest.approx(1.5 * 1.4)
    assert x.match_key == "sofa:1"
    assert x.chance <= 0.6
    assert len(sb.leg_rows(x)) == 2
    res = sb.build([], record, NOW, 2.0, any_family=True, max_odds=5.0,
                   builders=[_builder(1, a, b, p=0.6)])
    assert res.slips and res.slips[0].legs[0].leg["market"] == sb.BUILDER_MARKET
    text = sb.render(res, day="2026-10-20", target=2.0, record=record, now=NOW)
    assert "iloczynem kursów nóg (zasada operatora 26.10)" in text
    # the product, labelled, never a builder price of ours (CLAUDE.md)
    assert "2.10 iloczyn |" in text and "ekran ~" not in text
    assert "zwrot wg naszych liczb najwyżej" in text


def test_builder_with_a_refused_leg_never_enters() -> None:
    from bet.sofa.contracts import LegRead

    record = _record({PLUS: _fam(80, 0.80, 0.80)})
    a = _leg(1, 1.5, 0.70)
    b = _leg(1, 1.4, 0.75, line=8.5)
    watch = LegRead(sofascore_event_id=1, market="corners_total", subject="",
                    line=8.5, direction="OVER", verdict="WATCH",
                    author="analyst", reason="test")
    pool, refused = sb.builder_candidates([_builder(1, a, b)], record, NOW,
                                          max_odds=5.0, slip_reads=[watch])
    assert pool == []
    assert refused == {"builder: noga odrzucona przez analityka": 1}


def test_check_reads_the_operators_own_builder_leg_by_leg() -> None:
    # A builder from the screen: two legs on the day's coupon, one not. The
    # check names the legs below price by the measured chance, says what the
    # missing leg's match offers, and never calls the product a joint chance.
    singles = [
        _leg(1, 1.12, 0.84),
        _leg(1, 1.31, 0.78, market="cards_total", direction="UNDER", line=6.5,
             superbet_market="Liczba kartek", superbet_selection="poniżej 6.5"),
    ]
    record = _record({MINUS: _fam(200, 0.76, 0.80)})
    assert sb.find_leg(singles, "a1|LICZBA KARTEK|poniżej 6.5")[0] is singles[1]
    missing, near = sb.find_leg(singles, "A1|Liczba goli|poniżej 4.5")
    assert missing is None and len(near) == 2
    with pytest.raises(ValueError):
        sb.find_leg(singles, "A1|Liczba goli")
    text = sb.render_check(
        ["A1|Liczba rzutów rożnych|powyżej 7.5", "A1|Liczba kartek|poniżej 6.5",
         "A1|Liczba goli|poniżej 4.5"],
        singles, record, 1.62, {},
        {"k": 9, "n": 20, "legs_read": 2, "legs_without_history": []})
    assert text.startswith("**Builder: 2 z 3 nóg na kuponie dnia, 2 z szansą "
                           "zmierzoną poniżej ceny.**")
    assert "Liczba goli|poniżej 4.5 - nie ma na kuponie dnia" in text
    assert "razem w 9 z 20 ostatnich meczów" in text
    assert "Iloczyn" not in text  # never the product of chances (skill rule)
    # the column and the headline read one rule: measured chance vs 1/odds
    # (E2E 2026-10-29: a confidence above 1/odds showed "nie" beside a
    # headline counting the leg below price)
    assert "| szansa zmierzona < 1/kurs |" in text
    rows = [x for x in text.splitlines() if x.startswith("| Liczba ")]
    assert len(rows) == 2 and all("| **tak** |" in x for x in rows)
    assert "1/kurs 61,7%" in text
    # a leg refused or removed says why it is not on the coupon
    why = sb.render_check(
        ["A1|Liczba goli|poniżej 4.5"], singles, record, None, {}, None,
        [{"match": "A1 - B1", "superbet_market": "Liczba goli",
          "superbet_selection": "poniżej 4.5", "why": "odrzucona: ODDS_TOO_LOW"}])
    assert "poniżej 4.5 - nie na kuponie: odrzucona: ODDS_TOO_LOW" in why
