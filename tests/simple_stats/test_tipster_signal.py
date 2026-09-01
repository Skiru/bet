"""TIPSTERS: matching, column semantics, and the separation invariant.

The invariant test is the important one. Everything else here can be re-derived
by reading the code; the guarantee that tipster opinion never reaches a
statistic is a decision that has to survive future edits by people who did not
make it, so it is asserted field by field rather than described in a comment.
"""
from __future__ import annotations

from dataclasses import replace

from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
)
from bet.simple_stats.tipster_signal import (
    MATCH_THRESHOLD,
    attach_tipster_column,
    build_tipster_signal,
    column_for_row,
    summarize,
)
from bet.tipsters.contracts import TipsterPick


def _event(event_id="EV1", home="Valencia", away="Real Betis", sport="football") -> EventRecord:
    return EventRecord(
        event_id=event_id,
        sport=sport,
        competition="La Liga",
        home_team=home,
        away_team=away,
        start_time="2026-08-25T19:00:00Z",
        identity_confidence="CONFIRMED",
        status="ACTIVE",
    )


def _event_list(*events: EventRecord) -> EventListV1:
    return EventListV1(
        run_id="RID-1",
        generated_at="2026-08-25T09:00:00Z",
        date="2026-08-25",
        sports=["football"],
        events=list(events) or [_event()],
    )


def _pick(
    market="Poniżej 10,5 rzutów rożnych",
    home="Valencia",
    away="Real Betis",
    *,
    source_id="zawodtyper",
    tipster="AnalystA",
    sport="football",
    is_combo=False,
    direction="UNDER",
) -> TipsterPick:
    return TipsterPick(
        source_id=source_id,
        source_name=source_id.title(),
        sport=sport,
        event=f"{home} vs {away}",
        home_team=home,
        away_team=away,
        market=market,
        market_family="corners",
        direction=direction,
        tipster_name=tipster,
        match_date="2026-08-25",
        is_combo=is_combo,
    )


def _row(market="corners_total", line=10.5, direction="UNDER", event_id="EV1") -> StatsSheetRow:
    return StatsSheetRow(
        event_id=event_id,
        sport="football",
        market=market,
        line=line,
        direction=direction,
        hits=9,
        sample_size=12,
        hit_rate=0.75,
        p_low=0.4677,
        mean=9.4,
        median=9.0,
        sources=["espn-football", "highlightly"],
        cross_provider_agreement="AGREE",
        confidence="HIGH",
        data_quality="READY",
    )


def _sheet(*rows: StatsSheetRow) -> StatsSheetV1:
    return StatsSheetV1(
        run_id="RID-1", date="2026-08-25", generated_at="2026-08-25T12:00:00Z", rows=list(rows) or [_row()]
    )


class TestSeparationInvariant:
    """Tipster opinion is reported beside the statistics and never inside them."""

    STATISTICAL_FIELDS = (
        "event_id", "sport", "market", "line", "direction", "hits", "sample_size",
        "hit_rate", "mean", "median", "sources", "cross_provider_agreement",
        "confidence", "data_quality",
    )

    def test_attaching_the_column_changes_no_other_field(self):
        sheet = _sheet(_row(), _row(direction="OVER"), _row(market="cards_total", line=4.5))
        signal = build_tipster_signal(_event_list(), [_pick(), _pick(tipster="AnalystB")])

        after = attach_tipster_column(sheet, signal)

        assert len(after.rows) == len(sheet.rows)
        for before_row, after_row in zip(sheet.rows, after.rows):
            for field in self.STATISTICAL_FIELDS:
                assert getattr(after_row, field) == getattr(before_row, field), field

    def test_the_column_actually_landed(self):
        """Guards the test above from passing vacuously."""
        sheet = _sheet(_row())
        signal = build_tipster_signal(_event_list(), [_pick(), _pick(tipster="AnalystB")])
        after = attach_tipster_column(sheet, signal)
        assert after.rows[0].tipster is not None
        assert after.rows[0].tipster.agree == 2

    def test_row_order_is_preserved(self):
        """The sheet's ranking is statistical; agreement does not get a vote."""
        rows = [_row(line=9.5), _row(line=10.5), _row(line=11.5)]
        sheet = _sheet(*rows)
        signal = build_tipster_signal(_event_list(), [_pick()])
        after = attach_tipster_column(sheet, signal)
        assert [r.line for r in after.rows] == [9.5, 10.5, 11.5]

    def test_the_original_sheet_is_not_mutated(self):
        sheet = _sheet(_row())
        signal = build_tipster_signal(_event_list(), [_pick()])
        attach_tipster_column(sheet, signal)
        assert sheet.rows[0].tipster is None

    def test_a_sheet_without_a_signal_is_still_valid(self):
        sheet = _sheet(_row())
        assert sheet.rows[0].tipster is None
        assert "tipster" in sheet.model_dump(mode="json")["rows"][0]


class TestColumnVerdicts:
    def test_unanimous_agreement_confirms(self):
        signal = build_tipster_signal(
            _event_list(), [_pick(tipster="A"), _pick(tipster="B", source_id="typersi")]
        )
        column = column_for_row(_row(), signal)
        assert column.verdict == "CONFIRMS"
        assert (column.agree, column.oppose) == (2, 0)
        assert column.sources == ["typersi", "zawodtyper"]

    def test_unanimous_opposition_contradicts(self):
        signal = build_tipster_signal(
            _event_list(), [_pick(market="Powyżej 10,5 rzutów rożnych", direction="OVER")]
        )
        column = column_for_row(_row(direction="UNDER"), signal)
        assert column.verdict == "CONTRADICTS"
        assert (column.agree, column.oppose) == (0, 1)

    def test_disagreement_is_split_not_averaged(self):
        signal = build_tipster_signal(
            _event_list(),
            [
                _pick(tipster="A"),
                _pick(tipster="B", market="Powyżej 10,5 rzutów rożnych", direction="OVER"),
            ],
        )
        column = column_for_row(_row(), signal)
        assert column.verdict == "SPLIT"
        assert (column.agree, column.oppose) == (1, 1)

    def test_covered_fixture_with_no_comparable_claim_reports_why(self):
        """The common case: tipsters covered the match, all on 1X2."""
        signal = build_tipster_signal(
            _event_list(),
            [_pick(market="Winner: 1", direction="HOME"), _pick(market="BTTS - TAK", direction="BTTS_YES")],
        )
        column = column_for_row(_row(), signal)
        assert column.verdict == "NO_COVERAGE"
        assert column.considered == 2  # they were there...
        assert column.agree == 0  # ...but none was about this market
        assert column.excluded == {"outcome_market_not_a_total": 2}

    def test_uncovered_fixture_has_no_column_at_all(self):
        """None is 'nobody talked about this match', distinct from a 0/0 column."""
        signal = build_tipster_signal(_event_list(), [])
        assert column_for_row(_row(), signal) is None

    def test_a_stronger_claim_settles_this_row_and_is_counted(self):
        """Under 9.5 corners cannot be right while under 10.5 is wrong."""
        signal = build_tipster_signal(_event_list(), [_pick(market="Poniżej 9,5 rzutów rożnych")])
        column = column_for_row(_row(line=10.5, direction="UNDER"), signal)
        assert column.verdict == "CONFIRMS"
        assert (column.agree, column.oppose) == (1, 0)
        # Counted, but not a claim about this row's own number.
        assert column.exact == 0

    def test_a_weaker_claim_says_nothing_and_is_excluded(self):
        """Under 10.5 leaves under 9.5 entirely open, so it is not evidence."""
        signal = build_tipster_signal(_event_list(), [_pick(market="Poniżej 10,5 rzutów rożnych")])
        column = column_for_row(_row(line=9.5, direction="UNDER"), signal)
        assert column.verdict == "NO_COVERAGE"
        assert column.excluded == {"line_too_weak_to_inform": 1}

    def test_a_claim_on_this_exact_line_is_marked_exact(self):
        signal = build_tipster_signal(_event_list(), [_pick(market="Poniżej 10,5 rzutów rożnych")])
        column = column_for_row(_row(line=10.5, direction="UNDER"), signal)
        assert (column.agree, column.exact) == (1, 1)

    def test_an_incompatible_claim_contradicts(self):
        """Under 9.5 and over 10.5 cannot both land."""
        signal = build_tipster_signal(_event_list(), [_pick(market="Poniżej 9,5 rzutów rożnych")])
        column = column_for_row(_row(line=10.5, direction="OVER"), signal)
        assert column.verdict == "CONTRADICTS"
        assert (column.agree, column.oppose) == (0, 1)

    def test_a_different_market_is_never_counted(self):
        signal = build_tipster_signal(_event_list(), [_pick(market="Poniżej 9,5 rzutów rożnych")])
        column = column_for_row(_row(market="cards_total", line=10.5), signal)
        assert column.verdict == "NO_COVERAGE"
        assert column.excluded == {"different_market": 1}


class TestSubjectJoin:
    """A scoped claim must reach its own row and no other."""

    def test_a_team_claim_reaches_that_team_and_not_the_opponent(self):
        signal = build_tipster_signal(
            _event_list(), [_pick(market="Valencia powyżej 4,5 rożnych", direction="OVER")]
        )
        mine = column_for_row(_row(market="corners_for", line=4.5, direction="OVER"), signal)
        assert mine is not None
        theirs = column_for_row(
            _row(market="corners_for", line=4.5, direction="OVER"), signal
        )
        # The row fixture carries no team, so it cannot be either side's row.
        assert theirs.verdict == "NO_COVERAGE"

    def test_a_player_prop_joins_on_the_player_not_their_club(self):
        """Every player row also carries team_name, so precedence decides this.

        Reading team_name first compared the claim's player against the club and
        excluded the whole prop family, which is the largest one the sheet has.
        """
        signal = build_tipster_signal(
            _event_list(),
            [_pick(market="Hugo Duro powyżej 1,5 strzałów", direction="OVER")],
        )
        row = _row(market="player_total_shots", line=1.5, direction="OVER")
        row = row.model_copy(update={"team_name": "Valencia", "player_name": "Hugo Duro"})
        column = column_for_row(row, signal)
        assert column.verdict == "CONFIRMS"
        assert column.agree == 1

    def test_a_prop_about_someone_else_is_not_counted(self):
        signal = build_tipster_signal(
            _event_list(),
            [_pick(market="Hugo Duro powyżej 1,5 strzałów", direction="OVER")],
        )
        row = _row(market="player_total_shots", line=1.5, direction="OVER")
        row = row.model_copy(update={"team_name": "Valencia", "player_name": "Pepelu"})
        column = column_for_row(row, signal)
        assert column.verdict == "NO_COVERAGE"
        assert column.excluded == {"different_team_or_player": 1}

    def test_a_match_total_claim_does_not_leak_onto_a_per_team_row(self):
        signal = build_tipster_signal(
            _event_list(), [_pick(market="Poniżej 10,5 rzutów rożnych")]
        )
        row = _row(market="corners_total", line=10.5, direction="UNDER")
        row = row.model_copy(update={"market": "corners_for", "team_name": "Valencia"})
        column = column_for_row(row, signal)
        assert column.verdict == "NO_COVERAGE"


class TestEventMatching:
    def test_spelling_variants_match(self):
        signal = build_tipster_signal(
            _event_list(_event(home="Bodø/Glimt", away="NEC Nijmegen")),
            [_pick(home="Bodo/Glimt", away="NEC Nijmegen", market="Powyżej 9,5 rożnych", direction="OVER")],
        )
        assert signal.picks_matched == 1
        # EXACT, not FUZZY: the matcher folds ø to o, so the two renderings are
        # the same string rather than a near miss rescued by a ratio.
        assert signal.events[0].match_quality == "EXACT"
        assert signal.events[0].match_score >= MATCH_THRESHOLD

    def test_reversed_sides_still_match_and_are_flagged_fuzzy(self):
        signal = build_tipster_signal(
            _event_list(), [_pick(home="Real Betis", away="Valencia")]
        )
        assert signal.picks_matched == 1
        assert signal.events[0].match_quality == "FUZZY"

    def test_unrelated_fixture_is_reported_not_attached(self):
        signal = build_tipster_signal(
            _event_list(), [_pick(home="Jeju SK", away="Pohang", market="Winner: 1")]
        )
        assert signal.picks_matched == 0
        assert signal.picks_unmatched == 1
        assert any("Jeju SK" in entry for entry in signal.unmatched_events)

    def test_sport_mismatch_never_matches(self):
        """A tennis pick must not land on a football fixture with similar names."""
        signal = build_tipster_signal(
            _event_list(), [_pick(sport="tennis", home="Valencia", away="Real Betis")]
        )
        assert signal.picks_matched == 0

    def test_tennis_events_match_on_player_names(self):
        event = EventRecord(
            event_id="EV-T",
            sport="tennis",
            competition="ATP",
            player_one="Novak Djokovic",
            player_two="Jannik Sinner",
            start_time="2026-08-25T13:00:00Z",
            identity_confidence="CONFIRMED",
            status="ACTIVE",
        )
        signal = build_tipster_signal(
            _event_list(event),
            [_pick(sport="tennis", home="Novak Djokovic", away="Jannik Sinner", market="Over 22.5 games")],
        )
        assert signal.picks_matched == 1
        assert signal.events[0].home_team == "Novak Djokovic"


class TestSourceDeclaredCombos:
    def test_source_combo_flag_overrides_a_clean_looking_claim(self):
        """ZawodTyper's bet-builder flag is authoritative about its own products."""
        signal = build_tipster_signal(_event_list(), [_pick(is_combo=True)])
        pick = signal.events[0].picks[0]
        assert not pick.countable
        assert pick.reject_reason == "combo_bet_legs_not_separable"
        assert signal.countable_claims == 0


class TestPublicLean:
    def test_outcome_picks_are_summarised_separately(self):
        signal = build_tipster_signal(
            _event_list(),
            [
                _pick(market="Winner: 1", direction="HOME", tipster="A"),
                _pick(market="Winner: 1", direction="HOME", tipster="B"),
                _pick(market="Winner: 2", direction="AWAY", tipster="C"),
            ],
        )
        assert signal.events[0].public_lean == {"HOME": 2, "AWAY": 1}

    def test_public_lean_is_absent_from_the_column(self):
        """A 1X2 lean is a different market and must not appear as agreement."""
        signal = build_tipster_signal(
            _event_list(), [_pick(market="Winner: 1", direction="HOME") for _ in range(5)]
        )
        column = column_for_row(_row(), signal)
        assert column.agree == 0
        assert column.verdict == "NO_COVERAGE"

    def test_combos_are_excluded_from_the_lean(self):
        signal = build_tipster_signal(
            _event_list(), [_pick(market="Winner: 1", direction="HOME", is_combo=True)]
        )
        assert signal.events[0].public_lean == {}


class TestSummary:
    def test_summary_reports_exclusion_reasons(self):
        signal = build_tipster_signal(
            _event_list(),
            [_pick(), _pick(market="Winner: 1", direction="HOME"), _pick(is_combo=True)],
        )
        summary = summarize(signal)
        assert summary["picks_matched"] == 3
        assert summary["countable_claims"] == 1
        assert summary["excluded_by_reason"]["outcome_market_not_a_total"] == 1
        assert summary["excluded_by_reason"]["combo_bet_legs_not_separable"] == 1


class TestKickoffDriftGuard:
    """The date filter is deliberately loose about timezones; the event match is
    where a pick's stated date meets the fixture's real UTC kickoff."""

    def test_a_pick_from_the_same_fixture_in_another_timezone_still_matches(self):
        event = _event(event_id="EV-LATE")
        event = event.model_copy(update={"start_time": "2026-08-25T22:30:00+00:00"})
        # The source lists this 22:30 UTC fixture as 00:30 local the next day.
        pick = replace(_pick(), match_date="2026-08-26")
        signal = build_tipster_signal(_event_list(event), [pick])
        assert signal.picks_matched == 1

    def test_the_same_two_clubs_a_week_apart_do_not_match(self):
        """A two-legged tie, or last week's meeting, must not attach to today."""
        event = _event().model_copy(update={"start_time": "2026-08-25T19:00:00+00:00"})
        pick = replace(_pick(), match_date="2026-09-02")
        signal = build_tipster_signal(_event_list(event), [pick])
        assert signal.picks_matched == 0
        assert signal.picks_unmatched == 1

    def test_an_undated_pick_is_not_rejected_by_the_drift_guard(self):
        event = _event().model_copy(update={"start_time": "2026-08-25T19:00:00+00:00"})
        pick = replace(_pick(), match_date=None)
        signal = build_tipster_signal(_event_list(event), [pick])
        assert signal.picks_matched == 1

    def test_an_unparseable_event_start_time_does_not_block_matching(self):
        event = _event().model_copy(update={"start_time": "sometime tuesday"})
        signal = build_tipster_signal(_event_list(event), [_pick()])
        assert signal.picks_matched == 1


class TestColumnIndexing:
    def test_the_prebuilt_index_and_the_linear_scan_agree(self):
        signal = build_tipster_signal(_event_list(), [_pick(), _pick(tipster="B")])
        row = _row()
        index = {e.event_id: e for e in signal.events}
        assert column_for_row(row, signal) == column_for_row(row, signal, index)
