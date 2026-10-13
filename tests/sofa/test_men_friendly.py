"""Men's national-team friendlies (851) - the goal sample window and the goals
prior, behind epochs.MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC and
MEN_FRIENDLY_BASELINE_FROM_UTC (both None: the operator decides).
Evidence: docs/sofa/evidence/national_friendly_samples_2026-10-13.md.
Off = byte-identical; on = synthetic fixtures. Offline and fast."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bet.sofa import epochs
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureSamples, Observation
from bet.sofa.men_friendly import (
    MEN_FRIENDLY_COMPETITION_ID,
    FriendlyBaseline,
    baseline_from_events,
    is_men_friendly_fixture,
    pick_friendly_window,
)
from bet.sofa.samples import process_fixture_samples
from scripts.sofa.run_sheet import sample_centre

KICKOFF = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
HOME, AWAY = 4700, 4701
WCQ = 11  # a competitive national-team competition


def _played(eid: int, days_ago: int, home: int, away: int, hs: int, as_: int,
            comp: int, unique: str = "World Cup Qual.") -> dict[str, Any]:
    return {
        "id": eid,
        "tournament": {
            "name": unique,
            "category": {"name": "World", "sport": {"slug": "football"}},
            "uniqueTournament": {"id": comp, "name": unique,
                                 "slug": "int-friendly-games"
                                 if comp == MEN_FRIENDLY_COMPETITION_ID else "x"},
        },
        "roundInfo": {"round": 1},
        "status": {"type": "finished", "code": 100},
        "startTimestamp": int((KICKOFF - timedelta(days=days_ago)).timestamp()),
        "homeTeam": {"id": home, "name": f"N{home}", "national": True},
        "awayTeam": {"id": away, "name": f"N{away}", "national": True},
        "homeScore": {"current": hs, "period1": hs, "period2": 0, "normaltime": hs},
        "awayScore": {"current": as_, "period1": as_, "period2": 0,
                      "normaltime": as_},
        "season": {"id": 1},
    }


def _listings(friendly_comp: int) -> dict[int, list[dict[str, Any]]]:
    home = [
        # twelve competitive matches, days 10..120, 1-0
        *(_played(100 + i, 10 * (i + 1), HOME, 900 + i, 1, 0, WCQ)
          for i in range(12)),
        # six friendlies, days 5..55, 3-0
        *(_played(200 + i, 5 + 10 * i, HOME, 950 + i, 3, 0, friendly_comp,
                  "International Friendly Games") for i in range(6)),
    ]
    away = [_played(300 + i, 6 + 7 * i, AWAY, 980 + i, 1, 1, WCQ) for i in range(10)]
    return {HOME: home, AWAY: away}


def _fixture(comp: int) -> Fixture:
    return Fixture(
        sofascore_event_id=17100001, superbet_event_ids=["1"], sport="football",
        kickoff_utc=KICKOFF, home_name=f"N{HOME}", away_name=f"N{AWAY}",
        home_entity_id=HOME, away_entity_id=AWAY,
        competition_name="International Friendly Games", competition_id=comp,
        season_id=1, category_name="World", identity="CONFIRMED", round_number=None,
        round_name=None, cup_round_type=None, previous_leg_event_id=None,
        venue_name=None, referee=None, ground_type=None, default_period_count=2,
    )


def _sample(tmp_path: Path, comp: int, *, listings_comp: int | None = None,
            **kw: Any) -> FixtureSamples:
    from bet.sofa.db import migrate

    db = str(tmp_path / f"t_{comp}_{sorted(kw.items())}.db")
    migrate(db)
    cache = SofaCache(SofaConfig(db_path=db))
    listings = _listings(listings_comp if listings_comp is not None else comp)
    client = MagicMock()
    client.entity_events.side_effect = lambda eid, kind, page: (
        {"events": listings[eid], "hasNextPage": False} if page == 0 else None
    )
    client.event_statistics.return_value = {"statistics": []}
    client.event_incidents.return_value = {}
    superbet = MagicMock()
    superbet.event_odds.return_value = {"odds": [
        {"marketName": "Liczba goli"},
        {"marketName": f"N{HOME} - liczba goli"},
        {"marketName": f"1. polowa - N{HOME} - liczba goli"},
    ]}
    return process_fixture_samples(
        _fixture(comp), client, cache, superbet,
        SofaConfig(sample_n=10, min_sample=5), **kw)


def _ids(res: FixtureSamples, metric: str, side: str = "side_a") -> set[int]:
    return {o.sofascore_event_id for o in getattr(res.metrics[metric], side)}


# --- the switches ---------------------------------------------------------------


def test_both_switches_are_off_until_the_operator_decides() -> None:
    assert epochs.MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC is None
    assert epochs.MEN_FRIENDLY_BASELINE_FROM_UTC is None
    assert not epochs.men_friendly_sample_window("2030-01-01")
    assert not epochs.men_friendly_baseline("2030-01-01")


def test_a_switch_reads_the_day_and_the_build_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC", at)
    monkeypatch.setattr(epochs, "MEN_FRIENDLY_BASELINE_FROM_UTC", at)
    for fn in (epochs.men_friendly_sample_window, epochs.men_friendly_baseline):
        assert fn("2026-10-15", at)
        assert not fn("2026-10-14", at)
        assert not fn("2026-10-15", at - timedelta(minutes=1))


def test_only_the_mens_friendly_is_one() -> None:
    assert is_men_friendly_fixture("football", 851)
    assert not is_men_friendly_fixture("football", 852)
    assert not is_men_friendly_fixture("football", WCQ)
    assert not is_men_friendly_fixture("basketball", 851)


# --- variant C ----------------------------------------------------------------


def test_the_window_is_every_match_since_the_oldest_of_the_newest_friendlies() -> None:
    # (ts, competition), newest first
    pool = [(100, 851), (95, 11), (90, 851), (80, 851), (70, 11), (60, 851),
            (50, 851), (40, 11), (30, 851), (20, 11)]
    got = pick_friendly_window(pool, 851, 5, lambda p: p[1], lambda p: True,
                               lambda p: p[0])
    # the newest five 851 matches reach back to ts 50
    assert got == pool[:7]
    # n caps the friendlies only: the window may hold more than n matches
    assert len(got) > 5


def test_below_the_minimum_or_a_knockout_reads_the_newest_n() -> None:
    pool = [(100, 851), (95, 11), (90, 11), (80, 11), (70, 851), (60, 11)]
    assert pick_friendly_window(pool, 851, 4, lambda p: p[1], lambda p: True,
                                lambda p: p[0]) == pool[:4]
    full = [(100 - i, 851) for i in range(8)]
    assert pick_friendly_window(full, 851, 4, lambda p: p[1], lambda p: True,
                                lambda p: p[0], knockout=True) == full[:4]


# --- SAMPLES --------------------------------------------------------------------


def test_off_the_mens_friendly_reads_the_newest_competitive_matches(
    tmp_path: Path,
) -> None:
    res = _sample(tmp_path, 851)
    assert _ids(res, "goals_total") == {100 + i for i in range(10)}
    assert all(o.value == 1.0 for o in res.metrics["goals_for"].side_a)


def test_off_is_byte_identical(tmp_path: Path) -> None:
    default = _sample(tmp_path, 851)
    off = _sample(tmp_path, 851, men_friendly_window=False)
    assert default.model_dump_json() == off.model_dump_json()


@pytest.mark.parametrize("comp", [852, WCQ])
def test_on_leaves_every_other_fixture_alone(tmp_path: Path, comp: int) -> None:
    off = _sample(tmp_path, comp)
    on = _sample(tmp_path, comp, men_friendly_window=True)
    assert on.model_dump_json() == off.model_dump_json()


def test_on_the_mens_friendly_reads_the_friendly_window(tmp_path: Path) -> None:
    off = _sample(tmp_path, 851)
    on = _sample(tmp_path, 851, men_friendly_window=True)
    # six friendlies (days 5..55) and the five competitive matches since
    window = {200 + i for i in range(6)} | {100 + i for i in range(5)}
    assert _ids(on, "goals_total") == window
    assert _ids(on, "goals_for") == window
    assert sorted(o.value for o in on.metrics["goals_for"].side_a) == (
        [1.0] * 5 + [3.0] * 6)
    # the away side has no friendlies: its newest ten, as before
    assert _ids(on, "goals_total", "side_b") == _ids(off, "goals_total", "side_b")
    # half-match goals are not measured: the usual sample
    assert (on.metrics["goals_1h_for"].model_dump_json()
            == off.metrics["goals_1h_for"].model_dump_json())


# --- the baseline ---------------------------------------------------------------


def test_the_baseline_is_the_as_of_mean_of_mens_friendlies() -> None:
    cut = int(KICKOFF.timestamp())
    friendlies = [_played(1000 + i, 30 + i, 1, 2, 2, 1, 851) for i in range(30)]
    noise = [
        _played(2000, 40, 1, 2, 9, 9, 852),           # women's
        _played(2001, 40, 1, 2, 9, 9, WCQ),           # competitive
        _played(2002, -1, 1, 2, 9, 9, 851),           # after the cut
    ]
    club = _played(2003, 40, 1, 2, 9, 9, 851)
    club["homeTeam"]["national"] = False
    b = baseline_from_events([*friendlies, *noise, club, friendlies[0]], cut)
    assert (b.mean_total, b.n) == (3.0, 30)
    total = b.prior("goals_total")
    side = b.prior("goals_for")
    assert total is not None and total[0] == 3.0
    assert total[1].startswith("PRIOR_MEN_FRIENDLY")
    assert side is not None and side[0] == 1.5
    assert b.prior("goals_1h_for") is None
    assert b.prior("corners_total") is None
    thin = baseline_from_events(friendlies[:29], cut)
    assert thin.mean_total is None and thin.prior("goals_total") is None


# --- SHEET ----------------------------------------------------------------------

BASELINES = {"goals_total": {"global": {"mean": 3.26, "n": 1000}},
             "goals_for": {"global": {"mean": 1.63, "n": 1000}},
             "corners_total": {"global": {"mean": 9.9, "n": 1000}}}
FRIENDLY = FriendlyBaseline(2.5, 2365, int(KICKOFF.timestamp()))


def _centre(fixture: Fixture, market: str, **kw: Any,
            ) -> tuple[float, list[str], list[str], tuple[float, str] | None]:
    obs = [Observation(sofascore_event_id=i, value=1.0,
                       match_date_utc=datetime(2026, 10, 1, tzinfo=UTC),
                       opponent="X", competition_id=WCQ, season_id=1,
                       venue="home") for i in range(10)]
    return sample_centre(
        fixture=fixture, market=market, subject="", n=10, mean=1.0,
        own_sides=[obs], own_events=set(), own_teams=[HOME],
        baselines=BASELINES, day_obs={}, football=None, tennis_tiers=None,
        engine_constants={}, k_centre=15.0, per_market_k_on=False, **kw)


def test_off_the_sheet_centre_is_byte_identical() -> None:
    fx = _fixture(851)
    assert _centre(fx, "goals_total") == _centre(
        fx, "goals_total", men_friendly_baseline=None)
    # the global pool, as today
    centre, notes, _u, _r = _centre(fx, "goals_total")
    assert centre == pytest.approx(0.4 * 1.0 + 0.6 * 3.26)
    assert any(n.startswith("PRIOR_GLOBAL") for n in notes)


def test_on_the_mens_friendly_shrinks_toward_its_own_baseline() -> None:
    fx = _fixture(851)
    centre, notes, _u, _r = _centre(fx, "goals_total", men_friendly_baseline=FRIENDLY)
    assert centre == pytest.approx(0.4 * 1.0 + 0.6 * 2.5)
    assert any(n.startswith("PRIOR_MEN_FRIENDLY") for n in notes)
    assert not any(n.startswith("PRIOR_GLOBAL") for n in notes)
    centre_f, _n, _u, _r = _centre(fx, "goals_for", men_friendly_baseline=FRIENDLY)
    assert centre_f == pytest.approx(0.4 * 1.0 + 0.6 * 1.25)
    # an unmeasured market and any other fixture: as before
    assert _centre(fx, "corners_total", men_friendly_baseline=FRIENDLY) == _centre(
        fx, "corners_total")
    for comp in (852, WCQ):
        other = _fixture(comp)
        assert (_centre(other, "goals_total", men_friendly_baseline=FRIENDLY)
                == _centre(other, "goals_total"))


def test_a_thin_baseline_falls_back_to_the_usual_prior() -> None:
    fx = _fixture(851)
    thin = FriendlyBaseline(None, 12, int(KICKOFF.timestamp()))
    assert _centre(fx, "goals_total", men_friendly_baseline=thin) == _centre(
        fx, "goals_total")
