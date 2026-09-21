from datetime import UTC, datetime, timedelta

import pytest

from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung, SheetRow, Veto
from bet.sofa.coupon import build_coupon
from bet.sofa.veto import find_unmatched_vetoes, match_vetoes


@pytest.fixture
def base_sheet_row():
    return SheetRow(
        sofascore_event_id=1,
        sport="football",
        market="shots_on_target_for",
        subject="Player A",
        line=1.5,
        direction="OVER",
        sample_size=10,
        sample_mean=2.5,
        sample_sd=1.0,
        centre=2.2,
        p_central=0.7,
        # Was 0.5. A +0.20 model-minus-price gap is in the measured-negative
        # band (realised 0.400 against a claimed 0.677), so every test using
        # this fixture was silently exercising DISAGREES_WITH_PRICE once that
        # gate reached the coupon. The fixture is meant to be an ordinary
        # passing row.
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


@pytest.fixture
def base_fixture():
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["S1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 20, 0, tzinfo=UTC),
        home_name="Home",
        away_name="Away",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="League",
        competition_id=100,
        season_id=200,
        category_name="Country",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )


@pytest.fixture
def current_time():
    return datetime(2026, 9, 17, 10, 0, tzinfo=UTC)


def test_t26_veto_with_subject(base_sheet_row):
    row_a = base_sheet_row.model_copy(update={"subject": "Player A"})
    row_b = base_sheet_row.model_copy(update={"subject": "Player B"})
    row_c = base_sheet_row.model_copy(update={"subject": "Player C"})

    veto = Veto(
        sofascore_event_id=1,
        market="shots_on_target_for",
        subject="Player A",
        line=None,
        direction=None,
        reason_class="OTHER",
        reason="Test",
    )

    # Veto na jednego (Player A), dwa pozostale przezywaja
    assert match_vetoes(row_a, [veto]) == [veto]
    assert match_vetoes(row_b, [veto]) == []
    assert match_vetoes(row_c, [veto]) == []


def test_t27_unmatched_veto(base_sheet_row):
    row_a = base_sheet_row.model_copy(update={"subject": "Player A"})

    veto1 = Veto(
        sofascore_event_id=1,
        market="shots_on_target_for",
        subject="Player A",
        line=None,
        direction=None,
        reason_class="OTHER",
        reason="Match",
    )

    veto2 = Veto(
        sofascore_event_id=1,
        market="shots_on_target_for",
        subject="Player B",
        line=None,
        direction=None,
        reason_class="OTHER",
        reason="Unmatched",
    )

    unmatched = find_unmatched_vetoes([row_a], [veto1, veto2])
    assert unmatched == [veto2]


def test_t28_family_limit_by_surplus(base_sheet_row, base_fixture, current_time):
    # Dwa wiersze z tej samej rodziny (np. goals_total i goals_1h_total - both scoring)
    # Row 1 ma wiekszy edge, ale mniejszy surplus
    # Row 2 ma mniejszy edge, ale wiekszy surplus
    row1 = base_sheet_row.model_copy(
        update={
            "market": "goals_total",
            "edge": 0.2,  # wiekszy
            "surplus": 0.1,  # mniejszy
        }
    )

    row2 = base_sheet_row.model_copy(
        update={
            "market": "goals_1h_total",
            "edge": 0.1,  # mniejszy
            "surplus": 0.3,  # wiekszy
        }
    )

    # Both rungs need a fetched_at, or the rows drop on STALE_PRICE before
    # the family rule is ever reached.
    from bet.sofa.contracts import PricedRung

    offer = FixtureOffer(
        sofascore_event_id=1,
        unmapped_markets=[],
        rungs=[
            PricedRung(
                market="goals_total",
                subject="Player A",
                line=1.5,
                over_odds=2.0,
                under_odds=2.0,
                fetched_at_utc=current_time,
            ),
            PricedRung(
                market="goals_1h_total",
                subject="Player A",
                line=1.5,
                over_odds=2.0,
                under_odds=2.0,
                fetched_at_utc=current_time,
            ),
        ],
    )

    result = build_coupon(
        sheet_rows=[row1, row2],
        fixtures=[base_fixture],
        offers=[offer],
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )

    # Powinno wybrac row2 (wiekszy surplus)
    coupon = result.coupon
    assert len(coupon.singles) == 1
    assert coupon.singles[0].market == "goals_1h_total"
    # L18: the evicted sibling is reported, not silently dropped.
    assert any(d.reason == "FAMILY_SLOT_TAKEN" for d in result.dropped)


def test_t29_kickoff_and_stale_price(base_sheet_row, base_fixture, current_time):
    # Row1: Kickoff in past
    fixture_past = base_fixture.model_copy(
        update={"kickoff_utc": current_time - timedelta(hours=1)}
    )

    # Row2: Stale price
    fixture_stale = base_fixture.model_copy(update={"sofascore_event_id": 2})
    row_stale = base_sheet_row.model_copy(update={"sofascore_event_id": 2})

    # Row3: OK
    fixture_ok = base_fixture.model_copy(update={"sofascore_event_id": 3})
    row_ok = base_sheet_row.model_copy(update={"sofascore_event_id": 3})

    from bet.sofa.contracts import PricedRung

    offers = [
        FixtureOffer(
            sofascore_event_id=1,
            unmapped_markets=[],
            rungs=[
                PricedRung(
                    market="shots_on_target_for",
                    subject="Player A",
                    line=1.5,
                    over_odds=2.0,
                    under_odds=2.0,
                    fetched_at_utc=current_time,
                )
            ],
        ),
        FixtureOffer(
            sofascore_event_id=2,
            unmapped_markets=[],
            rungs=[
                PricedRung(
                    market="shots_on_target_for",
                    subject="Player A",
                    line=1.5,
                    over_odds=2.0,
                    under_odds=2.0,
                    fetched_at_utc=current_time - timedelta(hours=2),
                )
            ],
        ),
        FixtureOffer(
            sofascore_event_id=3,
            unmapped_markets=[],
            rungs=[
                PricedRung(
                    market="shots_on_target_for",
                    subject="Player A",
                    line=1.5,
                    over_odds=2.0,
                    under_odds=2.0,
                    fetched_at_utc=current_time,
                )
            ],
        ),
    ]

    result = build_coupon(
        sheet_rows=[base_sheet_row, row_stale, row_ok],
        fixtures=[fixture_past, fixture_stale, fixture_ok],
        offers=offers,
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )

    coupon = result.coupon
    assert len(coupon.singles) == 1
    assert coupon.singles[0].sofascore_event_id == 3
    # T29: both exclusions must be *named*, not merely absent.
    reasons = {d.reason for d in result.dropped}
    assert "KICKOFF_TOO_SOON" in reasons
    assert "STALE_PRICE" in reasons


def test_a_stale_sample_is_refused_the_way_a_stale_price_is(
    base_sheet_row, base_fixture, current_time
):
    """The price had a freshness limit from the start; the evidence had none.

    Measured 2026-09-21: the day's highest-surplus single (+2.741 at odds of
    5.90) rested on a sample whose newest match was 105 days old, and one row
    reached the coupon on a sample last updated 193 days earlier. Nothing in
    the artifact said so, and staleness is selected *for* — a sample that has
    stopped tracking a player disagrees with the price more often, and the
    coupon ranks on that disagreement.
    """
    stale = base_sheet_row.model_copy(update={"sample_newest_days": 105})
    offer = FixtureOffer(
        sofascore_event_id=1,
        rungs=[
            PricedRung(
                market=stale.market,
                subject=stale.subject,
                line=stale.line,
                over_odds=2.0,
                under_odds=1.8,
                fetched_at_utc=current_time,
            )
        ],
        unmapped_markets=[],
    )
    result = build_coupon(
        sheet_rows=[stale],
        fixtures=[base_fixture],
        offers=[offer],
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )
    assert result.coupon.singles == []
    assert [d.reason for d in result.dropped] == ["STALE_SAMPLE"]
    assert "105 days old" in result.dropped[0].detail


def test_a_fresh_sample_still_reaches_the_coupon(
    base_sheet_row, base_fixture, current_time
):
    fresh = base_sheet_row.model_copy(update={"sample_newest_days": 5})
    offer = FixtureOffer(
        sofascore_event_id=1,
        rungs=[
            PricedRung(
                market=fresh.market,
                subject=fresh.subject,
                line=fresh.line,
                over_odds=2.0,
                under_odds=1.8,
                fetched_at_utc=current_time,
            )
        ],
        unmapped_markets=[],
    )
    result = build_coupon(
        sheet_rows=[fresh],
        fixtures=[base_fixture],
        offers=[offer],
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )
    assert len(result.coupon.singles) == 1


def test_a_sample_with_no_date_is_kept_because_unknown_is_not_stale(
    base_sheet_row, base_fixture, current_time
):
    """Refusing undated samples would drop whole markets, not fix one."""
    undated = base_sheet_row.model_copy(update={"sample_newest_days": None})
    offer = FixtureOffer(
        sofascore_event_id=1,
        rungs=[
            PricedRung(
                market=undated.market,
                subject=undated.subject,
                line=undated.line,
                over_odds=2.0,
                under_odds=1.8,
                fetched_at_utc=current_time,
            )
        ],
        unmapped_markets=[],
    )
    result = build_coupon(
        sheet_rows=[undated],
        fixtures=[base_fixture],
        offers=[offer],
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )
    assert len(result.coupon.singles) == 1


def test_the_coupon_row_can_re_derive_its_own_p_bar(
    base_sheet_row, base_fixture, current_time
):
    """F48 put `calibration_correction` on the sheet row; the coupon row
    dropped it again, so three of 2026-09-21's 63 rows could not be checked
    from the file the operator actually opens."""
    row = base_sheet_row.model_copy(
        update={"calibration_correction": 0.0069, "sample_newest_days": 3}
    )
    offer = FixtureOffer(
        sofascore_event_id=1,
        rungs=[
            PricedRung(
                market=row.market,
                subject=row.subject,
                line=row.line,
                over_odds=2.0,
                under_odds=1.8,
                fetched_at_utc=current_time,
            )
        ],
        unmapped_markets=[],
    )
    result = build_coupon(
        sheet_rows=[row],
        fixtures=[base_fixture],
        offers=[offer],
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )
    single = result.coupon.singles[0]
    assert single.calibration_correction == 0.0069
    assert single.sample_newest_days == 3


def test_a_row_above_its_market_measured_ceiling_is_refused(
    base_sheet_row, base_fixture, current_time
):
    """CONFIDENCE refused these; the coupon did not, and the two paths
    disagreeing about one measured fact is how `games_won_for` ended up
    banned from the PDF and dominant in the singles. 9,286 settled rows, no
    bucket above 0.825, best measured bucket realising 0.756 — and 7 coupon
    rows on 2026-09-21 claiming p_central 0.900."""
    from bet.sofa.confidence import Calibration

    cal = Calibration(
        pooled={},
        by_market={
            "games_won_for": {"0.800-0.825": {"realised_lo95": 0.7159, "n": 480}}
        },
    )
    # market_p tracks p_central so this test isolates the ceiling gate from
    # DISAGREES_WITH_PRICE, which sits in front of it and would otherwise be
    # the reason reported.
    row = base_sheet_row.model_copy(
        update={
            "market": "games_won_for",
            "p_central": 0.90,
            "market_p": 0.88,
            "sample_newest_days": 3,
        }
    )
    def run(r, **extra):
        rung = PricedRung(
            market=r.market,
            subject=r.subject,
            line=r.line,
            over_odds=2.0,
            under_odds=1.8,
            fetched_at_utc=current_time,
        )
        return build_coupon(
            sheet_rows=[r],
            fixtures=[base_fixture],
            offers=[FixtureOffer(
                sofascore_event_id=1, rungs=[rung], unmapped_markets=[]
            )],
            vetoes=[],
            current_time=current_time,
            min_kickoff=current_time + timedelta(minutes=15),
            max_price_age=timedelta(minutes=45),
            **extra,
        )

    result = run(row, calibration=cal)
    assert result.coupon.singles == []
    assert result.dropped[0].reason == "ABOVE_MEASURED_CEILING"

    # Inside the measured range the same row is fine.
    inside = row.model_copy(update={"p_central": 0.81, "market_p": 0.79})
    assert len(run(inside, calibration=cal).coupon.singles) == 1

    # A market with no curve at all is unmeasured, not contradicted.
    uncurved = row.model_copy(update={"market": "shots_on_target_for"})
    assert len(run(uncurved, calibration=cal).coupon.singles) == 1

    # And with no calibration passed the gate is inert, as before.
    assert len(run(row).coupon.singles) == 1


def test_the_unstaked_path_is_not_looser_than_the_staked_one(
    base_sheet_row, base_fixture, current_time
):
    """MAX_DISAGREEMENT lived only in CONFIDENCE until 2026-09-21.

    Both products read the same sheet and the same samples, but only the
    staked one refused a row whose model sat far above the devigged price —
    the region measured at 0.451 realised against a claimed 0.800. On
    2026-09-21 all 22 tennis singles sat above +0.177 and six above +0.30.
    """
    from bet.sofa.confidence import MAX_DISAGREEMENT

    row = base_sheet_row.model_copy(
        update={"p_central": 0.80, "market_p": 0.40, "sample_newest_days": 3}
    )
    rung = PricedRung(
        market=row.market,
        subject=row.subject,
        line=row.line,
        over_odds=2.0,
        under_odds=1.8,
        fetched_at_utc=current_time,
    )
    kwargs = dict(
        fixtures=[base_fixture],
        offers=[FixtureOffer(
            sofascore_event_id=1, rungs=[rung], unmapped_markets=[]
        )],
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )
    result = build_coupon(sheet_rows=[row], **kwargs)
    assert result.coupon.singles == []
    assert result.dropped[0].reason == "DISAGREES_WITH_PRICE"

    # At the limit itself the row survives — the gate is on "more than".
    at_limit = row.model_copy(update={"market_p": 0.80 - MAX_DISAGREEMENT})
    assert len(build_coupon(sheet_rows=[at_limit], **kwargs).coupon.singles) == 1

    # A row with no devigged price cannot disagree with one.
    no_price = row.model_copy(update={"market_p": None})
    assert len(build_coupon(sheet_rows=[no_price], **kwargs).coupon.singles) == 1
