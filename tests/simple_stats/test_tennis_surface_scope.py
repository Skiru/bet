"""The surface rule in ``scope_values``, and the plumbing that feeds it.

Written from the 2026-09-02 defect: the only row on a 50,329-row sheet that
beat its own price was Boulter-Muchova ``aces_total`` OVER 5.5 at 2.07, off a
sample whose median was 10.5 -- and every one of Muchova's eight observations
was grass while the fixture was hard court. Those two players' hard-court
median match total is 6.0 and 5.0, which is where Superbet's 5.5 line sat.

Properties, not pinned numbers: what must hold is that a mismatched surface is
removed, that an unknown surface on *either* side removes nothing, and that
football is untouched.
"""

from __future__ import annotations

import json

import pytest

from bet.simple_stats.analyze import scope_values, tennis_surface
from bet.simple_stats.contracts import ProviderValue
from bet.simple_stats.providers import _surface_or_none


def _pv(
    value: float,
    *,
    surface: str | None = None,
    provider: str = "tennis-abstract",
    match_id: str = "m1",
    competition_id: str | None = None,
    season_id: str | None = None,
    opponent: str = "someone",
) -> ProviderValue:
    return ProviderValue(
        provider=provider,
        match_id=match_id,
        match_date="2026-06-29",
        opponent=opponent,
        value=value,
        observed_at="2026-09-02T12:00:00+00:00",
        competition_id=competition_id,
        season_id=season_id,
        surface=surface,
    )


class TestSurfaceRule:
    def test_a_mismatched_surface_is_dropped_and_counted(self) -> None:
        values = [_pv(11.0, surface="Grass", match_id="g1"), _pv(6.0, surface="Hard", match_id="h1")]
        kept, dropped = scope_values(values, surface="Hard")
        assert [pv.value for pv in kept] == [6.0]
        assert dropped == {"SURFACE_MISMATCH": 1}

    def test_the_matching_surface_survives_whole(self) -> None:
        values = [_pv(5.0, surface="Hard", match_id=f"h{i}") for i in range(4)]
        kept, dropped = scope_values(values, surface="Hard")
        assert len(kept) == 4
        assert "SURFACE_MISMATCH" not in dropped

    def test_no_fixture_surface_drops_nothing(self) -> None:
        """An unpinned competition must scope exactly as before this rule existed."""
        values = [_pv(11.0, surface="Grass"), _pv(6.0, surface="Hard", match_id="h1")]
        kept, dropped = scope_values(values, surface=None)
        assert len(kept) == 2
        assert "SURFACE_MISMATCH" not in dropped

    def test_an_observation_nobody_can_place_is_never_dropped(self) -> None:
        """'Unknown is not degraded' -- the rule the whole config family follows.

        Narrowed on 2026-09-02 from "an observation without a surface is never
        dropped". It still holds for a row nothing in the sample can place; what
        changed is that a row describing a match another row *does* place is no
        longer unknown. See ``_share_surface_within_a_match``: a provider that
        never states a surface was not uninformative under the old rule, it was
        immune to the filter, and on that day's slate the filter removed 145 of
        tennis-abstract's 522 observations and 0 of espn-tennis's 478.
        """
        values = [
            _pv(9.0, surface=None, opponent="nobody else played them"),
            _pv(11.0, surface="Grass", match_id="g1"),
        ]
        kept, dropped = scope_values(values, surface="Hard")
        assert [pv.value for pv in kept] == [9.0]
        assert dropped == {"SURFACE_MISMATCH": 1}

    def test_a_surface_reaches_the_other_providers_row_for_the_same_match(self) -> None:
        """Both providers describe the same match; only one of them says where.

        This is the espn-tennis case exactly: its rows carry the tournament and
        no surface, and the surface table pins only ten Grand Slam names -- 16%
        of its cached rows. The other 84% are placed here instead, by the match
        rather than by the tournament's name.
        """
        values = [
            _pv(11.0, surface="Grass", match_id="ta1"),
            _pv(11.0, surface=None, provider="espn-tennis", match_id="espn1"),
        ]
        kept, dropped = scope_values(values, surface="Hard")
        assert kept == []
        assert dropped == {"SURFACE_MISMATCH": 2}

    def test_a_repeat_meeting_on_two_surfaces_places_neither(self) -> None:
        """Unanimity, which is what makes the propagation safe.

        Two matches against one opponent on different surfaces land in one
        group. The group disagrees about where it was played, so it hands
        nothing over and the unplaced row keeps its None -- the conservative
        answer, and the reason a wrong surface cannot be manufactured here.
        """
        values = [
            _pv(11.0, surface="Grass", match_id="ta1"),
            _pv(6.0, surface="Hard", match_id="ta2"),
            _pv(9.0, surface=None, provider="espn-tennis", match_id="espn1"),
        ]
        kept, dropped = scope_values(values, surface="Hard")
        assert sorted(pv.value for pv in kept) == [6.0, 9.0]
        assert dropped == {"SURFACE_MISMATCH": 1}

    def test_football_never_enters_the_surface_propagation(self) -> None:
        """Football rows all carry surface None, so the pass must be a no-op
        rather than something that groups clubs by opponent name."""
        values = [
            _pv(9.0, surface=None, provider="espn-football", opponent="Betis"),
            _pv(11.0, surface=None, provider="bzzoiro", opponent="Betis"),
        ]
        kept, dropped = scope_values(values, surface=None)
        assert len(kept) == 2
        assert all(pv.surface is None for pv in kept)
        assert dropped == {}

    def test_dropping_every_observation_is_allowed(self) -> None:
        """A sample entirely on the wrong surface must collapse, not survive.

        This is the Muchova case: eight grass observations against a hard
        fixture. An empty sample is the correct answer -- 'no evidence' -- and
        is what stops p_low being computed from a surface nobody is playing on.
        """
        values = [_pv(11.0, surface="Grass", match_id=f"g{i}") for i in range(8)]
        kept, dropped = scope_values(values, surface="Hard")
        assert kept == []
        assert dropped == {"SURFACE_MISMATCH": 8}

    def test_the_reasons_partition_and_do_not_double_count(self) -> None:
        """A stale-season row must not also be billed as a surface mismatch.

        The current-season row is dated later than the stale one on purpose:
        ``_season_sort_key`` picks a competition's current season from its
        *newest* observation and breaks same-day ties on ``match_id``, so two
        rows sharing a date would let the lexicographically larger id decide
        which season is current.
        """
        current = _pv(3.0, surface="Hard", match_id="cur", competition_id="c1", season_id="2026")
        stale = _pv(9.0, surface="Grass", match_id="old", competition_id="c1", season_id="2025")
        object.__setattr__(stale, "match_date", "2025-11-02")
        values = [current, stale]
        kept, dropped = scope_values(values, surface="Hard")
        assert [pv.value for pv in kept] == [3.0]
        assert dropped == {"STALE_SEASON": 1}
        assert sum(dropped.values()) == len(values) - len(kept)

    def test_surface_and_season_each_bill_their_own_row(self) -> None:
        """Three rows, one clean, one stale, one wrong surface: one count each."""
        clean = _pv(3.0, surface="Hard", match_id="a", competition_id="c1", season_id="2026")
        stale = _pv(4.0, surface="Hard", match_id="b", competition_id="c1", season_id="2025")
        object.__setattr__(stale, "match_date", "2025-11-02")
        wrong = _pv(9.0, surface="Grass", match_id="c", competition_id="c1", season_id="2026")
        kept, dropped = scope_values([clean, stale, wrong], surface="Hard")
        assert [pv.value for pv in kept] == [3.0]
        assert dropped == {"STALE_SEASON": 1, "SURFACE_MISMATCH": 1}


class TestSurfaceMapReader:
    @pytest.mark.parametrize(
        ("competition", "expected"),
        [
            ("WTA US Open", "Hard"),
            ("ATP US Open", "Hard"),
            ("ATP Roland Garros", "Clay"),
            ("WTA Wimbledon", "Grass"),
        ],
    )
    def test_pinned_competitions_resolve(self, competition: str, expected: str) -> None:
        assert tennis_surface(competition) == expected

    @pytest.mark.parametrize("competition", ["", None, "Challenger Somewhere", "Premier League"])
    def test_unpinned_is_none_and_never_a_guess(self, competition: str | None) -> None:
        assert tennis_surface(competition) is None

    def test_atp_and_wta_are_pinned_separately(self) -> None:
        """Same discipline as tennis_match_format: never fold the two draws."""
        pinned = json.loads(
            (__import__("pathlib").Path(__file__).resolve().parents[2] / "config" / "tennis_surface_map.json").read_text()
        )["surfaces"]
        assert "US Open" not in pinned
        assert {"ATP US Open", "WTA US Open"} <= set(pinned)


class TestSurfaceIngest:
    def test_only_surface_bearing_providers_record_it(self) -> None:
        assert _surface_or_none("tennis-abstract", "Hard") == "Hard"
        assert _surface_or_none("espn-football", "Hard") is None
        assert _surface_or_none("bzzoiro", "Hard") is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("Hard", "Hard"), ("hard", "Hard"), (" GRASS ", "Grass"), ("clay", "Clay")],
    )
    def test_provider_spelling_is_normalised(self, raw: str, expected: str) -> None:
        assert _surface_or_none("tennis-abstract", raw) == expected

    @pytest.mark.parametrize("raw", ["", "Carpet", "unknown", None, 3, "hardcourt"])
    def test_anything_unplaceable_becomes_none_not_a_fourth_surface(self, raw: object) -> None:
        """A value we cannot place must read as 'not stated'.

        If it became its own category it would differ from every pinned
        surface and silently delete the observation.
        """
        assert _surface_or_none("tennis-abstract", raw) is None
