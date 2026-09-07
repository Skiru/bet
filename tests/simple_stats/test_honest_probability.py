"""The correction that lets the day be ranked by probability without a price gate.

The operator's instruction, 2026-09-07: stop deciding anything about Superbet,
say which statistic in which direction at which value is most likely, and let
him price it live. The obstacle was never the price filter itself -- it was that
ranking by ``p_central`` put saturated arithmetic on top, which is what made a
filter feel necessary. So the claim is corrected against its own market's
settled record and the ranking runs off the corrected number.

Every threshold asserted here is a design decision that can be argued with, and
each test names the reason rather than the value.
"""
from __future__ import annotations

import pytest

from bet.simple_stats.calibration import (
    CALIBRATION_SHRINKAGE_K,
    MIN_BUCKET_FIXTURES,
    corrected_points,
    curve_points,
    honest_probability,
    measured_gap,
)


def _entry(curve: dict, *, fixtures: int = 400, rungs: int = 2000) -> dict:
    return {"fixtures": fixtures, "rungs": rungs, "calibration_curve": curve}


def _bucket(
    claimed: float,
    realised: float,
    *,
    fixtures: int,
    rungs: int = 200,
    half: float | None = None,
) -> dict:
    """One config bucket. ``half`` gives it a clustered interval of that width.

    Left out by default so the shrinkage mode is what these fixtures exercise
    unless a test asks for the interval; a bucket without ``gap_ci`` is exactly
    the legacy config shape and falls back to shrinkage by construction.
    """
    gap = round(claimed - realised, 4)
    out = {
        "rungs": rungs,
        "fixtures": fixtures,
        "claimed": claimed,
        "realised": realised,
        "gap": gap,
    }
    if half is not None:
        out["gap_ci"] = [round(gap - half, 4), round(gap + half, 4)]
    return out


# --- one-sided: the correction may only ever lower a probability ------------

def test_an_overconfident_bucket_lowers_the_claim():
    """shots_for's real shape: claims 0.868 around there and realises 0.758."""
    entry = _entry({"0.85": _bucket(0.868, 0.758, fixtures=19)})
    honest, note = honest_probability(0.868, entry, mode="shrink")
    assert honest < 0.868
    assert "skorygowane" in note


def test_an_underconfident_bucket_is_left_exactly_alone():
    """The asymmetry is the point, not an oversight.

    Roughly half the buckets on the board under-claim -- player_shots_on_target
    claims 0.772 at the 0.75 bucket and realises 0.810 -- and a symmetric
    correction would raise those rows. Raising a probability off a bucket-level
    wobble manufactures confidence nobody measured, and the two errors do not
    cost the same: a probability that is too high becomes a bet, one that is too
    low becomes a pass.
    """
    entry = _entry({"0.75": _bucket(0.772, 0.810, fixtures=60)})
    honest, note = honest_probability(0.772, entry)
    assert honest == 0.772
    assert "nie podnoszę" in note
    assert "tylko w dół" in note


def test_no_correction_can_ever_exceed_the_claim_on_the_shipped_config():
    """Read the real config and assert the invariant across every scope.

    The one property the rest of the pipeline is allowed to rely on: p_honest
    is never above p_central, so a corrected ranking cannot invent a read that
    the estimator did not already make.
    """
    from bet.simple_stats.analyze import market_reliability

    checked = 0
    for entry in market_reliability().values():
        for claim in (0.50, 0.55, 0.62, 0.70, 0.75, 0.81, 0.88, 0.93, 0.95, 0.99):
            honest, _ = honest_probability(claim, entry)
            assert honest <= claim + 1e-12, (entry.get("rungs"), claim, honest)
            assert honest >= 0.01
            checked += 1
    assert checked > 200


# --- shrinkage is by fixtures, and it bites ---------------------------------

def test_a_thin_bucket_gets_less_of_its_gap_than_a_thick_one():
    """Same measured gap, different evidence behind it, different correction."""
    thin = _entry({"0.85": _bucket(0.85, 0.70, fixtures=6)})
    thick = _entry({"0.85": _bucket(0.85, 0.70, fixtures=200)})
    thin_p, _ = honest_probability(0.85, thin, mode="shrink")
    thick_p, _ = honest_probability(0.85, thick, mode="shrink")
    assert thick_p < thin_p < 0.85
    # 6/(6+12) = one third of a 0.15 gap; 200/212 = almost all of it.
    assert thin_p == pytest.approx(0.85 - 0.15 / 3, abs=1e-3)
    assert thick_p == pytest.approx(0.85 - 0.15 * 200 / 212, abs=1e-3)


def test_the_shrinkage_constant_is_in_fixtures_not_rungs():
    """A bucket standing on K fixtures gets exactly half its gap applied.

    Stated as a test because the constant's units are the whole difficulty: one
    match contributes up to forty rungs off one sample, so a bucket of 1,559
    rungs can be 24 matches. Weighting rungs would trust every bucket almost
    completely and let one unusual afternoon set a market's correction.
    """
    entry = _entry({"0.80": _bucket(0.80, 0.70, fixtures=int(CALIBRATION_SHRINKAGE_K))})
    honest, _ = honest_probability(0.80, entry, mode="shrink")
    assert honest == pytest.approx(0.80 - 0.10 * 0.5, abs=1e-6)


def test_a_bucket_thinner_than_the_floor_is_discarded_not_shrunk():
    """Under the floor a bucket is one weekend, so the curve reaches past it."""
    entry = _entry(
        {
            "0.70": _bucket(0.70, 0.60, fixtures=80),
            "0.90": _bucket(0.90, 0.10, fixtures=int(MIN_BUCKET_FIXTURES) - 1),
        }
    )
    assert [round(b.claimed, 3) for b in curve_points(entry)] == [0.70]
    # The absurd 0.90 bucket is gone, so a claim of 0.90 is corrected by the
    # 0.70 bucket's gap held flat rather than by an 80-point cliff.
    honest, _ = honest_probability(0.90, entry, mode="shrink")
    assert honest > 0.80


# --- interpolation ----------------------------------------------------------

def test_a_claim_between_two_buckets_gets_a_blend_of_both_gaps():
    """Snapping to a bucket would move the correction by whole points as a
    claim crossed 0.875, and correct two rungs one line apart differently for
    no reason present in the evidence."""
    entry = _entry(
        {
            "0.80": _bucket(0.80, 0.75, fixtures=100),   # gap +0.05
            "0.90": _bucket(0.90, 0.75, fixtures=100),   # gap +0.15
        }
    )
    gap, fixtures = measured_gap(0.85, entry)
    assert gap == pytest.approx(0.10, abs=1e-9)
    assert fixtures == pytest.approx(100.0)


def test_outside_the_curve_the_nearest_bucket_is_held_flat_not_extrapolated():
    """A market measured to 0.90 says nothing about 0.99 beyond the last thing
    seen, and a trend fitted there would put the biggest corrections exactly
    where there is no data."""
    entry = _entry(
        {
            "0.70": _bucket(0.70, 0.66, fixtures=100),
            "0.90": _bucket(0.90, 0.80, fixtures=100),
        }
    )
    assert measured_gap(0.99, entry)[0] == pytest.approx(0.10)
    assert measured_gap(0.55, entry)[0] == pytest.approx(0.04)


# --- monotone fit -----------------------------------------------------------

def test_two_buckets_in_the_wrong_order_are_pooled_rather_than_believed():
    """total_games@BO3's real shape: rows claiming 0.573 realised 0.610 and
    rows claiming 0.621 realised 0.568.

    Read literally that says claiming *more* on this market makes a row less
    likely, which is not a fact about tennis -- it is two thin buckets in the
    wrong order. It matters because a bucket's corrected probability is exactly
    its realised rate (``claim - (claim - realised)``), so an inversion in
    ``realised`` is an inversion in the number the whole day is ranked by, and
    a row would be punished for claiming slightly less than the row beside it.
    Pooling adjacent violators is the standard answer and adds no parameter.
    """
    entry = _entry(
        {
            "0.55": _bucket(0.5733, 0.6102, fixtures=12),
            "0.60": _bucket(0.6207, 0.5676, fixtures=15),
        }
    )
    raw = curve_points(entry, isotonic=False)
    # Uncorrected: 0.610 then 0.568 -- the inversion, in the shipped units.
    assert [round(b.realised, 3) for b in raw] == [0.610, 0.568]
    smoothed = curve_points(entry)
    assert len(smoothed) == 1
    # The pooled block keeps the higher claim, so a row is still corrected
    # against the record of rows claiming at least as much as it does, and the
    # fixture counts add up because the two blocks are disjoint sets of matches.
    assert smoothed[0].claimed == pytest.approx(0.6207)
    assert smoothed[0].fixtures == pytest.approx(27.0)
    # The pooled realised rate is the rung-weighted mean of the two.
    pooled_realised = (0.6102 + 0.5676) / 2      # equal rung counts in the fixture
    assert smoothed[0].realised == pytest.approx(pooled_realised, abs=1e-9)


def test_the_shipped_tennis_length_market_actually_needed_the_fit():
    """Not a hypothetical. Assert the inversion exists in the real config, so
    that if a future re-measurement removes it this test says so rather than
    leaving a smoother nobody can justify."""
    from bet.simple_stats.analyze import market_reliability

    curve = market_reliability()["total_games@BO3"]["calibration_curve"]
    realised = [curve[k]["realised"] for k in sorted(curve)]
    assert any(
        later < earlier
        for earlier, later in zip(realised, realised[1:], strict=False)
    ), realised


def test_the_corrected_probability_rises_with_the_claim_on_every_shipped_scope():
    """The property the monotone fit exists to guarantee.

    Without it a row is punished for claiming slightly less than the row beside
    it, purely because two buckets landed out of order.
    """
    from bet.simple_stats.analyze import market_reliability

    claims = [0.50 + 0.01 * i for i in range(50)]
    for scope, entry in market_reliability().items():
        values = [honest_probability(c, entry)[0] for c in claims]
        for earlier, later in zip(values, values[1:], strict=False):
            assert later >= earlier - 1e-9, scope


def test_an_already_monotone_curve_is_not_touched_by_the_fit():
    entry = _entry(
        {
            "0.70": _bucket(0.70, 0.66, fixtures=70),
            "0.80": _bucket(0.80, 0.74, fixtures=50),
            "0.90": _bucket(0.90, 0.80, fixtures=30),
        }
    )
    assert curve_points(entry) == curve_points(entry, isotonic=False)


# --- the silent cases -------------------------------------------------------

def test_a_claim_below_a_half_is_returned_untouched_and_unremarked():
    """The curve is built from the favoured side of each rung only -- reading
    both makes every market claim 0.500 and realise 0.500 by construction -- so
    it says nothing down here, and nothing ranks off it either."""
    entry = _entry({"0.85": _bucket(0.85, 0.70, fixtures=100)})
    assert honest_probability(0.30, entry) == (0.30, None)


def test_an_unmeasured_market_keeps_its_number_and_says_so():
    honest, note = honest_probability(0.91, None)
    assert honest == 0.91
    assert "brak zmierzonej kalibracji" in note
    honest, note = honest_probability(0.91, {"rungs": 12})
    assert honest == 0.91
    assert "brak zmierzonej kalibracji" in note


def test_a_none_claim_stays_none():
    assert honest_probability(None, None) == (None, None)


def test_a_config_without_per_bucket_fixtures_is_deflated_not_trusted():
    """Backwards compatibility that must not become over-confidence.

    market_reliability.json gained per-bucket ``fixtures`` on 2026-09-07. An
    older copy has only ``rungs``, and treating 200 rungs as 200 independent
    matches would apply essentially the whole gap. The scope's own
    rungs-per-fixture ratio deflates it instead.
    """
    legacy = {
        "fixtures": 100,
        "rungs": 2000,          # 20 rungs a fixture
        "calibration_curve": {
            "0.85": {"rungs": 200, "claimed": 0.85, "realised": 0.75}
        },
    }
    gap, fixtures = measured_gap(0.85, legacy)
    assert gap == pytest.approx(0.10)
    assert fixtures == pytest.approx(10.0)     # 200 * 100 / 2000
    # No gap_ci, so the interval mode is unavailable and the default falls
    # back to shrinkage rather than silently applying nothing.
    honest, _ = honest_probability(0.85, legacy)
    assert honest == pytest.approx(0.85 - 0.10 * 10 / 22, abs=1e-6)


# --- the interval mode, which is what ships ---------------------------------

def test_a_well_calibrated_bucket_is_left_completely_alone():
    """The property the first version lacked, and why it did not ship.

    Measured on held-out dates, correcting by the point estimate everywhere
    moved nineteen scopes that had nothing wrong with them -- it pushed markets
    that already under-claimed further under. Requiring the interval to clear
    zero first leaves those untouched: a bucket claiming 0.80 and
    realising 0.79 on a wide interval has not measured anything to subtract.
    """
    entry = _entry({"0.80": _bucket(0.80, 0.79, fixtures=40, half=0.05)})
    honest, note = honest_probability(0.80, entry)
    assert honest == 0.80
    assert "nie wychodzi poza szum" in note


def test_the_interval_mode_subtracts_only_the_part_beyond_zero():
    """gap +0.15 on an interval of +/-0.04 means at least 0.11 is real."""
    entry = _entry({"0.85": _bucket(0.85, 0.70, fixtures=60, half=0.04)})
    honest, note = honest_probability(0.85, entry, mode="ci")
    assert honest == pytest.approx(0.85 - 0.11, abs=1e-6)
    assert "skorygowane" in note
    assert "realizowały 70,0%" in note


def test_the_interval_mode_shrinks_itself_on_thin_evidence():
    """No constant needed: the same gap on a wider interval corrects less.

    This is why the interval mode has no K. A thin bucket is not damped by a
    number somebody chose, it is damped by how little it knows.
    """
    tight = _entry({"0.85": _bucket(0.85, 0.70, fixtures=200, half=0.02)})
    wide = _entry({"0.85": _bucket(0.85, 0.70, fixtures=8, half=0.12)})
    tight_p, _ = honest_probability(0.85, tight, mode="ci")
    wide_p, _ = honest_probability(0.85, wide, mode="ci")
    assert tight_p == pytest.approx(0.85 - 0.13, abs=1e-6)
    assert wide_p == pytest.approx(0.85 - 0.03, abs=1e-6)
    assert tight_p < wide_p


def test_the_interval_mode_never_corrects_more_than_the_shrinkage_mode_here():
    """Sanity on the direction of the choice: the shipped mode is the more
    conservative of the two on a bucket with real overconfidence."""
    entry = _entry({"0.85": _bucket(0.85, 0.70, fixtures=60, half=0.04)})
    ci, _ = honest_probability(0.85, entry, mode="ci")
    shrink, _ = honest_probability(0.85, entry, mode="shrink")
    assert shrink <= ci


def test_the_shipped_config_carries_an_interval_on_every_bucket():
    """Otherwise the default mode silently degrades to shrinkage everywhere."""
    from bet.simple_stats.analyze import market_reliability

    seen = 0
    for scope, entry in market_reliability().items():
        for label, bucket in (entry.get("calibration_curve") or {}).items():
            assert "gap_ci" in bucket, (scope, label)
            low, high = bucket["gap_ci"]
            assert low <= bucket["gap"] <= high, (scope, label)
            seen += 1
    assert seen > 100


def test_the_closed_form_interval_agrees_with_the_bootstrap():
    """The measurement swapped a 2,000-draw bootstrap for a cluster-robust
    expression because it now runs once per bucket rather than once per scope,
    and inside the validator's leave-one-date-out loop as well. The two must
    give the same answer or the swap changed the finding."""
    import random
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "scripts"))
    from simple.measure_market_reliability import _clustered_gap, clustered_gap_ci

    rng = random.Random(3)
    points = []
    for fixture in range(60):
        rate = rng.random()
        for _ in range(rng.randint(1, 40)):
            claim = 0.5 + 0.45 * rng.random()
            points.append(
                (claim, 1.0 if rng.random() < rate else 0.0, f"fx{fixture}")
            )
    exact = clustered_gap_ci(points)
    drawn = _clustered_gap(points, draws=4000)
    assert exact[0] == pytest.approx(drawn[0], abs=1e-9)
    assert exact[1] == pytest.approx(drawn[1], abs=0.01)
    assert exact[2] == pytest.approx(drawn[2], abs=0.01)


# --- the gated mode, which is the one that ships ----------------------------

def test_the_gated_mode_applies_the_full_damped_gap_where_the_gap_is_real():
    """The interval decides *whether*, the damping decides *how much*.

    Two questions, two mechanisms, and that is the whole design. Correcting by
    the interval's lower bound alone (mode "ci") was measured too timid to be
    worth having -- refit without one date a bucket holds a dozen matches, the
    interval is wide, and the bound sits near zero even where the
    overconfidence is plainly real. Out of sample it brought total_games@BO3
    from +0.0960 only to +0.0685, against +0.0008 gated.
    """
    entry = _entry({"0.85": _bucket(0.85, 0.70, fixtures=60, half=0.04)})
    gated, note = honest_probability(0.85, entry)
    shrink, _ = honest_probability(0.85, entry, mode="shrink")
    assert gated == shrink
    assert gated == pytest.approx(0.85 - 0.15 * 60 / 72, abs=1e-6)
    assert "skorygowane" in note


def test_the_gated_mode_applies_nothing_where_the_gap_is_noise():
    """The property mode "shrink" lacks, and why it did not ship despite
    scoring the best bucketed error.

    "shrink" corrects every bucket whose point estimate happens to be positive,
    and on a perfectly calibrated market half of them are by noise. Measured
    out of sample it moved nineteen of twenty-seven scopes the wrong way,
    pushing markets that already under-claimed further under. Gated moves seven
    and leaves fourteen -- 47,263 rungs -- completely untouched, while fixing
    the hot ones at least as well.
    """
    entry = _entry({"0.80": _bucket(0.80, 0.78, fixtures=40, half=0.05)})
    gated, note = honest_probability(0.80, entry)
    shrink, _ = honest_probability(0.80, entry, mode="shrink")
    assert gated == 0.80
    assert shrink < 0.80
    assert "nie wychodzi poza szum" in note


def test_the_shipped_default_is_the_gated_mode():
    """Pinned, because the default is the only one the pipeline ever uses and
    the three modes differ by a factor of seven on a hot market."""
    from bet.simple_stats.calibration import DEFAULT_MODE

    assert DEFAULT_MODE == "gated"


def test_the_hot_tennis_length_market_is_actually_corrected_on_the_real_config():
    """An end-to-end check on the shipped numbers rather than a fixture.

    total_games@BO3 is the worst-calibrated market the sheet prices and the one
    this whole mechanism has to earn its place on. A claim in its hot stretch
    must come back materially lower, and the note must say what such rows
    really did.
    """
    from bet.simple_stats.analyze import market_reliability

    entry = market_reliability()["total_games@BO3"]
    honest, note = honest_probability(0.75, entry)
    assert honest < 0.70, (honest, note)
    assert "realizowały" in note


def test_a_well_calibrated_football_market_is_untouched_on_the_real_config():
    """The other half of the same claim: goals_total is calibrated to within
    two points and must come back exactly as it went in."""
    from bet.simple_stats.analyze import market_reliability

    entry = market_reliability()["goals_total"]
    for claim in (0.60, 0.70, 0.80, 0.90):
        honest, _ = honest_probability(claim, entry)
        assert honest == claim, claim


# --- the tail gate ----------------------------------------------------------

def test_one_thin_top_bucket_cannot_exempt_every_claim_above_it():
    """The defect the shipped tennis market found, in miniature.

    Gating each bucket on its own interval reads the top of a curve backwards.
    ``total_games@BO3`` runs +0.0685, +0.1289, +0.1527, +0.1595 -- rising
    overconfidence, the first three clearing zero comfortably -- and its fourth
    bucket stands on 27 matches with a lower bound of -0.0207. Bucket by
    bucket, that one exempted every claim above 0.826: a row claiming 0.80 was
    corrected 6.4 points and a row claiming 0.93 was corrected nothing at all.
    The more it claimed, the less came off.
    """
    entry = _entry(
        {
            "0.65": _bucket(0.674, 0.545, fixtures=176, rungs=140, half=0.064),
            "0.75": _bucket(0.771, 0.618, fixtures=89, rungs=90, half=0.102),
            "0.80": _bucket(0.826, 0.667, fixtures=27, rungs=30, half=0.180),
        }
    )
    # A claim above the measured range inherits the highest bucket that
    # actually cleared, not the thin one that did not.
    honest, note = honest_probability(0.93, entry)
    assert honest < 0.85, (honest, note)
    assert "realizowały" in note
    # And the correction never shrinks as the claim grows.
    values = [honest_probability(c, entry)[0] for c in (0.70, 0.80, 0.90, 0.95)]
    applied = [c - v for c, v in zip((0.70, 0.80, 0.90, 0.95), values, strict=True)]
    for earlier, later in zip(applied, applied[1:], strict=False):
        assert later >= earlier - 1e-9, applied


def test_a_bucket_that_under_claims_is_kept_rather_than_dropped():
    """The distinction the drop rule turns on.

    "Hot here but inside the noise" and "genuinely calibrated here" are
    different findings, and only the second is evidence. The first is dropped so
    the claim inherits a neighbouring real measurement; the second is kept with
    no correction, because a market that under-claims has told us something and
    the one-sided rule is what respects it.
    """
    entry = _entry(
        {
            "0.65": _bucket(0.674, 0.545, fixtures=176, rungs=140, half=0.064),
            "0.90": _bucket(0.90, 0.94, fixtures=60, rungs=80, half=0.03),
        }
    )
    kept = [round(t.claimed, 3) for t in corrected_points(entry)]
    assert 0.9 in kept
    honest, note = honest_probability(0.90, entry)
    assert honest == 0.90
    assert "zaniża" in note


def test_a_market_measured_but_inconclusive_says_so_and_is_not_silent():
    """games_won@BO3 on the real config: four buckets, all hot, none past the
    noise on 31 fixtures. Reporting that as "never measured" would be a
    different and false statement to an operator deciding what to trust."""
    from bet.simple_stats.analyze import market_reliability

    entry = market_reliability()["games_won@BO3"]
    assert corrected_points(entry) == []
    honest, note = honest_probability(0.80, entry)
    assert honest == 0.80
    assert "zmierzony, ale" in note
    assert "brak zmierzonej kalibracji" not in note


def test_the_gate_is_the_pooled_tail_and_not_the_bucket():
    """Asserted on the shipped config, and it is not a tautology.

    ``player_was_fouled`` is corrected while **no single bucket** of its curve
    has an interval clearing zero -- which is the pooling working, not a bug:
    several buckets each individually inconclusive pool into a tail on far more
    matches, and a tail is always a superset of its own first bucket, so it can
    only ever add evidence. The property that must hold is the one the gate
    claims: every corrected bucket's pooled tail clears zero.
    """
    from bet.simple_stats.analyze import market_reliability
    from bet.simple_stats.calibration import _tail_gate

    pooled_only = []
    for scope, entry in market_reliability().items():
        points = curve_points(entry)
        gates = _tail_gate(points)
        for bucket, gated in zip(points, gates, strict=True):
            corrected = bucket.gap > 0.0 and gated
            if not corrected:
                continue
            # The gate held; and note where the bucket alone would not have.
            assert gated, scope
            if (bucket.ci_low or -1.0) <= 0.0:
                pooled_only.append(scope)
    assert "player_was_fouled" in pooled_only, sorted(set(pooled_only))
