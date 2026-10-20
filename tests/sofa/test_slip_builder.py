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
    assert got[0] == pytest.approx(0.80)
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
    assert "to nie jest kurs kuponu" in text
    assert "2 nogi" in text
    assert math.isclose(res.slips[0].chance, (1 / 1.5 - 0.008) ** 2)


def test_script_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    day = "2026-10-20"
    assert (
        build_slip.main(["--date", day, "--target", "2", "--runs-dir", str(tmp_path)])
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
        build_slip.main(["--date", day, "--target", "2", "--runs-dir", str(tmp_path)])
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
