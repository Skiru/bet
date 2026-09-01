"""The coupons assembler: what reaches the operator's file, and what never can.

The single most important assertion here is that no combined price exists
anywhere in the output. Everything else protects a threshold the operator bets
real money against, which is why this is tested code rather than an agent
writing arithmetic into a report each morning.
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    MarketSignalColumn,
    StatsSheetRow,
    StatsSheetV1,
    TipsterColumn,
)
from bet.simple_stats import coupons as coupons_module
from bet.simple_stats.coupons import (
    MARKET_LABELS,
    MIN_SINGLE_P_LOW,
    CouponSet,
    build_coupons,
    competition_tier,
    market_label,
)


@pytest.fixture(autouse=True)
def _clear_competition_tier_cache():
    coupons_module.reset_competition_tier_cache()
    yield
    coupons_module.reset_competition_tier_cache()


def _row(**overrides):
    kwargs = dict(
        event_id="evt-1", sport="football", market="corners_total", line=9.5,
        direction="UNDER", hits=9, sample_size=12, hit_rate=0.75, p_low=0.60,
        mean=9.1, median=9.0, sources=["bzzoiro", "espn-football"],
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    kwargs.update(overrides)
    return StatsSheetRow(**kwargs)


def _sheet(*rows):
    return StatsSheetV1(
        run_id="RID-1", date="2026-08-29",
        generated_at="2026-08-29T00:00:00+00:00", rows=list(rows),
    )


def _events(*records):
    return EventListV1(
        run_id="RID-1", generated_at="2026-08-29T00:00:00+00:00",
        date="2026-08-29", sports=["football"], events=list(records),
    )


def _event(event_id="evt-1", home="Valencia", away="Real Betis"):
    return EventRecord(
        event_id=event_id, sport="football", competition="La Liga",
        home_team=home, away_team=away, start_time="2026-08-29T19:00:00+00:00",
        identity_confidence="CONFIRMED", status="ACTIVE",
    )


# --- the price that must never exist --------------------------------------


def test_a_combined_price_cannot_be_set_even_deliberately():
    """Typed None on the contract, not defaulted to it. The product of
    correlated legs understates the slip's real probability in the direction
    that flatters the bet, and no provider here serves a real combined price."""
    with pytest.raises(ValidationError):
        CouponSet(generated_at="x", combined_price=2.4)


def test_no_combined_price_appears_anywhere_in_the_output():
    coupons = build_coupons(
        _sheet(_row(), _row(market="cards_total", line=4.5)), _events(_event())
    )
    dumped = coupons.model_dump()
    assert dumped["combined_price"] is None
    for slip in coupons.slips:
        assert slip.draft.combined_price is None
        # and no product of the legs has been smuggled in under another name
        product = 1.0
        for leg in slip.draft.legs:
            product *= leg.fair_odds
        assert product not in slip.draft.model_dump().values()


def test_no_stake_or_ev_field_exists_on_any_coupon():
    """EV needs a price and a stake needs a bankroll; this tool has neither and
    must not appear to."""
    coupons = build_coupons(_sheet(_row()), _events(_event()))
    banned = {"stake", "ev", "expected_value", "bankroll", "kelly", "units"}
    for model in (CouponSet, type(coupons.singles[0])):
        assert not (banned & set(model.model_fields))


# --- selection ------------------------------------------------------------


def test_rows_below_the_threshold_never_become_singles():
    """Below p_low 0.50 the fair odds pass 2.00, and after the tier margin the
    required price exceeds what these markets realistically pay. Printing one as
    a bet is printing something unplaceable."""
    coupons = build_coupons(_sheet(_row(p_low=MIN_SINGLE_P_LOW - 0.01)), _events(_event()))
    assert coupons.singles == []
    assert coupons.excluded["p_low_below_threshold"] == 1


def test_weak_and_dropped_rows_never_become_singles():
    coupons = build_coupons(
        _sheet(_row(sample_size=4, hits=4), _row(sample_size=2, hits=2)), _events(_event())
    )
    assert coupons.singles == []
    assert coupons.excluded["tier_weak"] == 1
    assert coupons.excluded["tier_drop"] == 1


def test_one_market_per_fixture_so_four_lines_are_not_four_bets():
    """Four lines of one market are one read, not four bets, and would otherwise
    fill the file with the same opinion at different prices."""
    coupons = build_coupons(
        _sheet(
            _row(line=8.5, p_low=0.72), _row(line=9.5, p_low=0.68),
            _row(line=10.5, p_low=0.61), _row(line=11.5, p_low=0.55),
        ),
        _events(_event()),
    )
    assert len(coupons.singles) == 1
    assert coupons.singles[0].line == 8.5
    assert coupons.excluded["duplicate_market_for_event"] == 3


def test_singles_are_ranked_by_p_low_not_hit_rate():
    """Real figures from `wilson_lower_bound`: 6/6 is a hit rate of 1.000 and a
    p_low of 0.6097; 19/21 is 0.905 and 0.7109. Ranking on hit_rate would put
    the perfect-but-tiny sample on top, which is the whole reason p_low is the
    sort key. (4/4 would make the point even harder but never reaches this
    function -- n<5 is WEAK and is excluded before ranking.)"""
    coupons = build_coupons(
        _sheet(
            _row(market="cards_total", line=4.5, hits=6, sample_size=6, hit_rate=1.0, p_low=0.6097),
            _row(market="corners_total", hits=19, sample_size=21, hit_rate=0.905, p_low=0.7109),
        ),
        _events(_event()),
    )
    assert [s.market for s in coupons.singles] == ["corners_total", "cards_total"]
    # The higher hit_rate genuinely is the lower-ranked one.
    assert coupons.singles[0].hit_rate < coupons.singles[1].hit_rate


# --- edge ranking: priced rows outrank unpriced ones (Faza 5c) ------------


def _signal(**overrides):
    kwargs = dict(
        verdict="CONFIRMS", model_probability=0.64,
        market_implied_probability=0.58, market_price=1.74, market_bookmaker="unibet",
    )
    kwargs.update(overrides)
    return MarketSignalColumn(**kwargs)


def test_a_priced_row_outranks_an_unpriced_row_with_higher_p_low():
    """The whole point of Faza 5c: p_low alone cannot tell a row with a real
    edge over the market apart from one that merely has no price to compare
    against. A lower-p_low goals row with a real edge must lead a higher-p_low
    cards row that has no market reference at all."""
    priced = _row(
        market="goals_total", line=2.5, p_low=0.55,
        market_signal=_signal(market_implied_probability=0.45),
    )
    unpriced = _row(market="cards_total", line=4.5, p_low=0.80)
    coupons = build_coupons(_sheet(priced, unpriced), _events(_event()))
    assert [s.market for s in coupons.singles] == ["goals_total", "cards_total"]
    assert coupons.singles[0].edge == pytest.approx(0.10)
    assert coupons.singles[1].edge is None


def test_priced_rows_are_ranked_by_edge_not_p_low():
    bigger_edge_lower_p_low = _row(
        market="goals_total", line=2.5, p_low=0.55,
        market_signal=_signal(market_implied_probability=0.40),
    )
    smaller_edge_higher_p_low = _row(
        market="corners_total", line=9.5, p_low=0.70,
        market_signal=_signal(market_implied_probability=0.68),
    )
    coupons = build_coupons(
        _sheet(smaller_edge_higher_p_low, bigger_edge_lower_p_low), _events(_event())
    )
    assert [s.market for s in coupons.singles] == ["goals_total", "corners_total"]


def test_no_market_data_verdict_is_not_treated_as_a_market_reference():
    """A NO_MARKET_DATA verdict still carries a MarketSignalColumn -- checking
    for the object rather than for market_implied_probability would put this
    row in the wrong section and crash computing its edge against None."""
    row = _row(p_low=0.60, market_signal=MarketSignalColumn(
        verdict="NO_MARKET_DATA", reason="market not covered by provider",
    ))
    coupons = build_coupons(_sheet(row), _events(_event()))
    assert coupons.singles[0].edge is None


# --- competition tier: youth/friendly stay off the coupon (Faza 5d) -------


def _use_tier_map(monkeypatch, tmp_path, tiers):
    import json

    path = tmp_path / "competition_tier_map.json"
    path.write_text(json.dumps({"tiers": tiers}), encoding="utf-8")
    monkeypatch.setattr(coupons_module, "_COMPETITION_TIER_MAP_PATH", path)
    coupons_module.reset_competition_tier_cache()


def test_a_youth_competition_is_excluded_even_above_the_p_low_floor(monkeypatch, tmp_path):
    _use_tier_map(monkeypatch, tmp_path, {"Premier League 2": "YOUTH"})
    row = _row(p_low=0.90)
    events = _events(EventRecord(
        event_id="evt-1", sport="football", competition="Premier League 2",
        home_team="A", away_team="B", start_time="2026-08-29T19:00:00+00:00",
        identity_confidence="CONFIRMED", status="ACTIVE",
    ))
    coupons = build_coupons(_sheet(row), events)
    assert coupons.singles == []
    assert coupons.excluded.get("competition_youth_or_friendly") == 1


def test_a_friendly_competition_is_excluded_from_slips_too(monkeypatch, tmp_path):
    _use_tier_map(monkeypatch, tmp_path, {"Friendlies Clubs": "FRIENDLY"})
    row_a = _row(market="corners_total", line=9.5, p_low=0.65)
    row_b = _row(market="cards_total", line=4.5, p_low=0.60)
    events = _events(EventRecord(
        event_id="evt-1", sport="football", competition="Friendlies Clubs",
        home_team="A", away_team="B", start_time="2026-08-29T19:00:00+00:00",
        identity_confidence="CONFIRMED", status="ACTIVE",
    ))
    coupons = build_coupons(_sheet(row_a, row_b), events)
    assert coupons.singles == []
    assert coupons.slips == []


def test_an_unmapped_competition_is_not_guessed_at():
    """No entry in the map is not TIER_3 by default -- guessing would be the
    same overconfident mapping mistake the pinned ESPN map was fixed for."""
    assert competition_tier("Some League Nobody Has Classified Yet") is None
    coupons = build_coupons(_sheet(_row(p_low=0.90)), _events(_event()))
    assert len(coupons.singles) == 1


def test_a_broken_tier_map_file_degrades_to_excluding_nothing(monkeypatch, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(coupons_module, "_COMPETITION_TIER_MAP_PATH", path)
    coupons_module.reset_competition_tier_cache()

    coupons = build_coupons(_sheet(_row(p_low=0.90)), _events(_event()))
    assert len(coupons.singles) == 1


# --- analyst vetoes: the closed loop from bet-analyst to the coupon (Faza 5e) --


def _veto(**overrides):
    from bet.simple_stats.coupons import AnalystVeto

    kwargs = dict(
        event_id="evt-1", market="corners_total", line=9.5, direction="UNDER",
        action="VETO", reason="test reason",
    )
    kwargs.update(overrides)
    return AnalystVeto(**kwargs)


def test_a_veto_removes_the_row_and_reports_why():
    coupons = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()),
        vetoes=[_veto(reason="suspended fixture")],
    )
    assert coupons.singles == []
    assert coupons.excluded.get("analyst_veto") == 1
    assert any("suspended fixture" in n for n in coupons.notes)


def test_a_downgrade_steps_the_tier_down_once_without_touching_p_low():
    row = _row(p_low=0.90, cross_provider_agreement="AGREE", sample_size=12)
    assert build_coupons(_sheet(row), _events(_event())).singles[0].tier == "CALL"

    coupons = build_coupons(
        _sheet(row), _events(_event()),
        vetoes=[_veto(action="DOWNGRADE", reason="thin referee sample")],
    )
    single = coupons.singles[0]
    assert single.tier == "LEAN"
    assert single.p_low == 0.90
    assert any("thin referee sample" in n for n in coupons.notes)


def test_a_downgrade_that_reaches_weak_is_excluded_like_any_other_weak_row():
    row = _row(p_low=0.90, cross_provider_agreement="SINGLE_SOURCE", sample_size=6)
    assert build_coupons(_sheet(row), _events(_event())).singles[0].tier == "LEAN"

    coupons = build_coupons(
        _sheet(row), _events(_event()),
        vetoes=[_veto(action="DOWNGRADE")],
    )
    assert coupons.singles == []
    assert coupons.excluded.get("tier_weak") == 1


def test_a_veto_for_a_different_row_is_a_no_op():
    coupons = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()),
        vetoes=[_veto(event_id="evt-does-not-exist")],
    )
    assert len(coupons.singles) == 1


def test_no_vetoes_is_the_default_and_changes_nothing():
    with_none = build_coupons(_sheet(_row(p_low=0.90)), _events(_event()))
    with_empty = build_coupons(_sheet(_row(p_low=0.90)), _events(_event()), vetoes=[])
    assert with_none.singles == with_empty.singles
    assert with_none.excluded == with_empty.excluded
    assert with_none.notes == with_empty.notes


def _market_context(*, football_unlimited_entitled=None, entitlements=()):
    from bet.simple_stats.contracts import EventMarketContext, MarketContextV1

    return MarketContextV1(
        generated_at="2026-08-29T00:00:00+00:00",
        football_unlimited_entitled=football_unlimited_entitled,
        events=[
            EventMarketContext(
                event_id=f"evt-{i}", provider_event_id=f"p{i}", comparison_entitlement=e,
            )
            for i, e in enumerate(entitlements)
        ],
    )


def test_no_market_context_is_the_default_and_adds_no_note():
    with_none = build_coupons(_sheet(_row(p_low=0.90)), _events(_event()))
    with_explicit_none = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()), market_context=None,
    )
    assert with_none.notes == with_explicit_none.notes
    assert not any("Football Unlimited" in n for n in with_none.notes)


def test_a_fully_entitled_run_adds_no_entitlement_note():
    coupons = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()),
        market_context=_market_context(
            football_unlimited_entitled=True, entitlements=["ENTITLED", "ENTITLED"],
        ),
    )
    assert not any("Football Unlimited" in n for n in coupons.notes)


def test_a_run_that_never_attempted_the_probe_adds_no_note():
    """NOT_ATTEMPTED alone is not evidence the entitlement is gone -- it is
    already surfaced per-event as its own data_gap message."""
    coupons = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()),
        market_context=_market_context(entitlements=["NOT_ATTEMPTED"]),
    )
    assert not any("Football Unlimited" in n for n in coupons.notes)


def test_a_confirmed_not_entitled_run_warns_first_in_the_notes():
    coupons = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()),
        market_context=_market_context(
            football_unlimited_entitled=False, entitlements=["NOT_ENTITLED"],
        ),
    )
    assert coupons.notes
    assert "Football Unlimited" in coupons.notes[0]
    assert "NOT_ENTITLED" in coupons.notes[0]


def test_an_entitlement_probe_error_also_warns_even_though_the_bool_cannot_see_it():
    """The run-level bool only ever caches ENTITLED/NOT_ENTITLED (never
    ERROR), so the note must read the per-event field directly or an errored
    probe would pass through silently."""
    coupons = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()),
        market_context=_market_context(
            football_unlimited_entitled=None, entitlements=["ERROR"],
        ),
    )
    assert any("Football Unlimited" in n for n in coupons.notes)


def test_mid_run_entitlement_drift_is_reported_with_both_values_seen():
    coupons = build_coupons(
        _sheet(_row(p_low=0.90)), _events(_event()),
        market_context=_market_context(
            football_unlimited_entitled=False,
            entitlements=["ENTITLED", "NOT_ENTITLED"],
        ),
    )
    note = next(n for n in coupons.notes if "Football Unlimited" in n)
    assert "ENTITLED" in note and "NOT_ENTITLED" in note


def test_a_trivial_low_line_under_never_leads_the_file():
    """'Player carded UNDER 0.5' at 10/10 lands near 0.72 -- above almost every
    corners row -- because most players are not carded in most matches, which is
    also exactly why that side is priced near 1.05 and is not a bet."""
    trivial = _row(
        market="player_cards", line=0.5, direction="UNDER", p_low=0.80,
        player_id="p1", player_name="Openda", lineup_status="confirmed",
        team_name="Valencia",
    )
    real = _row(market="corners_total", p_low=0.61)
    coupons = build_coupons(_sheet(trivial, real), _events(_event()))
    assert [s.market for s in coupons.singles] == ["corners_total", "player_cards"]
    assert any("niska linia" in c.lower() for c in coupons.singles[1].caveats)
    assert any("UNDER" in n for n in coupons.notes)


# --- thresholds -----------------------------------------------------------


def test_minimum_odds_carries_the_tier_margin_over_fair_odds():
    """p_low is already an optimistic floor -- its trials are not independent --
    so a price exactly at fair odds loses money at the true probability."""
    call = build_coupons(_sheet(_row(p_low=0.50)), _events(_event())).singles[0]
    assert call.tier == "CALL"
    assert call.fair_odds == pytest.approx(2.0)
    assert call.min_acceptable_odds == pytest.approx(2.10)


def test_a_lean_needs_more_headroom_than_a_call_at_the_same_p_low():
    call = build_coupons(_sheet(_row(p_low=0.60)), _events(_event())).singles[0]
    lean = build_coupons(
        _sheet(_row(p_low=0.60, cross_provider_agreement="SINGLE_SOURCE")), _events(_event())
    ).singles[0]
    assert call.fair_odds == lean.fair_odds
    assert lean.min_acceptable_odds > call.min_acceptable_odds


def test_the_market_signal_is_reported_but_moves_no_threshold():
    """A CONFIRMS verdict is worth reading. Letting it change min_acceptable_odds
    would put a bookmaker's price into a number derived from p_low and then check
    the price against it -- circular."""
    plain = _row(p_low=0.60)
    signalled = plain.model_copy(update={"market_signal": MarketSignalColumn(
        verdict="CONFIRMS", model_probability=0.64,
        market_implied_probability=0.58, market_price=1.74, market_bookmaker="unibet",
    )})
    a = build_coupons(_sheet(plain), _events(_event())).singles[0]
    b = build_coupons(_sheet(signalled), _events(_event())).singles[0]
    assert a.market_verdict is None and b.market_verdict == "CONFIRMS"
    assert b.market_price == 1.74 and b.market_bookmaker == "unibet"
    assert b.min_acceptable_odds == a.min_acceptable_odds
    assert b.tier == a.tier


def test_tipster_agreement_is_reported_but_moves_no_threshold():
    plain = _row(p_low=0.60)
    with_tipster = plain.model_copy(update={"tipster": TipsterColumn(
        verdict="CONFIRMS", agree=3, oppose=0, considered=7, sources=["zawodtyper"],
    )})
    a = build_coupons(_sheet(plain), _events(_event())).singles[0]
    b = build_coupons(_sheet(with_tipster), _events(_event())).singles[0]
    assert a.tipster is None and b.tipster == "3/3"
    assert b.min_acceptable_odds == a.min_acceptable_odds


# --- slips ----------------------------------------------------------------


def test_a_one_leg_slip_is_not_a_slip():
    """It is a single wearing a different hat, and printing it in both sections
    double-counts one read."""
    coupons = build_coupons(_sheet(_row()), _events(_event()))
    assert coupons.singles and coupons.slips == []


def test_slips_are_ranked_by_their_weakest_leg():
    """A slip settles on every leg, so its evidence is the evidence of the leg
    you are least sure about. Averaging would let three strong legs carry a
    fourth nobody should be betting."""
    strong = _sheet(
        _row(event_id="evt-1", market="corners_total", p_low=0.90),
        _row(event_id="evt-1", market="cards_total", line=4.5, p_low=0.88),
        _row(event_id="evt-2", market="corners_total", p_low=0.95),
        _row(event_id="evt-2", market="cards_total", line=4.5, p_low=0.55),
    )
    coupons = build_coupons(strong, _events(_event("evt-1"), _event("evt-2", "Lyon", "Nice")))
    # evt-2 has the single best leg (0.95) but the worst weakest leg (0.55).
    assert [s.event_id for s in coupons.slips] == ["evt-1", "evt-2"]
    assert coupons.slips[0].weakest_leg_p_low == pytest.approx(0.88)


def test_correlated_legs_are_flagged_high_on_every_slip_that_has_them():
    coupons = build_coupons(
        _sheet(
            _row(market="corners_total", p_low=0.70),
            _row(market="cards_total", line=4.5, p_low=0.68),
        ),
        _events(_event()),
    )
    assert coupons.slips[0].draft.correlation_risk == "HIGH"
    assert "never multiply" in coupons.slips[0].draft.correlation_note.lower()


# --- identity -------------------------------------------------------------


def test_every_coupon_names_its_fixture():
    """event_id is a hash. A file that shows one to a human is not a deliverable."""
    coupons = build_coupons(_sheet(_row()), _events(_event()))
    assert coupons.singles[0].match == "Valencia – Real Betis"
    assert coupons.singles[0].competition == "La Liga"


def test_a_missing_event_list_says_so_rather_than_printing_a_hash():
    coupons = build_coupons(_sheet(_row()), None)
    assert "nieznany mecz" in coupons.singles[0].match


def test_a_tennis_fixture_is_named_by_its_players():
    event = EventRecord(
        event_id="evt-t", sport="tennis", competition="Cincinnati (atp_1000)",
        player_one="Sinner", player_two="Alcaraz",
        start_time="2026-08-29T17:00:00+00:00",
        identity_confidence="CONFIRMED", status="ACTIVE",
    )
    coupons = build_coupons(
        _sheet(_row(event_id="evt-t", sport="tennis", market="total_games", line=21.5)),
        _events(event),
    )
    assert coupons.singles[0].match == "Sinner – Alcaraz"


def test_market_labels_are_human_readable_and_fall_back_safely():
    assert market_label("corners_total") == "rożne (mecz)"
    assert market_label("some_new_market") == "some new market"


def _football_canonical_markets():
    """Every canonical row.market a football STATS_SHEET_V1 row can carry,
    derived the same way analyze.py derives them -- so a market added to
    STANDARD_MARKET_LINES/PLAYER_PROP_LINES without a label lights this up
    immediately (docs/PLAN_BOGATE_STATYSTYKI.md 3bis.3) instead of silently
    falling back to `market.replace("_", " ")` -- an English name in a Polish
    coupon file, silently."""
    from bet.simple_stats.analyze import _MARKET_STAT_TO_CANONICAL, _TEAM_MARKET_STAT_TO_CANONICAL
    from bet.stats.market_ranking import PLAYER_PROP_LINES, STANDARD_MARKET_LINES

    markets: set[str] = set()
    for market_def in STANDARD_MARKET_LINES["football"]:
        table = _MARKET_STAT_TO_CANONICAL if market_def["is_combined"] else _TEAM_MARKET_STAT_TO_CANONICAL
        canonical = table.get(market_def["stat"])
        if canonical is not None:
            markets.add(canonical)
    for market_def in PLAYER_PROP_LINES["football"]:
        markets.add(market_def["stat"])
    return sorted(markets)


@pytest.mark.parametrize("market", _football_canonical_markets())
def test_every_football_market_has_a_polish_label(market):
    assert market in MARKET_LABELS, f"{market!r} falls back to market_label()'s English default"


# --- the clock: a started match is not a bet ------------------------------


def _at(iso):
    return datetime.fromisoformat(iso)


def test_a_fixture_that_already_kicked_off_is_dropped_from_singles():
    """The file is read hours after it is written. A match in the past is not a
    bet at any price, however good its p_low looks sitting at the top."""
    sheet = _sheet(
        _row(event_id="past", p_low=0.95),
        _row(event_id="ahead", p_low=0.70),
    )
    events = _events(
        _event("past").model_copy(update={"start_time": "2026-08-29T12:00:00+00:00"}),
        _event("ahead").model_copy(update={"start_time": "2026-08-29T21:00:00+00:00"}),
    )
    coupons = build_coupons(sheet, events, not_before=_at("2026-08-29T18:00:00+00:00"))

    assert [s.event_id for s in coupons.singles] == ["ahead"]
    assert coupons.excluded["kickoff_passed"] == 1
    assert coupons.not_before == "2026-08-29T18:00:00+00:00"


def test_a_started_fixture_does_not_consume_a_singles_slot():
    """Filtered before the max_singles cap, not after. Otherwise a morning
    match with a high p_low silently pushes a bettable evening one off the end
    of the list -- the row disappears and nothing says why."""
    rows = [_row(event_id="past", p_low=0.95, market=m) for m in ("corners_total", "cards_total")]
    rows += [_row(event_id="ahead", p_low=0.70, market=m) for m in ("corners_total", "cards_total")]
    events = _events(
        _event("past").model_copy(update={"start_time": "2026-08-29T12:00:00+00:00"}),
        _event("ahead").model_copy(update={"start_time": "2026-08-29T21:00:00+00:00"}),
    )
    coupons = build_coupons(
        _sheet(*rows), events, max_singles=2, not_before=_at("2026-08-29T18:00:00+00:00")
    )

    assert len(coupons.singles) == 2
    assert {s.event_id for s in coupons.singles} == {"ahead"}


def test_no_cutoff_keeps_the_whole_day_for_review():
    """Reviewing yesterday needs every fixture, including the played ones."""
    sheet = _sheet(_row(event_id="past", p_low=0.95))
    events = _events(
        _event("past").model_copy(update={"start_time": "2026-08-29T12:00:00+00:00"})
    )
    coupons = build_coupons(sheet, events, not_before=None)

    assert len(coupons.singles) == 1
    assert coupons.not_before is None
    assert "kickoff_passed" not in coupons.excluded


def test_an_unknown_kickoff_is_kept_not_dropped():
    """Not knowing when a match starts is not evidence that it started.
    Dropping it would silently hide a live fixture from the operator."""
    sheet = _sheet(_row(event_id="orphan", p_low=0.95))
    coupons = build_coupons(sheet, None, not_before=_at("2026-08-29T18:00:00+00:00"))

    assert len(coupons.singles) == 1
    assert "kickoff_passed" not in coupons.excluded


def test_the_cutoff_is_an_argument_so_the_build_stays_reproducible():
    """Same artifact plus same cutoff must give the same file. If the clock
    were read inside, a coupon set could never be re-derived from its inputs."""
    sheet = _sheet(_row(event_id="ahead", p_low=0.70))
    events = _events(
        _event("ahead").model_copy(update={"start_time": "2026-08-29T21:00:00+00:00"})
    )
    cutoff = _at("2026-08-29T18:00:00+00:00")
    first = build_coupons(sheet, events, not_before=cutoff)
    second = build_coupons(sheet, events, not_before=cutoff)

    assert first.model_dump(exclude={"generated_at"}) == second.model_dump(
        exclude={"generated_at"}
    )
