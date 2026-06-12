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
