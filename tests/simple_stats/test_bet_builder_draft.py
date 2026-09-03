"""The Bet Builder draft tool: tier rules, thresholds, and the price it refuses.

The single most important assertion in this file is that no combined price ever
appears. Every other test protects a threshold that would otherwise be
free-handed in prose each report -- which is precisely the failure
``wilson_lower_bound`` already exists to prevent: arithmetic done in a sentence
cannot be audited, reproduced, or caught when it slips.
"""
import pytest
from pydantic import ValidationError

from bet.simple_stats.bet_builder_draft import (
    CORRELATION_LAMBDA_FLAT,
    CORRELATION_LAMBDA_NESTED,
    TIER_MARGIN,
    BetBuilderDraft,
    draft_legs,
    tier_for_row,
)
from bet.simple_stats.contracts import MarketSignalColumn, StatsSheetRow, StatsSheetV1


def _row(**overrides):
    kwargs = dict(
        event_id="evt-1", sport="football", market="corners_total", line=9.5,
        direction="UNDER", hits=9, sample_size=12, hit_rate=0.75, p_low=0.50,
        mean=9.1, median=9.0, sources=["bzzoiro", "espn-football"],
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    kwargs.update(overrides)
    return StatsSheetRow(**kwargs)


def _sheet(*rows):
    return StatsSheetV1(
        run_id="RID-1", date="2026-08-28",
        generated_at="2026-08-28T00:00:00+00:00", rows=list(rows),
    )


# --- the price that must never exist --------------------------------------


def test_a_combined_price_cannot_be_set_even_deliberately():
    """Typed ``None`` on the contract rather than defaulted to it, so this is a
    validation error and not merely an unset field somebody could fill in. The
    product of correlated legs is wrong in the direction that flatters the bet,
    and no endpoint anywhere in this stack serves a real one."""
    with pytest.raises(ValidationError):
        BetBuilderDraft(event_id="evt-1", combined_price=3.4)


def test_the_draft_never_carries_a_combined_price():
    draft = draft_legs(_sheet(_row(), _row(market="cards_total", line=4.5)), "evt-1")
    assert draft.combined_price is None
    # And the product of the legs appears nowhere in the serialized output --
    # not under another name, not as an "estimate".
    product = 1.0
    for leg in draft.legs:
        product *= leg.fair_odds
    assert product not in draft.model_dump().values()
    assert BetBuilderDraft.model_fields["combined_price"].annotation is type(None)


def test_two_correlated_legs_are_flagged_high_risk_with_the_reason():
    """Corners and cards in one match are not independent -- a foul-heavy match
    is a card-heavy match. Almost any same-game multi trips this, which is the
    point: it must be said every time, not noticed sometimes."""
    draft = draft_legs(
        _sheet(_row(market="corners_total"), _row(market="cards_total", line=4.5)), "evt-1"
    )
    assert len(draft.legs) == 2
    assert draft.correlation_risk == "HIGH"
    assert "never multiply" in draft.correlation_note.lower()


def test_a_single_leg_has_no_correlation_risk_to_report():
    draft = draft_legs(_sheet(_row()), "evt-1")
    assert draft.correlation_risk == "NOT_APPLICABLE"


# --- legs that cannot both win ---------------------------------------------


def test_a_slip_never_contains_an_arithmetically_impossible_pair():
    """"goals_total UNDER 2.5" and "Valencia goals_for OVER 2.5" were drafted
    into one slip and labelled positively correlated -- but Valencia scoring
    three forces the total to three, so the slip loses by arithmetic before
    the match kicks off. The per-team and match samples come from different
    histories and can each clear ``min_p_low`` while contradicting each other;
    the draft has to notice, because Superbet will only notice at placement,
    after the slip has burned one of the day's slots."""
    draft = draft_legs(
        _sheet(
            _row(market="goals_total", line=2.5, direction="UNDER", p_low=0.60),
            _row(market="goals_for", line=2.5, direction="OVER",
                 team_name="Valencia", p_low=0.55),
        ),
        "evt-1",
    )
    assert len(draft.legs) == 1
    assert draft.excluded.get("jointly_impossible") == 1


def test_an_integer_pair_that_can_at_best_push_is_still_impossible():
    """OVER 3 on the team and UNDER 3 on the match: at exactly three both legs
    push, and a leg that can at best push has not won the slip."""
    draft = draft_legs(
        _sheet(
            _row(market="goals_total", line=3.0, direction="UNDER", p_low=0.60),
            _row(market="goals_for", line=3.0, direction="OVER",
                 team_name="Valencia", p_low=0.55),
        ),
        "evt-1",
    )
    assert len(draft.legs) == 1
    assert draft.excluded.get("jointly_impossible") == 1


def test_a_compatible_component_pair_is_left_alone():
    """The guard must not swallow the ordinary correlated slip: a team OVER
    that fits under the match UNDER is bettable, and flagging it would turn
    the conflict check into a ban on same-family legs."""
    draft = draft_legs(
        _sheet(
            _row(market="goals_total", line=3.5, direction="UNDER", p_low=0.60),
            _row(market="goals_for", line=1.5, direction="OVER",
                 team_name="Valencia", p_low=0.55),
        ),
        "evt-1",
    )
    assert len(draft.legs) == 2
    assert "jointly_impossible" not in draft.excluded


def test_every_football_market_is_in_the_correlated_family():
    """A market outside `_CORRELATED_FOOTBALL_FAMILY` gets no correlation
    warning at all, silently -- and goals correlates with shots and corners
    at least as strongly as anything already in the set (a goal-heavy match
    is a shot-heavy match). docs/PLAN_BOGATE_STATYSTYKI.md 3bis.4: this must
    fail the moment a market is added to STANDARD_MARKET_LINES/
    PLAYER_PROP_LINES without a matching addition here."""
    from bet.simple_stats.analyze import _MARKET_STAT_TO_CANONICAL, _TEAM_MARKET_STAT_TO_CANONICAL
    from bet.simple_stats.bet_builder_draft import _CORRELATED_FOOTBALL_FAMILY
    from bet.stats.market_ranking import PLAYER_PROP_LINES, STANDARD_MARKET_LINES

    markets: set[str] = set()
    for market_def in STANDARD_MARKET_LINES["football"]:
        table = _MARKET_STAT_TO_CANONICAL if market_def["is_combined"] else _TEAM_MARKET_STAT_TO_CANONICAL
        canonical = table.get(market_def["stat"])
        if canonical is not None:
            markets.add(canonical)
    for market_def in PLAYER_PROP_LINES["football"]:
        markets.add(market_def["stat"])

    outside = markets - _CORRELATED_FOOTBALL_FAMILY
    assert not outside, f"{outside} would get no correlation warning at all"


# --- tiers: bet-analyst.md's own table, implemented ------------------------


@pytest.mark.parametrize(
    "sample_size,agreement,quality,expected",
    [
        (12, "AGREE", "READY", "CALL"),
        (8, "AGREE", "READY", "CALL"),
        # Since 2026-09-02 a complete primary sample reaches CALL on its own:
        # requiring AGREE made the top tier a property of espn-football's
        # league map, and corroboration predicts +0.4pp [-2.3, +3.4].
        (12, "SINGLE_SOURCE", "READY", "CALL"),
        # ...and an incomplete one does not, however large n grows.
        (12, "SINGLE_SOURCE", "PARTIAL", "LEAN"),
        # AGREE still reaches CALL where the primary's sample is thin: two
        # providers on the same match is its own kind of complete.
        (12, "AGREE", "PARTIAL", "CALL"),
        (12, "DISAGREE", "READY", "LEAN"),
        (6, "AGREE", "READY", "LEAN"),
        # n 5-7 with nothing corroborating it: the gap in the table, answered
        # LEAN on evidence -- see
        # test_the_thin_uncorroborated_category_is_not_a_losing_one.
        (6, "SINGLE_SOURCE", "READY", "LEAN"),
        (6, "DISAGREE", "READY", "LEAN"),
        (4, "AGREE", "READY", "WEAK"),
        (2, "AGREE", "READY", "DROP"),
    ],
)
def test_the_tier_table_is_implemented_not_free_handed(
    sample_size, agreement, quality, expected
):
    assert tier_for_row(
        _row(
            sample_size=sample_size,
            cross_provider_agreement=agreement,
            data_quality=quality,
        )
    ) == expected


def test_a_single_source_row_reaches_call_only_on_a_complete_primary_sample():
    """The ceiling that replaced "single-source can never be CALL".

    Only bzzoiro keeps the two sides apart or serves player history, so those
    rows are single-source by construction however large n grows -- which under
    the old rule capped the pipeline's richest markets at LEAN forever. What
    stands in for corroboration is the primary's own completeness: settled over
    5 slates, n>=8 + READY wins 82.5% against the old rule's 82.4% on twice the
    rows, while the n>=8 rows with an incomplete sample win 81.1%.
    """
    complete = _row(sample_size=40, cross_provider_agreement="SINGLE_SOURCE")
    assert tier_for_row(complete) == "CALL"
    assert tier_for_row(complete.model_copy(update={"data_quality": "PARTIAL"})) == "LEAN"


def test_a_tennis_row_still_needs_a_second_provider_for_call():
    """The new ceiling is football-only, because that is where it was measured:
    backtest_slate settles football alone. Tennis has no primary provider, so
    its READY still means "two providers agreed" and CALL still asks for it."""
    row = _row(sport="tennis", market="total_games", line=21.5,
               cross_provider_agreement="SINGLE_SOURCE", data_quality="READY")
    assert tier_for_row(row) == "LEAN"
    assert tier_for_row(row.model_copy(update={"cross_provider_agreement": "AGREE"})) == "CALL"


def test_a_predicted_xi_prop_is_capped_at_lean():
    """The sample is real and the premise is a guess. A prop on a player who does
    not start is not a losing bet, it is a void one -- or worse, a live one on a
    substitute with twenty minutes."""
    row = _row(
        market="player_total_shots", line=1.5, direction="OVER",
        player_id="2190", player_name="Loïs Openda", lineup_status="predicted",
        sample_size=12, cross_provider_agreement="AGREE",
    )
    assert tier_for_row(row) == "LEAN"
    assert tier_for_row(row.model_copy(update={"lineup_status": "confirmed"})) == "CALL"


def test_a_blocked_row_is_dropped_however_large_its_sample():
    assert tier_for_row(_row(sample_size=40, data_quality="BLOCKED")) == "DROP"


# --- context flags: may downgrade once, never promote (Faza 5b) -----------


def _flag(direction="ARGUES_AGAINST", source="referee"):
    from bet.simple_stats.contracts import ContextFlag

    return ContextFlag(source=source, direction=direction, magnitude=1.0, note="test flag")


def test_an_arguing_flag_steps_a_call_down_to_lean():
    row = _row(sample_size=12, cross_provider_agreement="AGREE")
    assert tier_for_row(row) == "CALL"
    flagged = row.model_copy(update={"context_flags": [_flag()]})
    assert tier_for_row(flagged) == "LEAN"


def test_an_arguing_flag_steps_a_lean_down_to_weak():
    row = _row(sample_size=6, cross_provider_agreement="AGREE")
    assert tier_for_row(row) == "LEAN"
    flagged = row.model_copy(update={"context_flags": [_flag()]})
    assert tier_for_row(flagged) == "WEAK"


def test_an_arguing_flag_never_pushes_weak_to_drop():
    row = _row(sample_size=4, cross_provider_agreement="AGREE")
    assert tier_for_row(row) == "WEAK"
    flagged = row.model_copy(update={"context_flags": [_flag()]})
    assert tier_for_row(flagged) == "WEAK"


def test_multiple_arguing_flags_still_step_down_only_once():
    row = _row(sample_size=12, cross_provider_agreement="AGREE")
    flagged = row.model_copy(
        update={"context_flags": [_flag(source="referee"), _flag(source="weather")]}
    )
    assert tier_for_row(flagged) == "LEAN"


def test_a_supporting_flag_never_promotes_and_never_downgrades():
    row = _row(sample_size=6, cross_provider_agreement="SINGLE_SOURCE")
    assert tier_for_row(row) == "LEAN"
    flagged = row.model_copy(update={"context_flags": [_flag(direction="SUPPORTS")]})
    assert tier_for_row(flagged) == "LEAN"


# --- thresholds -----------------------------------------------------------


def test_minimum_odds_is_fair_odds_plus_the_tiers_margin():
    """Both margins are above 1.0 because ``p_low`` is already an optimistic
    floor: its trials are not independent (the sample pools both teams and their
    h2h), so a price exactly at fair odds loses money at the true probability."""
    draft = draft_legs(_sheet(_row(p_low=0.50)), "evt-1")
    leg = draft.legs[0]
    assert leg.tier == "CALL"
    assert leg.fair_odds == pytest.approx(2.0)
    assert leg.min_acceptable_odds == pytest.approx(2.0 * TIER_MARGIN["CALL"])


def test_a_lean_needs_more_headroom_than_a_call():
    """A LEAN carries a structural caveat a CALL does not, so the same fair odds
    must clear a higher bar before it is worth taking."""
    call = draft_legs(_sheet(_row(p_low=0.50)), "evt-1").legs[0]
    # PARTIAL rather than SINGLE_SOURCE: what separates the tiers since
    # 2026-09-02 is whether the primary's sample is complete, not whether a
    # corroborator happened to cover the competition.
    lean = draft_legs(
        _sheet(_row(p_low=0.50, data_quality="PARTIAL",
                    cross_provider_agreement="SINGLE_SOURCE")), "evt-1"
    ).legs[0]
    assert call.fair_odds == lean.fair_odds
    assert lean.min_acceptable_odds > call.min_acceptable_odds


def test_weak_rows_are_excluded_and_counted_never_priced():
    """bet-analyst.md refuses to put a minimum price on three or four
    observations, because a threshold computed off four matches reads as
    precision that is not there. Putting one in a multi compounds that against
    three other legs."""
    draft = draft_legs(
        _sheet(_row(), _row(market="fouls_total", line=22.5, sample_size=4, hits=3)), "evt-1"
    )
    assert [leg.market for leg in draft.legs] == ["corners_total"]
    assert draft.excluded["tier_weak"] == 1


# --- selection ------------------------------------------------------------


def test_legs_are_ranked_by_the_sheets_own_ranking():
    draft = draft_legs(
        _sheet(
            _row(market="cards_total", line=4.5, p_low=0.44),
            _row(market="corners_total", p_low=0.61),
            _row(market="shots_on_target_total", line=6.5, p_low=0.52),
        ),
        "evt-1",
    )
    assert [leg.market for leg in draft.legs] == [
        "corners_total", "shots_on_target_total", "cards_total"
    ]


def test_a_leg_that_beats_its_price_outranks_a_more_certain_one_that_does_not():
    """Value first, exactly as the singles list ranks.

    Ranking on ``-p_low`` alone filled slips with near-tautologies. Measured
    2026-09-01: all eight slips shipped 28 legs and none beat its threshold,
    because "under 3.5 first-half goals" at p_low 0.72 is priced 1.01 and so
    outranked ``corners_for 4.5 UNDER`` at p_low 0.57 priced 2.70 -- the row
    actually worth taking, dropped as ``over_max_legs``.
    """
    tautology = _row(market="goals_1h_total", line=3.5, direction="UNDER", p_low=0.72)
    worth_it = _row(market="corners_for", line=4.5, direction="UNDER", p_low=0.57)

    prices = {"goals_1h_total": 1.01, "corners_for": 2.70}

    def price_for(row):
        return "OFFERED", prices[row.market]

    draft = draft_legs(
        _sheet(tautology, worth_it), "evt-1", max_legs=1, price_for=price_for
    )
    assert [leg.market for leg in draft.legs] == ["corners_for"]
    leg = draft.legs[0]
    assert leg.superbet_price >= leg.min_acceptable_odds
    assert draft.excluded["over_max_legs"] == 1


def test_without_prices_the_ranking_is_still_the_sheets_own():
    """No ``price_for`` means nothing to rank value on -- p_low order stands."""
    draft = draft_legs(
        _sheet(
            _row(market="goals_1h_total", line=3.5, direction="UNDER", p_low=0.72),
            _row(market="corners_for", line=4.5, direction="UNDER", p_low=0.57),
        ),
        "evt-1",
    )
    assert [leg.market for leg in draft.legs] == ["goals_1h_total", "corners_for"]


def test_among_legs_that_all_beat_their_price_the_widest_surplus_leads():
    def price_for(row):
        return "OFFERED", {"corners_total": 2.60, "cards_total": 2.20}[row.market]

    draft = draft_legs(
        _sheet(
            _row(market="cards_total", line=4.5, p_low=0.55),
            _row(market="corners_total", line=9.5, p_low=0.55),
        ),
        "evt-1",
        price_for=price_for,
    )
    assert [leg.market for leg in draft.legs] == ["corners_total", "cards_total"]


def test_a_leg_the_book_does_not_offer_is_still_dropped_not_ranked():
    """The availability gate must survive the reordering."""
    def price_for(row):
        if row.market == "corners_total":
            return "LINE_NOT_OFFERED", None
        return "OFFERED", 2.60

    draft = draft_legs(
        _sheet(
            _row(market="corners_total", line=9.5, p_low=0.80),
            _row(market="cards_total", line=4.5, p_low=0.55),
        ),
        "evt-1",
        price_for=price_for,
    )
    assert [leg.market for leg in draft.legs] == ["cards_total"]
    assert draft.excluded["superbet_line_not_offered"] == 1


def test_price_for_is_called_once_per_eligible_row():
    """Pricing moved above the loop; it must not double-charge the caller."""
    calls: list[str] = []

    def price_for(row):
        calls.append(row.market)
        return "OFFERED", 2.60

    draft_legs(
        _sheet(
            _row(market="corners_total", line=9.5, p_low=0.55),
            _row(market="cards_total", line=4.5, p_low=0.55),
        ),
        "evt-1",
        price_for=price_for,
    )
    assert sorted(calls) == ["cards_total", "corners_total"]


def test_only_this_fixtures_rows_are_drafted():
    draft = draft_legs(_sheet(_row(), _row(event_id="evt-2", market="cards_total")), "evt-1")
    assert len(draft.legs) == 1
    assert draft.legs[0].event_id == "evt-1"


def test_the_same_market_is_never_drafted_twice():
    """Two lines of one market are the same read twice, and Superbet will not
    accept both on one slip anyway."""
    draft = draft_legs(
        _sheet(_row(line=9.5, p_low=0.61), _row(line=10.5, p_low=0.55)), "evt-1"
    )
    assert len(draft.legs) == 1
    assert draft.excluded["duplicate_market"] == 1


def test_max_legs_is_honoured_and_the_overflow_counted():
    rows = [
        _row(market=m, line=4.5, p_low=0.6 - i / 100)
        for i, m in enumerate(
            ["corners_total", "cards_total", "fouls_total", "shots_total", "shots_on_target_total"]
        )
    ]
    draft = draft_legs(_sheet(*rows), "evt-1", max_legs=3)
    assert len(draft.legs) == 3
    assert draft.excluded["over_max_legs"] == 2


def test_a_fixture_with_nothing_eligible_returns_an_empty_draft_not_an_error():
    draft = draft_legs(_sheet(_row(sample_size=2)), "evt-1")
    assert draft.legs == []
    assert draft.excluded == {"tier_drop": 1}


# --- the market signal is carried, never priced with ----------------------


def test_the_market_verdict_is_reported_but_changes_no_threshold():
    """The one rule that keeps this tool honest. A CONFIRMS verdict is worth
    reading; letting it move ``min_acceptable_odds`` would put a bookmaker's
    price into a number derived from ``p_low`` and nothing else."""
    plain = _row(p_low=0.50)
    signalled = plain.model_copy(
        update={
            "market_signal": MarketSignalColumn(
                verdict="CONFIRMS", model_probability=0.62,
                market_implied_probability=0.58, market_price=1.72,
                market_bookmaker="pinnacle",
            )
        }
    )
    without = draft_legs(_sheet(plain), "evt-1").legs[0]
    with_signal = draft_legs(_sheet(signalled), "evt-1").legs[0]

    assert without.market_verdict is None
    assert with_signal.market_verdict == "CONFIRMS"
    assert with_signal.fair_odds == without.fair_odds
    assert with_signal.min_acceptable_odds == without.min_acceptable_odds
    assert with_signal.tier == without.tier


# --- the slip's own bar (2026-09-03) --------------------------------------
#
# The combined bar exists because the correlation that justified refusing it
# was measured and came back at 1.009 (95% CI [1.005, 1.013]) over 12,555
# same-fixture leg pairs settled against real results. These tests pin the
# arithmetic that replaced the refusal.


def _priced(prices):
    """A ``price_for`` that answers OFFERED at ``prices[market]``."""
    return lambda row: ("OFFERED", prices.get(row.market))


def test_the_combined_bar_is_the_margin_over_the_joint_probability():
    """``margin / (product x lambda)``, and nothing else.

    Written out here rather than trusted to the implementation because it is
    the number an operator compares a real Bet Builder price against.
    """
    sheet = _sheet(
        _row(market="corners_total", p_low=0.60, p_central=0.80),
        _row(market="cards_total", line=4.5, p_low=0.60, p_central=0.75),
    )
    draft = draft_legs(
        sheet, "evt-1",
        price_for=_priced({"corners_total": 2.00, "cards_total": 2.00}),
    )

    assert len(draft.legs) == 2
    # Neither market is inside the other, so the flat lambda applies.
    assert draft.correlation_lambda == CORRELATION_LAMBDA_FLAT
    expected_joint = 0.80 * 0.75 * CORRELATION_LAMBDA_FLAT
    assert draft.joint_probability == pytest.approx(expected_joint, abs=1e-6)
    # CALL rows, so the margin is 1.05 -- the weakest leg's, charged once.
    assert draft.min_acceptable_combined_odds == pytest.approx(
        TIER_MARGIN["CALL"] / expected_joint, abs=1e-4
    )


def test_the_slip_margin_is_charged_once_and_not_per_leg():
    """Four legs do not carry four margins.

    The margin covers a calibration error in the estimator, which is a property
    of the estimator and not of how many times it was called. Compounding it
    would demand 1.05^4 = 1.22 of headroom from a four-leg slip and is the same
    mistake ``p_low`` already made once by being multiplied.
    """
    sheet = _sheet(
        _row(market="corners_total", p_low=0.60, p_central=0.90),
        _row(market="cards_total", line=4.5, p_low=0.60, p_central=0.90),
        _row(market="fouls_total", line=20.5, p_low=0.60, p_central=0.90),
        _row(market="shots_total", line=22.5, p_low=0.60, p_central=0.90),
    )
    draft = draft_legs(sheet, "evt-1", price_for=_priced(dict.fromkeys(
        ("corners_total", "cards_total", "fouls_total", "shots_total"), 2.00
    )))

    assert len(draft.legs) == 4
    implied_margin = draft.min_acceptable_combined_odds * draft.joint_probability
    assert implied_margin == pytest.approx(TIER_MARGIN["CALL"], abs=1e-3)


def test_nested_legs_in_the_same_direction_get_the_larger_measured_lambda():
    """1.045 over 1,326 pairs, and only where one leg is inside the other.

    ``goals_for`` is counted within ``goals_total``: the same goal settles both.
    That is the one place the correlation story survived measurement.
    """
    sheet = _sheet(
        _row(market="goals_total", line=2.5, direction="UNDER", p_low=0.60, p_central=0.80),
        _row(market="goals_for", line=1.5, direction="UNDER", team_name="Valencia",
             p_low=0.60, p_central=0.80),
    )
    draft = draft_legs(
        sheet, "evt-1",
        price_for=_priced({"goals_total": 2.00, "goals_for": 2.00}),
    )

    assert len(draft.legs) == 2
    assert draft.correlation_lambda == CORRELATION_LAMBDA_NESTED


def test_the_joint_probability_never_exceeds_the_weakest_leg():
    """A slip cannot win more often than its least likely leg does.

    With a high lambda and two near-certain legs the raw product times lambda
    can exceed ``min(p)``, which is arithmetic rather than evidence.
    """
    sheet = _sheet(
        _row(market="goals_total", line=2.5, direction="UNDER", p_low=0.60, p_central=0.99),
        _row(market="goals_for", line=1.5, direction="UNDER", team_name="Valencia",
             p_low=0.60, p_central=0.99),
    )
    draft = draft_legs(
        sheet, "evt-1",
        price_for=_priced({"goals_total": 2.00, "goals_for": 2.00}),
    )

    assert draft.joint_probability <= 0.99


def test_a_leg_priced_below_its_fair_odds_is_refused_because_it_lowers_the_slip():
    """Parlay arithmetic: adding a leg multiplies expected value by
    ``price x p``. Below fair odds that is less than one, so the leg subtracts
    from a slip it appears to strengthen.

    The 2026-09-03 file took ``player_total_shots 0.5 OVER`` at 1.04 against
    fair odds of 1.15 as a fourth leg, lowering the slip's expectation by 10%
    in exchange for looking like a fuller coupon.
    """
    sheet = _sheet(
        _row(market="corners_total", p_low=0.60, p_central=0.80),
        # fair odds 1/0.90 = 1.111; offered 1.05, so it destroys value.
        _row(market="cards_total", line=4.5, p_low=0.60, p_central=0.90),
    )
    draft = draft_legs(
        sheet, "evt-1",
        price_for=_priced({"corners_total": 2.00, "cards_total": 1.05}),
    )

    assert [leg.market for leg in draft.legs] == ["corners_total"]
    assert draft.excluded["leg_would_lower_slip_value"] == 1
    # One leg is not a slip, so there is nothing to price.
    assert draft.min_acceptable_combined_odds is None


def test_legs_that_miss_the_bar_are_ranked_by_how_far_they_miss_it():
    """Not by ``p_low``, which sorts near-tautologies above every real read.

    On a normal day nothing clears its bar and every leg lands in this group.
    Ranking it on ``p_low`` is what filled the 2026-09-03 slips with legs
    priced 1.002-1.16 while the same fixtures had legs at 1.28 on the singles
    list.
    """
    # LEAN rows, so the margin is 1.10 and each leg's window between its fair
    # odds and its bar is wide enough to price inside. Both legs are on the
    # screen, both above fair odds, both below their own bar -- the group this
    # ranking governs.
    lean = dict(cross_provider_agreement="SINGLE_SOURCE", data_quality="PARTIAL")
    sheet = _sheet(
        # The near-tautology: highest p_low in the fixture, priced at almost
        # nothing. fair 1.053, bar 1.158, offered 1.08 -> ratio 0.93.
        _row(market="goals_1h_total", line=3.5, direction="UNDER",
             p_low=0.90, p_central=0.95, **lean),
        # The real read: lowest p_low, but the price nearly reaches its bar.
        # fair 1.667, bar 1.833, offered 1.80 -> ratio 0.98.
        _row(market="corners_total", p_low=0.50, p_central=0.60, **lean),
    )
    draft = draft_legs(sheet, "evt-1", price_for=_priced({
        "goals_1h_total": 1.08, "corners_total": 1.80,
    }))

    assert [leg.tier for leg in draft.legs] == ["LEAN", "LEAN"]
    # Neither leg clears its bar, so both are ranked by ratio -- and the order
    # is the reverse of what p_low alone would have given.
    assert all(
        leg.superbet_price < leg.min_acceptable_odds for leg in draft.legs
    )
    assert [leg.market for leg in draft.legs] == ["corners_total", "goals_1h_total"]
