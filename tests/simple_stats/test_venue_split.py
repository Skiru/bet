"""Home and away: the field, the prior it feeds, and the two rules it did not.

Why this exists at all. All three per-team losses of 2026-09-01 were bets on
the home side of that night's fixture -- Sheffield United corners UNDER 4.5,
Preston shots on target UNDER 3.5, Birmingham shots UNDER 12.5 -- and every one
was priced off a sample that counted that team's home and away matches as equal
trials. Home/away sat on every provider's fixture row all along: it is what
splits each historical match's stats between the two sides
(``providers._side_of``, highlightly's ``home_away``, bzzoiro's
``home_team.provider_team_id``). It was used for the split and then dropped
rather than recorded, so the question could not even be asked.

**What shipped.** ``ProviderValue.venue``, filled by every football provider
that knows it, plus a per-venue shrinkage target in
``config/market_priors.json`` read by ``analyze.shrunk_centre``. A home
``corners_for`` row is now pulled toward 5.25 rather than toward the pooled
4.74; an away one toward 4.20.

**The measurement.** Real home/away resolved for 191 teams across the
2026-08-31 and 2026-09-01 slates -- 1,852 match-venue pairs read from
bzzoiro's own fixture listings -- and joined back onto the frozen dossiers so
every historical observation could be labelled. Pooled over all teams:

    shots_for              +2.59 a game at home   z = +8.15
    shots_on_target_for    +1.12                  z = +7.63
    shots_1h_for           +1.50                  z = +6.97
    corners_for            +1.05                  z = +6.76
    cards_for              -0.52                  z = -6.73
    goals_for              +0.31                  z = +4.49
    fouls_for              -0.14                  z = -0.56
    offsides_for           +0.11                  z = +1.25

``cards_for`` is the important row: it is the *opposite* sign, which is the
referee home bias, and an artifact of fitting would not have produced it.
``fouls_for`` and ``offsides_for`` show nothing and correctly get no venue
prior. Every market kept has |z| >= 3, at least 120 observations a side, and
the same sign measured on each slate separately.

**What did not ship, and why it is worth writing down.** The obvious use of
this field is a per-team split -- price a home row off that team's own home
matches. Over 358 per-team samples with at least three matches at each venue,
the gap between a team's home mean and its away mean was a median of 0.52 of
the sample's own standard deviation and above one sigma on 20.9% of them.
Assigning the *same observations* a venue by coin flip produced a median of
0.40-0.53 and 10.6-18.9% above one sigma. A single team's split is
indistinguishable from noise at these depths: three to five matches a venue
cannot measure an effect of a third of a goal. Two context-flag shapes built on
it were measured and deleted; ``context_flags.py``'s own comment block records
both, and ``test_a_per_team_split_is_not_a_tier_lever`` holds the conclusion.
"""
from __future__ import annotations

import math
import statistics

import pytest

from bet.simple_stats import context_flags as context_flags_module
from bet.simple_stats.analyze import (
    SHRINKAGE_K,
    market_priors,
    shrunk_centre,
    venue_market_priors,
)
from bet.simple_stats.providers import (
    NATIVE_ID_PROVIDERS_BY_SPORT,
    PROVIDERS_BY_SPORT,
    _make_values,
    _venue_or_none,
)


# --- 1. the field: recorded where it is known, refused where it is not ------


def test_a_football_provider_records_the_venue_it_already_knew():
    values = _make_values(
        "bzzoiro", "214005", "2026-08-29", "Bolton Wanderers",
        {"corners_for": 3.0}, side="home",
    )
    assert values["corners_for"].venue == "home"


def test_a_tennis_provider_records_no_venue_because_a_draw_slot_is_not_one():
    """``_side_of`` answers which participant slot a player occupied, which is
    not a venue -- neither player is at home at a neutral tournament. Recording
    slot one as "home" would be the same class of invented fact as the
    impossible orderings ``_is_absent_not_zero`` refuses."""
    values = _make_values(
        "espn-tennis", "9001", "2026-08-29", "Iga Świątek",
        {"double_faults_total": 4.0}, side="home",
    )
    assert values["double_faults_total"].venue is None


def test_the_gate_is_one_function_and_not_a_check_at_each_call_site():
    """Six call sites have a side to hand. A provider added to the tennis list
    later must not start emitting venues because one of them forgot the
    distinction.

    Read off the rosters rather than spelled out, so that a provider joining or
    leaving one cannot leave this test asserting something about a name nobody
    fetches any more -- which is what happened when ``understat`` and
    ``api-football`` left the football roster on 2026-09-02 and this test went
    on demanding a venue from one of them.
    """
    football = (
        *PROVIDERS_BY_SPORT["football"],
        *NATIVE_ID_PROVIDERS_BY_SPORT["football"],
    )
    tennis = (
        *PROVIDERS_BY_SPORT["tennis"],
        *NATIVE_ID_PROVIDERS_BY_SPORT.get("tennis", ()),
    )
    assert football and tennis, "a roster emptied would make this vacuous"
    for provider in football:
        assert _venue_or_none(provider, "home") == "home", provider
        assert _venue_or_none(provider, "away") == "away", provider
    for provider in tennis:
        assert _venue_or_none(provider, "home") is None, provider
        assert _venue_or_none(provider, "away") is None, provider
    # Not a side at all: None, never coerced.
    assert _venue_or_none("bzzoiro", None) is None
    assert _venue_or_none("bzzoiro", "neutral") is None


def test_an_unstated_venue_is_none_and_never_defaults_to_away():
    """The "unknown is not degraded" rule, on this field. A provider that did
    not say which side the team was must leave it unstated rather than have
    its observations counted as away matches."""
    values = _make_values(
        "bzzoiro", "214006", "2026-08-29", "Someone FC", {"corners_for": 3.0}
    )
    assert values["corners_for"].venue is None


def test_the_h2h_path_records_no_venue():
    """``_team_total_rows`` refuses to read the H2H bucket for a per-team row
    because an H2H value carries no marker for which of the two teams it
    belongs to. For the same reason it carries no venue, and
    ``_fetch_h2h_generic`` passes no side."""
    import inspect

    from bet.simple_stats.providers import _fetch_h2h_generic

    source = inspect.getsource(_fetch_h2h_generic)
    assert "side=" not in source


# --- 2. the prior it feeds --------------------------------------------------


def test_a_home_row_is_pulled_toward_the_home_prior():
    pooled = market_priors()["corners_for"]
    home = venue_market_priors()[("corners_for", "home")]
    away = venue_market_priors()[("corners_for", "away")]
    assert away < pooled < home

    values = [2.0, 4.0, 3.0, 2.0, 3.0]          # Sheffield United, that night
    n = float(len(values))
    weight = n / (n + SHRINKAGE_K)
    expected = weight * statistics.fmean(values) + (1.0 - weight) * home
    assert shrunk_centre(values, "corners_for", "home") == pytest.approx(expected)
    # And it is strictly further from the sample than the pooled target, which
    # is the whole point for a home UNDER: 2.80 observed, 5.25 expected of a
    # home side, and the match returned 5.
    assert shrunk_centre(values, "corners_for", "home") > shrunk_centre(
        values, "corners_for"
    )


def test_an_away_row_is_pulled_the_other_way():
    values = [2.0, 4.0, 3.0, 2.0, 3.0]
    assert shrunk_centre(values, "corners_for", "away") < shrunk_centre(
        values, "corners_for"
    )


def test_cards_go_the_other_way_and_that_is_the_evidence_it_is_real():
    """Away sides are carded more, not less. Every other market's home offset
    is positive, so a fitting artifact would have made this one positive too;
    it is -0.52 at z=-6.73 and negative on both slates measured separately."""
    home = venue_market_priors()[("cards_for", "home")]
    away = venue_market_priors()[("cards_for", "away")]
    assert home < away


def test_the_markets_with_no_measured_effect_have_no_venue_prior():
    """``fouls_for`` (z=-0.56) and ``offsides_for`` (z=+1.25) show no home
    effect over 1,000-odd observations a side. They keep the pooled prior, and
    a home fouls row must price identically to an away one."""
    for market in ("fouls_for", "offsides_for"):
        assert ("home", market) not in venue_market_priors()
        assert (market, "home") not in venue_market_priors()
        values = [11.0, 13.0, 12.0, 14.0, 10.0]
        assert shrunk_centre(values, market, "home") == shrunk_centre(
            values, market, "away"
        ) == shrunk_centre(values, market)


def test_a_match_total_has_no_venue_of_its_own():
    """Every match has one home side and one away side, so the total is not a
    home or an away quantity. No ``*_total`` market carries a venue prior, and
    ``_rows_for_sample`` passes none for one."""
    venue_markets = {market for market, _ in venue_market_priors()}
    assert not any(market.endswith("_total") for market in venue_markets)
    values = [9.0, 11.0, 10.0]
    assert shrunk_centre(values, "corners_total", "home") == shrunk_centre(
        values, "corners_total"
    )


def test_every_venue_prior_has_a_pooled_one_between_its_two_sides():
    """A sanity invariant over the whole config rather than a spot check: the
    pooled mean is a weighted average of the two venue means, so it must lie
    between them. A transcription slip that swapped one pair would break it."""
    priors = market_priors()
    by_venue = venue_market_priors()
    markets = {market for market, _ in by_venue}
    assert markets, "no venue priors are configured at all"
    for market in markets:
        home, away = by_venue[(market, "home")], by_venue[(market, "away")]
        assert market in priors, f"{market} has venue priors and no pooled one"
        assert min(home, away) <= priors[market] <= max(home, away), market


def test_an_unknown_market_is_still_left_alone_at_either_venue():
    """The pre-2026-09-02 fallback, unchanged: no prior means no shrinkage,
    not an error."""
    for venue in (None, "home", "away"):
        assert shrunk_centre([1.0, 2.0, 3.0], "nobody_measured_this", venue) == 2.0


def test_tennis_is_excluded_by_the_data_and_by_the_caller():
    """Two independent refusals, because either alone would be a single point
    of failure: ``providers._venue_or_none`` records no venue for a draw slot,
    and ``_team_total_rows`` passes ``venue=None`` for a non-football
    dossier."""
    import inspect

    from bet.simple_stats.analyze import _team_total_rows

    source = inspect.getsource(_team_total_rows)
    assert 'venue=venue if dossier.sport == "football" else None' in source
    tennis_markets = {
        market for market, _ in venue_market_priors()
        if market in ("aces_total", "double_faults_total", "total_games")
    }
    assert not tennis_markets


# --- 3. the rules that were measured and rejected ---------------------------


def test_a_per_team_split_is_not_a_tier_lever():
    """The conclusion of the measurement, pinned so the rule is not re-added.

    A single team's home/away gap is indistinguishable from a coin-flip split
    of the same observations (real: median 0.52 sigma, 20.9% above one sigma;
    null: 0.40-0.53 and 10.6-18.9%), so any threshold on it fires on noise.
    Two flag shapes built on it were written, measured and deleted --
    ``context_flags.py``'s comment block records both and why.

    Asserted as the absence of the rule rather than as prose, because the
    tempting thing for the next reader holding a populated ``venue`` field is
    exactly to add it back.
    """
    sources = {rule.__name__ for rule in context_flags_module._FLAG_RULES}
    assert "_venue_flag" not in sources
    assert not hasattr(context_flags_module, "_venue_flag")
    # The reasoning has to survive too, or the next reader repeats the work.
    module_source = context_flags_module.__doc__ or ""
    import inspect

    module_source += inspect.getsource(context_flags_module)
    assert "indistinguishable from" in module_source
    assert "coin flip" in module_source


def test_the_venue_effect_is_large_relative_to_the_noise_it_replaces():
    """Why the pooled form works where the per-team one does not: it is the
    same effect measured with two orders of magnitude more observations.

    A per-team split has 3-5 matches a venue, so the standard error on its
    difference of means is around the sample's own standard deviation -- the
    effect is buried. Pooled over 191 teams there are 500-650 a side and the
    same effect stands at z of 6 to 8. This test asserts the arithmetic of
    that claim from the recorded observation counts, so a future re-measurement
    that thins the sample cannot quietly keep the priors.
    """
    import json
    import pathlib

    from bet.simple_stats.analyze import _MARKET_PRIORS_PATH

    doc = json.loads(pathlib.Path(_MARKET_PRIORS_PATH).read_text())
    for market, block in doc["priors"].items():
        if "home" not in block:
            continue
        assert block["observations_home"] >= 120, market
        assert block["observations_away"] >= 120, market
        assert abs(block["venue_z"]) >= 3.0, market
        # The offset and the z agree in sign -- a transcription slip would
        # break this even if both numbers looked plausible alone.
        assert math.copysign(1.0, block["home"] - block["away"]) == math.copysign(
            1.0, block["venue_z"]
        ), market
