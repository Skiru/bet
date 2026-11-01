"""bet.sofa.slip_builder and scripts/sofa/build_slip.py: a chat slip to a
target price from the day's coupon - fewest legs, one per match, each leg on
its own statistics, never above its price (min(confidence, 1/odds)), one search
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
        "sample_size": 10,
        "sample_hit_rate": 0.8,
        **extra,
    }


def test_measured_chance_is_the_legs_own_confidence_at_or_below_its_price() -> None:
    """Operator 2026-10-31: no family, sport or tier shortfall - a leg's
    confidence (it carries the line evidence) at or below 1/odds is its
    measured chance."""
    chance, source = sb.measured_chance(
        _leg(1, 1.25, 0.78, market="goals_total", direction="UNDER"), 1.25)
    assert chance == pytest.approx(0.78) and source == "pewność"
    tennis = dict(_leg(2, 1.25, 0.6), sport="tennis")
    assert sb.measured_chance(tennis, 1.25) == (pytest.approx(0.6), "pewność")
    at_price = _leg(3, 1.25, 0.80)
    assert sb.measured_chance(at_price, 1.25) == (pytest.approx(0.80), "pewność")


def test_any_leg_above_its_price_is_read_at_its_price() -> None:
    """min(confidence, 1/odds) for every sport, flagged `price_gap` or not:
    a leg 1 pp above its price is read at its price as one 20 pp above
    (2026-10-31 smoke: unflagged volleyball set handicaps at 82% against 57%
    at the price topped a ~3 slip)."""
    vb = dict(_leg(1, 1.75, 0.82, market="set_handicap"), sport="volleyball")
    assert sb.measured_chance(vb, 1.75) == (
        pytest.approx(1 / 1.75), "cena (pewność ponad cenę)")
    flagged = _leg(2, 1.25, 0.95, price_gap={"flag": "CONFIDENCE_ABOVE_PRICE"})
    assert sb.measured_chance(flagged, 1.25) == (
        pytest.approx(0.80), "cena (pewność ponad cenę)")
    slight = dict(_leg(3, 1.25, 0.81), sport="hockey")
    assert sb.measured_chance(slight, 1.25) == (
        pytest.approx(0.80), "cena (pewność ponad cenę)")


def test_measured_chance_is_monotone_and_never_above_the_price() -> None:
    """Review 2026-10-31: the old rule stepped at price_gap.GAP (0.029 above
    the price kept the confidence, 0.031 dropped to 1/odds)."""
    odds = 1.60
    price = 1 / odds
    confs = [price + d / 1000 for d in range(-100, 101)]
    chances = [sb.measured_chance(_leg(1, odds, c), odds)[0] for c in confs]
    assert all(b >= a - 1e-12 for a, b in zip(chances, chances[1:], strict=False))
    assert all(ch <= price + 1e-12 for ch in chances)
    assert sb.measured_chance(_leg(1, odds, price + 0.029), odds)[0] == pytest.approx(
        sb.measured_chance(_leg(1, odds, price + 0.031), odds)[0])


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
    res = sb.build([_leg(1, 1.5, 0.66), _leg(2, 1.5, 0.66)], NOW, target=2.2)
    text = sb.render(res, day="2026-10-20", target=2.2, now=NOW)
    assert text.startswith("**Dzień daje 1 z 1")
    assert "Liczba rzutów rożnych: powyżej 7.5" in text
    assert "sprawdź na ekranie Superbetu" in text
    assert "Cel ~2.2 osiągnięty" in text and "2.25" not in text
    assert "2 nogi" in text
    # each leg at its own confidence (0.66, below 1/1.5)
    assert math.isclose(res.slips[0].chance, 0.66**2)
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
    short = sb.build(legs, NOW, target=3.0, slip_reads=keep, max_legs=3)
    assert {x.leg["sofascore_event_id"] for x in short.slips[0].legs} == {1, 2, 3}
    # at the default 2 legs ~3 is out of reach: the closest 2-leg slip, flagged
    two = sb.build(legs, NOW, target=3.0, slip_reads=keep)
    assert len(two.slips[0].legs) == 2 and two.slips[0].needs_legs == 3


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
    leg above its price at its price), and it shares the match with that
    match's singles."""
    # both legs are above their price - b (0.75 at 1.40) by 3.6 pp, a (0.68
    # at 1.50) by 1.3 pp - and each is read at its price (no GAP step)
    a = _leg(1, 1.5, 0.68)
    b = _leg(1, 1.4, 0.75, line=8.5)
    pool, _ = sb.builder_candidates([_builder(1, a, b, p=0.6)], NOW,
                                    max_odds=5.0)
    (x,) = pool
    assert x.odds == pytest.approx(1.5 * 1.4)
    assert x.match_key == "sofa:1"
    assert x.chance == pytest.approx(0.6 * ((1 / 1.4) / 0.75) * ((1 / 1.5) / 0.68))
    assert len(sb.leg_rows(x)) == 2
    res = sb.build([], NOW, 2.0, max_odds=5.0,
                   builders=[_builder(1, a, b, p=0.6)])
    assert res.slips and res.slips[0].legs[0].leg["market"] == sb.BUILDER_MARKET
    text = sb.render(res, day="2026-10-20", target=2.0, now=NOW)
    assert "iloczynem kursów nóg (zasada operatora 26.10)" in text
    # the product, labelled, never a builder price of ours (CLAUDE.md)
    assert "2.10 iloczyn |" in text and "ekran ~" not in text
    # no return from our own numbers (operator 2026-10-31); a builder gets no
    # per-leg formula (review 2026-10-31): its measured numbers and the screen
    assert "zwrot wg naszych liczb" not in text
    assert "0,946^" not in text
    assert "−16,6% stawki (10-13..10-26, n 88) i −45,8%" in text
    head = next(x for x in text.splitlines() if x.startswith("### Kupon 1"))
    assert "builder: bez wzoru na nogę" in head
    assert "kurs buildera decyduje ekran Superbetu" in head


def test_slip_mixing_a_builder_and_singles_states_both_parts() -> None:
    """Review 2026-10-31: the singles' 0.88 x 0.946^n - 1 was printed for a
    slip holding a Bet Builder. A mixed slip states the singles part and the
    builder's measured numbers apart - never a combined number."""
    a = _leg(1, 1.5, 0.60)
    b = _leg(1, 1.4, 0.65, line=8.5)
    single = _leg(2, 1.5, 0.62)
    res = sb.build([single], NOW, 2.8, max_odds=5.0, max_legs=2,
                   builders=[_builder(1, a, b, p=0.4)])
    (slip,) = res.slips
    assert slip.has_builder and len(slip.legs) == 2
    assert (slip.rows, slip.single_rows) == (3, 1)
    line = sb.slip_money_line(slip)
    assert line.startswith("część pojedyncza (1 noga): każda noga zwraca ok. 0,96 ")
    assert "builder: bez wzoru na nogę - Bet Buildery zmierzone po podatku" in line
    assert "kurs buildera decyduje ekran Superbetu" in line
    assert "łącznego zwrotu kuponu nie podajemy" in line
    assert "0,946^" not in line and "=" not in line
    text = sb.render(res, day="2026-10-20", target=2.8, now=NOW)
    assert "0,946^" not in text  # no singles-only slip, no per-leg formula line
    # a singles-only slip keeps the measured formula
    only = sb.build([single, _leg(3, 1.5, 0.62)], NOW, 2.2)
    assert sb.slip_money_line(only.slips[0]) == sb.money_line(2)


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
    # 0.78 above 1/1.31 = 0.763: read at its price, so not below it
    assert "| 78,0% | 76,3% | nie |" in rows["| Liczba kartek: poniżej 6.5"]
    assert "1/kurs 61,7%" in text
    # a leg refused or removed says why it is not on the coupon
    why = sb.render_check(
        ["A1|Liczba goli|poniżej 4.5"], singles, None, {}, None,
        [{"match": "A1 - B1", "superbet_market": "Liczba goli",
          "superbet_selection": "poniżej 4.5", "why": "odrzucona: ODDS_TOO_LOW"}])
    assert "poniżej 4.5 - nie na kuponie: odrzucona: ODDS_TOO_LOW" in why


# --- the least-loss flow (operator's go 2026-10-31; backtest
# docs/sofa/evidence/slip_flow_backtest_2026-10-31.md) ---


def test_default_is_two_legs_and_builders_are_opt_in(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(1) 2 legs by default in the module and the script; the day's Bet
    Builders enter only with --builders, and then the answer names their
    measured loss; a raised limit lists the measured cost of each leg."""
    assert sb.MAX_LEGS == 2
    legs = [_leg(i, 1.3, 0.76) for i in range(1, 7)]
    res = sb.build(legs, NOW, target=2.0)  # 1.3^3 = 2.197 needs 3 legs
    assert all(len(s.legs) <= 2 for s in res.slips)
    raised = sb.build(legs, NOW, target=2.0, max_legs=3)
    assert len(raised.slips[0].legs) == 3 and raised.slips[0].reached
    text = sb.render(raised, day="2026-10-20", target=2.0, now=NOW)
    assert ("Limit nóg 3 (domyślnie 2): każda kolejna noga mnoży zwrot przez "
            "0,96") in text
    assert "1 noga −15,5%, 2 nogi −18,9%, 3 nogi −22,1%" in text
    day = "2026-10-20"
    run = tmp_path / day
    run.mkdir()
    a = _leg(1, 1.5, 0.68, kickoff="2099-01-01T00:00:00Z")
    b = _leg(1, 1.4, 0.75, line=8.5, kickoff="2099-01-01T00:00:00Z")
    builder = dict(_builder(1, a, b, p=0.6), kickoff_utc="2099-01-01T00:00:00Z")
    (run / "11_coupon.json").write_text(
        json.dumps({"singles": [], "builders": [builder]}), encoding="utf-8")
    base = ["--date", day, "--target", "2", "--max-odds", "5", "--runs-dir",
            str(tmp_path)]
    assert build_slip.main(base) == 1  # no builder without the flag
    assert "Bet Buildery zmierzone" not in capsys.readouterr().out
    assert build_slip.main(base + ["--builders"]) == 0
    out = capsys.readouterr().out
    assert "Bet Buildery zmierzone po podatku: −16,6% stawki" in out
    assert "−45,8% (hold-out 10-27..10-30, n 10)" in out


def test_target_out_of_reach_of_the_leg_limit_is_said_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(2) ~4 with 2 legs at most 1.8 each: the first line says how many legs
    the target needs and the cost of each, the slip is the closest 2-leg one
    (never a silent third leg), marked not reached; exit code 1."""
    legs = [_leg(i, 1.8, 0.55) for i in range(1, 4)] + [_leg(9, 1.6, 0.62)]
    res = sb.build(legs, NOW, target=4.0)
    (slip,) = res.slips
    assert len(slip.legs) == 2 and not slip.reached and slip.needs_legs == 3
    assert slip.price_product == pytest.approx(1.8 * 1.8)
    text = sb.render(res, day="2026-10-20", target=4.0, now=NOW)
    first = text.splitlines()[0]
    assert first == ("**Na ~4 trzeba 3 nóg - każda kolejna noga to ok. −4% więcej; "
                     "z 2 nogami najbliżej ~3.24 (iloczyn kursów nóg, nie kurs "
                     "kuponu).**")
    assert "Cel ~4 NIE osiągnięty" in text and "Cel ~4 osiągnięty" not in text
    # a pool no number of legs reaches is still "dziś żadnego", no fallback
    alone = sb.build([_leg(1, 1.5, 0.7)], NOW, target=4.0)
    assert alone.slips == []
    # one slip reaches, the second would need more legs
    two = sb.build([_leg(1, 2.0, 0.5), _leg(2, 2.0, 0.5), _leg(3, 1.9, 0.52),
                    _leg(4, 1.6, 0.6), _leg(5, 1.5, 0.64)], NOW, target=4.0, slips=2)
    assert [s.reached for s in two.slips] == [True, False]
    head = sb.render(two, day="2026-10-20", target=4.0, now=NOW).splitlines()[0]
    assert head.startswith("**Dzień daje 1 z 2 kuponów na ~4; na kolejny trzeba 3 nóg")
    day = "2026-10-20"
    (tmp_path / day).mkdir()
    far = [_leg(i, 1.8, 0.55, kickoff="2099-01-01T00:00:00Z") for i in range(1, 4)]
    (tmp_path / day / "11_coupon.json").write_text(
        json.dumps({"singles": far}), encoding="utf-8")
    base = ["--date", day, "--target", "4", "--runs-dir", str(tmp_path)]
    assert build_slip.main(base) == 1
    assert capsys.readouterr().out.startswith("**Na ~4 trzeba 3 nóg")
    assert build_slip.main(base + ["--max-legs", "3"]) == 0
    assert "Limit nóg 3 (domyślnie 2)" in capsys.readouterr().out


def test_low_margin_leg_wins_a_tie_and_the_margin_is_shown() -> None:
    """(3) at equal measured chance a leg of a two-sided ladder with overround
    < 0.08 ranks first; the preference is a near-tie-break (+0.25% relative
    chance), so a clearly better chance still wins; the table shows "marża"."""
    low = _leg(1, 2.0, 0.5, overround=0.06)
    high = _leg(2, 2.0, 0.5, overround=0.11)
    one_sided = _leg(3, 2.0, 0.5)
    got = sb.build([high, one_sided, low], NOW, target=1.9, max_legs=1)
    assert [x.leg["sofascore_event_id"] for x in got.slips[0].legs] == [1]
    assert sb.LOW_MARGIN == 0.08
    assert sb.LOW_MARGIN_TIE == pytest.approx(math.log(1.0025))
    better = _leg(4, 1.95, 0.51, overround=0.12)  # 0.51 <= 1/1.95
    got = sb.build([low, better], NOW, target=1.9, max_legs=1)
    assert [x.leg["sofascore_event_id"] for x in got.slips[0].legs] == [4]
    pair = sb.build([low, high, one_sided], NOW, target=3.9)
    text = sb.render(pair, day="2026-10-20", target=3.9, now=NOW)
    assert "| pewność < 1/kurs | model | próbka | zestawienie |" in text
    assert "| **6,0%** |" in text
    assert ("| 11,0% |" in text) or ("| 1-str. |" in text)


def test_objective_is_the_measured_chance_unchanged() -> None:
    """(4) the slip maximises sum log(measured chance) under the target, one
    leg per match; a leg above its price reads at its price, so it never
    outranks a fair leg on its confidence alone."""
    over = _leg(1, 1.5, 0.80)  # 13 pp above 1/1.5: read at 0.667
    fair = _leg(2, 1.45, 0.68)  # below 1/1.45 = 0.690: read at 0.68
    got = sb.build([over, fair], NOW, target=1.45, max_legs=1)
    assert [x.leg["sofascore_event_id"] for x in got.slips[0].legs] == [2]
    assert got.slips[0].legs[0].chance == pytest.approx(0.68)


def test_money_line_is_measured_after_tax_never_our_confidence() -> None:
    """(5) the honest money line: 0.88 x 0.960^n - 1 with its source (the
    /kupon pool's measured realisation, redesign 2026-10-31), in the
    first lines and on every slip; never "zwrot wg naszych liczb"; a single
    below 1/0.88 is marked as paying back less than the stake."""
    assert sb.REALISED_PER_LEG == 0.960 and sb.TAX == 0.12
    assert sb.expected_return(1) == pytest.approx(0.88 * 0.960 - 1)
    assert sb.expected_return(2) == pytest.approx(0.88 * 0.960**2 - 1)
    line = ("oczekiwany zwrot po podatku ≈ 0,88 × 0,96^2 − 1 = −18,9% stawki "
            "(zmierzone: pula /kupon - próbka meczu ≥ 8, kurs nie urósł > 2%; "
            "nogi kuponu 10-13..10-30, n 36 940; podatek 12%)")
    assert sb.money_line(2) == line
    res = sb.build([_leg(1, 1.5, 0.69), _leg(2, 1.5, 0.69)], NOW, target=2.2)
    text = sb.render(res, day="2026-10-20", target=2.2, now=NOW)
    lines = text.splitlines()
    assert lines[1].startswith("O" + line[1:])
    assert f"- {line}" in text  # the slip header too
    assert "zwrot wg naszych liczb" not in text
    single = sb.build([_leg(1, 1.12, 0.88)], NOW, target=1.11)
    text = sb.render(single, day="2026-10-20", target=1.11, now=NOW)
    assert "0,96^1 − 1 = −15,5% stawki" in text
    assert "wygrana zwraca mniej niż gotówka (kurs < 1,136 przy podatku 12%)" in text
    ok = sb.build([_leg(1, 1.2, 0.82)], NOW, target=1.15)
    assert "mniej niż gotówka" not in sb.render(ok, day="2026-10-20", target=1.15,
                                                 now=NOW)


def test_legs_needed_and_reach_share_the_per_match_best_odds() -> None:
    """Review 2026-10-31: one helper builds the per-match best-odds map for
    both legs_needed and reach."""
    pool, _ = sb.candidates(
        [_leg(1, 1.3, 0.7), _leg(1, 1.9, 0.5, line=9.5), _leg(2, 1.6, 0.6),
         _leg(3, 1.2, 0.8)], NOW)
    assert sb.best_odds_by_match(pool) == [1.9, 1.6, 1.2]
    assert sb.reach(pool, 2) == pytest.approx(1.9 * 1.6)
    assert sb.legs_needed(pool, 1.9) == 1
    assert sb.legs_needed(pool, 3.0) == 2
    assert sb.legs_needed(pool, 3.6) == 3
    assert sb.legs_needed(pool, 3.7) is None


# --- the redesign 2026-10-31 (docs/sofa/evidence/kupon_od_nowa_2026-10-31.md)


def test_a_leg_needs_its_matchs_own_sample() -> None:
    """31.10 operator: penalties under 0.5 from the league rate (sample 0),
    Byfield's power-play points (sample 0) and a 4-game winner stood in the
    slips; a /kupon leg needs MIN_SAMPLE of its match's own games. A CS2
    engine leg records no sample and is not refused for it; --allow-no-sample
    admits a leg with none, never a micro-sample."""
    legs = [
        _leg(1, 1.40, 0.70, market="penalties_total", direction="UNDER",
             sample_size=0, forecast_source="league_rate"),
        _leg(2, 1.40, 0.70, sample_size=4, sample_hit_rate=1.0),
        dict(_leg(3, 1.40, 0.70, sample_size=0), sport="cs2",
             forecast_source="cs2_engine", family="map_winner"),
        dict(_leg(4, 1.40, 0.70), sport="basketball", family="winner",
             sample_size=None, sample_n=18, sample_k=10),
        _leg(5, 1.40, 0.70, sample_size=8, sample_hit_rate=0.5),
    ]
    pool, refused = sb.candidates(legs, NOW)
    assert sorted(x.leg["sofascore_event_id"] for x in pool) == [3, 4, 5]
    assert refused == {"bez próbki meczu (stawka ligi / sam model)": 1,
                       f"mikropróbka (< {sb.MIN_SAMPLE} meczów)": 1}
    pool, refused = sb.candidates(legs, NOW, allow_no_sample=True)
    assert sorted(x.leg["sofascore_event_id"] for x in pool) == [1, 3, 4, 5]
    assert sb.own_sample(legs[3]) == (10, 18)
    assert sb.own_sample(legs[4]) == (4, 8)
    assert sb.own_sample(legs[0]) is None


def test_a_leg_whose_price_rose_drops_and_the_next_takes_its_place() -> None:
    """31.10: Bernau rose from 1.52 to 1.65 before the start (the market
    against it) and nobody looked. The chosen legs are re-asked; a price more
    than PRICE_RISE_DROP above the coupon's drops the leg and the slips are
    rebuilt; a lower fresh price replaces the coupon's (the measured chance
    with it); each round asks only legs not asked yet."""
    legs = [_leg(1, 1.52, 0.70), _leg(2, 1.40, 0.70), _leg(3, 1.45, 0.60)]
    asked: list[list[int]] = []
    fresh = {1: sb.FreshPrice(sb.FRESH_OK, 1.65, "2026-10-20T07:59:00Z"),
             2: sb.FreshPrice(sb.FRESH_OK, 1.38, "2026-10-20T07:59:00Z"),
             3: sb.FreshPrice(sb.FRESH_OK, 1.46, "2026-10-20T07:59:00Z")}

    def ask(chosen: Any) -> dict[tuple[Any, ...], sb.FreshPrice]:
        asked.append(sorted(g["sofascore_event_id"] for g in chosen))
        return {sb.fresh_key(g): fresh[g["sofascore_event_id"]] for g in chosen}

    res = sb.build(legs, NOW, target=1.9, fresh_prices=ask)
    picked = {x.leg["sofascore_event_id"]: x for x in res.slips[0].legs}
    assert sorted(picked) == [2, 3]
    assert asked == [[1, 2], [3]]
    assert picked[2].odds == 1.38 and picked[2].coupon_odds == 1.40
    assert picked[2].chance == pytest.approx(min(0.70, 1 / 1.38))
    assert picked[3].odds == 1.46  # +0.7%: under the drop, the fresh price stands
    assert res.refused == {"kurs urósł > 2% od kuponu (rynek przeciw)": 1}
    text = sb.render(res, day="2026-10-20", target=1.9, now=NOW)
    assert "| 1.38 | 1.40 → 1.38 |" in text
    assert sb.NO_EDGE in text


def test_a_leg_gone_from_the_offer_drops_and_an_unasked_one_is_marked() -> None:
    legs = [_leg(1, 1.45, 0.70), _leg(2, 1.42, 0.70), _leg(3, 1.40, 0.68)]

    def ask(chosen: Any) -> dict[tuple[Any, ...], sb.FreshPrice]:
        out = {}
        for g in chosen:
            if g["sofascore_event_id"] == 1:
                out[sb.fresh_key(g)] = sb.FreshPrice(sb.FRESH_GONE)
        return out  # 2 and 3: nothing back = not asked (breaker, error)

    res = sb.build(legs, NOW, target=1.9, fresh_prices=ask)
    assert sorted(x.leg["sofascore_event_id"] for x in res.slips[0].legs) == [2, 3]
    assert all(x.fresh == sb.FRESH_NOT_ASKED for x in res.slips[0].legs)
    assert res.refused == {"zeszła z oferty Superbetu (świeży kurs)": 1}
    text = sb.render(res, day="2026-10-20", target=1.9, now=NOW)
    assert "**nie dopytano**" in text
    offline = sb.build(legs, NOW, target=1.9)
    assert "| nie dopytano |" in sb.render(offline, day="2026-10-20", target=1.9,
                                           now=NOW)


def test_the_evidence_columns_stand_beside_the_price() -> None:
    """Every signal next to 1/odds: model, own sample, match-up, league, h2h,
    referee - display only (no ranking, no gate)."""
    from bet.sofa.dossier import matchup_key

    leg = _leg(1, 1.30, 0.75, forecast_p=0.81, sample_size=10, sample_hit_rate=0.9)
    res = sb.build([leg], NOW, target=1.25)
    ev = {matchup_key(leg): {"league": "150/228 (Liga)", "h2h": "2/3",
                             "referee": "11/20"}}
    text = sb.render(res, day="2026-10-20", target=1.25, now=NOW,
                     matchups={matchup_key(leg):
                               "zestawienie: A1 9/10 · B1 traci 7/10"},
                     evidence=ev)
    row = next(r for r in text.splitlines() if r.startswith("| 20.10"))
    assert ("| 76,9% | 75,0% | 75,0% | **tak** | 81,0% | 9/10 (90,0%) | "
            "A1 9/10 · B1 traci 7/10 | 150/228 (Liga) | 2/3 | 11/20 |") in row


def test_sport_fresh_reads_the_newest_snapshot_before_the_start(tmp_path: Path) -> None:
    day = tmp_path / "shadow" / "basketball" / "2026-10-31"
    day.mkdir(parents=True)
    line = {"superbet_event_id": "77", "market_id": 759, "family": "winner",
            "period": 0, "subject": "", "line": None, "side": "T2"}
    snaps = [
        {"fetched_at_utc": "2026-10-31T09:00:00Z", "superbet_event_id": "77",
         "kickoff_utc": "2026-10-31T18:30:00Z", "lines": [{**line, "odds": 1.52}]},
        {"fetched_at_utc": "2026-10-31T17:50:00Z", "superbet_event_id": "77",
         "kickoff_utc": "2026-10-31T18:30:00Z", "lines": [{**line, "odds": 1.65}]},
        {"fetched_at_utc": "2026-10-31T18:40:00Z", "superbet_event_id": "77",
         "kickoff_utc": "2026-10-31T18:30:00Z", "lines": [{**line, "odds": 3.10}]},
    ]
    (day / "snapshots.jsonl").write_text("".join(json.dumps(s) + "\n" for s in snaps))
    leg = {"sport": "basketball", "source_date": "2026-10-31",
           "superbet_event_id": "77",
           "market_id": 759, "family": "winner", "period": 0, "subject": "",
           "line": None, "side": "T2", "kickoff_utc": "2026-10-31T18:30:00Z",
           "price_fetched_at_utc": "2026-10-31T09:00:00Z"}
    got = build_slip.sport_fresh(str(tmp_path), leg)
    assert got == sb.FreshPrice(sb.FRESH_OK, 1.65, "2026-10-31T17:50:00Z")
    gone = build_slip.sport_fresh(str(tmp_path), {**leg, "side": "T1"})
    assert gone.status == sb.FRESH_GONE
    stale = build_slip.sport_fresh(
        str(tmp_path), {**leg, "price_fetched_at_utc": "2026-10-31T18:00:00Z"})
    assert stale.status == sb.FRESH_NOT_ASKED


def test_a_sample_below_the_price_is_bold_never_a_gate() -> None:
    """31.10: a volleyball set at 1.58 stood on 3 of 8 (37.5%) - shown bold
    beside 1/odds; measured, such legs were no worse, so it stays."""
    leg = {"sample_size": 8, "sample_hit_rate": 0.375}
    assert sb._sample(leg, 1.58) == "**3/8 (37,5%)**"
    assert sb._sample(leg, 3.0) == "3/8 (37,5%)"
    assert sb.sample_refusal(leg) is None


def test_json_out_records_slips_keyed_as_coupon_results(tmp_path: Path) -> None:
    from bet.sofa.coupon_results import key_of

    day = "2026-10-20"
    run = tmp_path / day
    run.mkdir()
    legs = [_leg(1, 1.5, 0.7, kickoff="2099-01-01T00:00:00Z"),
            _leg(2, 1.5, 0.7, kickoff="2099-01-01T00:00:00Z")]
    (run / "11_coupon.json").write_text(json.dumps({"singles": legs}), encoding="utf-8")
    out = tmp_path / "slip.json"
    assert build_slip.main(["--date", day, "--target", "2", "--runs-dir", str(tmp_path),
                            "--no-fresh-price", "--json-out", str(out)]) == 0
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rec["schema"] == sb.SLIP_RECORD_SCHEMA
    assert rec["params"]["target"] == 2.0 and rec["requested"] == 1
    (slip,) = rec["slips"]
    assert slip["reached"] and len(slip["legs"]) == 2
    assert {g["result_key"] for g in slip["legs"]} == {key_of(g) for g in legs}
    assert all(g["odds"] == 1.5 and g["coupon_odds"] == 1.5 for g in slip["legs"])
    assert slip["legs"][0]["superbet_selection"] == "powyżej 7.5"


def test_slip_read_set_hands_the_matchs_earlier_section(tmp_path: Path) -> None:
    from bet.sofa import analyses

    run = tmp_path / "run"
    run.mkdir()
    section = {"author": "analyst", "report": "r.md", "recorded_at_utc": "T",
               "web_tags": ["[WEB: x, publ. 1.11]"], "context_pass": True}
    (run / analyses.STORE).write_text(json.dumps(
        {"version": analyses.VERSION, "events": {"1": [section]}}), encoding="utf-8")
    res = sb.build([_leg(1, 1.5, 0.7), _leg(2, 1.5, 0.7)], NOW, target=2.2)
    build_slip.write_read_set(tmp_path / "rs", res, run, fetch_h2h=False,
                              fetch_lineups=False)
    rows = json.loads((tmp_path / "rs" / "read_set_slip_football.json").read_text())
    prior = {r["sofascore_event_id"]: r.get("prior_analysis") for r in rows}
    assert prior[2] is None
    assert prior[1] is not None and prior[1]["report"] == "r.md"
    assert prior[1]["full_pass_report"] == "r.md"
    assert rows[0]["slip_price"]["fresh"] == sb.FRESH_NOT_ASKED
    assert rows[0]["slip_price"]["odds"] == rows[0]["slip_price"]["coupon_odds"] == 1.5


def test_the_safest_slip_takes_the_surest_legs_above_the_cash_floor() -> None:
    """Operator 2026-11-01 ("chcę żeby weszło, nawet jak mniej zarobimy"):
    at a price target the search took 1.40 legs at ~71%; the safest mode
    takes the highest measured chance whose price product still pays back
    more than the stake after tax (SAFE_TARGET 1.14)."""
    assert sb.SAFE_TARGET == 1.14 and sb.SAFE_TARGET > sb.SINGLE_CASH_FLOOR
    legs = [_leg(1, 1.40, 0.71), _leg(2, 1.16, 0.86), _leg(3, 1.11, 0.90),
            _leg(4, 1.10, 0.89)]
    safe = sb.build(legs, NOW, sb.SAFE_TARGET, safe=True)
    # a 1.11 single pays back less than the stake; 1.16 alone (0.86) is surer
    # than 1.11 x 1.10 (0.90 x 0.89 = 0.80) and than the 1.40 leg
    assert [x.leg["sofascore_event_id"] for x in safe.slips[0].legs] == [2]
    assert safe.safe
    # a kept slip stands only within SAFE_KEEP_TOLERANCE of the pool's best
    keep = [_read(1, 7.5, "KEEP")]
    kept = sb.build(legs, NOW, sb.SAFE_TARGET, slip_reads=keep, safe=True)
    assert [x.leg["sofascore_event_id"] for x in kept.slips[0].legs] == [2]
    close = [_read(1, 7.5, "KEEP")]
    near = [_leg(1, 1.15, 0.855), *legs[1:]]  # 0.5 pp below the best
    held = sb.build(near, NOW, sb.SAFE_TARGET, slip_reads=close, safe=True)
    assert [x.leg["sofascore_event_id"] for x in held.slips[0].legs] == [1]
    # the default search keeps read legs at any chance
    default = sb.build(legs, NOW, sb.SAFE_TARGET, slip_reads=keep)
    assert [x.leg["sofascore_event_id"] for x in default.slips[0].legs] == [1]
    text = sb.render(safe, day="2026-10-20", target=sb.SAFE_TARGET, now=NOW)
    assert "Tryb pewny" in text and "≥ 1,14" in text
    assert "wygrana przy iloczynie 1,16 zwraca ok. +2% stawki" in text
    assert "Tryb pewny" not in sb.render(default, day="2026-10-20",
                                         target=sb.SAFE_TARGET, now=NOW)


def test_safest_cli_raises_a_low_target_to_the_cash_floor(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    day = "2026-10-20"
    run = tmp_path / day
    run.mkdir()
    far = "2099-01-01T00:00:00Z"
    (run / "11_coupon.json").write_text(json.dumps({"singles": [
        _leg(1, 1.11, 0.90, kickoff=far), _leg(2, 1.16, 0.86, kickoff=far),
        _leg(3, 1.35, 0.72, kickoff=far)]}), encoding="utf-8")
    base = ["--date", day, "--runs-dir", str(tmp_path), "--no-fresh-price"]
    assert build_slip.main([*base, "--safest"]) == 0
    out = capsys.readouterr().out
    assert "na ~1.14" in out and "Tryb pewny" in out and "A2 - B2" in out
    assert build_slip.main([*base, "--safest", "--target", "1.05"]) == 0
    assert "na ~1.14" in capsys.readouterr().out
    assert build_slip.main([*base, "--safest", "--target", "1.3"]) == 0
    out = capsys.readouterr().out
    assert "≥ 1,30" in out and "A3 - B3" in out


def test_the_safest_slip_rule_holds_on_the_closest_under_target_path() -> None:
    """Review 11-01: when no slip reaches the target the closest-under slip
    went through the default keep-first pick; in the safe mode it compares
    with the pool's surest too."""
    legs = [_leg(1, 1.20, 0.70), _leg(2, 1.20, 0.82)]
    keep = [_read(1, 7.5, "KEEP")]
    safe = sb.build(legs, NOW, 1.3, slip_reads=keep, max_legs=1, safe=True)
    assert safe.slips[0].needs_legs is not None
    assert [x.leg["sofascore_event_id"] for x in safe.slips[0].legs] == [2]
    default = sb.build(legs, NOW, 1.3, slip_reads=keep, max_legs=1)
    assert [x.leg["sofascore_event_id"] for x in default.slips[0].legs] == [1]
