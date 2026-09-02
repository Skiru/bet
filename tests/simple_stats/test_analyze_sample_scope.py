"""Which historical matches may become trials, and which cannot.

Two faults, both found in the 2026-09-01 file, both of which produced a
``p_low`` that described something other than the fixture being priced:

* **Pre-season friendlies counted as league matches.** Five of Bromley's nine
  corners observations were July friendlies against West Bromwich Albion,
  Crystal Palace, Millwall, Queens Park Rangers and Barnet. The row read 9/9,
  ``p_low`` 0.701, minimum price 1.57, and Superbet's 1.70 made it the day's
  sixth-ranked single. The four League One matches read 4/4, ``p_low`` 0.510,
  minimum 2.16 -- not a bet at any price on offer.

* **The previous season counted as this one.** Seven of Parma's fourteen shots
  observations came from May 2026 or earlier, six of thirteen for Al-Hilal's
  corners, and one Monza observation was twelve and a half months old.

The analyst removed both in prose, every day, by hand. ``p_low`` kept counting
them, and ``p_low`` is what the coupon ranks on.

The third fault has the same shape and lives here too: a best-of-three tennis
sample cannot measure a best-of-five tie, so no length-dependent row is emitted
for one at all.
"""
from __future__ import annotations

import pytest

from bet.simple_stats import analyze as analyze_module
from bet.simple_stats.analyze import (
    _tennis_match_keys,
    analyze_dossier,
    scope_values,
    suppressed_markets_for,
    tennis_match_format,
)
from bet.simple_stats.contracts import (
    EventDossierV1,
    MetricObservation,
    ProviderValue,
)

# bzzoiro's real ids, pinned in config/observation_scope.json and verified live
# on 2026-09-01. Named here so a test failure points at the config entry.
CLUB_FRIENDLIES = "79"
CHAMPIONSHIP = "12"
CARABAO_CUP = "40"


@pytest.fixture(autouse=True)
def _clear_scope_caches():
    analyze_module.reset_scope_caches()
    yield
    analyze_module.reset_scope_caches()


def _pv(
    value: float,
    match_date: str,
    *,
    provider: str = "bzzoiro",
    match_id: str = "m",
    competition_id: str | None = CHAMPIONSHIP,
    season_id: str | None = "1111",
) -> ProviderValue:
    return ProviderValue(
        provider=provider,
        match_id=match_id,
        match_date=match_date,
        opponent="Opponent FC",
        value=value,
        observed_at="2026-09-01T00:00:00+00:00",
        competition_id=competition_id,
        season_id=season_id,
    )


# --- pre-season friendlies --------------------------------------------------


def test_a_pinned_friendly_competition_is_dropped_from_the_sample():
    kept, dropped = scope_values([
        _pv(2.0, "2026-08-29", match_id="a"),
        _pv(4.0, "2026-08-22", match_id="b"),
        _pv(1.0, "2026-07-25", match_id="c",
            competition_id=CLUB_FRIENDLIES, season_id="1552"),
        _pv(1.0, "2026-07-21", match_id="d",
            competition_id=CLUB_FRIENDLIES, season_id="1552"),
    ])
    assert [pv.match_id for pv in kept] == ["a", "b"]
    assert dropped == {"PRE_SEASON_FRIENDLY": 2}


def test_the_friendly_pin_is_per_provider():
    """The id space is the provider's own. Competition 79 means club friendlies
    at bzzoiro and means nothing in particular anywhere else, so the pin must
    not leak across providers."""
    kept, dropped = scope_values([
        _pv(2.0, "2026-08-29", provider="espn-football", match_id="a",
            competition_id=CLUB_FRIENDLIES, season_id="1552"),
    ])
    assert len(kept) == 1
    assert dropped == {}


def test_dropping_friendlies_changes_the_read_and_not_only_the_count():
    """Bromley's corners row, reproduced: nine observations under 5.5 become
    four, and a p_low of 0.70 becomes 0.51."""
    league = [_pv(v, f"2026-08-{d:02d}", match_id=f"L{d}")
              for d, v in ((29, 3.0), (22, 2.0), (15, 2.0), (8, 5.0))]
    friendlies = [
        _pv(v, f"2026-07-{d:02d}", match_id=f"F{d}",
            competition_id=CLUB_FRIENDLIES, season_id="1552")
        for d, v in ((31, 1.0), (28, 5.0), (25, 1.0), (17, 3.0))
    ]
    dossier = EventDossierV1(
        event_id="evt1", sport="football", readiness="READY", data_gaps=[],
        team_a_name="Bromley", team_b_name="Leyton Orient",
        metrics={"corners_for": MetricObservation(
            canonical_name="corners_for", team_a_l10=[*league, *friendlies],
        )},
    )
    row = next(
        r for r in analyze_dossier(dossier)
        if r.market == "corners_for" and r.line == 5.5
        and r.direction == "UNDER" and r.team_name == "Bromley"
    )
    assert row.sample_size == 4
    assert row.p_low < 0.55
    assert row.sample_excluded == {"PRE_SEASON_FRIENDLY": 4}


# --- the previous season ----------------------------------------------------


def test_an_observation_from_last_season_is_dropped():
    kept, dropped = scope_values([
        _pv(20.0, "2026-08-29", match_id="a", season_id="1375"),
        _pv(25.0, "2026-05-24", match_id="b", season_id="1200"),
        _pv(26.0, "2026-05-10", match_id="c", season_id="1200"),
    ])
    assert [pv.match_id for pv in kept] == ["a"]
    assert dropped == {"STALE_SEASON": 2}


def test_the_current_season_is_decided_per_competition_not_per_sample():
    """Sheffield United's Championship 26/27 and Carabao Cup 26/27 matches are
    both current and both stay. Folding them into one target would have thrown
    away every cup tie in the sample -- which are exactly the competitive
    matches the friendly filter is trying to keep."""
    kept, dropped = scope_values([
        _pv(3.0, "2026-08-29", match_id="league-new", season_id="1111"),
        _pv(4.0, "2026-08-09", match_id="cup-new",
            competition_id=CARABAO_CUP, season_id="1092"),
        _pv(5.0, "2026-04-01", match_id="league-old", season_id="1000"),
    ])
    assert {pv.match_id for pv in kept} == {"league-new", "cup-new"}
    assert dropped == {"STALE_SEASON": 1}


def test_newest_by_date_decides_which_season_is_current():
    """Not first-seen, not highest id. The buckets arrive in provider order and
    the h2h bucket in particular is often oldest-first."""
    kept, _ = scope_values([
        _pv(1.0, "2025-09-14", match_id="old", season_id="1000"),
        _pv(2.0, "2026-08-29", match_id="new", season_id="1111"),
    ])
    assert [pv.match_id for pv in kept] == ["new"]


def test_a_provider_date_format_we_do_not_share_still_sorts():
    """``_day_key`` and not a raw string slice, so ``22/08/2026`` is compared
    against ISO rather than landing before every date in the sample."""
    kept, _ = scope_values([
        _pv(1.0, "01/04/2026", match_id="old", season_id="1000"),
        _pv(2.0, "29/08/2026", match_id="new", season_id="1111"),
    ])
    assert [pv.match_id for pv in kept] == ["new"]


# --- unknown is never degraded ----------------------------------------------


def test_an_observation_with_no_competition_id_is_kept():
    """Not every provider publishes league ids. Dropping what we cannot
    classify would quietly delete whole providers from the sample -- which is
    the same overconfident-mapping mistake the pinned competition maps exist to
    avoid."""
    kept, dropped = scope_values([
        _pv(2.0, "2026-08-29", match_id="a", competition_id=None, season_id=None),
        _pv(3.0, "2026-05-01", match_id="b", competition_id=None, season_id=None),
    ])
    assert len(kept) == 2
    assert dropped == {}


def test_an_observation_with_a_competition_but_no_season_is_kept():
    kept, dropped = scope_values([
        _pv(2.0, "2026-08-29", match_id="a", season_id="1111"),
        _pv(3.0, "2026-05-01", match_id="b", season_id=None),
    ])
    assert {pv.match_id for pv in kept} == {"a", "b"}
    assert dropped == {}


def test_a_sheet_built_from_pre_scope_dossiers_is_unchanged():
    """Every ProviderValue written before this existed carries None for both
    ids, so an old artifact re-analysed today yields the same rows it did."""
    values = [_pv(float(v), f"2026-08-{d:02d}", match_id=f"m{d}",
                  competition_id=None, season_id=None)
              for d, v in ((29, 8.0), (22, 9.0), (15, 10.0), (8, 11.0))]
    dossier = EventDossierV1(
        event_id="evt1", sport="football", readiness="READY", data_gaps=[],
        metrics={"corners_total": MetricObservation(
            canonical_name="corners_total", team_a_l10=values,
        )},
    )
    for row in analyze_dossier(dossier):
        assert row.sample_excluded == {}
        assert row.sample_size == 4


# --- best-of-five tennis ----------------------------------------------------


def _tennis_dossier(*set_counts: float) -> EventDossierV1:
    return EventDossierV1(
        event_id="evt-t", sport="tennis", readiness="READY", data_gaps=[],
        team_a_name="Alex Molcan", team_b_name="Benjamin Bonzi",
        metrics={
            "total_sets": MetricObservation(
                canonical_name="total_sets",
                team_a_l10=[
                    _pv(v, f"2026-08-{i + 1:02d}", match_id=f"s{i}",
                        competition_id=None, season_id=None)
                    for i, v in enumerate(set_counts)
                ],
            ),
            "total_games": MetricObservation(
                canonical_name="total_games",
                team_a_l10=[
                    _pv(20.0 + i, f"2026-08-{i + 1:02d}", match_id=f"g{i}",
                        competition_id=None, season_id=None)
                    for i in range(len(set_counts))
                ],
            ),
        },
    )


def test_the_format_map_pins_the_men_and_women_draws_separately():
    assert tennis_match_format("ATP US Open") == "BO5"
    assert tennis_match_format("WTA US Open") == "BO3"
    assert tennis_match_format("Championship") is None


def test_a_best_of_three_sample_emits_no_length_rows_for_a_best_of_five_tie():
    """The Molcan-Bonzi rows, which reached the operator as a Bet Builder.
    ``total_sets UNDER 3.5`` at 15/15 off a sample whose maximum is 3.0 is not
    a read; it is the definition of best-of-three."""
    dossier = _tennis_dossier(2.0, 2.0, 3.0, 2.0, 3.0)
    rows = analyze_dossier(dossier, competition="ATP US Open")
    assert {r.market for r in rows} == set()
    assert suppressed_markets_for(dossier, "ATP US Open")


def test_a_sample_containing_a_five_set_match_is_left_alone():
    dossier = _tennis_dossier(2.0, 3.0, 5.0, 4.0, 3.0)
    rows = analyze_dossier(dossier, competition="ATP US Open")
    assert {r.market for r in rows} == {"total_sets", "total_games"}


def test_one_long_match_in_ten_does_not_stand_the_gate_down():
    """The 2026-09-02 artifact. Eleven of 21 ATP US Open ties stood the gate
    down on samples like this one -- 1 four-set match in 10 -- and 78 of the
    day's 82 bettable rows were the result: best-of-three statistics priced
    against Superbet's best-of-five ladder."""
    dossier = _tennis_dossier(2.0, 2.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0, 4.0)
    assert suppressed_markets_for(dossier, "ATP US Open")
    assert {r.market for r in analyze_dossier(dossier, competition="ATP US Open")} == set()


def test_a_third_of_the_sample_running_long_is_a_best_of_five_sample():
    """The other side of the same threshold: a player whose recent matches
    really are best-of-five keeps every length-dependent market."""
    dossier = _tennis_dossier(2.0, 3.0, 4.0, 3.0, 5.0, 2.0)
    assert suppressed_markets_for(dossier, "ATP US Open") == frozenset()
    assert {
        r.market for r in analyze_dossier(dossier, competition="ATP US Open")
    } == {"total_sets", "total_games"}


def test_the_gate_judges_the_sample_the_rows_are_priced_from():
    """Four Wimbledon matches stand the raw gate down, and then the surface
    rule deletes exactly those four before pricing -- the typical men's profile
    at US Open time, since Wimbledon is the only recent best-of-five. The gate
    must measure the scoped sample, or the surviving hard-court best-of-three
    sample meets the best-of-five ladder unguarded."""
    dossier = _tennis_dossier(2.0, 2.0, 3.0, 2.0, 3.0, 2.0, 4.0, 5.0, 4.0, 4.0)
    for obs in dossier.metrics.values():
        bucket = obs.team_a_l10
        bucket[6:] = [pv.model_copy(update={"surface": "Grass"}) for pv in bucket[6:]]
        bucket[:6] = [pv.model_copy(update={"surface": "Hard"}) for pv in bucket[:6]]
    assert suppressed_markets_for(dossier, "ATP US Open")
    assert {r.market for r in analyze_dossier(dossier, competition="ATP US Open")} == set()


def test_best_of_five_evidence_on_the_fixture_s_own_surface_still_stands_the_gate_down():
    """The converse: when the long matches survive the surface rule, they are
    the sample and the gate must leave it alone."""
    dossier = _tennis_dossier(4.0, 5.0, 4.0, 4.0, 2.0, 2.0, 3.0, 2.0, 3.0, 2.0)
    for obs in dossier.metrics.values():
        bucket = obs.team_a_l10
        bucket[:4] = [pv.model_copy(update={"surface": "Hard"}) for pv in bucket[:4]]
        bucket[4:] = [pv.model_copy(update={"surface": "Grass"}) for pv in bucket[4:]]
    assert suppressed_markets_for(dossier, "ATP US Open") == frozenset()


def test_the_women_s_draw_at_the_same_tournament_is_untouched():
    """Same venue, same fortnight, different format. Folding ATP and WTA into
    one "US Open" entry would suppress every women's row on the slate."""
    dossier = _tennis_dossier(2.0, 2.0, 3.0, 2.0, 3.0)
    rows = analyze_dossier(dossier, competition="WTA US Open")
    assert {r.market for r in rows} == {"total_sets", "total_games"}


def test_an_unpinned_competition_suppresses_nothing():
    dossier = _tennis_dossier(2.0, 2.0, 3.0)
    assert suppressed_markets_for(dossier, "ATP Some Challenger") == frozenset()
    assert suppressed_markets_for(dossier, None) == frozenset()


def test_football_is_never_touched_by_the_format_gate():
    dossier = EventDossierV1(
        event_id="evt1", sport="football", readiness="READY", data_gaps=[],
        metrics={},
    )
    assert suppressed_markets_for(dossier, "ATP US Open") == frozenset()


# --- tennis opponent identity ----------------------------------------------


def _obs(provider: str, opponent: str, value: float = 1.0) -> ProviderValue:
    return ProviderValue(
        provider=provider,
        match_id=f"{provider}:{opponent}",
        match_date="2026-08-13",
        opponent=opponent,
        value=value,
        observed_at="2026-09-01T00:00:00Z",
    )


class TestTennisOpponentIdentity:
    """One match reported by two providers is one trial, whatever they call it.

    The key used to be the bare normalized opponent string, so every spelling
    difference opened a second slot and counted one match twice. Measured on
    2026-09-01: nine such pairs across the tennis slate. These are those pairs,
    verbatim.
    """

    @pytest.mark.parametrize("a,b", [
        ("Juncheng Shang", "Shang Juncheng"),
        ("Shuai Zhang", "Zhang Shuai"),
        ("Xiyu Wang", "Wang Xiyu"),
        ("Qinwen Zheng", "Zheng Qinwen"),
        ("Coleman Wong", "Chak Lam Coleman Wong"),
        ("Joel Schwaerzler", "Joel Josef Schwaerzler"),
        ("Daniel Merida Aguilar", "Daniel Merida"),
        ("Soon Woo Kwon", "Soonwoo Kwon"),
    ])
    def test_one_match_named_two_ways_is_one_slot(self, a, b):
        keys = _tennis_match_keys([_obs("tennis-abstract", a), _obs("espn-tennis", b)])
        assert len(set(keys)) == 1, keys

    def test_a_repeat_meeting_from_one_provider_keeps_its_own_slot(self):
        """The provider's own row count is the evidence about how often they met."""
        keys = _tennis_match_keys([
            _obs("tennis-abstract", "Clara Tauson"),
            _obs("tennis-abstract", "Clara Tauson"),
        ])
        assert len(set(keys)) == 2, keys

    def test_two_players_sharing_a_surname_are_not_merged(self):
        """Tennis has real sibling pairs; collapsing them would invent a trial."""
        keys = _tennis_match_keys([
            _obs("tennis-abstract", "Mirra Andreeva"),
            _obs("espn-tennis", "Erika Andreeva"),
        ])
        assert len(set(keys)) == 2, keys

    def test_an_unnamed_opponent_gets_no_slot(self):
        keys = _tennis_match_keys([_obs("tennis-abstract", "")])
        assert keys == [""]

    @pytest.mark.xfail(reason="diminutive vs full given name: needs a nickname "
                              "table; a fuzzy ratio here would merge the "
                              "Andreeva sisters", strict=True)
    def test_a_diminutive_is_still_a_second_slot(self):
        """Documents the one 2026-09-01 pair this does not fix.

        It counted Tatjana Maria's 29-game match against McNally twice, both
        copies in the high tail of a total_games sample.
        """
        keys = _tennis_match_keys([
            _obs("tennis-abstract", "Caty Mcnally"),
            _obs("espn-tennis", "Catherine McNally"),
        ])
        assert len(set(keys)) == 1, keys
