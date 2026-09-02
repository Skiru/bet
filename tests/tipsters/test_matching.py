"""Fixture-name matching: what it must join, and what it must keep apart.

Every case below is a real pairing from the 2026-09-02 slate, where 61 of 242
picks reached no fixture. The recoveries and the refusals are tested together on
purpose: each recovery here loosened something, and the pairs that must still
score zero are the reason the loosening is safe rather than merely effective.
"""
from __future__ import annotations

import pytest

from bet.tipsters.matching import pair_score, side_score

# The threshold both sides must clear. Imported as a literal rather than from
# tipster_signal to keep this module's tests about matching alone.
THRESHOLD = 82


class TestPlayersAreNotClubs:
    """Club vocabulary read against a person's name says the wrong thing."""

    @pytest.mark.parametrize(
        "source,event",
        [
            ("Shelton B.", "Ben Shelton"),
            ("Nakashima B.", "Brandon Nakashima"),
            ("Hurkacz H.", "Hubert Hurkacz"),
            ("Michelsen A.", "Alex Michelsen"),
        ],
    )
    def test_an_initial_is_not_a_reserve_team_marker(self, source, event):
        """"b" and "c" are how a second and third XI are written, and also how
        half the tour's given names begin. The club rule vetoed those players to
        zero: Ben Shelton, Brandon Nakashima and Sorana Cirstea all vanished."""
        assert side_score(source, event, person=True) >= THRESHOLD

    def test_a_short_surname_still_identifies(self):
        """The old rule wanted a shared token of four characters, which quietly
        excluded every short surname rather than the particles it meant."""
        assert side_score("Y. Wu", "Wu Yibing", person=True) >= THRESHOLD

    @pytest.mark.parametrize(
        "source,event",
        [
            ("Williams V.", "Serena Williams"),
            ("Zverev A.", "Mischa Zverev"),
            ("Cirstea J. C.", "Sorana Cirstea"),
        ],
    )
    def test_a_shared_surname_is_not_a_shared_person(self, source, event):
        """The initial has to be consistent with the full name, or it is a
        sibling, a namesake, or a source typing about someone else."""
        assert side_score(source, event, person=True) < THRESHOLD

    def test_a_shared_particle_identifies_nobody(self):
        assert side_score("de Minaur A.", "Alex de Jong", person=True) < THRESHOLD


class TestWomensFixtures:
    """The marker that Polish sources write and the event list spells out."""

    @pytest.mark.parametrize("source", ["Servette K", "Servette [K]", "Servette (K)"])
    def test_a_womens_pick_does_not_reach_the_mens_fixture(self, source):
        """This scored 86 against "Servette FC" and the pair scored 81 -- one
        point under threshold. The fixture was kept apart by luck, not by rule."""
        assert side_score(source, "Servette FC") == 0

    def test_a_womens_pick_reaches_the_womens_fixture(self):
        """Two renderings of the same marker previously vetoed each other."""
        assert side_score("Servette K", "Servette Women") >= THRESHOLD
        assert side_score("Sparta Praga K", "Sparta Prague Women") >= THRESHOLD

    def test_a_leading_k_is_not_the_marker(self):
        """Belgian clubs carry a leading "K" for Koninklijke, which means
        nothing about who is playing."""
        assert side_score("K Beerschot VA", "Beerschot VA") >= THRESHOLD


class TestAgeAndReserveSides:
    @pytest.mark.parametrize(
        "source,event",
        [
            ("Barcelona", "Barcelona B"),
            ("Palmeiras", "Palmeiras U17"),
            ("Juventude", "Juventude U17"),
        ],
    )
    def test_a_senior_pick_does_not_reach_the_junior_fixture(self, source, event):
        assert side_score(source, event) == 0

    def test_two_age_groups_are_not_one_team(self):
        assert side_score("Vasco U17", "Vasco U20") == 0

    def test_one_reserve_side_written_two_ways(self):
        assert side_score("Barcelona B", "Barcelona II") >= THRESHOLD


class TestClubRenderings:
    @pytest.mark.parametrize(
        "source,event",
        [
            ("Falkirk", "Falkirk F.C."),
            ("Midtyland", "FC Midtjylland"),
            ("Bayern Monachium", "Bayern Munich"),
            ("Red Bull Salzburg", "RB Salzburg"),
            ("Rapid Vienna", "Rapid Wien"),
            ("SK Rapid", "Rapid Wien"),
            ("MK Dons", "Milton Keynes Dons"),
            ("AEL Larissa", "Larisa"),
            ("Mardin 1969", "Mardin BB"),
            ("St. Truiden", "Sint-Truidense VV"),
            ("Royale Union SG", "Royale Union Saint-Gilloise"),
            ("Royale Union SG", "Union Saint-Gilloise"),
            ("Arab Contractors", "El Mokawloon"),
        ],
    )
    def test_renderings_of_one_club_join(self, source, event):
        assert side_score(source, event) >= THRESHOLD

    def test_dotted_initials_are_not_a_third_team(self):
        """"F.C." folds to the two tokens "f" and "c", and "c" is how a third XI
        is written -- so Falkirk was vetoed against itself."""
        assert side_score("Falkirk", "Falkirk F.C.") >= THRESHOLD

    @pytest.mark.parametrize(
        "source,event",
        [
            ("Real Madrid", "Real Sociedad"),
            ("Sparta Praga", "Sparta Rotterdam"),
            ("Rapid Wien", "Rapid Bucuresti"),
            ("FC Zurich", "FC Basel"),
            ("Union SG", "Union Berlin"),
        ],
    )
    def test_clubs_sharing_a_word_stay_apart(self, source, event):
        """Structure words and city prefixes are shared by dozens of clubs. The
        score has to turn on the identifying part of the name, not the decoration."""
        assert side_score(source, event) < THRESHOLD


class TestPairOrientation:
    def test_a_reversed_listing_is_the_same_fixture(self):
        score, swapped = pair_score("Rangers", "Falkirk", "Falkirk F.C.", "Rangers")
        assert score >= THRESHOLD
        assert swapped

    def test_recognising_one_side_is_not_a_fixture(self):
        score, _ = pair_score("Falkirk", "Celtic", "Falkirk F.C.", "Rangers")
        assert score < THRESHOLD
