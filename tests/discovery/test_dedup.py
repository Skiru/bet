"""Tests for DeduplicationEngine."""

from datetime import datetime

import pytest

from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent


@pytest.fixture
def engine():
    return DeduplicationEngine(fuzzy_threshold=85)


def _make_event(
    source="sofascore",
    external_id="123",
    sport="football",
    home="FC Barcelona",
    away="Real Madrid",
    kickoff_str="2026-05-14T20:00:00+00:00",
    competition="La Liga",
    **kwargs,
):
    return DiscoveredEvent(
        source=source,
        external_id=external_id,
        sport=sport,
        competition=competition,
        home_team=home,
        away_team=away,
        kickoff=datetime.fromisoformat(kickoff_str),
        **kwargs,
    )


class TestExactMatch:
    def test_same_teams_same_sport_merge(self, engine):
        events = {
            "sofascore": [_make_event(source="sofascore", external_id="s1")],
            "odds-api": [_make_event(source="odds-api", external_id="o1")],
        }
        merged = engine.merge(events)
        assert len(merged) == 1
        assert len(merged[0].sources) == 2
        # odds-api is in priority list (index 1), sofascore is not → odds-api wins
        assert merged[0].primary_source == "odds-api"

    def test_different_sports_not_merged(self, engine):
        events = {
            "sofascore": [
                _make_event(source="sofascore", sport="football", external_id="s1"),
                _make_event(
                    source="sofascore",
                    sport="basketball",
                    external_id="s2",
                    home="FC Barcelona",
                    away="Real Madrid",
                ),
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 2

    def test_different_teams_not_merged(self, engine):
        events = {
            "sofascore": [
                _make_event(
                    source="sofascore",
                    external_id="s1",
                    home="Real Madrid",
                    away="Barcelona",
                ),
                _make_event(
                    source="sofascore",
                    external_id="s2",
                    home="Real Sociedad",
                    away="Athletic Bilbao",
                ),
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 2


class TestFuzzyMatch:
    def test_fc_suffix_matches(self, engine):
        """FC Barcelona vs Barcelona → merge."""
        events = {
            "sofascore": [_make_event(source="sofascore", home="FC Barcelona")],
            "odds-api": [
                _make_event(source="odds-api", home="Barcelona", external_id="o1")
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 1
        assert len(merged[0].sources) == 2

    def test_dynamo_kyiv_vs_kiev(self, engine):
        """Dynamo Kyiv vs Dynamo Kiev → fuzzy match."""
        events = {
            "sofascore": [
                _make_event(
                    source="sofascore", home="Dynamo Kyiv", away="Shakhtar Donetsk"
                )
            ],
            "odds-api": [
                _make_event(
                    source="odds-api",
                    home="Dynamo Kiev",
                    away="Shakhtar Donetsk",
                    external_id="o1",
                )
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 1
        assert merged[0].sources[1].confidence < 1.0  # fuzzy

    def test_no_false_positive_real_teams(self, engine):
        """Real Madrid vs Real Sociedad → NOT merged."""
        events = {
            "sofascore": [
                _make_event(
                    source="sofascore",
                    home="Real Madrid",
                    away="Getafe",
                    external_id="s1",
                ),
                _make_event(
                    source="sofascore",
                    home="Real Sociedad",
                    away="Athletic Bilbao",
                    external_id="s2",
                    kickoff_str="2026-05-14T18:00:00+00:00",
                ),
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 2


class TestTemporalMatch:
    def test_within_window_merges(self, engine):
        """Events 1h apart → merge."""
        events = {
            "sofascore": [
                _make_event(source="sofascore", kickoff_str="2026-05-14T20:00:00+00:00")
            ],
            "odds-api": [
                _make_event(
                    source="odds-api",
                    external_id="o1",
                    kickoff_str="2026-05-14T21:00:00+00:00",
                )
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 1

    def test_outside_window_separate(self, engine):
        """Events 3h apart → separate (even if same teams)."""
        events = {
            "sofascore": [
                _make_event(source="sofascore", kickoff_str="2026-05-14T15:00:00+00:00")
            ],
            "odds-api": [
                _make_event(
                    source="odds-api",
                    external_id="o1",
                    kickoff_str="2026-05-14T20:00:00+00:00",
                )
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 2


class TestThreeSourceMerge:
    def test_all_three_sources(self, engine):
        """Same match from 3 sources → 1 fixture with 3 sources."""
        events = {
            "sofascore": [_make_event(source="sofascore", external_id="s1")],
            "odds-api": [
                _make_event(source="odds-api", external_id="o1", odds={"h2h": 1.5})
            ],
            "api-football": [_make_event(source="api-football", external_id="af1")],
        }
        merged = engine.merge(events)
        assert len(merged) == 1
        assert len(merged[0].sources) == 3
        assert merged[0].odds == {"h2h": 1.5}  # from odds-api

    def test_no_duplicate_sources(self, engine):
        """Same source with different external IDs must fail closed."""
        events = {
            "sofascore": [
                _make_event(source="sofascore", external_id="s1"),
                _make_event(source="sofascore", external_id="s2"),
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 2
        assert all(len(item.sources) == 1 for item in merged)


class TestEdgeCases:
    def test_empty_input(self, engine):
        merged = engine.merge({})
        assert merged == []

    def test_single_source_only(self, engine):
        events = {
            "sofascore": [
                _make_event(source="sofascore", external_id="s1"),
                _make_event(
                    source="sofascore",
                    external_id="s2",
                    home="Liverpool",
                    away="Chelsea",
                ),
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 2
        assert all(m.source_count == 1 for m in merged)

    def test_bzzoiro_priority_and_placeholder_competition_upgrade(self, engine):
        """bzzoiro has higher priority than superbet and upgrades
        placeholder competition.
        """
        events = {
            "superbet": [
                _make_event(
                    source="superbet",
                    external_id="sb_123",
                    home="Rakow Czestochowa",
                    away="Motor Lublin",
                    competition="Superbet League 187",
                )
            ],
            "bzzoiro": [
                _make_event(
                    source="bzzoiro",
                    external_id="bz_456",
                    home="Raków Częstochowa",
                    away="Motor Lublin",
                    competition="Ekstraklasa Poland",
                    country="Poland",
                )
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 1
        assert merged[0].primary_source == "bzzoiro"
        assert merged[0].competition == "Ekstraklasa Poland"
        assert merged[0].country == "Poland"


class TestPrimarySourceIsDecidedOnlyAtCreation:
    """``merge()`` visits sources in a single pass, strictly in
    ``SOURCE_PRIORITY`` order, draining one source fully before the next --
    so the first source to create a fixture is always the highest-priority
    one that discovered it at all. ``_attach_source`` therefore carries no
    step that reassigns ``primary_source``: a version of it once did, gated
    on ``rank(new) < rank(existing)``, and that condition cannot be true
    under this architecture. Its only test passed without exercising it,
    because bzzoiro sorts first in ``SOURCE_PRIORITY`` and had already set
    every field the test checked at fixture-creation time -- see
    ``test_bzzoiro_priority_and_placeholder_competition_upgrade`` above.
    """

    def test_a_higher_priority_source_arriving_after_creation_does_not_move_primary_source(
        self, engine
    ):
        """A real ``events_by_source`` dict can never hand bzzoiro's event to
        ``_attach_source`` after superbet's has already created the fixture --
        bzzoiro always sorts first. This calls ``_attach_source`` directly to
        prove the *removed* branch is not missed: the placeholder competition
        and country still upgrade (that part of the method is unconditional),
        but ``primary_source`` stays exactly what ``merge()``'s single pass
        established.
        """
        events = {
            "superbet": [
                _make_event(
                    source="superbet", external_id="sb_1",
                    competition="Superbet League 1",
                )
            ],
        }
        merged = engine.merge(events)
        assert merged[0].primary_source == "superbet"

        bzzoiro_event = _make_event(
            source="bzzoiro", external_id="bz_1",
            competition="Ekstraklasa Poland", country="Poland",
        )
        engine._attach_source(merged[0], bzzoiro_event)

        assert merged[0].primary_source == "superbet"
        assert merged[0].primary_external_id == "sb_1"
        assert merged[0].competition == "Ekstraklasa Poland"
        assert merged[0].country == "Poland"


class TestSwappedSides:
    """Regression for 2026-09-12: the merge loop only ever compared
    home-against-home and away-against-away, so a feed listing the same real
    match with home/away reversed was invisible to exact, containment and
    same-club matching alike -- Bali United - Adhyaksa Farmel FC (bzzoiro) and
    Adhyaksa Farmel FC - Bali United (superbet) arrived as two separate
    fixtures on the live 2026-09-12 slate, each then carrying only one of
    Superbet's two listings of that match and neither carrying a usable
    price.
    """

    def test_reversed_home_away_at_identical_kickoff_merges(self, engine):
        events = {
            "bzzoiro": [
                _make_event(
                    source="bzzoiro", external_id="bz_1",
                    home="Bali United", away="Adhyaksa Farmel FC",
                    kickoff_str="2026-09-12T12:00:00+00:00",
                    competition="Superbet League 212",
                )
            ],
            "superbet": [
                _make_event(
                    source="superbet", external_id="sb_1",
                    home="Adhyaksa Farmel FC", away="Bali United",
                    kickoff_str="2026-09-12T12:00:00+00:00",
                    competition="Superbet League 212",
                )
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 1
        assert len(merged[0].sources) == 2

    def test_reversed_sides_within_the_fuzzy_window_but_not_at_the_same_instant_do_not_merge(
        self, engine
    ):
        """The safety argument is exact kickoff, not merely "close": a one-hour
        gap is still inside the ±2h fuzzy window (so the fourth chance is
        reached at all), but the two clubs cannot have played each other
        twice, reversed, an hour apart -- these must be read as unrelated and
        left unmerged rather than collapsed on the strength of the swap."""
        events = {
            "bzzoiro": [
                _make_event(
                    source="bzzoiro", external_id="bz_1",
                    home="Bali United", away="Adhyaksa Farmel FC",
                    kickoff_str="2026-09-12T12:00:00+00:00",
                )
            ],
            "superbet": [
                _make_event(
                    source="superbet", external_id="sb_1",
                    home="Adhyaksa Farmel FC", away="Bali United",
                    kickoff_str="2026-09-12T13:00:00+00:00",
                )
            ],
        }
        merged = engine.merge(events)
        assert len(merged) == 2
