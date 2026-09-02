"""A subject the operator cannot identify is not a bet.

Found 2026-09-02 by probing invariants against five real rebuilt slates:
Juventude fielded **two players called Marcos Paulo** on 2026-09-01 -- bzzoiro
ids 187 and 17556, ten appearances each, means of 1.3 and 0.8 shots -- and 46
stats-sheet rows on that slate were indistinguishable from another row because
the pipeline keyed a subject by its display name.

Three separate faults came out of the one cause:

1. **The coupon dedupe** keyed on ``_subject(row)``, the name. The second
   Marcos Paulo was counted as ``duplicate_market_for_event`` and dropped, and
   which of the two survived depended on the ranking order.
2. **The Superbet join** resolves our spelling to theirs by name
   (``player_alias_index``), so both of our rows join to the one line Superbet
   posted. One of them is certainly priced against the other's market -- the
   Benoit Paire failure shape: real numbers, real table, wrong human.
3. **The frozen-fixture diff** raised "duplicate stats-sheet row" on a sheet
   containing no duplicate bet at all, because ``_row_key`` had the same hole.

The rows stay on the sheet, where the analyst can see both and resolve them
live. They are refused a place in the coupon, and the artifact now names the
person by id.
"""
from __future__ import annotations

from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
)
from bet.simple_stats.coupons import (
    _ambiguous_player_names,
    _subject_key,
    build_coupons,
    reset_competition_tier_cache,
)


def _player_row(**overrides) -> StatsSheetRow:
    kwargs = dict(
        event_id="evt-1", sport="football", market="player_total_shots",
        line=0.5, direction="OVER", team_name="Juventude",
        player_id="187", player_name="Marcos Paulo", lineup_status="confirmed",
        hits=9, sample_size=12, hit_rate=0.75, p_low=0.60, p_central=0.78,
        mean=1.3, median=1.0, dispersion=1.3 ** 0.5, sources=["bzzoiro"],
        cross_provider_agreement="SINGLE_SOURCE", confidence="HIGH",
        data_quality="READY",
    )
    kwargs.update(overrides)
    return StatsSheetRow(**kwargs)


def _sheet(*rows) -> StatsSheetV1:
    return StatsSheetV1(
        run_id="RID-1", date="2026-09-01",
        generated_at="2026-09-01T00:00:00+00:00", rows=list(rows),
    )


def _events() -> EventListV1:
    return EventListV1(
        run_id="RID-1", generated_at="2026-09-01T00:00:00+00:00",
        date="2026-09-01", sports=["football"],
        events=[EventRecord(
            event_id="evt-1", sport="football", competition="Serie B",
            home_team="Londrina", away_team="Juventude",
            start_time="2026-09-01T22:30:00+00:00",
            identity_confidence="CONFIRMED", status="ACTIVE",
        )],
    )


def _coupons(*rows):
    reset_competition_tier_cache()
    try:
        return build_coupons(_sheet(*rows), _events(), not_before=None)
    finally:
        reset_competition_tier_cache()


# --- the identity itself ----------------------------------------------------


def test_two_people_with_one_name_are_two_subjects():
    one = _player_row(player_id="187")
    two = _player_row(player_id="17556", mean=0.8)
    assert _subject_key(one) != _subject_key(two)


def test_a_team_is_still_keyed_by_its_name():
    """A team name *is* its identity in this pipeline -- the dossier has
    exactly two of them and ``_side_for_team`` matches on the name. Keying a
    team on a player id it does not have would make every per-team row's key
    ``(None, name)``, which is what it already was."""
    row = _player_row(player_id=None, player_name=None, market="corners_for")
    assert _subject_key(row) == (None, "Juventude")


def test_the_ambiguity_is_scoped_to_one_fixture():
    """Two clubs may each field a Marcos Paulo without either being ambiguous.
    The name only fails to identify somebody *within* the event whose ladder
    is being read."""
    here = _player_row(event_id="evt-1", player_id="187")
    elsewhere = _player_row(event_id="evt-2", player_id="17556")
    assert _ambiguous_player_names([here, elsewhere]) == set()


def test_the_ambiguity_is_detected_within_a_fixture():
    rows = [_player_row(player_id="187"), _player_row(player_id="17556")]
    assert _ambiguous_player_names(rows) == {("evt-1", "Marcos Paulo")}


def test_one_person_listed_twice_is_not_ambiguous():
    """The same id at two lines is the ordinary case -- a ladder -- not two
    humans. Flagging it would refuse every player prop in the file."""
    rows = [_player_row(line=0.5), _player_row(line=1.5)]
    assert _ambiguous_player_names(rows) == set()


# --- what the coupon does about it -----------------------------------------


def test_an_ambiguous_player_reaches_the_sheet_and_not_the_coupon():
    coupons = _coupons(
        _player_row(player_id="187"),
        _player_row(player_id="17556", mean=0.8, p_low=0.58),
    )
    assert coupons.singles == []
    assert coupons.excluded.get("ambiguous_player_name") == 2
    # Not counted as duplicates: they are two different bets, and mislabelling
    # them would send the next reader looking for a dedupe bug.
    assert "duplicate_market_for_event" not in coupons.excluded


def test_an_unambiguous_player_is_unaffected():
    coupons = _coupons(_player_row(player_id="187"))
    assert len(coupons.singles) == 1
    assert coupons.singles[0].subject == "Marcos Paulo"
    assert coupons.singles[0].subject_kind == "player"
    assert coupons.singles[0].subject_id == "187"
    assert "ambiguous_player_name" not in coupons.excluded


def test_two_different_players_both_still_reach_the_coupon():
    """The fix must not make the dedupe stricter for the legitimate case. Two
    people are two subjects and each may hold a slot -- which is already true
    of two teams in one fixture."""
    coupons = _coupons(
        _player_row(player_id="187", player_name="Marcos Paulo"),
        _player_row(player_id="17556", player_name="Gabriel Taliari", mean=0.9),
    )
    assert len(coupons.singles) == 2
    assert {s.subject_id for s in coupons.singles} == {"187", "17556"}


def test_a_team_subject_carries_no_id_and_says_so():
    coupons = _coupons(_player_row(
        player_id=None, player_name=None, lineup_status=None,
        market="corners_for", line=4.5, direction="UNDER",
    ))
    assert len(coupons.singles) == 1
    single = coupons.singles[0]
    assert (single.subject, single.subject_kind, single.subject_id) == (
        "Juventude", "team", None
    )


def test_a_match_total_names_nobody():
    coupons = _coupons(_player_row(
        player_id=None, player_name=None, team_name=None, lineup_status=None,
        market="corners_total", line=9.5, direction="UNDER",
    ))
    assert len(coupons.singles) == 1
    single = coupons.singles[0]
    assert (single.subject, single.subject_kind, single.subject_id) == (None, None, None)


def test_the_bet_builder_refuses_the_same_rows_the_singles_loop_does():
    """"Every gate a single passes, a leg passes too" -- the invariant the
    2026-09-01 Bet Builder failure came from breaking, when thirty legs went
    out past gates only the singles loop applied.

    ``draft_legs`` takes a sheet rather than a row, so the refusal has to be
    applied to the sheet it is handed. Two markets here, so the slip would
    otherwise have the two legs it needs to be printed at all.
    """
    coupons = _coupons(
        _player_row(player_id="187", market="player_total_shots"),
        _player_row(player_id="17556", market="player_total_shots", mean=0.8),
        _player_row(player_id="187", market="player_fouls", line=0.5),
        _player_row(player_id="17556", market="player_fouls", line=0.5, mean=0.9),
    )
    assert coupons.slips == []
    legs = [leg for slip in coupons.slips for leg in slip.draft.legs]
    assert legs == []
