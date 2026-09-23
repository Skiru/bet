"""The three defects the 2026-09-23 PDF was built on (F55).

COUPON selected zero VALUE singles that day, so the whole PDF came from
CONFIDENCE — the path that does not ask whether a price is worth paying. All
30 printed singles were BELOW_BAR in 05_sheet.json, 29 of them carrying
"no sample could clear this price", and every one of them was priced from an
empirical-frequency metric whose shrunk centre had been computed, written to
the row's note, and then discarded.
"""

import inspect
from datetime import UTC, datetime, timedelta

from bet.sofa.confidence import has_unreachable_bar_note
from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung, SheetRow
from bet.sofa.coupon import build_coupon
from bet.sofa.engine import (
    p_empirical_centred_raw,
    p_empirical_raw,
    uses_empirical_frequency,
    winning_boundary,
)

# ---------------------------------------------------------------------------
# 1. The ladder shrink reaches the number, not just the note.
# ---------------------------------------------------------------------------


def test_no_shift_reproduces_the_raw_frequency_exactly():
    """An unshrunk caller must be bit-for-bit unaffected."""
    values = [1.0, 7.0, 3.0, 6.0, 2.0, 6.0, 4.0, 6.0, 0.0, 5.0]
    boundary = winning_boundary(4.5, "OVER")
    hits = sum(1 for v in values if v > boundary)
    assert p_empirical_centred_raw(values, boundary, "OVER", 0.0) == p_empirical_raw(
        hits, len(values)
    )


def test_the_shrunk_centre_changes_the_priced_number():
    """The real row from runs/sofa/2026-09-23, games_won_set2_for OVER 4.5.

    The note read "CENTRE_SHRUNK_TO_LADDER: sample 3.40 pulled to 5.23
    (ladder 5.84)" and the row was priced 0.40 — which is 4/10, the raw sample
    at the location the shrink had just rejected.
    """
    values = [1.0, 6.0, 2.0, 6.0, 3.0, 1.0, 6.0, 4.0, 2.0, 3.0]
    assert abs(sum(values) / len(values) - 3.4) < 1e-9
    centre = 5.2316
    boundary = winning_boundary(4.5, "OVER")

    raw = p_empirical_centred_raw(values, boundary, "OVER", 0.0)
    shrunk = p_empirical_centred_raw(values, boundary, "OVER", centre - 3.4)

    # Three observations clear 4.5 where the sample sits; the shrink moves
    # every one of them up by 1.8316, so three more cross. The sample keeps
    # its shape and only changes location, which is the point.
    assert raw == 0.3
    assert shrunk == 0.6
    assert shrunk > raw, "a centre pulled UP must not lower an OVER"


def test_the_shift_moves_over_and_under_in_opposite_directions():
    values = [1.0, 6.0, 2.0, 6.0, 3.0, 1.0, 6.0, 4.0, 2.0, 3.0]
    shift = 1.8316
    over = p_empirical_centred_raw(values, winning_boundary(4.5, "OVER"), "OVER", shift)
    under = p_empirical_centred_raw(
        values, winning_boundary(4.5, "UNDER"), "UNDER", shift
    )
    assert over > 0.3
    assert under < 0.7
    assert abs(over + under - 1.0) < 1e-9, "4.5 is unpushable, so the two must sum to 1"


def test_a_shrink_toward_the_sample_is_a_no_op():
    """centre == mean means no shrink happened, and nothing may move."""
    values = [2.0, 4.0, 6.0, 8.0]
    boundary = winning_boundary(4.5, "OVER")
    mean = sum(values) / len(values)
    assert p_empirical_centred_raw(values, boundary, "OVER", mean - mean) == 0.5


def test_both_estimator_call_sites_pass_the_centre():
    """F30: run_sheet and settle must price the SAME estimator.

    The centred frequency moves every empirical rung, so a settle path left on
    the raw one would recalibrate the curve against a model no coupon was ever
    built from — measuring nothing, which is the F30 mistake repeated.
    """
    import bet.sofa.settle as settle_mod
    import scripts.sofa.run_sheet as sheet_mod

    for mod in (sheet_mod, settle_mod):
        src = inspect.getsource(mod)
        assert "p_empirical_centred_raw(" in src, mod.__name__
        assert "p_empirical_raw(hits, n)" not in src, (
            f"{mod.__name__} still prices the raw sample at its unshrunk location"
        )


def test_the_metrics_that_carried_the_whole_2026_09_23_pdf_are_empirical():
    """209 of that day's 230 confidence singles sat on these four."""
    for market in (
        "games_won_set1_for",
        "games_won_set2_for",
        "games_won_for",
        "sets_total",
    ):
        assert uses_empirical_frequency(market), market


# ---------------------------------------------------------------------------
# 2. CONFIDENCE refuses a price no sample could have justified.
# ---------------------------------------------------------------------------


def test_an_unreachable_row_is_refused():
    notes = [
        "CENTRE_SHRUNK_TO_LADDER: sample 3.40 pulled to 5.23",
        "UNREACHABLE_BAR: no sample could clear this price "
        "(market_p 0.7513, best possible required odds 1.2931 > offered 1.27)",
        "UNFITTED_CONSTANTS: K_PRICE, MAX_LADDER_SIGMA",
    ]
    assert has_unreachable_bar_note(notes)


def test_a_merely_below_bar_row_is_not_refused():
    """The gate is deliberately narrow.

    CONFIDENCE exists to answer a different question from COUPON. 9,867 of the
    2026-09-23 sheet's 10,917 rows are BELOW_BAR; refusing them here would not
    fix the stage, it would delete it.
    """
    assert not has_unreachable_bar_note(["PRICE_GAP: edge -0.351 vs market"])
    assert not has_unreachable_bar_note([])
    assert not has_unreachable_bar_note(None)


def test_the_gate_is_wired_into_the_stage():
    import scripts.sofa.run_confidence as mod

    src = inspect.getsource(mod)
    assert "has_unreachable_bar_note(row.get(\"notes\"))" in src
    assert 'refused["UNREACHABLE_BAR"]' in src


# ---------------------------------------------------------------------------
# 3. The page shows the clock the stage gated on.
# ---------------------------------------------------------------------------


def _fixture(kickoff: datetime, superbet: datetime | None) -> Fixture:
    return Fixture(
        sofascore_event_id=17160579,
        superbet_event_ids=["1"],
        sport="tennis",
        kickoff_utc=kickoff,
        home_name="Isabel Adrover Gallego",
        away_name="Kateryna Lazarenko",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="ITF W50 Yecla Women",
        competition_id=3,
        season_id=4,
        category_name="ITF Women",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=3,
        superbet_kickoff_utc=superbet,
    )


def _sheet_row() -> SheetRow:
    return SheetRow(
        sofascore_event_id=17160579,
        sport="tennis",
        market="games_won_for",
        subject="kateryna lazarenko",
        line=4.5,
        direction="OVER",
        sample_size=10,
        sample_mean=6.0,
        sample_sd=1.0,
        centre=6.0,
        p_central=0.7,
        market_p=0.66,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=0.6,
        bar_reason=None,
        required_odds=1.75,
        offered_odds=2.0,
        edge=0.2,
        surplus=0.25,
        verdict="VALUE",
        notes=[],
    )


def _offer(at: datetime) -> FixtureOffer:
    return FixtureOffer(
        sofascore_event_id=17160579,
        unmapped_markets=[],
        rungs=[
            PricedRung(
                market="games_won_for",
                subject="kateryna lazarenko",
                line=4.5,
                over_odds=2.0,
                under_odds=2.0,
                fetched_at_utc=at,
            )
        ],
    )


def test_coupon_prints_the_clock_it_gated_on():
    """Sofascore publishes ITF local time as though it were UTC, so its clock
    is the LATER one — by 8 h on the worst of the 11 mismatched singles the
    2026-09-23 PDF printed (page said 13:00Z, Superbet said 05:00Z).

    This goes through build_coupon rather than re-deriving min() beside it: the
    defect was never in the arithmetic, it was that the selected row carried a
    different field from the one the gate had read.
    """
    now = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
    sofascore = datetime(2026, 9, 23, 13, 0, tzinfo=UTC)
    superbet = datetime(2026, 9, 23, 5, 0, tzinfo=UTC)

    result = build_coupon(
        sheet_rows=[_sheet_row()],
        fixtures=[_fixture(sofascore, superbet)],
        offers=[_offer(now)],
        vetoes=[],
        current_time=now,
        min_kickoff=now + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )

    assert len(result.coupon.singles) == 1, result.dropped
    printed = result.coupon.singles[0].kickoff_utc
    assert printed == superbet
    assert sofascore - printed == timedelta(hours=8)


def test_coupon_prints_the_only_clock_when_superbet_has_none():
    now = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
    sofascore = datetime(2026, 9, 23, 13, 0, tzinfo=UTC)

    result = build_coupon(
        sheet_rows=[_sheet_row()],
        fixtures=[_fixture(sofascore, None)],
        offers=[_offer(now)],
        vetoes=[],
        current_time=now,
        min_kickoff=now + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )

    assert result.coupon.singles[0].kickoff_utc == sofascore


def test_both_staked_paths_print_the_gated_clock():
    import bet.sofa.coupon as coupon_mod
    import scripts.sofa.run_confidence as conf_mod

    assert "kickoff_utc=fixture.kickoff_utc," not in inspect.getsource(coupon_mod), (
        "COUPON gates on the earlier clock and must not print the later one"
    )
    conf_src = inspect.getsource(conf_mod)
    assert '"kickoff_utc": fx["kickoff_utc"],' not in conf_src
    assert "effective_kickoff = min(clocks)" in conf_src
