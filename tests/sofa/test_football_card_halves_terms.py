"""epochs.FOOTBALL_CARD_HALVES_TERMS: the card halves on the full-match live
centre, the side events (penalties_for, penalties_1h_for, red_cards_for at
0.5) with the side's game state. Evidence:
docs/sofa/evidence/football_card_halves_terms_2026-10-21.md."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa import football_card_halves as fch
from bet.sofa.game_state import MAX_SUPREMACY, GameStateTable
from bet.sofa.referees import RefereeEffectTable, RefereeRead, parse_effect_table
from scripts.sofa.run_sheet import card_half_rows, card_half_term_mults
from tests.sofa.test_football_card_halves import _fixture, _forecast, _rates, _rung


def test_the_switch_rides_on_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert epochs.FOOTBALL_CARD_HALVES_TERMS == "card_halves_terms_v1"
    monkeypatch.setattr(epochs, "FOOTBALL_CARD_HALVES_TERMS_FROM_UTC", None)
    assert not epochs.football_card_halves_terms("2026-10-21")
    on = datetime(2026, 10, 21, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_CARD_HALVES_TERMS_FROM_UTC", on)
    assert epochs.football_card_halves_terms("2026-10-21", on)
    assert not epochs.football_card_halves_terms("2026-10-20", on)
    assert not epochs.football_card_halves_terms(
        "2026-10-21", datetime(2026, 10, 20, 23, tzinfo=UTC))


def test_side_event_p_scales_the_league_intensity_by_the_game_state() -> None:
    p = 0.13
    lam = -math.log(1 - p)
    fav = fch.side_event_p(fch.PEN_FOR, 0.5, p, 1.0)
    assert fav == pytest.approx(1 - math.exp(-lam * math.exp(0.2760)))
    assert fch.side_event_p(fch.PEN_FOR, 0.5, p, 0.0) == pytest.approx(p)
    dog = fch.side_event_p(fch.PEN_FOR, 0.5, p, -1.0)
    assert dog is not None and fav is not None and dog < p < fav
    # reds: the outsider is sent off more often
    red_dog = fch.side_event_p(fch.RED_FOR, 0.5, 0.10, -1.5)
    assert red_dog is not None and red_dog > 0.10
    # clamped like GAME_STATE
    assert fch.side_event_p(fch.PEN_FOR, 0.5, p, 10.0) == pytest.approx(
        fch.side_event_p(fch.PEN_FOR, 0.5, p, MAX_SUPREMACY))
    # not a market / line of the term, or nothing to read: the flat rate
    assert fch.side_event_p(fch.RED_1H_FOR, 0.5, p, 1.0) is None
    assert fch.side_event_p(fch.PEN_1H_TOTAL, 0.5, p, 1.0) is None
    assert fch.side_event_p(fch.RED_FOR, 1.5, p, 1.0) is None
    assert fch.side_event_p(fch.PEN_FOR, 0.5, p, None) is None


def _effect() -> RefereeEffectTable:
    return parse_effect_table({"markets": {"cards_points_for": {
        "family": "cards_points", "beta": 0.5, "K": 10.0}}})


def test_term_mults_are_the_full_match_terms_and_one_when_off() -> None:
    fc = _forecast()
    off = card_half_term_mults(fc, None, None, None, None)
    assert off["side_a"][0] == 1.0 and off["side_b"][0] == 1.0
    gs = GameStateTable({"cards_points_for": -0.1})
    read = RefereeRead(7, 20, 30.0, None)  # ratio (30 + 10) / 30
    on = card_half_term_mults(fc, gs, _effect(), {"cards_points": read}, None)
    sup = fc.supremacy("side_a")
    assert sup is not None
    ref = (40.0 / 30.0) ** 0.5
    assert on["side_a"][0] == pytest.approx(math.exp(-0.1 * sup) * ref)
    assert on["side_b"][0] == pytest.approx(math.exp(0.1 * sup) * ref)
    assert "APPLIED" in on["side_a"][1]


def test_card_half_rows_read_the_live_centre_else_rating_x_terms() -> None:
    fc, rates = _forecast(), _rates()
    rung = _rung(fch.CARDS_1H_FOR, "Getafe", 0.5, 1.4, 2.7)
    share = rates.half_share(2, 1)
    ca = fc.centre("cards_points_for", "side_a")
    assert share is not None and ca is not None
    mults = {"side_a": (1.2, "x"), "side_b": (0.9, "y")}
    live, _ = card_half_rows(_fixture(), rung, fc, rates, {}, True,
                             {"side_a": 3.0}, mults)
    a = fch.half_count_pmf(3.0 * share, fch.HALF_NB_R[1])
    assert live[0].p_central == pytest.approx(round(1 - a[0], 4))
    assert live[0].incident_rule == epochs.FOOTBALL_CARD_HALVES_TERMS
    assert any("FOOTBALL_CARD_HALVES_TERMS" in n for n in live[0].notes)
    fallback, _ = card_half_rows(_fixture(), rung, fc, rates, {}, True, {}, mults)
    b = fch.half_count_pmf(ca[0] * 1.2 * share, fch.HALF_NB_R[1])
    assert fallback[0].p_central == pytest.approx(round(1 - b[0], 4))
    old, _ = card_half_rows(_fixture(), rung, fc, rates, {}, True)
    assert old[0].incident_rule == epochs.FOOTBALL_CARD_HALVES
    assert not any("TERMS" in n for n in old[0].notes)


def test_side_events_read_the_game_state_only_under_the_switch() -> None:
    fc, rates = _forecast(), _rates()
    rung = _rung(fch.RED_FOR, "Rayo Vallecano", 0.5, 6.0, 1.1)
    flat = rates.p_over(fch.RED_FOR, 2, 0.5)
    sup = fc.supremacy("side_b")
    assert flat is not None and sup is not None
    old, _ = card_half_rows(_fixture(), rung, fc, rates, {}, True)
    assert old[0].p_central == pytest.approx(round(flat, 4))
    new, _ = card_half_rows(_fixture(), rung, fc, rates, {}, True, {},
                            {"side_a": (1.0, ""), "side_b": (1.0, "")})
    want = fch.side_event_p(fch.RED_FOR, 0.5, flat, sup)
    assert want is not None and new[0].p_central == pytest.approx(round(want, 4))
    assert new[0].incident_rule == epochs.FOOTBALL_CARD_HALVES_TERMS
    # a total keeps the flat rate
    tot = _rung(fch.RED_1H_TOTAL, "", 0.5, 6.0, 1.1)
    t_old, _ = card_half_rows(_fixture(), tot, fc, rates, {}, True)
    t_new, _ = card_half_rows(_fixture(), tot, fc, rates, {}, True, {},
                              {"side_a": (1.0, ""), "side_b": (1.0, "")})
    assert [r.p_central for r in t_old] == [r.p_central for r in t_new]
