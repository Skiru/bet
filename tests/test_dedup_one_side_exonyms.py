"""Merging a fixture two feeds spell in two languages.

Discovery joins fixtures by fuzzy name match at a threshold of 85, with a second
chance for token containment ("Genk" / "KRC Genk"). Neither reaches an exonym:
"FC Copenhagen" / "FC Kobenhavn" scores 63, "Diriyah Club" / "Al Diriyah" 82,
"Stade Lavallois" / "Laval" 26. An alias table is the usual answer and does not
scale -- every feed spells a different subset of the world's clubs its own way.

Until 2026-09-02 an unmerged pair meant a fixture appearing twice, which is bad.
Since ENRICH gates the slate it means a fixture **deleted twice**: one copy
carries the bzzoiro id and no Superbet price, the other the price and no id, and
the gate refuses both halves. FC Copenhagen - Nordsjaelland and Al Diriyah -
Al-Qadsiah were both lost that way on the live 2026-09-03 slate.

The rule that fixes it is a fact about football rather than a matcher tuning: a
club cannot play two matches at the same instant in the same competition.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent

KICKOFF = datetime(2026, 9, 3, 18, 0)


def _event(
    source: str,
    home: str,
    away: str,
    *,
    competition: str = "Denmark Superliga",
    kickoff: datetime = KICKOFF,
    sport: str = "football",
) -> DiscoveredEvent:
    return DiscoveredEvent(
        source=source,
        external_id=f"{source}-{home}-{away}",
        sport=sport,
        competition=competition,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status="scheduled",
    )


def _merge(*events: DiscoveredEvent):
    return DeduplicationEngine().deduplicate_events(list(events))


@pytest.mark.parametrize(
    "left,right",
    [
        # The two that were being deleted on the live 2026-09-03 slate.
        (("FC Copenhagen", "FC Nordsjaelland"), ("FC København", "FC Nordsjælland")),
        (("Diriyah Club", "Al-Qadsiah"), ("Al Diriyah", "Al-Qadsiah")),
        # The rest of the eleven found across 2026-08-28 .. 2026-09-03.
        (("Al-Fayha", "Abha Club"), ("Al-Fayha", "Abha")),
        (("Stade Lavallois", "Grenoble Foot 38"), ("Laval", "Grenoble")),
        (("West Bromwich Albion", "Charlton Athletic"), ("West Brom", "Charlton")),
        (("Atlético Mineiro", "Cruzeiro"), ("Atletico-MG", "Cruzeiro")),
        (("FC Inter Turku", "KuPS Kuopio"), ("Inter Turku", "Kuopion Palloseura")),
    ],
)
def test_one_side_and_an_identical_kickoff_merge_the_fixture(left, right):
    merged = _merge(_event("odds-api", *left), _event("bzzoiro", *right))
    assert len(merged) == 1, f"{left} and {right} stayed two fixtures"
    assert {s.source for s in merged[0].sources} == {"odds-api", "bzzoiro"}


@pytest.mark.parametrize(
    "left,right,why",
    [
        (
            ("Manchester United", "Arsenal"),
            ("Manchester City", "Aston Villa"),
            "normalize_team_name strips United and City, so both sides read "
            "'manchester' and score 100",
        ),
        (
            ("Widzew Łódź", "Polonia Bytom"),
            ("Widzew II Łódź", "Ruch Chorzów"),
            "the reserve marker is stripped too",
        ),
        (
            ("Bayern Munich", "Werder Bremen"),
            ("Bayern Munich II", "Hansa Rostock"),
            "same",
        ),
    ],
)
def test_a_stripped_word_that_distinguishes_two_clubs_blocks_the_merge(
    left, right, why
):
    merged = _merge(_event("odds-api", *left), _event("bzzoiro", *right))
    assert len(merged) == 2, f"merged on a distinguishing word: {why}"


def test_the_two_feeds_need_not_agree_on_the_competition():
    """They routinely do not: 'Puchar Polski' against 'Cup', 'Belgium First Div'
    against 'Pro League'. Requiring agreement cost two thirds of the recovery
    and left Hibernian - Hearts split in two on the live 2026-09-03 slate.

    The fact the rule rests on -- a club plays one match at a time -- does not
    care what either feed calls the competition.
    """
    merged = _merge(
        _event("odds-api", "Hibernian", "Hearts", competition="Premiership - Scotland",
               kickoff=datetime(2026, 9, 3, 18, 45)),
        _event(
            "bzzoiro", "Hibernian", "Heart of Midlothian",
            competition="Scottish Premiership",
            kickoff=datetime(2026, 9, 3, 18, 45),
        ),
    )
    assert len(merged) == 1
    assert {s.source for s in merged[0].sources} == {"odds-api", "bzzoiro"}


def test_a_different_kickoff_is_never_merged_on_one_side():
    merged = _merge(
        _event("odds-api", "FC Copenhagen", "FC Nordsjaelland"),
        _event("bzzoiro", "FC København", "Silkeborg",
               kickoff=datetime(2026, 9, 3, 18, 30)),
    )
    assert len(merged) == 2


def test_the_other_side_still_has_to_be_in_the_neighbourhood():
    """One club matching is not enough on its own: the opponent has to be a
    plausible spelling of the same club, not an unrelated one."""
    merged = _merge(
        _event("odds-api", "FC Copenhagen", "FC Nordsjaelland"),
        _event("bzzoiro", "FC København", "Randers FC"),
    )
    assert len(merged) == 2
