"""F54 — per-player markets, football and tennis.

Two families that look alike and are not:

* **Tennis** already had the player as a side. What was missing was the
  *set-scoped* per-player games market — 827 priced markets on 166 of
  2026-09-22's tennis fixtures, all dropped — and it needed a metric, not a
  new axis. It is two-sided, so it can reach the coupon.
* **Football** needed a third axis: a subject who is neither side, a sample
  that is one person's appearances, and a source (`/lineups`) nothing else
  reads. Superbet quotes it one-sided, so it cannot reach the coupon while
  `NO_PRICE_ANCHOR` stands — and that is asserted here, deliberately, so a
  later change to that rule cannot let this family through unnoticed.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureOffer, GapReason, PricedRung
from bet.sofa.engine import uses_empirical_frequency
from bet.sofa.market_mapper import (
    classify_market,
    classify_player_market,
    get_mechanism_family,
    is_player_market,
)
from bet.sofa.metrics import TENNIS_METRICS, extract_metric
from bet.sofa.offer import OfferFetcher, parse_line
from bet.sofa.players import (
    PLAYER_METRICS,
    extract_player_metric,
    match_player,
    squad_statistics,
)
from bet.sofa.samples import (
    build_player_samples,
    metrics_from_offer,
    players_from_offer,
)

LINEUPS_EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "sofa"
    / "evidence"
    / "event_16363633_lineups.json"
)


@pytest.fixture(scope="module")
def lineups() -> dict[str, Any]:
    payload = json.loads(LINEUPS_EVIDENCE.read_text(encoding="utf-8"))
    body = payload["response"]["body"]
    assert isinstance(body, dict)
    return body


# ---------------------------------------------------------------------------
# tennis: a player's games in one set
# ---------------------------------------------------------------------------


def _tennis_event(**periods: int | None) -> dict[str, Any]:
    home = {f"period{i}": v for i, v in enumerate(periods["home"], start=1)}  # type: ignore[arg-type]
    away = {f"period{i}": v for i, v in enumerate(periods["away"], start=1)}  # type: ignore[arg-type]
    return {"homeScore": home, "awayScore": away, "status": {"code": 100}}


@pytest.mark.parametrize(
    ("metric", "is_home", "expected"),
    [
        ("games_won_set1_for", True, 6.0),
        ("games_won_set1_for", False, 4.0),
        ("games_won_set2_for", True, 3.0),
        ("games_won_set2_for", False, 6.0),
        ("games_won_set3_for", True, 7.0),
        ("games_won_set3_for", False, 5.0),
    ],
)
def test_set_games_come_from_the_set_score(
    metric: str, is_home: bool, expected: float
) -> None:
    """The listing's set score IS the quantity — no /statistics call at all.

    `gamesWon` is absent from /statistics on 35% of cached tennis events and
    is never keyed by set, while `check_identities` has always asserted
    sum(period1..5) == gamesWon. So this reads a term of an invariant the
    pipeline already enforces.
    """
    event = _tennis_event(home=[6, 3, 7], away=[4, 6, 5])
    assert extract_metric(metric, "tennis", {}, None, event, is_home) == expected


def test_an_unplayed_set_is_not_a_zero() -> None:
    """A straight-sets win has no third set, and Superbet voids that bet.

    Settling it at zero games would be the L1/L2 fabrication AND a wrong
    answer about the bet at the same time.
    """
    event = _tennis_event(home=[6, 6], away=[4, 2])
    assert (
        extract_metric("games_won_set3_for", "tennis", {}, None, event, True)
        is GapReason.STAT_KEY_ABSENT
    )


def test_a_tiebreak_set_counts_the_tiebreak_game() -> None:
    """7-6 is seven games and six, not six and six."""
    event = _tennis_event(home=[7], away=[6])
    assert extract_metric("games_won_set1_for", "tennis", {}, None, event, True) == 7.0


@pytest.mark.parametrize(
    ("name", "expected_market", "expected_player"),
    [
        ("1. set - Kenta Kawada liczba gemów", "games_won_set1_for", "kenta kawada"),
        (
            "2. set - Mirgiiaz Mirdzhaliev liczba gemów",
            "games_won_set2_for",
            "mirgiiaz mirdzhaliev",
        ),
    ],
)
def test_the_market_names_superbet_actually_sends(
    name: str, expected_market: str, expected_player: str
) -> None:
    assert classify_market(name) == (expected_market, expected_player)


def test_the_scope_prefix_on_the_line_is_checked_not_assumed() -> None:
    """Superbet sends the line as "1-4.5". A disagreeing prefix is refused.

    Taking the number and ignoring the prefix would price a set-2 quote on a
    set-1 ladder, which is worse than no rung at all.
    """
    assert parse_line("1-4.5", "games_won_set1_for") == 4.5
    assert parse_line("3-6.5", "games_won_set3_for") == 6.5
    with pytest.raises(ValueError, match="disagrees"):
        parse_line("2-4.5", "games_won_set1_for")


def test_a_set_is_a_scope_not_a_mechanism() -> None:
    """One fixture must not spend two coupon slots on the same fact."""
    for metric in ("games_won_set1_for", "games_won_set2_for", "games_won_set3_for"):
        assert get_mechanism_family(metric) == get_mechanism_family("games_won_for")


def test_per_set_games_is_priced_from_its_own_frequency() -> None:
    """The measured trough at five and wall at six — see
    docs/sofa/evidence/games_won_per_set_distribution.md. A normal CDF puts
    smooth density across a 4.4% gap and a 45.6% spike, and Superbet's 5.5
    rung sits exactly there.
    """
    for metric in ("games_won_set1_for", "games_won_set2_for", "games_won_set3_for"):
        assert metric in TENNIS_METRICS
        assert uses_empirical_frequency(metric)


# ---------------------------------------------------------------------------
# football: the classifier
# ---------------------------------------------------------------------------


def test_player_market_reads_subject_and_line_off_the_selection() -> None:
    """The market name carries neither. One name covers the whole squad."""
    assert classify_player_market(
        "Zawodnik - liczba celnych strzałów",
        "Castan, Luciano - powyżej 0.5",
        "sr:player:1011725-Castan, Luciano-0.5",
    ) == ("player_shots_on_target_for", "Castan, Luciano", 0.5, "OVER")


def test_a_hyphenated_name_does_not_eat_the_line() -> None:
    """The line is read from the END of specialBetValue, so a surname with a
    hyphen in it cannot be mistaken for the separator."""
    assert classify_player_market(
        "Zawodnik - liczba strzałów",
        "Alexander-Arnold, Trent - powyżej 1.5",
        "sr:player:99-Alexander-Arnold, Trent-1.5",
    ) == ("player_shots_for", "Alexander-Arnold, Trent", 1.5, "OVER")


def test_the_fallback_keeps_the_name_as_written() -> None:
    """Without a parseable specialBetValue the selection carries both, and the
    subject reaches the coupon the operator reads — accents and all."""
    assert classify_player_market(
        "Zawodnik - liczba strzałów", "Łukasz Kowalczyk - poniżej 1.5", None
    ) == ("player_shots_for", "Łukasz Kowalczyk", 1.5, "UNDER")


@pytest.mark.parametrize(
    "market_name",
    [
        # Sofascore's /lineups reports no body-part or location breakdown, so
        # pricing these off a total-shots sample would be inventing the split.
        "Zawodnik - liczba strzałów lewą nogą",
        "Zawodnik - liczba celnych strzałów głową",
        "Zawodnik - liczba celnych strzałów spoza pola karnego",
        # No line: a yes/no proposition, not a rung on a ladder.
        "Zawodnik - strzeli gola",
        "Zawodnik - otrzyma kartkę",
        # No identity in the payload proves an absent totalOffside is a zero.
        "Zawodnik - liczba spalonych",
    ],
)
def test_variants_we_cannot_source_stay_unmapped(market_name: str) -> None:
    """Exact folded names, never a prefix. A prefix rule would quietly price a
    left-footed shot line off a total-shots sample."""
    assert (
        classify_player_market(
            market_name, "Kowalski, Jan - powyżej 0.5", "sr:player:1-Kowalski, Jan-0.5"
        )
        is None
    )


def test_direction_is_read_not_defaulted() -> None:
    """Every one of the 437 player selections enumerated on 2026-09-22 said
    "powyżej" and none said "poniżej". A family that is one-sided today is not
    one-sided by definition, and a defaulted OVER would price the first UNDER
    Superbet posts as its own complement."""
    assert classify_player_market(
        "Zawodnik - liczba strzałów", "Kowalski, Jan - poniżej 2.5", None
    ) == ("player_shots_for", "Kowalski, Jan", 2.5, "UNDER")
    # A selection with no direction word at all is not a rung.
    assert (
        classify_player_market("Zawodnik - liczba strzałów", "Kowalski, Jan", None)
        is None
    )


def test_a_player_and_his_team_are_one_mechanism() -> None:
    for metric in PLAYER_METRICS:
        assert is_player_market(metric)
        assert get_mechanism_family(metric) == get_mechanism_family("shots_for")


# ---------------------------------------------------------------------------
# football: reading one player out of a real /lineups payload
# ---------------------------------------------------------------------------


def _find(squad: dict[str, dict[str, Any]], needle: str) -> dict[str, Any]:
    for name, stats in squad.items():
        if needle in name:
            return stats
    raise AssertionError(f"{needle!r} not in squad")


def test_squad_statistics_splits_the_two_sides(lineups: dict[str, Any]) -> None:
    home = squad_statistics(lineups, is_home=True)
    away = squad_statistics(lineups, is_home=False)
    assert home is not None and away is not None
    assert len(home) == 20 and len(away) == 20
    assert not set(home) & set(away)


def test_a_missing_payload_is_not_an_empty_squad() -> None:
    """None means "no squad list", which is a different fact from "nobody
    played" and must not be read as one."""
    assert squad_statistics(None, is_home=True) is None
    assert squad_statistics({"away": {"players": []}}, is_home=True) is None


def test_a_squad_member_who_did_not_play_yields_no_observation(
    lineups: dict[str, Any],
) -> None:
    """He carries `totalShots: 0` and no `minutesPlayed`. Counting that zero
    would be a fabrication AND wrong about the bet: Superbet voids a player
    market when the player does not appear, it does not settle it at zero.
    """
    home = squad_statistics(lineups, is_home=True)
    assert home is not None
    unused = _find(home, "gyokeres")
    assert unused.get("totalShots") == 0
    assert "minutesPlayed" not in unused
    assert (
        extract_player_metric("player_shots_for", unused)
        is GapReason.EVENT_NOT_FINISHED
    )


def test_an_absent_shot_on_target_is_a_zero_only_when_the_identity_closes(
    lineups: dict[str, Any],
) -> None:
    """Sofascore omits `onTargetScoringAttempt` for a player who had none —
    6 of the 31 who appeared carry it. The zero is taken because the payload
    proves it:

        totalShots == onTarget + offTarget + blocked + woodwork

    which held for 31 of 31 appearing players in this payload.
    """
    home = squad_statistics(lineups, is_home=True)
    assert home is not None
    keeper = _find(home, "raya")
    assert "onTargetScoringAttempt" not in keeper
    assert keeper["totalShots"] == 0
    assert extract_player_metric("player_shots_on_target_for", keeper) == 0.0


def test_the_identity_holds_for_every_player_who_appeared(
    lineups: dict[str, Any],
) -> None:
    """The evidence behind `zero_when_absent`, asserted rather than quoted."""
    checked = 0
    for is_home in (True, False):
        squad = squad_statistics(lineups, is_home=is_home)
        assert squad is not None
        for stats in squad.values():
            if "minutesPlayed" not in stats:
                continue
            parts = sum(
                float(stats.get(k, 0))
                for k in (
                    "onTargetScoringAttempt",
                    "shotOffTarget",
                    "blockedScoringAttempt",
                    "hitWoodwork",
                )
            )
            assert float(stats["totalShots"]) == parts
            checked += 1
    assert checked == 31


def test_an_absent_key_whose_identity_does_not_close_is_refused() -> None:
    """The remainder is not ours to invent. A player with three shots and one
    blocked has two unaccounted for, and "on target" is not the only thing
    they could have been."""
    stats = {"minutesPlayed": 90, "totalShots": 3, "blockedScoringAttempt": 1}
    assert (
        extract_player_metric("player_shots_on_target_for", stats)
        is GapReason.INTERNAL_INCONSISTENT
    )


def test_assists_are_never_defaulted() -> None:
    """`goalAssist` is written for all 31 players who appeared, including
    every zero, so an absent one is missing data."""
    assert PLAYER_METRICS["player_assists_for"]["zero_when_absent"] is False
    assert (
        extract_player_metric("player_assists_for", {"minutesPlayed": 90})
        is GapReason.STAT_KEY_ABSENT
    )
    assert (
        extract_player_metric(
            "player_assists_for", {"minutesPlayed": 90, "goalAssist": 0}
        )
        == 0.0
    )


# ---------------------------------------------------------------------------
# football: matching Superbet's name to a squad member
# ---------------------------------------------------------------------------


def test_superbet_writes_the_name_backwards(lineups: dict[str, Any]) -> None:
    away = squad_statistics(lineups, is_home=False)
    assert away is not None
    target = next(n for n in away if "sakamoto" in n)
    assert match_player("Sakamoto, Tatsuhiro", away) == target


def test_two_plausible_team_mates_are_refused_not_guessed() -> None:
    """A squad is a closed list competing for one match, so the failure mode
    is the wrong team-mate, not no match. A shots line priced against a
    team-mate's sample is F31 with a smaller subject, and nothing downstream
    could catch it on merit.

    Neither of these is the name Superbet wrote, and they score 92.9 and 90.3
    against it — two different people, one letter apart, and picking the
    higher is a coin flip dressed as a match.
    """
    squad = {"jose rodrigues": {}, "jose rodriguez jr": {}}
    assert match_player("Rodriguez, Jose", squad) is None


def test_a_squad_full_of_near_misses_is_refused_on_the_threshold() -> None:
    """Below 85 nothing is a match, however much better it is than the rest.

    The threshold is higher than `determine_side`'s 70 because a squad is a
    closed list of ~20 names competing for one match: the failure mode is the
    wrong team-mate, not no match.
    """
    squad = {"caue vinicius junior": {}, "caue vinicius silva": {}}
    assert match_player("Vinicius, Caue", squad) is None


def test_an_exact_match_still_wins_over_a_near_one() -> None:
    """The margin rule must not refuse the easy case: where one squad member
    IS the name and another merely resembles it, there is no ambiguity."""
    squad = {"bruno santos": {"id": 1}, "bruno dos santos": {"id": 2}}
    assert match_player("Santos, Bruno", squad) == "bruno santos"


def test_a_name_in_neither_squad_is_refused() -> None:
    assert match_player("Lionel Messi", {"david raya": {}, "bukayo saka": {}}) is None


# ---------------------------------------------------------------------------
# the stage wiring
# ---------------------------------------------------------------------------


def _rung(
    market: str, subject: str, line: float, over: float | None = 2.0
) -> PricedRung:
    return PricedRung(
        market=market,
        subject=subject,
        line=line,
        over_odds=over,
        under_odds=None,
        fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC),
    )


def test_a_player_metric_never_reaches_extract_metric() -> None:
    """It has no reading there. Asking would return STAT_KEY_ABSENT once per
    historical event per player and bury the real gaps under invented ones.
    """
    offer = FixtureOffer(
        sofascore_event_id=1,
        rungs=[
            _rung("player_shots_for", "Kowalski, Jan", 1.5),
            _rung("corners_total", "", 9.5),
        ],
        unmapped_markets=[],
    )
    assert metrics_from_offer(offer) == {"corners_total"}
    assert players_from_offer(offer) == {"player_shots_for": {"Kowalski, Jan"}}


def _result(event_id: int, squad: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "collected": {},
        "is_h2h": False,
        "halves_divergences": [],
        "squad": squad,
        "match_date_utc": datetime(2026, 9, 1 + event_id, tzinfo=UTC),
        "opponent": "Someone",
        "competition_id": 7,
        "season_id": 1,
        "venue": "home",
    }


def _played(shots: float, minutes: float = 90.0) -> dict[str, Any]:
    return {"minutesPlayed": minutes, "totalShots": shots}


def test_the_sample_is_the_player_s_appearances_not_the_team_s_matches() -> None:
    side_a = [
        _result(1, {"jan kowalski": _played(3.0)}),
        _result(2, {"jan kowalski": {"totalShots": 0}}),  # named, never came on
        _result(3, {"jan kowalski": _played(1.0, minutes=20.0)}),
        _result(4, {"piotr nowak": _played(2.0)}),  # not in the squad that day
    ]
    gaps: list[Any] = []
    samples = build_player_samples(
        {"player_shots_for": {"Kowalski, Jan"}},
        {"side_a": side_a, "side_b": []},
        gaps,
    )
    sample = samples["player_shots_for|Kowalski, Jan"]
    assert [o.value for o in sample.observations] == [1.0, 3.0]
    assert [o.minutes for o in sample.observations] == [20.0, 90.0]
    assert sample.side == "side_a"
    # The honest denominator: four matches carried a squad, he played two.
    assert sample.squad_matches == 4


def test_a_player_matching_both_squads_equally_is_refused() -> None:
    """Two different people, or one we cannot place. Either way the side is
    not decided by which list was iterated first."""
    squad = {"jan kowalski": _played(1.0)}
    gaps: list[Any] = []
    samples = build_player_samples(
        {"player_shots_for": {"Kowalski, Jan"}},
        {"side_a": [_result(1, squad)], "side_b": [_result(2, squad)]},
        gaps,
    )
    assert samples == {}
    assert [g.reason for g in gaps] == [GapReason.AMBIGUOUS_ENTITY]


def test_a_player_nobody_matched_says_so() -> None:
    gaps: list[Any] = []
    samples = build_player_samples(
        {"player_shots_for": {"Lionel Messi"}},
        {"side_a": [_result(1, {"jan kowalski": _played(1.0)})], "side_b": []},
        gaps,
    )
    assert samples == {}
    assert [g.reason for g in gaps] == [GapReason.NO_ENTITY_FOUND]


def test_offer_builds_player_rungs_from_a_real_payload() -> None:
    """The shape Superbet actually sends, recorded from event 13718742 on
    2026-09-22: one market name, the player and the line on the selection,
    and **no UNDER anywhere** — 437 "powyżej" and 0 "poniżej"."""
    items = [
        {
            "marketName": "Zawodnik - liczba celnych strzałów",
            "name": "Romarinho - powyżej 1.5",
            "specialBetValue": "sr:player:1112039-Romarinho-1.5",
            "price": 4.0,
        },
        {
            "marketName": "Zawodnik - liczba celnych strzałów",
            "name": "Romarinho - powyżej 2.5",
            "specialBetValue": "sr:player:1112039-Romarinho-2.5",
            "price": 10.0,
        },
    ]

    class _Client:
        def event_odds(self, _: str) -> dict[str, Any]:
            return {"odds": items}

    offer = OfferFetcher(_Client()).fetch_offers([_fixture()])[0]
    assert {(r.market, r.subject, r.line) for r in offer.rungs} == {
        ("player_shots_on_target_for", "Romarinho", 1.5),
        ("player_shots_on_target_for", "Romarinho", 2.5),
    }
    assert all(r.under_odds is None for r in offer.rungs)


def _fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["13718742"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 23, tzinfo=UTC),
        home_name="Criciúma",
        away_name="Operário-PR",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="Série B",
        competition_id=1,
        season_id=1,
        category_name="Brazil",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )


def test_lineups_are_only_fetched_when_a_player_market_asked(tmp_path: Path) -> None:
    """A squad list per historical event is 20 extra requests per fixture. On
    2026-09-22 four of 182 football fixtures carried a player rung, so the
    gate is the difference between ~80 requests a day and ~3,600."""
    from bet.sofa import samples as samples_mod

    config = dataclasses.replace(
        SofaConfig.from_env(), db_path=str(tmp_path / "t.db")
    )
    cache = SofaCache(config)
    calls: list[int] = []

    class _Client:
        def event_lineups(self, event_id: int) -> dict[str, Any]:
            calls.append(event_id)
            return {"home": {"players": []}}

    event = {"id": 42, "status": {"type": "finished"}}
    samples_mod.fetch_lineups(_Client(), cache, event)  # type: ignore[arg-type]
    samples_mod.fetch_lineups(_Client(), cache, event)  # type: ignore[arg-type]
    # Second call served from cache: a finished match's squad never changes.
    assert calls == [42]


def test_an_empty_answer_is_cached_as_a_fact(tmp_path: Path) -> None:
    """A tournament that publishes no squads must cost one request, not one
    per run — the F17 shape, in a new family."""
    from bet.sofa import samples as samples_mod

    config = dataclasses.replace(
        SofaConfig.from_env(), db_path=str(tmp_path / "t.db")
    )
    cache = SofaCache(config)
    calls: list[int] = []

    class _Client:
        def event_lineups(self, event_id: int) -> None:
            calls.append(event_id)
            return None

    event = {"id": 7, "status": {"type": "finished"}}
    assert samples_mod.fetch_lineups(_Client(), cache, event) is None  # type: ignore[arg-type]
    assert samples_mod.fetch_lineups(_Client(), cache, event) is None  # type: ignore[arg-type]
    assert calls == [7]


# ---------------------------------------------------------------------------
# SHEET: what each family can and cannot become
# ---------------------------------------------------------------------------


def _sheet(
    fixture: Fixture, samples: Any, offer: FixtureOffer
) -> list[Any]:
    from scripts.sofa.run_sheet import process_fixture

    rows, _skipped = process_fixture(
        fixture,
        samples,
        offer,
        baselines={},
        reliability={},
        engine_constants={},
        vetoes=[],
        config=SofaConfig(),
    )
    return rows


def _player_samples(values: list[float], minutes: float = 90.0) -> Any:
    from bet.sofa.contracts import FixtureSamples, Observation, PlayerSample

    return FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={},
        gaps=[],
        players={
            "player_shots_for|Romarinho": PlayerSample(
                metric="player_shots_for",
                player="Romarinho",
                matched_name="romarinho",
                side="side_a",
                squad_matches=10,
                observations=[
                    Observation(
                        sofascore_event_id=1000 + i,
                        match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
                        opponent=f"Opp{i}",
                        value=v,
                        minutes=minutes,
                        competition_id=1,
                        season_id=1,
                        venue="home",
                    )
                    for i, v in enumerate(values)
                ],
            )
        },
    )


def test_a_football_player_row_is_priced_off_the_player_s_own_sample() -> None:
    """The subject is a person, so the sample must be that person's — not the
    side's, and not a fuzzy guess at kick-off. SAMPLES did the name match
    against each historical squad; SHEET looks it up by the exact
    (market, subject) pair the rung carries."""
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[_rung("player_shots_for", "Romarinho", 1.5, over=2.6)],
        unmapped_markets=[],
    )
    rows = _sheet(_fixture(), _player_samples([3, 2, 4, 1, 3, 2, 5, 2, 3, 2]), offer)
    over = [r for r in rows if r.direction == "OVER"]
    assert len(over) == 1
    assert over[0].subject == "Romarinho"
    assert over[0].sample_size == 10
    assert over[0].sample_mean == pytest.approx(2.7)


def test_a_one_sided_player_rung_can_never_be_value() -> None:
    """The measurement that decides what this family is worth today.

    Superbet quotes football player counts on ONE side only — 437 "powyżej"
    and 0 "poniżej" across every player market on the 2026-09-22 board — so
    there is no complement to devig, `market_p` is None, and the row is
    selected by our model alone with no price checking it. That is precisely
    the population the settled record says loses: on 2026-09-19 the 71
    unanchored rows carried a median surplus of 4.95 against 0.24 for the
    anchored ones.

    So the family ships as a forecast and stops at LEAN. If `NO_PRICE_ANCHOR`
    is ever relaxed, this test is what says out loud that football player
    props start reaching the coupon on the same day.
    """
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        # A price far above anything the sample could justify, so nothing but
        # the missing anchor can be what holds the row back.
        rungs=[_rung("player_shots_for", "Romarinho", 1.5, over=30.0)],
        unmapped_markets=[],
    )
    rows = _sheet(_fixture(), _player_samples([3, 2, 4, 1, 3, 2, 5, 2, 3, 2]), offer)
    over = next(r for r in rows if r.direction == "OVER")
    assert over.market_p is None
    assert over.surplus is not None and over.surplus > 0
    assert over.verdict == "LEAN"
    assert any(n.startswith("NO_PRICE_ANCHOR") for n in over.notes)


def test_the_row_reports_the_minutes_behind_it() -> None:
    """A starter's ninety and a substitute's twelve are not two observations
    of the same quantity, and nothing else in the row can say so. Reported,
    never blocking — Superbet pays a player market out on a cameo, so a cameo
    is a real observation of a real bet, just a weaker one."""
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[_rung("player_shots_for", "Romarinho", 1.5, over=2.6)],
        unmapped_markets=[],
    )
    rows = _sheet(
        _fixture(), _player_samples([3, 2, 4, 1, 3, 2, 5, 2, 3, 2], minutes=18.0), offer
    )
    note = next(n for n in rows[0].notes if n.startswith("PLAYER_MINUTES"))
    assert "median 18'" in note
    assert "0/10 appearances of 60'+" in note
    assert "played 10 of 10 sampled matches" in note


def test_a_player_with_no_sample_is_skipped_not_guessed() -> None:
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[_rung("player_shots_for", "Someone Else", 1.5)],
        unmapped_markets=[],
    )
    from scripts.sofa.run_sheet import process_fixture

    rows, skipped = process_fixture(
        _fixture(),
        _player_samples([1, 2, 3]),
        offer,
        baselines={},
        reliability={},
        engine_constants={},
        vetoes=[],
        config=SofaConfig(),
    )
    assert rows == []
    assert [reason for _, reason, _ in skipped] == [GapReason.NO_ENTITY_FOUND]


def test_a_tennis_per_set_player_rung_can_reach_value() -> None:
    """The other half of the deliverable, and the difference that matters:
    Superbet quotes this one on BOTH sides, so it devigs, so it is checked by
    a price and can be staked. 827 of these were priced across 166 tennis
    fixtures on 2026-09-22 and every one was dropped."""
    from bet.sofa.contracts import FixtureSamples, MetricSample, Observation

    def obs(values: list[float], start: int) -> list[Observation]:
        return [
            Observation(
                sofascore_event_id=start + i,
                match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
                opponent=f"Opp{i}",
                value=v,
                competition_id=1,
                season_id=1,
                venue=None,
            )
            for i, v in enumerate(values)
        ]

    fixture = dataclasses_replace_tennis()
    samples = FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={
            "games_won_set1_for": MetricSample(
                metric="games_won_set1_for",
                side_a=obs([6, 6, 6, 7, 6, 6, 4, 6, 6, 6], 1000),
                side_b=obs([3, 2, 4, 1, 3, 2, 5, 2, 3, 2], 2000),
                h2h=[],
            )
        },
        gaps=[],
    )
    ladder = [
        PricedRung(
            market="games_won_set1_for",
            subject="Kenta Kawada",
            line=line,
            over_odds=over,
            under_odds=under,
            fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC),
        )
        for line, over, under in (
            (3.5, 1.41, 2.57),
            (4.5, 1.60, 2.20),
            (5.5, 2.60, 1.45),
        )
    ]
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", rungs=ladder, unmapped_markets=[]
    )
    rows = _sheet(fixture, samples, offer)
    assert rows, "the ladder produced no rows at all"
    # Two-sided, so every row carries a devigged market price — the check the
    # football family cannot have.
    assert all(r.market_p is not None for r in rows)
    assert {r.verdict for r in rows} <= {"VALUE", "LEAN", "BELOW_BAR"}
    assert any(r.verdict == "VALUE" for r in rows)


def dataclasses_replace_tennis() -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["sb1"],
        sport="tennis",
        kickoff_utc=datetime(2026, 9, 23, tzinfo=UTC),
        home_name="Kenta Kawada",
        away_name="Mirgiiaz Mirdzhaliev",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="ITF",
        competition_id=1,
        season_id=1,
        category_name="ITF Men",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type="Hardcourt outdoor",
        default_period_count=3,
    )


# ---------------------------------------------------------------------------
# CONFIDENCE: the builder must not double-count one quantity
# ---------------------------------------------------------------------------


def test_a_player_and_his_team_share_a_quantity_family() -> None:
    """A builder takes at most one leg per quantity family.

    Without this, a player row would fall through to `quantity_family`'s
    "be your own family" default and a builder could multiply "Romarinho
    over 1.5 shots" by "Criciúma over 11.5 shots" as two independent legs.
    They are one fact counted twice — the exact error that table exists to
    prevent — and an assist cannot happen without the goal it set up.
    """
    from bet.sofa.confidence import quantity_family

    assert quantity_family("player_shots_for") == quantity_family("shots_for")
    assert quantity_family("player_shots_on_target_for") == quantity_family(
        "shots_on_target_total"
    )
    assert quantity_family("player_assists_for") == quantity_family("goals_total")
    # And the tennis side keeps working: a set's games are the match's games.
    assert quantity_family("games_won_set1_for") == quantity_family("games_total")


def test_confidence_finds_a_player_row_s_observations() -> None:
    """The gate that reads the distribution has to be given one.

    `side_observations` looks a row up on the metrics axis and asks
    `determine_side` which of the two teams it names. A player names neither,
    so a player row reached the builder pool with an EMPTY observation list
    and every shape gate — extremum, mode, freshness — was answering a
    question about nothing.
    """
    from bet.sofa.players import player_observations, player_sample_key

    fixture_samples = {
        "metrics": {},
        "players": {
            player_sample_key("player_shots_for", "Romarinho"): {
                "observations": [{"sofascore_event_id": 1, "value": 3.0}]
            }
        },
    }
    assert player_observations(
        fixture_samples, "player_shots_for", "Romarinho"
    ) == [{"sofascore_event_id": 1, "value": 3.0}]
    # A player nobody sampled gets [], the same answer the metrics axis gives
    # for a missing metric — not a KeyError halfway through CONFIDENCE.
    assert player_observations(fixture_samples, "player_shots_for", "Nobody") == []
    assert player_observations({}, "player_shots_for", "Romarinho") == []


def test_one_key_for_the_player_sample_everywhere() -> None:
    """SAMPLES writes it, SHEET reads it, CONFIDENCE reads it. Three copies of
    an f-string is how the two halves of `derived_side_metric` drifted."""
    from bet.sofa.players import player_sample_key

    assert player_sample_key("player_shots_for", "Tolo, Nouhou") == (
        "player_shots_for|Tolo, Nouhou"
    )
