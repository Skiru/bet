"""The tennis gender x tier x surface prior (bet.sofa.tennis_prior).

A tennis rung with no ladder fell into the football baseline lookup, keyed on
a competition id that is one week of one tournament, so it reached the global
pool (sets_total n=101, every level together) or no prior at all.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureSamples, MetricSample, Observation
from bet.sofa.tennis_prior import (
    MIN_TIER_OBSERVATIONS,
    TIER_PRIOR_METRICS,
    fit_tier_baselines,
    gender_of,
    tier_key,
    tier_prior,
)
from scripts.sofa.fit_constants import MIN_BASELINE_OBSERVATIONS
from scripts.sofa.run_sheet import process_fixture
from tests.sofa.test_sheet import make_fixture, make_offer, rung


def _match(
    event_id: int,
    sets: list[tuple[int, int]],
    category: str = "ITF Men",
    ground: str = "Hardcourt outdoor",
    description: str = "Ended",
    player_type: int = 1,
) -> dict[str, Any]:
    home = {f"period{i}": h for i, (h, _) in enumerate(sets, 1)}
    away = {f"period{i}": a for i, (_, a) in enumerate(sets, 1)}
    home["current"] = sum(h > a for h, a in sets)
    away["current"] = sum(a > h for h, a in sets)
    return {
        "id": event_id,
        "startTimestamp": 1_750_000_000 + event_id,
        "status": {"type": "finished", "description": description},
        "homeTeam": {"id": 1, "type": player_type},
        "awayTeam": {"id": 2, "type": player_type},
        "homeScore": home,
        "awayScore": away,
        "groundType": ground,
        "tournament": {"category": {"name": category, "sport": {"slug": "tennis"}}},
    }


def test_the_tier_bar_is_the_league_bar() -> None:
    assert MIN_TIER_OBSERVATIONS == MIN_BASELINE_OBSERVATIONS


def test_keys_split_gender_tier_and_surface_family() -> None:
    assert gender_of("ITF Women") == "W" and gender_of("WTA 125") == "W"
    assert gender_of("Challenger") == "M" and gender_of("ATP") == "M"
    assert tier_key("ITF Women", "Red clay") == "tennis:W:ITF:clay"
    assert tier_key("Challenger", "Hardcourt indoor") == "tennis:M:CH:hard"
    assert tier_key("WTA", "Grass") == "tennis:W:TOUR:grass"
    assert tier_key(None, "Clay") is None


def test_fit_counts_each_match_once_and_only_completed_best_of_three() -> None:
    straight = [_match(i, [(6, 3), (6, 4)]) for i in range(MIN_TIER_OBSERVATIONS)]
    noise = [
        _match(900, [(6, 0), (6, 0)], description="Retired"),
        _match(901, [(6, 0), (6, 0)], player_type=2),  # doubles
        _match(902, [(6, 0), (6, 0), (6, 0)]),  # best of five
    ]
    # The same match sits in both players' listings.
    events = straight + straight[:5] + noise
    got = fit_tier_baselines(events, lambda _id: None, ["games_total", "sets_total"])
    assert got["games_total"]["tennis:M:ITF:hard"] == {"mean": 19.0,
                                                        "n": MIN_TIER_OBSERVATIONS}
    assert got["sets_total"]["tennis:M:ITF:hard"]["mean"] == 2.0


def test_a_level_below_the_evidence_bar_has_no_entry() -> None:
    events = [_match(i, [(6, 3), (6, 4)]) for i in range(MIN_TIER_OBSERVATIONS - 1)]
    assert fit_tier_baselines(events, lambda _id: None, ["games_total"]) == {}


def test_only_the_measured_metrics_get_a_tier_prior() -> None:
    assert TIER_PRIOR_METRICS == {
        "aces_for", "aces_total", "double_faults_for", "double_faults_total",
        "games_total", "sets_total"}
    events = [_match(i, [(6, 3), (6, 4)]) for i in range(MIN_TIER_OBSERVATIONS)]
    # games_won_for loses out of sample; per-set games were never measured.
    for metric in ("games_won_for", "games_won_set1_for", "games_set1_total"):
        assert fit_tier_baselines(events, lambda _id: None, [metric]) == {}
        baselines = {metric: {"tennis:M:ITF:hard": {"mean": 10.0, "n": 99}}}
        assert tier_prior(baselines, metric, "ITF Men", "Hard") is None


def test_lookup_names_where_the_prior_came_from() -> None:
    baselines = {"aces_total": {"tennis:W:ITF:clay": {"mean": 2.1, "n": 1652}}}
    got = tier_prior(baselines, "aces_total", "ITF Women", "Red clay")
    assert got is not None
    mean, note = got
    assert mean == 2.1
    assert note.startswith(
        "PRIOR_FROM_TENNIS_TIER: tennis:W:ITF:clay mean 2.1 over 1652")
    assert tier_prior(baselines, "aces_total", "ITF Men", "Red clay") is None


def _obs(ids: range, value: float) -> list[Observation]:
    return [
        Observation(sofascore_event_id=i,
                    match_date_utc=datetime(2026, 9, 1, tzinfo=UTC),
                    opponent="x", value=value, competition_id=5000 + i,
                    season_id=1, venue="home")
        for i in ids
    ]


def test_sheet_shrinks_a_ladderless_tennis_row_toward_its_tier() -> None:
    fixture = make_fixture(sport="tennis", category_name="ITF Women",
                           ground_type="Red clay", competition_id=31139)
    samples = FixtureSamples(
        sofascore_event_id=1, readiness="READY",
        metrics={"aces_total": MetricSample(
            metric="aces_total", side_a=_obs(range(100, 110), 6.0),
            side_b=_obs(range(200, 210), 6.0), h2h=[])},
        gaps=[])
    # One-sided: no ladder can be fitted, which is the case this prior is for.
    offer = make_offer([rung(4.5, 1.80, None, market="aces_total")])
    common: dict[str, Any] = dict(
        baselines={"aces_total": {"global": {"mean": 5.579, "n": 601}}},
        reliability={}, engine_constants={}, vetoes=[], config=SofaConfig())

    tiers = {"aces_total": {"tennis:W:ITF:clay": {"mean": 2.0, "n": 1652}}}
    rows, _ = process_fixture(fixture, samples, offer, tennis_tiers=tiers, **common)
    before, _ = process_fixture(fixture, samples, offer, **common)
    assert rows and before
    assert any(n.startswith("PRIOR_FROM_TENNIS_TIER") for n in rows[0].notes)
    assert not any(n.startswith("PRIOR_FROM_TENNIS_TIER") for n in before[0].notes)
    # Women's ITF clay serves far fewer aces than the all-levels pool.
    assert rows[0].centre < before[0].centre


def test_the_tier_file_is_read_from_the_env_override(
    tmp_path: Any, monkeypatch: Any
) -> None:
    import json

    from scripts.sofa.run_sheet import load_tennis_tier_baselines

    path = tmp_path / "tiers.json"
    path.write_text(json.dumps({"metrics": {"aces_total": {"tennis:M:ITF:hard": {
        "mean": 6.0, "n": 99}}}}))
    monkeypatch.setenv("SOFA_TENNIS_TIER_BASELINES", str(path))
    assert load_tennis_tier_baselines(SofaConfig()) == {
        "aces_total": {"tennis:M:ITF:hard": {"mean": 6.0, "n": 99}}}
    monkeypatch.setenv("SOFA_TENNIS_TIER_BASELINES", str(tmp_path / "absent.json"))
    assert load_tennis_tier_baselines(SofaConfig()) == {}


def test_a_best_of_five_match_is_not_pulled_toward_a_best_of_three_level() -> None:
    samples = FixtureSamples(
        sofascore_event_id=1, readiness="READY",
        metrics={"aces_total": MetricSample(
            metric="aces_total", side_a=_obs(range(100, 110), 20.0),
            side_b=_obs(range(200, 210), 20.0), h2h=[])},
        gaps=[])
    offer = make_offer([rung(18.5, 1.80, None, market="aces_total")])
    tiers = {"aces_total": {"tennis:M:TOUR:hard": {"mean": 12.0, "n": 900}}}
    for periods, expect in ((5, False), (3, True)):
        fixture = make_fixture(sport="tennis", category_name="ATP",
                               ground_type="Hardcourt outdoor",
                               default_period_count=periods)
        rows, _ = process_fixture(
            fixture, samples, offer, baselines={}, reliability={},
            engine_constants={}, vetoes=[], config=SofaConfig(), tennis_tiers=tiers)
        assert rows
        tagged = any(n.startswith("PRIOR_FROM_TENNIS_TIER") for n in rows[0].notes)
        assert tagged is expect, periods
