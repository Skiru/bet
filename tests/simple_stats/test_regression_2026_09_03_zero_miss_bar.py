"""2026-09-03: a 5/5 sample bought certainty from the count model.

``p_central`` is the fitted count model read at the sample's own centre. On a
sample with no miss the fit is calibrated against values that never crossed the
line, so its tail is a property of the fit -- and the bar is ``1/p x margin``,
so a tail of 0.99 demands 1.11 and every price on the screen clears it.

The two rows in the audit, exactly as the 2026-09-03 coupon recorded them:

    Bu Yunchaokete - Michael Zheng  double_faults_total 8.5 UNDER  5/5
        p_low 0.5655   p_central 0.9936   min 1.11   Superbet 1.95  "VALUE"
    Potapova - Jeanjean            aces_for 3.5 UNDER             5/5
        p_low 0.5655   p_central 0.9620   min 1.14   Superbet 1.63  "VALUE"

Potapova's 2026 season average is 3.25 aces and she hit 10 in round one; the
sample averaged 1.4. Superbet's pivot sat exactly on her season rate, and the
sheet called its own side of it a 96% shot.

The control is the Grenal's ``cards_for`` Internacional 3.5 UNDER at 8/9: it has
a miss, so nothing here may touch it. A cap that also moved that row would be a
small-sample penalty wearing a zero-miss label.
"""
import pytest

from bet.simple_stats.bet_builder_draft import (
    BAR_REASON_LAPLACE,
    BAR_REASON_SMALL_SAMPLE,
    bar_input,
    cap_tier_at_lean,
    laplace_rate,
    required_odds,
    tier_for_row,
)
from bet.simple_stats.contracts import StatsSheetRow


def _row(**kw) -> StatsSheetRow:
    base = dict(
        event_id="evt-1",
        sport="tennis",
        market="aces_for",
        line=3.5,
        direction="UNDER",
        hits=5,
        sample_size=5,
        hit_rate=1.0,
        p_low=0.565508505247919,
        p_central=0.9620365185087212,
        mean=1.4,
        median=1.0,
        dispersion=1.18,
        sources=["tennis-abstract"],
        cross_provider_agreement="SINGLE_SOURCE",
        confidence="MEDIUM",
        data_quality="PARTIAL",
    )
    base.update(kw)
    return StatsSheetRow(**base)


# --- the two audited rows --------------------------------------------------


@pytest.mark.parametrize(
    "market,p_central,recorded_minimum",
    [
        # Potapova aces_for 3.5 UNDER, and Bu-Zheng double_faults_total 8.5
        # UNDER. Same 5/5 sample shape, same p_low, two different fitted tails.
        ("aces_for", 0.9620365185087212, 1.1434),
        ("double_faults_total", 0.99361391628506, 1.1071),
    ],
)
def test_a_five_of_five_row_can_no_longer_demand_eleven_percent(
    market, p_central, recorded_minimum
):
    row = _row(market=market, p_central=p_central)

    # What shipped on 2026-09-03, reproduced from the recorded numbers so the
    # test fails if the old behaviour ever comes back.
    assert round((1.0 / p_central) * 1.10, 4) == recorded_minimum

    probability, reason = bar_input(row, "p_central")
    assert reason == BAR_REASON_SMALL_SAMPLE
    assert probability == row.p_low
    minimum = required_odds(row, "LEAN", basis="p_central")
    assert minimum >= 1.75, minimum
    assert minimum == pytest.approx(1.9452, abs=1e-4)


def test_potapova_stops_being_worth_her_price_and_bu_zheng_clears_by_half_a_percent():
    """What this cap does on its own, stated exactly.

    Both rows were printed under "Warte swojej ceny w Superbecie". The cap takes
    Potapova's 1.63 well below her new 1.95 minimum. It does **not** remove
    Bu-Zheng: Superbet priced that line at 1.95 against a bar of 1.9452, so it
    clears by five thousandths.

    The handoff note's acceptance criterion asked for both, and one cap cannot
    deliver both -- what removes Bu-Zheng is the market prior (Phase 3), where a
    5-observation sample stops being allowed to overrule a two-sided price on
    its own: the devigged Superbet probability for that outcome was 0.47 against
    our 0.99, and shrinking a 5-observation sample toward it at k=20 puts the
    bar past 2.2. Written down here rather than quietly relaxed, because a test
    that asserted both would be asserting something this code does not do.
    """
    row = _row()
    minimum = required_odds(row, "LEAN", basis="p_central")
    assert 1.63 < minimum
    assert 1.95 > minimum
    assert minimum == pytest.approx(1.9452, abs=1e-4)


def test_a_sample_with_a_miss_is_untouched():
    """The Grenal control: 8/9 keeps its 1.29 bar.

    The bar's basis only moves on the two conditions that were measured. A row
    with an observed failure rate and n>=8 is exactly the row ``p_central``
    became the default for.
    """
    row = _row(
        sport="football",
        market="cards_for",
        line=3.5,
        hits=8,
        sample_size=9,
        hit_rate=8 / 9,
        p_low=0.5649937852319398,
        p_central=0.8148841700447622,
        cross_provider_agreement="AGREE",
        confidence="HIGH",
        data_quality="READY",
    )
    probability, reason = bar_input(row, "p_central")
    assert reason is None
    assert probability == row.p_central
    assert required_odds(row, "CALL", basis="p_central") == pytest.approx(1.2885, abs=1e-4)


# --- the two caps, separately ----------------------------------------------


def test_laplace_is_the_largest_rate_a_clean_sweep_is_evidence_for():
    assert laplace_rate(5, 5) == pytest.approx(6 / 7)
    assert laplace_rate(10, 10) == pytest.approx(11 / 12)
    assert laplace_rate(20, 20) == pytest.approx(21 / 22)
    assert laplace_rate(0, 0) is None


def test_the_laplace_cap_binds_only_where_the_model_claims_more():
    """Grêmio ``cards_for`` 4.5 UNDER at 10/10: p_central 0.9238 against a
    Laplace 0.9167, so the cap moves the bar from 1.1366 to 1.1454.

    Neom ``cards_total`` 4.5 UNDER at 10/10 claimed only 0.7968, which is
    already below Laplace, and must not move at all -- a cap that raised a
    conservative row's bar would be charging twice for the same thinness.
    """
    gremio = _row(
        sport="football", market="cards_for", line=4.5,
        hits=10, sample_size=10, hit_rate=1.0,
        p_low=0.7224598312333834, p_central=0.9238482787708098,
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    probability, reason = bar_input(gremio, "p_central")
    assert reason == BAR_REASON_LAPLACE
    assert probability == pytest.approx(11 / 12)
    assert required_odds(gremio, "CALL", basis="p_central") == pytest.approx(1.1454, abs=1e-4)

    neom = _row(
        sport="football", market="cards_total", line=4.5,
        hits=10, sample_size=10, hit_rate=1.0,
        p_low=0.5834026844289967, p_central=0.7968472132681372,
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    probability, reason = bar_input(neom, "p_central")
    assert reason is None
    assert probability == neom.p_central
    assert required_odds(neom, "CALL", basis="p_central") == pytest.approx(1.3177, abs=1e-4)


def test_the_bar_takes_the_smallest_of_everything_that_applies():
    """Both caps on one row: n<8 and no miss.

    ``p_low`` is smaller than Laplace at every n this fires on, so the
    small-sample rule wins -- but it wins by being smaller, not by being last.
    """
    row = _row(hits=5, sample_size=5)
    probability, reason = bar_input(row, "p_central")
    assert probability == min(row.p_low, laplace_rate(5, 5), row.p_central)
    assert reason == BAR_REASON_SMALL_SAMPLE


def test_the_p_low_basis_is_never_capped():
    """It is already the tighter bar and already the honest statement of a thin
    sample, so neither cap can improve on it and reporting one against it would
    be noise."""
    row = _row()
    assert bar_input(row, "p_low") == (row.p_low, None)


def test_p_central_itself_does_not_move():
    """Only the bar's input moves. ``p_central`` is what the calibration
    reporting is measured on, and moving it would make the next measurement
    uninterpretable."""
    row = _row()
    before = row.p_central
    bar_input(row, "p_central")
    required_odds(row, "LEAN", basis="p_central")
    assert row.p_central == before


# --- the tier ceiling ------------------------------------------------------


def test_a_model_separated_rung_cannot_be_a_call():
    row = _row(
        sport="football", market="cards_points_total", line=8.5,
        hits=20, sample_size=20, hit_rate=1.0,
        p_low=0.83, p_central=0.95,
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    assert tier_for_row(row) == "CALL"
    capped = row.model_copy(update={"lean_ceiling_reasons": ["RUNG_SEPARATED_BY_MODEL"]})
    assert tier_for_row(capped) == "LEAN"


def test_the_ceiling_is_a_cap_and_not_a_step():
    """Three reasons to doubt a fixture do not make it three tiers worse.

    The Grenal fires several at once -- a derby, a knockout second leg, and a
    rung the model separated -- and ``step_tier_down`` per reason would have
    taken it to DROP.
    """
    assert cap_tier_at_lean("CALL") == "LEAN"
    assert cap_tier_at_lean("LEAN") == "LEAN"
    assert cap_tier_at_lean("WEAK") == "WEAK"
    assert cap_tier_at_lean("DROP") == "DROP"

    row = _row(
        sport="football", market="cards_points_total", line=8.5,
        hits=20, sample_size=20, hit_rate=1.0, p_low=0.83, p_central=0.95,
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
        lean_ceiling_reasons=["DERBY", "KNOCKOUT_SECOND_LEG", "RUNG_SEPARATED_BY_MODEL"],
    )
    assert tier_for_row(row) == "LEAN"
