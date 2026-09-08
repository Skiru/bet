"""The three defects the operator's 2026-09-07 tennis read left on the table.

One test file rather than three, because the three share a shape: a number the
pipeline had already measured, and a consumer that read something else.

* ``corroborated_matches``/``_cross_provider_agreement`` grouped tennis
  observations by calendar day, while ``_tennis_match_keys`` in the same module
  discards the date as unusable for tennis. Every tennis row on the
  2026-09-07 sheet -- 448 of them -- reported ``SINGLE_SOURCE`` and
  ``corroborated_matches: 0``, including Coco Gauff's sample where 7 of 10
  matches came from both providers and agreed to within a game.
* ``calibration.honest_probability`` announced a correction computed by
  interpolating across two blocks and then quoted a third thing -- the nearer
  block -- with the claim rounded to whole points and the realised rate to
  tenths. Both available inversions shipped in the same file.
* the coupon's bar was computed from ``p_central`` with no reference to
  ``config/market_reliability.json``, which records what rows claiming that
  much on that market have actually done. The forecast had been ranking the
  corrected number since 2026-09-07; the artifact with money on it had not.
"""
from __future__ import annotations

import pytest

from bet.simple_stats.analyze import (
    _cross_provider_agreement,
    corroborated_matches,
)
from bet.simple_stats.bet_builder_draft import (
    bar_components,
    bar_input,
    market_record_correction,
)
from bet.simple_stats.calibration import honest_probability
from bet.simple_stats.contracts import ProviderValue, StatsSheetRow


# --- defect 1: tennis corroboration was keyed on a date it does not have ----


def _tennis_pv(provider: str, value: float, *, opponent: str, day: str) -> ProviderValue:
    return ProviderValue(
        provider=provider,
        match_id=f"{provider}-{opponent}-{day}",
        match_date=day,
        opponent=opponent,
        value=value,
        observed_at="2026-09-07T00:00:00+00:00",
    )


def _gauff_sample() -> list[ProviderValue]:
    """Two providers on the same three matches, dated 10-11 days apart.

    tennis-abstract stamps a match with its tournament's start date, so the two
    feeds never share a calendar day even when they are describing the same
    match. That is the whole mechanism.
    """
    opponents = ("Iva Jovic", "Naomi Osaka", "Elena Rybakina")
    espn = [
        _tennis_pv("espn-tennis", 20.0 + i, opponent=name, day=f"2026-08-2{i}")
        for i, name in enumerate(opponents)
    ]
    abstract = [
        _tennis_pv("tennis-abstract", 20.0 + i, opponent=name, day=f"2026-08-1{i}")
        for i, name in enumerate(opponents)
    ]
    return espn + abstract


def test_tennis_corroboration_is_keyed_on_the_match_and_not_the_day():
    sample = _gauff_sample()
    # The old behaviour, still correct for football and still the default.
    assert corroborated_matches("total_games", sample, "football") == 0
    # Tennis identity: (bucket, opponent, nth meeting) -- the same slots
    # ``_one_per_day`` collapses the priced sample into.
    assert corroborated_matches("total_games", sample, "tennis") == 3


def test_a_tennis_sample_two_providers_agree_on_is_not_single_source():
    sample = _gauff_sample()
    assert _cross_provider_agreement("total_games", sample, 3, "football") == "SINGLE_SOURCE"
    assert _cross_provider_agreement("total_games", sample, 3, "tennis") == "AGREE"


def test_the_tennis_key_lets_a_real_disagreement_through_too():
    """The fix must not be one-way. On the 2026-09-07 slate it turned 18 buckets
    AGREE and **one** DISAGREE -- an Andreeva-Potapova h2h conflict the day key
    had been hiding -- and DISAGREE is a demotion."""
    sample = [
        _tennis_pv("espn-tennis", 16.0, opponent="Anastasia Potapova", day="2026-09-01"),
        _tennis_pv("tennis-abstract", 22.0, opponent="Anastasia Potapova", day="2026-08-21"),
    ]
    assert _cross_provider_agreement("total_games", sample, 1, "football") == "SINGLE_SOURCE"
    assert _cross_provider_agreement("total_games", sample, 1, "tennis") == "DISAGREE"


def _football_pv(provider: str, opponent: str, day: str, value: float) -> ProviderValue:
    return ProviderValue(
        provider=provider,
        match_id=f"{provider}-{day}",
        match_date=day,
        opponent=opponent,
        value=value,
        observed_at="2026-09-02T00:00:00+00:00",
    )


def test_football_corroboration_is_untouched_by_the_tennis_key():
    """Football still keys on the calendar day and clusters opponent names
    inside it. The default must stay the default: a club plays at most one match
    on a date, and that is a stronger identity than any name match."""
    same_match = [
        _football_pv("bzzoiro", "Real Betis", "2026-09-01", 9.0),
        _football_pv("espn-football", "Betis", "2026-09-01", 9.0),
    ]
    assert corroborated_matches("corners_total", same_match) == 1
    assert corroborated_matches("corners_total", same_match, "football") == 1


def test_corroboration_is_clustered_inside_a_bucket_and_never_across_them():
    """The bug the frozen 2026-08-31 fixture caught in the first version of this
    fix. Tsitsipas played Alex de Minaur (28 games) and Fils played Alex de
    Minaur (19); pooled, one opponent name held both, and the two feeds were
    reported as contradicting each other by nine games while agreeing about
    both matches."""
    a_side = [_tennis_pv("espn-tennis", 28.0, opponent="Alex de Minaur", day="2026-07-29")]
    b_side = [
        _tennis_pv("espn-tennis", 19.0, opponent="Alex de Minaur", day="2026-08-19"),
        _tennis_pv("tennis-abstract", 19.0, opponent="Alex De Minaur", day="2026-08-13"),
    ]
    pooled = a_side + b_side
    # Pooled into one keyspace the two feeds look like two meetings against one,
    # so the slot is refused and the real corroboration is lost with it. That is
    # the safe half of the failure and it is still a wrong answer.
    assert corroborated_matches("total_games", pooled, "tennis") == 0
    # Given the partition it is what it is: one corroborated match, agreeing,
    # and Tsitsipas' own de Minaur match uncorroborated on its own side.
    partition = [a_side, b_side, []]
    assert corroborated_matches("total_games", pooled, "tennis", partition) == 1
    assert (
        _cross_provider_agreement("total_games", pooled, 2, "tennis", partition)
        == "SINGLE_SOURCE"
    )


def test_a_repeat_meeting_the_two_feeds_truncate_differently_is_not_judged():
    """Andreeva - Potapova, 2026-09-07. tennis-abstract carries two meetings
    (2025-08-25, 16 games; 2026-04-06, 26) and espn-tennis one (2026-04-12, 26
    -- abstract's 2026-04-06 match, tournament-start-dated). Rank-0-to-rank-0
    pairs the 16 with the 26 and calls it a ten-game provider conflict.

    Neither end of the rank is safe -- Andreeva - Tjen the same day fails the
    other way -- so the slot is refused instead of guessed at. It must not
    corroborate and it must not DISAGREE."""
    sample = [
        _tennis_pv("tennis-abstract", 16.0, opponent="Anastasia Potapova", day="2025-08-25"),
        _tennis_pv("tennis-abstract", 26.0, opponent="Anastasia Potapova", day="2026-04-06"),
        _tennis_pv("espn-tennis", 26.0, opponent="Anastasia Potapova", day="2026-04-12"),
    ]
    assert corroborated_matches("total_games", sample, "tennis") == 0
    assert _cross_provider_agreement("total_games", sample, 2, "tennis") == "SINGLE_SOURCE"


def test_equal_meeting_counts_are_still_judged_in_both_directions():
    """The refusal above is about *unequal* windows only. Two feeds that both
    report two meetings with one opponent still pair, still corroborate, and
    still disagree when they disagree."""
    agreeing = [
        _tennis_pv("tennis-abstract", 20.0, opponent="Jiri Lehecka", day="2026-08-02"),
        _tennis_pv("tennis-abstract", 26.0, opponent="Jiri Lehecka", day="2026-08-13"),
        _tennis_pv("espn-tennis", 20.0, opponent="Jiri Lehecka", day="2026-08-06"),
        _tennis_pv("espn-tennis", 26.0, opponent="Jiri Lehecka", day="2026-08-18"),
    ]
    assert corroborated_matches("total_games", agreeing, "tennis") == 2
    assert _cross_provider_agreement("total_games", agreeing, 2, "tennis") == "AGREE"

    conflicting = list(agreeing)
    conflicting[2] = _tennis_pv(
        "espn-tennis", 29.0, opponent="Jiri Lehecka", day="2026-08-06"
    )
    assert _cross_provider_agreement("total_games", conflicting, 2, "tennis") == "DISAGREE"


# --- defect 2: a calibration note that contradicted its own arithmetic ------


def _curve(*buckets: tuple[str, float, float, int, float]) -> dict:
    return {
        "fixtures": 400,
        "rungs": 4000,
        "calibration_curve": {
            label: {
                "claimed": claimed,
                "realised": realised,
                "fixtures": fixtures,
                "rungs": 1500,
                "gap_ci": [
                    (claimed - realised) - half,
                    (claimed - realised) + half,
                ],
            }
            for label, claimed, realised, fixtures, half in buckets
        },
    }


def test_a_note_that_says_the_market_understates_shows_realised_above_claimed():
    """``player_was_fouled`` printed "realizował 92,8% przy deklaracji 93%" to
    introduce a sentence saying the market *under*-states. Both numbers are
    right (0.9267 against 0.9284); the claim was rounded to whole points and
    the realised rate to tenths, so the pair read as its own contradiction."""
    entry = _curve(("0.90", 0.9267, 0.9284, 325, 0.013))
    honest, note = honest_probability(0.944, entry)
    assert honest == pytest.approx(0.944)
    assert note is not None and "zaniża" in note
    # Both numbers at one precision, so rounding cannot invert the sentence.
    assert "92,7%" in note and "92,8%" in note


def test_a_downward_correction_never_quotes_only_a_block_that_over_delivered():
    """The other inversion, same day, same market: a row claiming 0.672 was told
    "skorygowane -0,4%: wiersze ... deklarujące ~77% realizowały 77,6%" -- a
    correction carried from the hot 0.515 block, footnoted with the one block
    that beat its claim. The note has to name what actually produced it."""
    entry = _curve(
        ("0.50", 0.5150, 0.5045, 343, 0.003),
        ("0.75", 0.7721, 0.7765, 323, 0.003),
    )
    honest, note = honest_probability(0.672, entry)
    assert honest < 0.672
    assert note is not None and note.startswith("skorygowane")
    # Interpolated between two blocks, so both are named.
    assert "51,5%" in note and "77,2%" in note
    assert "interpolacja" in note


def test_a_note_on_a_single_block_still_reads_as_one_measurement():
    entry = _curve(("0.90", 0.9266, 0.9157, 323, 0.008))
    honest, note = honest_probability(0.95, entry)
    assert honest < 0.95
    assert note is not None and "interpolacja" not in note
    assert "92,7%" in note and "91,6%" in note


# --- defect 3: the bar never read the market's own settled record -----------


def _row(**over) -> StatsSheetRow:
    base = dict(
        event_id="e" * 64,
        sport="football",
        market="cards_points_for",
        line=4.5,
        direction="UNDER",
        team_name="Pogon Szczecin",
        hits=10,
        sample_size=10,
        hit_rate=1.0,
        p_low=0.7226,
        p_central=0.95,
        mean=2.4,
        median=2.0,
        data_quality="READY",
        cross_provider_agreement="SINGLE_SOURCE",
        confidence="HIGH",
    )
    base.update(over)
    return StatsSheetRow(**base)


def test_the_bar_now_reads_what_this_market_actually_delivered():
    """``cards_points_for`` UNDER rows above the single floor realised 87.0%
    against a claimed 91.9% over 142 settled fixtures. The correction is the
    difference, and it reaches the price."""
    row = _row()
    correction, note = market_record_correction(row, "p_central")
    assert correction > 0.0
    assert note is not None
    uncorrected, _reason = bar_input(row, "p_central")
    components = bar_components(row, "p_central")
    assert components.p_bar == pytest.approx(uncorrected - correction)
    assert components.calibration == pytest.approx(correction)
    assert components.calibration_note == note


def test_the_correction_can_only_raise_a_bar_never_lower_one():
    """One-sided by construction (``honest_probability`` reports a negative gap
    and applies zero), so there is no fixture on any board for which this makes
    a row easier to clear."""
    for market in ("cards_points_for", "cards_points_total", "corners_for", "goals_total"):
        for claim in (0.55, 0.72, 0.86, 0.95):
            row = _row(market=market, p_central=claim, p_low=min(claim, 0.72))
            correction, _note = market_record_correction(row, "p_central")
            assert correction >= 0.0
            # The sample side of the bar never rises, so the required price
            # never falls. Compared against ``bar_input``, which is the same
            # claim before the market record is consulted.
            assert bar_input(row, "p_central")[0] >= bar_components(row, "p_central").p_bar


def test_a_p_low_run_is_not_corrected_at_all():
    """``p_low`` is the tighter bar already and is not the axis the curve was
    measured on -- reading it there would consult a bucket the row is not in."""
    row = _row()
    assert market_record_correction(row, "p_low") == (0.0, None)
    assert bar_components(row, "p_low").calibration == 0.0


def test_a_sheet_without_p_central_is_not_corrected():
    """Every sheet recorded before 2026-09-02. Unmeasured is not measured-bad."""
    row = _row(p_central=None)
    assert market_record_correction(row, "p_central") == (0.0, None)


def test_an_unmeasured_market_is_left_alone():
    row = _row(market="aces_for", sport="tennis", team_name=None)
    assert market_record_correction(row, "p_central") == (0.0, None)
