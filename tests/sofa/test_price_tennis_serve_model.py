"""The tennis serve-model pricer: match-chain invariants and the Superbet join.

Offline and fast. The chain is enumerated exactly, so the invariants are
checked to floating-point tolerance; the point-by-point Monte Carlo is the
independent implementation the enumerator is held against.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from scripts.sofa.price_tennis_serve_model import (
    Obs,
    Outcome,
    Quote,
    earliest_kickoff,
    fit_surface_rating,
    form_mixture,
    is_pre_match,
    match_distribution,
    model_ev,
    outcome_probability,
    outcome_value,
    pair_two_way,
    parse_outcome,
    quotes_from_payload,
    set_distribution,
    simulate_match_points,
    superbet_swapped,
    surface_family,
    tiebreak_win_prob,
)

NAMES = ("Jan Kowalski", "Piotr Nowak")


def p_of(dist: Any, o: Outcome) -> float:
    return outcome_probability(dist, o).p_settled_win


# --------------------------------------------------------------------------
# Chain invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pa,pb", [(0.62, 0.58), (0.55, 0.55), (0.70, 0.50)])
def test_path_probabilities_sum_to_one(pa: float, pb: float) -> None:
    dist = match_distribution(pa, pb)
    assert sum(p for p, _ in dist.paths) == pytest.approx(1.0, abs=1e-12)
    mixed = form_mixture(pa, pb)
    assert sum(p for p, _ in mixed.paths) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("a_first", [True, False])
def test_set_distribution_sums_to_one_and_every_score_is_legal(a_first: bool) -> None:
    dist = set_distribution(0.63, 0.57, a_first)
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-12)
    for ga, gb, tb in dist:
        hi, lo = max(ga, gb), min(ga, gb)
        assert (hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))
        assert tb == (hi == 7 and lo == 6)


def test_symmetric_players_are_a_coin() -> None:
    for dist in (match_distribution(0.6, 0.6), form_mixture(0.6, 0.6)):
        assert p_of(dist, Outcome("winner", player=0)) == pytest.approx(0.5, abs=1e-9)
        assert p_of(dist, Outcome("set_winner", player=1, set_no=1)) == pytest.approx(
            0.5, abs=1e-9
        )
    assert tiebreak_win_prob(0.6, 0.4, True) == pytest.approx(0.5, abs=1e-12)
    assert tiebreak_win_prob(0.6, 0.4, False) == pytest.approx(0.5, abs=1e-12)


def test_winning_the_match_implies_winning_a_set() -> None:
    dist = form_mixture(0.66, 0.57)
    for player in (0, 1):
        win = p_of(dist, Outcome("winner", player=player))
        a_set = p_of(dist, Outcome("wins_a_set", player=player, over=True))
        straight = p_of(dist, Outcome("straight_sets", player=player, over=True))
        assert a_set >= win >= straight


def test_winner_probabilities_are_complements() -> None:
    dist = form_mixture(0.64, 0.59)
    total = p_of(dist, Outcome("winner", player=0)) + p_of(
        dist, Outcome("winner", player=1)
    )
    assert total == pytest.approx(1.0, abs=1e-12)


def test_first_set_has_at_least_six_games() -> None:
    dist = match_distribution(0.8, 0.45)
    assert all(path[0][0] + path[0][1] >= 6 for _, path in dist.paths)
    assert p_of(dist, Outcome("set_games", line=5.5, set_no=1, over=True)) == (
        pytest.approx(1.0)
    )


def test_handicap_is_monotone_in_the_line() -> None:
    dist = form_mixture(0.63, 0.58)
    probs = [
        p_of(dist, Outcome("handicap_games", player=0, line=h))
        for h in (-6.5, -4.5, -2.5, -0.5, 0.5, 2.5, 4.5, 6.5)
    ]
    assert probs == sorted(probs)
    # The two selections of one line are complements.
    a = p_of(dist, Outcome("handicap_games", player=0, line=-2.5))
    b = p_of(dist, Outcome("handicap_games", player=1, line=2.5))
    assert a + b == pytest.approx(1.0, abs=1e-12)


def test_totals_are_monotone_and_over_under_complement() -> None:
    dist = form_mixture(0.6, 0.6)
    overs = [p_of(dist, Outcome("games_total", line=x)) for x in (18.5, 20.5, 22.5)]
    assert overs == sorted(overs, reverse=True)
    o = p_of(dist, Outcome("games_total", line=21.5, over=True))
    u = p_of(dist, Outcome("games_total", line=21.5, over=False))
    assert o + u == pytest.approx(1.0, abs=1e-12)


def test_a_whole_line_pushes_instead_of_winning() -> None:
    dist = match_distribution(0.6, 0.6)
    prob = outcome_probability(dist, Outcome("handicap_games", player=0, line=0.0))
    assert prob.p_push > 0
    # EV counts a push as the stake back, not as a win.
    assert model_ev(prob, 2.0) == pytest.approx(prob.p_win * 2.0 + prob.p_push - 1.0)


def test_set_three_markets_void_when_there_is_no_third_set() -> None:
    assert (
        outcome_value(
            ((6, 3, False), (6, 4, False)), Outcome("set_winner", player=0, set_no=3)
        )
        is None
    )
    dist = match_distribution(0.6, 0.6)
    prob = outcome_probability(dist, Outcome("set_winner", player=0, set_no=3))
    assert prob.p_void == pytest.approx(
        p_of(dist, Outcome("sets_total", line=2.5, over=False))
    )


def test_exact_enumeration_agrees_with_point_by_point_monte_carlo() -> None:
    pa, pb = 0.62, 0.57
    exact = match_distribution(pa, pb)
    sims = simulate_match_points(pa, pb, sims=6000, seed=7)
    for o in (
        Outcome("winner", player=0),
        Outcome("games_total", line=21.5),
        Outcome("tiebreaks", line=0.5),
        Outcome("set_player_games", player=1, line=4.5, set_no=2),
    ):
        mc = [v for v in (outcome_value(p, o) for p in sims) if v is not None]
        # 6,000 draws: sd <= 0.0065, so 0.025 is ~4 sd.
        assert sum(mc) / len(mc) == pytest.approx(p_of(exact, o), abs=0.025)


def test_zero_form_noise_is_the_plain_chain() -> None:
    plain = match_distribution(0.61, 0.58)
    mixed = form_mixture(0.61, 0.58, var=0.0, cov=0.0)
    o = Outcome("games_total", line=21.5)
    assert p_of(mixed, o) == pytest.approx(p_of(plain, o), abs=1e-12)


def test_form_noise_makes_matches_less_close() -> None:
    plain = match_distribution(0.6, 0.6)
    mixed = form_mixture(0.6, 0.6, var=0.1, cov=-0.05)
    three = Outcome("sets_total", line=2.5, over=True)
    assert p_of(mixed, three) < p_of(plain, three)


# --------------------------------------------------------------------------
# Rating
# --------------------------------------------------------------------------


def test_rating_ranks_the_stronger_server_and_reports_points() -> None:
    obs = []
    for k in range(6):
        obs.append(Obs(1, 2, "hard", "M", 50, 70, 1.0, k))  # 1 serves well vs 2
        obs.append(Obs(2, 1, "hard", "M", 35, 70, 1.0, k))
        obs.append(Obs(3, 2, "hard", "M", 42, 70, 1.0, k))
        obs.append(Obs(2, 3, "hard", "M", 42, 70, 1.0, k))
    rating = fit_surface_rating(obs)
    assert rating.p_serve(1, 2, "M", "hard") > rating.p_serve(3, 2, "M", "hard")
    assert rating.points(1) == (420, 420)
    assert rating.points(99) == (0, 0)  # never seen: LOW_DATA downstream


def test_surface_families_merge_the_generic_labels() -> None:
    assert surface_family("Hard") == surface_family("Hardcourt outdoor") == "hard"
    assert surface_family("Clay") == surface_family("Red clay") == "clay"
    assert surface_family(None) == "unknown"


# --------------------------------------------------------------------------
# Superbet market-name -> outcome join
# --------------------------------------------------------------------------


def odd(market: str, name: str, price: float = 1.9, **kw: Any) -> dict[str, Any]:
    return {
        "marketName": market,
        "name": name,
        "price": price,
        "status": "active",
        **kw,
    }


@pytest.mark.parametrize(
    "item,expected",
    [
        (odd("Zwycięzca", "1", code="1"), Outcome("winner", player=0)),
        (odd("Zwycięzca", "2", code="2"), Outcome("winner", player=1)),
        (
            odd("X. set - zwycięzca", "2. set - Piotr Nowak"),
            Outcome("set_winner", player=1, set_no=2),
        ),
        (
            odd("Jan Kowalski wygra seta", "Tak"),
            Outcome("wins_a_set", player=0, over=True),
        ),
        (
            odd("Piotr Nowak wygra bez straty seta", "Nie"),
            Outcome("straight_sets", player=1, over=False),
        ),
        (
            odd("Liczba setów", "Powyżej 2.5", specialBetValue="2.5"),
            Outcome("sets_total", line=2.5, over=True),
        ),
        (
            odd("Handicap gemy", "Jan Kowalski (-3.5)", specialBetValue="-3.5"),
            Outcome("handicap_games", player=0, line=-3.5),
        ),
        (
            odd("Handicap gemy", "Piotr Nowak (3.5)", specialBetValue="-3.5"),
            Outcome("handicap_games", player=1, line=3.5),
        ),
        (
            odd(
                "1. set - handicap gemy", "Piotr Nowak (-1.5)", specialBetValue="1.5-1"
            ),
            Outcome("set_handicap_games", player=1, line=-1.5, set_no=1),
        ),
        (
            odd("Liczba gemów", "Poniżej 21.5"),
            Outcome("games_total", line=21.5, over=False),
        ),
        (
            odd("Piotr Nowak liczba gemów", "Powyżej 10.5"),
            Outcome("player_games", player=1, line=10.5, over=True),
        ),
        (
            odd("1. set - liczba gemów", "Poniżej 9.5", specialBetValue="1-9.5"),
            Outcome("set_games", line=9.5, over=False, set_no=1),
        ),
        (
            odd("1. set - Jan Kowalski liczba gemów", "Powyżej 4.5"),
            Outcome("set_player_games", player=0, line=4.5, over=True, set_no=1),
        ),
        (
            odd("Liczba tiebreaków", "powyżej 0.5"),
            Outcome("tiebreaks", line=0.5, over=True),
        ),
    ],
)
def test_every_market_shape_maps_to_its_outcome(
    item: dict[str, Any], expected: Outcome
) -> None:
    assert parse_outcome(item, NAMES) == expected


@pytest.mark.parametrize(
    "item",
    [
        odd("Dokładny wynik", "2:0"),
        odd("Zwycięzca - Jan Kowalski; Piotr Nowak wygra seta", "Tak"),
        odd("1. set - zwycięzca & liczba gemów", "x"),
        odd("Jan Kowalski liczba asów", "Powyżej 3.5"),
        odd("Jan Kowalski 1. gem serwisowy - zwycięzca", "Tak"),
    ],
)
def test_markets_the_model_does_not_price_are_refused(item: dict[str, Any]) -> None:
    assert parse_outcome(item, NAMES) is None


def test_a_longer_name_is_not_shadowed_by_its_prefix() -> None:
    names = ("Anna Lee", "Anna Leeds")
    got = parse_outcome(odd("Anna Leeds liczba gemów", "Powyżej 8.5"), names)
    assert got == Outcome("player_games", player=1, line=8.5, over=True)


def test_player_names_are_reoriented_to_sofascore_sides() -> None:
    payload = {
        "matchName": "Piotr Nowak·Jan Kowalski",  # Superbet lists away first
        "odds": [
            odd("Piotr Nowak liczba gemów", "Powyżej 10.5", 1.8),
            odd("Piotr Nowak liczba gemów", "Poniżej 10.5", 1.95),
        ],
    }
    swap = superbet_swapped(
        ("Piotr Nowak", "Jan Kowalski"), "Jan Kowalski", "Piotr Nowak"
    )
    assert swap is True
    quotes, _ = quotes_from_payload(payload, swap)
    assert {q.outcome.player for q in quotes} == {1}


def test_unmatched_names_are_not_guessed() -> None:
    assert (
        superbet_swapped(("Xavier Q", "Yusuf Z"), "Jan Kowalski", "Piotr Nowak") is None
    )


# --------------------------------------------------------------------------
# Devig join
# --------------------------------------------------------------------------


def q(o: Outcome, odds: float) -> Quote:
    return Quote(o, odds, "", "")


def test_two_way_pair_is_devigged() -> None:
    pairs, refused = pair_two_way(
        [
            q(Outcome("games_total", line=21.5, over=True), 1.80),
            q(Outcome("games_total", line=21.5, over=False), 1.95),
        ]
    )
    assert refused == []
    (pair,) = pairs
    assert pair.p_a + pair.p_b == pytest.approx(1.0)
    assert pair.p_a > pair.p_b
    assert pair.margin == pytest.approx(1 / 1.8 + 1 / 1.95 - 1)


def test_one_sided_quotes_are_refused() -> None:
    pairs, refused = pair_two_way(
        [
            q(Outcome("games_total", line=21.5, over=True), 1.80),
            q(Outcome("player_games", player=0, line=10.5, over=False), 1.9),
            q(Outcome("handicap_games", player=0, line=-2.5), 1.9),
        ]
    )
    assert pairs == []
    assert len(refused) == 3


def test_handicap_pairs_on_opposite_lines() -> None:
    pairs, refused = pair_two_way(
        [
            q(Outcome("handicap_games", player=0, line=-2.5), 1.9),
            q(Outcome("handicap_games", player=1, line=2.5), 1.9),
            q(
                Outcome("handicap_games", player=1, line=3.5), 1.5
            ),  # its pair is missing
        ]
    )
    assert len(pairs) == 1
    assert [r.outcome.line for r in refused] == [3.5]


def test_suspended_and_non_prices_never_enter_the_join() -> None:
    payload = {
        "matchName": "Jan Kowalski·Piotr Nowak",
        "odds": [
            odd("Jan Kowalski wygra seta", "Tak", 1.0, status="block"),
            odd("Jan Kowalski wygra seta", "Nie", 20.0),
        ],
    }
    quotes, _ = quotes_from_payload(payload, False)
    pairs, refused = pair_two_way(quotes)
    assert pairs == [] and len(refused) == 1


# --------------------------------------------------------------------------
# Kickoff gate
# --------------------------------------------------------------------------


def test_kickoff_uses_the_earlier_clock() -> None:
    fx = {
        "kickoff_utc": "2026-09-23T12:00:00Z",
        "superbet_kickoff_utc": "2026-09-23T10:30:00Z",
    }
    assert earliest_kickoff(fx) == datetime(2026, 9, 23, 10, 30, tzinfo=UTC)
    now = datetime(2026, 9, 23, 10, 20, tzinfo=UTC)
    # Sofascore's clock says 1h40 away; Superbet's says 10 minutes - skipped.
    assert not is_pre_match(fx, now)
    assert is_pre_match(fx, now - timedelta(minutes=10))


def test_kickoff_margin_is_fifteen_minutes() -> None:
    fx = {"kickoff_utc": "2026-09-23T10:00:00Z", "superbet_kickoff_utc": None}
    assert not is_pre_match(fx, datetime(2026, 9, 23, 9, 45, tzinfo=UTC))
    assert is_pre_match(fx, datetime(2026, 9, 23, 9, 44, tzinfo=UTC))
    assert not is_pre_match({"kickoff_utc": None}, datetime(2026, 9, 23, tzinfo=UTC))
