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


def _tennis_dossier(
    *set_counts: float, levels: tuple[str | None, ...] = ()
) -> EventDossierV1:
    """A two-metric tennis dossier whose observations run ``set_counts``.

    ``levels`` states which draw each observation belonged to, positionally,
    and defaults to none of them stating anything -- which is what every
    provider said before ``ProviderValue.match_level`` existed, and therefore
    the right default for the tests that pin what happens when nobody knows.
    """
    draws = list(levels) + [None] * (len(set_counts) - len(levels))

    def bucket(base: float, prefix: str) -> list[ProviderValue]:
        return [
            _pv(base + i if prefix == "g" else v, f"2026-08-{i + 1:02d}",
                match_id=f"{prefix}{i}", competition_id=None, season_id=None)
            .model_copy(update={"match_level": draws[i]})
            for i, v in enumerate(set_counts)
        ]

    return EventDossierV1(
        event_id="evt-t", sport="tennis", readiness="READY", data_gaps=[],
        team_a_name="Alex Molcan", team_b_name="Benjamin Bonzi",
        metrics={
            "total_sets": MetricObservation(
                canonical_name="total_sets", team_a_l10=bucket(0.0, "s"),
            ),
            "total_games": MetricObservation(
                canonical_name="total_games", team_a_l10=bucket(20.0, "g"),
            ),
        },
    )


SLAM = "GRAND_SLAM"
TOUR = "TOUR"


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


def test_a_five_set_match_is_no_longer_what_stands_the_gate_down():
    """Match length used to be the whole of the evidence, and it is not
    evidence of a draw: this sample ran to four and five sets and still states
    nothing about which tournament it was played at, so the length-dependent
    markets stay suppressed. What used to pass here now needs ``levels``."""
    dossier = _tennis_dossier(2.0, 3.0, 5.0, 4.0, 3.0)
    assert suppressed_markets_for(dossier, "ATP US Open")
    assert {
        r.market for r in analyze_dossier(dossier, competition="ATP US Open")
    } == set()


def test_a_grand_slam_sample_keeps_every_length_dependent_market():
    dossier = _tennis_dossier(3.0, 4.0, 5.0, levels=(SLAM, SLAM, SLAM))
    assert suppressed_markets_for(dossier, "ATP US Open") == frozenset()
    assert {
        r.market for r in analyze_dossier(dossier, competition="ATP US Open")
    } == {"total_sets", "total_games"}


def test_straight_set_grand_slam_wins_are_a_best_of_five_sample():
    """The false negative that took the whole of ATP off the 2026-09-03 sheet.
    Taylor Fritz's six 2026 Grand Slam wins all came in straight sets, so the
    old "four sets or longer" share scored him zero out of six and suppressed a
    sample that was 100% best-of-five. A best-of-five won 3-0 and a
    best-of-three won 2-1 are both three sets; only the draw distinguishes
    them."""
    dossier = _tennis_dossier(*(3.0,) * 6, levels=(SLAM,) * 6)
    assert suppressed_markets_for(dossier, "ATP US Open") == frozenset()


def test_a_mixed_sample_keeps_the_slams_and_drops_the_tour_matches():
    """The whole point of moving the rule from the market to the observation:
    the sample holds both kinds, and the 2026-09-03 slate is mostly the second
    kind. Suppressing the market threw the first kind away with it."""
    dossier = _tennis_dossier(
        2.0, 2.0, 3.0, 4.0, 5.0, levels=(TOUR, TOUR, TOUR, SLAM, SLAM),
    )
    assert suppressed_markets_for(dossier, "ATP US Open") == frozenset()
    rows = analyze_dossier(dossier, competition="ATP US Open")
    assert rows, "a scoped best-of-five sample must still produce rows"
    for row in rows:
        assert row.sample_size == 2, row.market
        assert row.sample_excluded == {"MATCH_FORMAT_MISMATCH": 3}


def test_one_long_match_in_ten_does_not_stand_the_gate_down():
    """The 2026-09-02 artifact. Eleven of 21 ATP US Open ties stood the gate
    down on samples like this one -- 1 four-set match in 10 -- and 78 of the
    day's 82 bettable rows were the result: best-of-three statistics priced
    against Superbet's best-of-five ladder."""
    dossier = _tennis_dossier(2.0, 2.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0, 4.0)
    assert suppressed_markets_for(dossier, "ATP US Open")
    assert {
        r.market for r in analyze_dossier(dossier, competition="ATP US Open")
    } == set()


def test_an_unstated_draw_is_dropped_and_counted_as_unknown():
    """The one place this module drops an observation for saying nothing, and
    it is counted under its own reason so it is never mistaken for a match that
    was measurably a different game."""
    dossier = _tennis_dossier(3.0, 4.0, 2.0, levels=(SLAM, None, TOUR))
    rows = analyze_dossier(dossier, competition="ATP US Open")
    assert rows
    for row in rows:
        assert row.sample_size == 1, row.market
        assert row.sample_excluded == {
            "MATCH_FORMAT_UNKNOWN": 1, "MATCH_FORMAT_MISMATCH": 1,
        }


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
    assert {
        r.market for r in analyze_dossier(dossier, competition="ATP US Open")
    } == set()


def test_best_of_five_evidence_on_the_fixtures_own_surface_stands_the_gate_down():
    """The converse: when the Grand Slam matches survive the surface rule, they
    are the sample and the gate must leave it alone. Both rules apply and they
    are not the same rule -- these four are hard-court slams and the six that
    go are a grass slam and five hard-court tour matches."""
    dossier = _tennis_dossier(
        4.0, 5.0, 4.0, 4.0, 3.0, 2.0, 3.0, 2.0, 3.0, 2.0,
        levels=(SLAM, SLAM, SLAM, SLAM, SLAM, TOUR, TOUR, TOUR, TOUR, TOUR),
    )
    for obs in dossier.metrics.values():
        bucket = obs.team_a_l10
        bucket[:4] = [pv.model_copy(update={"surface": "Hard"}) for pv in bucket[:4]]
        bucket[4:5] = [pv.model_copy(update={"surface": "Grass"}) for pv in bucket[4:5]]
        bucket[5:] = [pv.model_copy(update={"surface": "Hard"}) for pv in bucket[5:]]
    assert suppressed_markets_for(dossier, "ATP US Open") == frozenset()
    for row in analyze_dossier(dossier, competition="ATP US Open"):
        assert row.sample_size == 4, row.market
        assert row.sample_excluded == {
            "SURFACE_MISMATCH": 1, "MATCH_FORMAT_MISMATCH": 5,
        }


def test_a_grass_tour_match_is_counted_once_and_as_the_surface_mismatch():
    """The drop counts are reported to the operator, so they must partition.
    A match that fails both rules is the surface objection they can check
    against the tournament name in front of them."""
    dossier = _tennis_dossier(3.0, 2.0, levels=(SLAM, TOUR))
    for obs in dossier.metrics.values():
        bucket = obs.team_a_l10
        bucket[0] = bucket[0].model_copy(update={"surface": "Hard"})
        bucket[1] = bucket[1].model_copy(update={"surface": "Grass"})
    for row in analyze_dossier(dossier, competition="ATP US Open"):
        assert row.sample_excluded == {"SURFACE_MISMATCH": 1}


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


# --- observations nothing can place in time ---------------------------------
#
# Found 2026-09-05. Every rule above keys on a competition, a season, a surface
# or a draw. A row carrying none of them is immune to all of them and enters
# ``hits``/``sample_size`` unexamined however old it is -- and the player-prop
# path produced exactly such rows in bulk, because an appearance outside the
# team's fixture window reaches ``_make_values`` with no date and no ids.
#
# Measured on the 2026-09-05 dossiers: all 155,291 team and tennis observations
# carry a date and are untouched by this rule, against 55,976 of 197,176
# ``player_*`` observations (28.4%) that carry none. Niclas Füllkrug's fouls
# sample was eight appearances of which six were undateable, and those six
# supplied every zero behind its median of 0 -- the row read 3/8 with a mean of
# 0.75 against a Superbet price of 1.21 asking for 0.826.


def test_an_undateable_observation_is_dropped_when_the_sample_has_dates():
    kept, dropped = scope_values([
        _pv(4.0, "2026-08-30", match_id="league"),
        _pv(1.0, "2026-08-22", match_id="cup"),
        _pv(0.0, "", match_id="nowhere", competition_id=None, season_id=None),
        _pv(0.0, "", match_id="nowhere2", competition_id=None, season_id=None),
    ])
    assert [pv.match_id for pv in kept] == ["league", "cup"]
    assert dropped == {"SCOPE_UNKNOWN": 2}


def test_a_sample_with_no_dates_at_all_is_kept_whole():
    """The context fetch failed, not the observations.

    The condition is relative on purpose: a missing date is evidence only when
    the sample also holds dated rows, because that is the only case in which we
    know a context was built and this row fell outside it. Deleting an entire
    sample because one provider call failed would be far worse than scoping
    none of it.
    """
    kept, dropped = scope_values([
        _pv(4.0, "", match_id="a", competition_id=None, season_id=None),
        _pv(1.0, "", match_id="b", competition_id=None, season_id=None),
    ])
    assert [pv.match_id for pv in kept] == ["a", "b"]
    assert "SCOPE_UNKNOWN" not in dropped


def test_undateable_rows_are_dropped_before_the_season_target_is_chosen():
    """Order matters: an undateable row must not vote on what season is current.

    It carries no season either, so it cannot vote directly -- but it must also
    not survive into ``kept`` by being invisible to every later rule, which is
    what this asserts.
    """
    kept, dropped = scope_values([
        _pv(2.0, "2026-08-29", match_id="this", season_id="2222"),
        _pv(9.0, "2026-05-16", match_id="last", season_id="1111"),
        _pv(0.0, "", match_id="unplaceable", competition_id=None, season_id=None),
    ])
    assert [pv.match_id for pv in kept] == ["this"]
    assert dropped == {"STALE_SEASON": 1, "SCOPE_UNKNOWN": 1}


def test_the_friendly_pin_still_fires_on_a_dated_player_appearance():
    """The other half of the 2026-09-05 fix, from the consumer's side.

    Serhou Guirassy's shots-on-target sample was nine appearances, five of them
    July friendlies on a tour of Japan and last May's Bundesliga. All nine were
    dated, so ``SCOPE_UNKNOWN`` does not touch them; they survived because the
    player path passed no ``competition_id`` at all. Once ``MatchContext``
    carries the id the existing pin does the work with no new rule.
    """
    kept, dropped = scope_values([
        _pv(2.0, "2026-08-29", match_id="hsv", season_id="2222"),
        _pv(0.0, "2026-08-01", match_id="tokyo",
            competition_id=CLUB_FRIENDLIES, season_id="1552"),
        _pv(0.0, "2026-07-29", match_id="cerezo",
            competition_id=CLUB_FRIENDLIES, season_id="1552"),
    ])
    assert [pv.match_id for pv in kept] == ["hsv"]
    assert dropped == {"PRE_SEASON_FRIENDLY": 2}
