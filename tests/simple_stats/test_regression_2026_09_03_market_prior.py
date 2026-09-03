"""2026-09-03: the book's own two-sided price was read and never used.

For every row the audit read, the devigged Superbet pivot was available and
disagreed with us by 20 to 50 points -- cards at a 7.5 pivot against a sample
median of 5.5, fouls 36.5 against 27.4, aces 3.5 against 1.4. The pipeline
downloaded the whole ladder, compared one rung's price against a threshold, and
threw the rest away. ``MAX_MARKET_DISAGREEMENT`` annotated the gap;
``MAX_LADDER_SIGMA`` demoted on it; neither let it into the arithmetic.

Every number below is from ``runs/2026-09-03/2026-09-03_coupons.json`` as it
shipped, so the market probability is reconstructed the way the file recorded
it: ``market_disagreement`` is ``p_central - p_mkt``, so ``p_mkt`` is the
difference. The four rows the handoff note names, and what each one's bar has
to do:

    row                                          n   p_central  p_mkt  price
    Grenal cards_for Inter 3.5 UNDER             9   0.8149     0.4375  2.07  clears
    Potapova aces_for 3.5 UNDER                  5   0.9620     0.5653  1.63  does not
    Dart games_won 5.5 OVER                      5   0.9152     0.6586  1.41  does not
    Bu-Zheng double_faults_total 8.5 UNDER       5   0.9936     0.4715  1.95  does not

The three that must fail are all n=5 in a tennis length-dependent market, where
k is 20 and a five-observation sample therefore keeps a fifth of its own
opinion. The one that must clear is n=9 football at k=10 and keeps nearly half.
"""
import pytest

from bet.simple_stats.bet_builder_draft import (
    DEFAULT_SHRINK_K,
    AnalystVeto,
    VetoIndex,
    bar_components,
    required_odds,
    shrink_k_for_market,
)
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.coupons import (
    VETO_CLASS_DOUBLE_K,
    VETO_CLASS_ZERO_WEIGHT,
    build_coupons,
)
from bet.simple_stats.superbet_offer import (
    devigged_ladder,
    devigged_probability,
    ladder_centre,
)

# --- the four audited rows, as recorded -----------------------------------

AUDITED = {
    "cards_for": dict(
        sport="football", market="cards_for", line=3.5, direction="UNDER",
        team_name="Internacional", hits=8, sample_size=9, hit_rate=8 / 9,
        p_low=0.5649937852319398, p_central=0.8148841700447622,
        mean=2.44, median=2.0, dispersion=1.56,
        p_mkt=0.4375, price=2.07, tier="CALL",
    ),
    "aces_for": dict(
        sport="tennis", market="aces_for", line=3.5, direction="UNDER",
        team_name="Anastasia Potapova", hits=5, sample_size=5, hit_rate=1.0,
        p_low=0.565508505247919, p_central=0.9620365185087212,
        mean=1.4, median=1.0, dispersion=1.18,
        p_mkt=0.5653, price=1.63, tier="LEAN",
    ),
    "games_won": dict(
        sport="tennis", market="games_won", line=5.5, direction="OVER",
        team_name="Harriet Dart", hits=5, sample_size=5, hit_rate=1.0,
        p_low=0.565508505247919, p_central=0.9152146620141512,
        mean=8.6, median=9.0, dispersion=2.93,
        p_mkt=0.6586, price=1.41, tier="LEAN",
    ),
    "double_faults_total": dict(
        sport="tennis", market="double_faults_total", line=8.5, direction="UNDER",
        team_name=None, hits=5, sample_size=5, hit_rate=1.0,
        p_low=0.565508505247919, p_central=0.99361391628506,
        mean=4.2, median=4.0, dispersion=2.05,
        p_mkt=0.4715, price=1.95, tier="LEAN",
    ),
}


def _row(spec: dict, **overrides) -> StatsSheetRow:
    fields = {
        k: v for k, v in spec.items() if k not in ("p_mkt", "price", "tier")
    }
    fields.update(
        event_id="evt-1",
        sources=["bzzoiro"],
        cross_provider_agreement="AGREE" if spec["sample_size"] >= 8 else "SINGLE_SOURCE",
        confidence="HIGH" if spec["sample_size"] >= 8 else "MEDIUM",
        data_quality="READY",
    )
    fields.update(overrides)
    return StatsSheetRow(**fields)


# --- the prior itself ------------------------------------------------------


@pytest.mark.parametrize("name", sorted(AUDITED))
def test_the_four_audited_rows_land_where_the_plan_says(name):
    spec = AUDITED[name]
    row = _row(spec)
    components = bar_components(
        row, "p_central", market_probability=spec["p_mkt"]
    )
    k = shrink_k_for_market(spec["market"])
    expected_weight = spec["sample_size"] / (spec["sample_size"] + k)
    assert components.weight == pytest.approx(expected_weight)

    minimum = required_odds(
        row, spec["tier"], basis="p_central", market_probability=spec["p_mkt"]
    )
    clears = spec["price"] >= minimum
    assert clears is (name == "cards_for"), (
        f"{name}: price {spec['price']} against minimum {minimum}"
    )


def test_the_grenal_card_row_still_clears_at_two_oh_seven():
    """The control, and the reason the prior is a weight and not a gate.

    Nine observations at k=10 keep 47% of their own opinion, so an edge of
    0.815 against 0.438 survives shrinking to 0.616 and the CALL margin fits
    inside it: the bar goes from 1.29 to 1.70 and Superbet pays 2.07. A gate
    that demoted on disagreement would have taken this row, which is the trade
    2026-09-02 made and reversed.
    """
    spec = AUDITED["cards_for"]
    row = _row(spec)
    components = bar_components(row, "p_central", market_probability=spec["p_mkt"])
    assert components.probability == pytest.approx(0.6163, abs=1e-3)
    minimum = required_odds(row, "CALL", basis="p_central", market_probability=spec["p_mkt"])
    assert minimum == pytest.approx(1.7036, abs=1e-3)
    assert spec["price"] > minimum
    # And it survives being capped to LEAN by a structural ceiling, which the
    # Grenal collects several of.
    lean = required_odds(row, "LEAN", basis="p_central", market_probability=spec["p_mkt"])
    assert spec["price"] > lean


def test_a_relative_edge_is_what_the_bar_now_asks_for():
    """The bar restated: beat the devigged price by ``margin_excess / w``.

    ``price * p_shrunk >= margin`` with ``price ~ 1/p_mkt`` reduces to
    ``p_bar / p_mkt - 1 >= (margin - 1) / w``. At n=5 and k=20, w is 0.2 and the
    demand is a 50% relative edge; at n=20 and k=10 it is 15%. That is the
    whole behaviour change in one line, and it is stated as a property because
    it is what an operator has to hold in his head.
    """
    for n, k, margin in ((5, 20.0, 1.10), (20, 10.0, 1.05)):
        p_mkt = 0.50
        needed = p_mkt * (1.0 + (margin - 1.0) / (n / (n + k)))
        row = _row(
            AUDITED["cards_for"],
            market="corners_total", team_name=None,
            hits=n, sample_size=n, hit_rate=1.0,
            p_low=needed, p_central=needed,
        )
        minimum = required_odds(
            row, "CALL" if margin == 1.05 else "LEAN",
            basis="p_central", market_probability=p_mkt, shrink_k=k,
        )
        # 1/p_mkt is the devigged fair price; at exactly the needed edge the bar
        # sits on it.
        assert minimum == pytest.approx(1.0 / p_mkt, rel=0.01)


def test_no_readable_price_means_no_prior():
    """A one-way market leaves the row priced on its sample alone.

    Not defaulted, not skipped: we cannot shrink toward a price we cannot read,
    and the pre-2026-09-03 behaviour is the correct answer for that row.
    """
    row = _row(AUDITED["cards_for"])
    components = bar_components(row, "p_central", market_probability=None)
    assert components.weight is None
    assert components.p_market is None
    assert components.probability == components.p_bar == row.p_central


def test_k_is_higher_where_the_sample_is_least_likely_to_measure_the_right_thing():
    assert shrink_k_for_market("corners_total") == DEFAULT_SHRINK_K
    assert shrink_k_for_market("cards_points_total") == DEFAULT_SHRINK_K
    for market in ("aces_total", "aces_for", "double_faults_total", "total_games",
                   "games_won", "total_sets", "breaks_total"):
        assert shrink_k_for_market(market) == 20.0


# --- devigging and the single-rung ladder ---------------------------------


def _line(market, line, direction, price, team=None, status="active"):
    return SuperbetLine(
        market=market, line=line, direction=direction, price=price,
        team_name=team, source_market_name=market, source_outcome_name="x",
        status=status,
    )


def test_devigging_removes_the_overround_and_not_less_than_it():
    offer = SuperbetEventOffer(
        superbet_event_id="1", superbet_match_name="A·B", sport="football",
        kickoff="2026-09-03T20:00:00Z", event_id="evt-1", match_quality="EXACT",
        lines=[
            _line("corners_total", 9.5, "UNDER", 1.90),
            _line("corners_total", 9.5, "OVER", 1.90),
        ],
    )
    # A symmetric pair devigs to exactly 0.5 whatever the overround.
    assert devigged_probability(
        offer, market="corners_total", line=9.5, direction="UNDER", team_name=None
    ) == pytest.approx(0.5)
    # 1/1.90 is 0.526, which is the overround and not a probability.
    assert 1 / 1.90 > 0.5


def test_one_rung_locates_the_centre_and_agrees_with_the_interpolated_answer():
    """The Grenal's own cards ladder, and why the single-rung path is trusted.

    The recorded run read ``ladder_sigma`` -0.878 for that sample off the whole
    ladder. From the 7.5 pivot alone -- devigged 0.4931 against a sample mean
    of 5.5 and a dispersion of 2.35 -- the same arithmetic gives -0.868. Ten
    thousandths of a standard deviation apart, which is what makes it defensible
    to read a centre from one rung on the 9 of 15 singles that had only one.
    """
    ladder = SuperbetEventOffer(
        superbet_event_id="1", superbet_match_name="A·B", sport="football",
        kickoff="2026-09-03T20:00:00Z", event_id="evt-1", match_quality="EXACT",
        lines=[
            _line("cards_points_total", 6.5, "UNDER", 2.65),
            _line("cards_points_total", 6.5, "OVER", 1.47),
            _line("cards_points_total", 7.5, "UNDER", 1.85),
            _line("cards_points_total", 7.5, "OVER", 1.90),
            _line("cards_points_total", 8.5, "UNDER", 1.42),
            _line("cards_points_total", 8.5, "OVER", 2.75),
        ],
    )
    cdf = devigged_ladder(ladder, market="cards_points_total", team_name=None)
    assert sorted(cdf) == [6.5, 7.5, 8.5]
    interpolated = ladder_centre(cdf, dispersion=2.35)
    assert interpolated is not None

    single = SuperbetEventOffer(
        superbet_event_id="1", superbet_match_name="A·B", sport="football",
        kickoff="2026-09-03T20:00:00Z", event_id="evt-1", match_quality="EXACT",
        lines=[
            _line("cards_points_total", 7.5, "UNDER", 1.85),
            _line("cards_points_total", 7.5, "OVER", 1.90),
        ],
    )
    from_pivot = ladder_centre(
        devigged_ladder(single, market="cards_points_total", team_name=None),
        dispersion=2.35,
    )
    assert from_pivot is not None
    assert from_pivot == pytest.approx(interpolated, abs=0.15)


def test_a_single_rung_needs_the_samples_own_spread():
    """Scale-free by construction: the pivot alone says only ``P(X < L)``, and
    turning that into a location needs a unit. No dispersion, no answer --
    never a ratio, which is the mistake ``ladder-check-must-be-scale-free``
    records."""
    cdf = {7.5: 0.4931}
    assert ladder_centre(cdf, dispersion=None) is None
    assert ladder_centre(cdf, dispersion=0.0) is None
    assert ladder_centre(cdf, dispersion=2.35) == pytest.approx(7.54, abs=0.02)
    # A pivot at certainty pins nothing and is refused.
    assert ladder_centre({7.5: 1.0}, dispersion=2.35) is None


# --- Phase 4: the analyst's verdicts get teeth ----------------------------


def _sheet(*rows):
    return StatsSheetV1(
        run_id="RID", date="2026-09-03",
        generated_at="2026-09-03T00:00:00+00:00", rows=list(rows),
    )


def _events():
    return EventListV1(
        run_id="RID", generated_at="2026-09-03T00:00:00+00:00",
        date="2026-09-03", sports=["football"],
        events=[EventRecord(
            event_id="evt-1", sport="football", competition="Copa do Brasil",
            start_time="2026-09-03T23:00:00+00:00",
            home_team="Grêmio", away_team="Internacional",
            identity_confidence="CONFIRMED", status="ACTIVE",
        )],
    )


def _offer(*lines):
    return SuperbetOfferV1(
        run_id="RID", date="2026-09-03",
        generated_at="2026-09-03T18:00:00+00:00",
        events=[SuperbetEventOffer(
            superbet_event_id="1", superbet_match_name="Grêmio·Internacional",
            sport="football", kickoff="2026-09-03T23:00:00Z",
            event_id="evt-1", match_quality="EXACT", lines=list(lines),
        )],
    )


FOULS_TOTAL = dict(
    sport="football", market="fouls_total", line=36.5, direction="UNDER",
    team_name=None, hits=19, sample_size=21, hit_rate=19 / 21,
    p_low=0.7108541613925933, p_central=0.930786138365556,
    mean=27.4, median=27.0, dispersion=5.23,
)
FOULS_PRICE = 1.82
FOULS_MKT = 0.930786138365556 - 0.4335


def _fouls_coupons(vetoes=None, price=FOULS_PRICE):
    """The Grenal's ``fouls_total`` 36.5 UNDER, priced against its own pivot.

    The offer carries both sides of 36.5 at prices whose devigged UNDER is the
    0.497 the recorded run implies, so the coupon reconstructs the same market
    probability the audit read.
    """
    under = 1.0 / (FOULS_MKT / 0.96)
    over = 1.0 / ((1.0 - FOULS_MKT) / 0.96)
    return build_coupons(
        _sheet(_row(FOULS_TOTAL)),
        _events(),
        superbet_offer=_offer(
            _line("fouls_total", 36.5, "UNDER", round(price, 2)),
            _line("fouls_total", 36.5, "OVER", round(over, 2)),
        ),
        vetoes=vetoes,
    )


def test_the_fouls_row_that_shipped_as_value_still_does_without_a_class():
    """The starting point. The prior alone does not remove it: 21 observations
    at k=10 keep 68% of their opinion, 0.931 against 0.497 shrinks to 0.792,
    and 1.10/0.792 = 1.39 against a price of 1.82."""
    coupons = _fouls_coupons()
    single = coupons.singles[0]
    assert single.superbet_verdict == "VALUE"
    assert single.sample_weight == pytest.approx(21 / 31, abs=1e-3)


@pytest.mark.parametrize("reason_class", sorted(VETO_CLASS_ZERO_WEIGHT))
def test_a_sample_declared_uninformative_is_worth_zero_observations(reason_class):
    """What DOWNGRADE should have meant on 2026-09-03.

    The analyst wrote "conditional on this match the record is 1/3, not 19/21".
    Under the old rule that bought a tier step -- 1.05 to 1.10 on the margin,
    a 5% move -- and the row printed as value at 1.82. With the class, the
    sample's weight is zero and the row is priced on the book's own devigged
    number plus the margin, which is a price the book does not sell.
    """
    veto = AnalystVeto(
        event_id="evt-1", market="fouls_total", action="DOWNGRADE",
        reason="conditional on this match the record is 1/3, not 19/21",
        reason_class=reason_class,
    )
    coupons = _fouls_coupons(vetoes=[veto])
    single = coupons.singles[0]
    assert single.sample_weight == 0.0
    assert single.bar_probability == single.market_probability
    assert single.superbet_verdict == "PRICED_BELOW_THRESHOLD"
    assert single.tier == "LEAN"


def test_missing_referee_halves_the_samples_weight_rather_than_deleting_it():
    """A card market with no referee is not measuring nothing.

    The two clubs' own histories are real; what is missing is the one input with
    no corroborating provider at all, and a referee is worth about a third of
    the spread in a cards line. So k doubles -- 21 observations at k=20 keep
    51% rather than 68% -- and the row stays in the file.
    """
    veto = AnalystVeto(
        event_id="evt-1", market="fouls_total", action="DOWNGRADE",
        reason="no referee assigned", reason_class="MISSING_REFEREE",
    )
    coupons = _fouls_coupons(vetoes=[veto])
    single = coupons.singles[0]
    assert single.sample_weight == pytest.approx(21 / 41, abs=1e-3)
    assert 0.0 < single.sample_weight < 21 / 31
    assert "MISSING_REFEREE" in VETO_CLASS_DOUBLE_K


def test_a_structural_missing_referee_ceiling_doubles_k_too():
    """ANALYZE's own flag does what the analyst's hand-written one does.

    The fault is the same fault -- no ``referee_id`` on the fixture -- and it
    would be strange for the pipeline to charge for it only when a human
    remembered to write it down.
    """
    row = _row(FOULS_TOTAL, lean_ceiling_reasons=["MISSING_REFEREE"])
    coupons = build_coupons(
        _sheet(row), _events(),
        superbet_offer=_offer(
            _line("fouls_total", 36.5, "UNDER", FOULS_PRICE),
            _line("fouls_total", 36.5, "OVER", round(1.0 / ((1.0 - FOULS_MKT) / 0.96), 2)),
        ),
    )
    single = coupons.singles[0]
    assert single.sample_weight == pytest.approx(21 / 41, abs=1e-3)
    assert single.tier == "LEAN"


def test_line_on_mode_without_a_line_names_no_rung_and_is_reported():
    """A per-rung fault written market-wide would strike every rung on a fault
    that belongs to one of them. Refused, and said out loud -- silently
    dropping a decision the analyst wrote down is worse than either applying or
    refusing it."""
    veto = AnalystVeto(
        event_id="evt-1", market="fouls_total", action="DOWNGRADE",
        reason="36.5 sits on the sample's mode", reason_class="LINE_ON_MODE",
    )
    index = VetoIndex([veto])
    assert index.for_row(_row(FOULS_TOTAL)) is None
    assert len(index.ignored) == 1

    coupons = _fouls_coupons(vetoes=[veto])
    assert any("POMINIĘTE WETO" in note for note in coupons.notes)


def test_line_on_mode_with_a_line_applies_to_that_rung_only():
    veto = AnalystVeto(
        event_id="evt-1", market="fouls_total", line=36.5, direction="UNDER",
        action="DOWNGRADE", reason="36.5 sits on the sample's mode",
        reason_class="LINE_ON_MODE",
    )
    index = VetoIndex([veto])
    assert index.for_row(_row(FOULS_TOTAL)) is veto
    assert index.for_row(_row(FOULS_TOTAL, line=38.5)) is None
    assert index.ignored == []
