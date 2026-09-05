"""Player props were the one sample nothing could scope.

Found by auditing two slips the operator had already placed on 2026-09-05.
Three of their legs were player props, and all three were priced off samples
that contained matches which were not trials of tonight's fixture at all:

* **Serhou Guirassy**, shots on target, nine appearances -- of which FC Tokyo
  and Cerezo Osaka on a July tour of Japan, Fortuna Düsseldorf and
  Rot-Weiß Oberhausen in pre-season, AS Roma in a friendly, and three from
  last May. One was a Bundesliga match of the current season. The row read
  5/9, mean 1.11, ``p_central`` 0.647.
* **Niclas Füllkrug**, fouls committed, eight appearances -- of which six had
  no date at all, and those six supplied every zero behind the row's median of
  0. It read 3/8, mean 0.75, against a Superbet price of 1.21 asking 0.826.
* **Antonio Nusa**, total shots, ten appearances -- eight undateable, three of
  them the zeros. It read 7/10 against a price of 1.006.

The measurement that settled it: on that day's sheet **0 of 143,790**
``player_*`` rows carried any ``sample_excluded`` at all, against **21,184 of
34,692** team rows (61.1%). Not "few". None. Two independent causes, one per
half of this file:

1. ``fetch_bzzoiro_player_history`` passed no ``competition_id`` or
   ``season_id``, and both surviving filters -- the friendly pin and
   ``STALE_SEASON`` -- key on exactly those. The ids were already on the team
   fixture listing the caller had in hand.
2. An appearance outside that listing's window arrives with no date either, so
   even with the ids wired up it stays invisible to every rule. All 155,291
   team and tennis observations that day were dated; 55,976 of 197,176 player
   observations were not.

Both directions matter and neither subsumes the other: Guirassy's sample is
entirely dated and is fixed only by (1); Füllkrug's and Nusa's are fixed only
by (2).
"""
from __future__ import annotations

import pytest

from bet.simple_stats import analyze as analyze_module
from bet.simple_stats.analyze import analyze_dossier
from bet.simple_stats.contracts import (
    EventDossierV1,
    PlayerMetricObservation,
    ProviderValue,
)

CLUB_FRIENDLIES = "79"
BUNDESLIGA = "5"
THIS_SEASON = "2222"
LAST_SEASON = "1111"


@pytest.fixture(autouse=True)
def _clear_scope_caches():
    analyze_module.reset_scope_caches()
    yield
    analyze_module.reset_scope_caches()


def _pv(
    value: float,
    match_id: str,
    date: str,
    *,
    competition_id: str | None = BUNDESLIGA,
    season_id: str | None = THIS_SEASON,
) -> ProviderValue:
    return ProviderValue(
        provider="bzzoiro",
        match_id=match_id,
        match_date=date,
        opponent=f"Opponent {match_id}",
        value=value,
        observed_at="2026-09-05T06:00:00+00:00",
        competition_id=competition_id,
        season_id=season_id,
    )


def _dossier(player_name: str, canonical: str, l10: list[ProviderValue]):
    return EventDossierV1(
        event_id="evt",
        sport="football",
        team_a_name="Borussia Dortmund",
        team_b_name="TSG Hoffenheim",
        lineup_status="confirmed",
        player_metrics=[
            PlayerMetricObservation(
                player_id="p1",
                player_name=player_name,
                team_side="home",
                canonical_name=canonical,
                l10=l10,
            )
        ],
        readiness="PARTIAL",
    )


def _row(dossier, canonical: str, line: float):
    rows = [
        r for r in analyze_dossier(dossier)
        if r.market == canonical and r.line == line and r.direction == "OVER"
    ]
    assert rows, f"no {canonical} row at {line}"
    return rows[0]


def test_guirassys_tour_of_japan_leaves_the_shots_on_target_sample():
    """The dated half of the defect. Every appearance here carries a date, so
    only the competition pin can remove the friendlies -- and it could not fire
    at all until the player path started carrying ``competition_id``."""
    dossier = _dossier(
        "Serhou Guirassy",
        "player_shots_on_target",
        [
            _pv(2.0, "hsv", "2026-08-29"),
            _pv(1.0, "roma", "2026-08-15",
                competition_id=CLUB_FRIENDLIES, season_id="1552"),
            _pv(0.0, "tokyo", "2026-08-01",
                competition_id=CLUB_FRIENDLIES, season_id="1552"),
            _pv(0.0, "cerezo", "2026-07-29",
                competition_id=CLUB_FRIENDLIES, season_id="1552"),
            _pv(0.0, "fortuna", "2026-07-25",
                competition_id=CLUB_FRIENDLIES, season_id="1552"),
            _pv(1.0, "oberhausen", "2026-07-18",
                competition_id=CLUB_FRIENDLIES, season_id="1552"),
            _pv(5.0, "werder", "2026-05-16", season_id=LAST_SEASON),
        ],
    )
    row = _row(dossier, "player_shots_on_target", 0.5)
    assert row.sample_excluded == {"PRE_SEASON_FRIENDLY": 5, "STALE_SEASON": 1}
    assert row.sample_size == 1
    assert row.hits == 1


def test_fullkrugs_undateable_appearances_leave_the_fouls_sample():
    """The undateable half. Every zero behind the median of 0 came from an
    appearance the team's fixture window could not place."""
    dossier = _dossier(
        "Niclas Füllkrug",
        "player_fouls",
        [
            _pv(4.0, "freiburg", "2026-08-30"),
            _pv(1.0, "lueneburg", "2026-08-22"),
            *[
                _pv(v, f"nowhere{i}", "", competition_id=None, season_id=None)
                for i, v in enumerate([0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
            ],
        ],
    )
    row = _row(dossier, "player_fouls", 0.5)
    assert row.sample_excluded == {"SCOPE_UNKNOWN": 6}
    assert (row.hits, row.sample_size) == (2, 2)


def test_the_two_causes_are_independent():
    """A sample carrying both faults must lose both, and the counts partition.

    Stated because the obvious cheap fix -- dropping undateable rows only --
    would leave Guirassy untouched, and wiring the ids only would leave
    Füllkrug untouched. Neither alone closes this.
    """
    dossier = _dossier(
        "Mixed Case",
        "player_total_shots",
        [
            _pv(4.0, "league", "2026-08-30"),
            _pv(5.0, "league2", "2026-08-22"),
            _pv(0.0, "friendly", "2026-07-25",
                competition_id=CLUB_FRIENDLIES, season_id="1552"),
            _pv(6.0, "lastyear", "2026-05-16", season_id=LAST_SEASON),
            _pv(0.0, "nowhere", "", competition_id=None, season_id=None),
        ],
    )
    row = _row(dossier, "player_total_shots", 1.5)
    assert row.sample_excluded == {
        "PRE_SEASON_FRIENDLY": 1,
        "STALE_SEASON": 1,
        "SCOPE_UNKNOWN": 1,
    }
    assert (row.hits, row.sample_size) == (2, 2)


def test_a_clean_prop_sample_is_left_alone():
    """Orkun Kökçü's shots sample was the one honest prop of the audit: four
    appearances, all competitive, all this season, none below three shots. A
    filter that also shrank this one would be removing evidence, not noise."""
    dossier = _dossier(
        "Orkun Kökçü",
        "player_total_shots",
        [
            _pv(3.0, "corum", "2026-08-31"),
            _pv(3.0, "alanyaspor", "2026-08-23"),
            _pv(6.0, "eyupspor", "2026-08-16"),
            _pv(4.0, "trnava", "2026-07-14"),
        ],
    )
    row = _row(dossier, "player_total_shots", 1.5)
    assert row.sample_excluded == {}
    assert (row.hits, row.sample_size) == (4, 4)


def test_a_prop_whose_whole_sample_is_undateable_survives():
    """The context fetch failed, not the player. Deleting every prop on the
    slate because one provider call returned nothing would be a far larger
    fault than the one being fixed."""
    dossier = _dossier(
        "No Context",
        "player_total_shots",
        [
            _pv(v, f"m{i}", "", competition_id=None, season_id=None)
            for i, v in enumerate([3.0, 2.0, 4.0, 1.0, 2.0, 3.0])
        ],
    )
    row = _row(dossier, "player_total_shots", 1.5)
    assert row.sample_excluded == {}
    assert row.sample_size == 6
