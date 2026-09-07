"""Turn a market's settled record into a correction on the number it claims.

``config/market_reliability.json`` carries, per scope, a ``calibration_curve``:
for each claim bucket, what rows on that market claiming roughly that much have
really realised over every settled fixture in ``runs/``. Until now that curve
was read for one purpose only -- ``bet_builder_draft`` steps a tier down when a
row claims at least ``hot_above``. That is a gate: it answers *may this be bet*
and destroys the number on the way.

The operator's question is the other one. He does not want a market removed, he
wants to know **which statistic, in which direction, at which value, is most
likely** -- and then he prices it himself, live, on a screen this process cannot
see. Ranking that list by ``p_central`` does not work: the top of it fills with
saturated arithmetic, which is exactly the pressure that put a price filter in
the forecast file in the first place. The answer is not to hide those rows. It
is to stop overstating them.

    p_honest = claim - shrunk(the gap this market's own curve shows at claim)

Three properties, each of which is load-bearing:

**Interpolated, not bucketed.** A row claiming 0.87 sits between the 0.85 and
0.90 buckets and gets a blend of the two gaps. Snapping to a bucket would make
the correction jump by whole points as a claim crossed 0.875, and two rungs one
line apart would be corrected differently for no reason in the evidence.

**Shrunk by fixtures, never by rungs.** One match contributes up to forty rungs
off one sample, so a bucket holding 1,559 rungs can be 24 matches. Weighting
the rungs would trust every bucket almost completely and let a single unusual
afternoon set a market's correction for good. ``fixtures`` is written per
bucket by the measurement pass for this reason; an older config that lacks it
is deflated by the scope's own rungs-per-fixture ratio rather than trusted.

**One-sided: it may only lower a probability.** Roughly half the buckets on the
board under-claim -- ``player_shots_on_target`` claims 0.772 at the 0.75 bucket
and realises 0.810 -- and a symmetric correction would raise those rows. That
would be manufacturing confidence out of a bucket-level wobble, and the failure
mode is not symmetric either: a probability that is too high becomes a bet and a
probability that is too low becomes a pass. So a negative gap is reported in the
note and applied as zero. ``p_central`` is printed beside ``p_honest`` in every
table, so the reader can always see what was taken off and put it back.

What this deliberately does **not** do is replace the grade. ``WORSE_THAN_AVERAGE``
still says the sample loses to its own format's mean, and no amount of
recalibration makes such a row evidence about the fixture -- the level is wrong,
not the confidence. The two are independent and both are shown.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

# In fixtures. A bucket standing on 12 distinct matches gets half of its
# measured gap applied, one standing on 36 gets three quarters. Chosen ahead of
# looking at the effect (the alternative -- picking the K that most improves
# the out-of-sample number -- fits the constant to the answer), then checked
# against held-out dates by scripts/simple/validate_calibration.py.
CALIBRATION_SHRINKAGE_K = 12.0

# Under this many fixtures a bucket is not evidence about the market, it is one
# weekend. Its gap is discarded rather than shrunk toward nothing, so the
# interpolation reaches across it to the buckets that do qualify.
MIN_BUCKET_FIXTURES = 5.0

# The curve is built from the favoured side of each rung only (see
# ``measure_market_reliability._calibration``: reading both sides makes every
# market claim 0.500 and realise 0.500 by construction). So it says nothing
# about a claim below a half, and such a row is left exactly as it came.
CURVE_FLOOR = 0.5

# The claim region ``at_75`` measures, and therefore the only region the tail
# fallback below may be read at. That aggregate pools every rung claiming at
# least three quarters, so reading it at 0.60 would apply a tail's
# overconfidence to the body of the curve.
TAIL_FALLBACK_FLOOR = 0.75

# Which correction ships. "gated": the damped point estimate where the
# clustered interval says the overconfidence is real, and nothing where it does
# not. Chosen on held-out dates -- see applied_correction for the three
# candidates and what each scored.
DEFAULT_MODE = "gated"


def _bucket_fixtures(
    bucket: Mapping[str, object], entry: Mapping[str, object]
) -> float:
    """How many distinct matches stand behind one bucket of the curve."""
    stated = bucket.get("fixtures")
    if stated is not None:
        return float(stated)
    # A config written before the measurement recorded this. Deflate the rung
    # count by the scope's own rungs-per-fixture rather than treating 1,559
    # rungs as 1,559 independent trials, which is the error that once turned a
    # population artifact into a corroboration effect.
    rungs = float(bucket.get("rungs") or 0.0)
    scope_rungs = float(entry.get("rungs") or 0.0)
    scope_fixtures = float(entry.get("fixtures") or 0.0)
    if not scope_rungs or not scope_fixtures:
        return 0.0
    return rungs * scope_fixtures / scope_rungs


class Bucket(NamedTuple):
    """One claim bucket of one market's settled record.

    ``half`` is the half-width of a clustered 95% interval on ``gap`` (the
    match is the unit, never the rung). ``None`` means the config predates
    per-bucket intervals, and then only the shrinkage mode is available.
    """

    claimed: float
    gap: float
    fixtures: float
    rungs: float
    half: float | None

    @property
    def realised(self) -> float:
        return self.claimed - self.gap

    @property
    def ci_low(self) -> float | None:
        return None if self.half is None else self.gap - self.half


def _isotonic(buckets: list[Bucket]) -> list[Bucket]:
    """Force the realised rate to rise with the claim (pool adjacent violators).

    Raw buckets are not monotone and cannot be expected to be: ``total_games@BO3``
    has rows claiming 0.573 realise 0.610 and rows claiming 0.621 realise 0.568,
    on twelve and fifteen matches. Taken literally that says claiming *more* on
    this market makes a row less likely, which is not a fact about tennis; it is
    two thin buckets in the wrong order. It matters because a bucket's corrected
    probability is exactly its realised rate -- ``claim - (claim - realised)`` --
    so an inversion there is an inversion in the number the whole day is ranked
    by, and a row would be punished for claiming slightly less than the row
    beside it.

    Pool-adjacent-violators is the standard answer and adds no parameter: while
    a bucket's realised rate sits below its neighbour's, merge the two and
    re-check leftward. The merged block keeps the *higher* claim, so a row is
    still read against rows claiming at least as much as it does.

    Blocks are disjoint sets of rungs, so the pooled interval combines in
    quadrature weighted by rungs -- which is the same expression the
    cluster-robust variance of the union would give if the blocks shared no
    matches. They can share a match (one fixture may land rungs in two
    buckets), and where they do this understates the width slightly; the
    correction that reads it is one-sided and floored at zero, so the effect is
    to correct marginally more on a pooled block and nothing anywhere else.
    """
    merged = list(buckets)
    index = 0
    while index < len(merged) - 1:
        left, right = merged[index], merged[index + 1]
        if left.realised <= right.realised:
            index += 1
            continue
        rungs = left.rungs + right.rungs
        weight_l = left.rungs / rungs if rungs else 0.5
        realised = left.realised * weight_l + right.realised * (1.0 - weight_l)
        if left.half is None or right.half is None:
            half = None
        else:
            half = (
                (left.rungs * left.half) ** 2 + (right.rungs * right.half) ** 2
            ) ** 0.5 / rungs
        merged[index : index + 2] = [
            Bucket(
                claimed=right.claimed,
                gap=right.claimed - realised,
                fixtures=left.fixtures + right.fixtures,
                rungs=rungs,
                half=half,
            )
        ]
        index = max(0, index - 1)
    return merged


def curve_points(
    entry: Mapping[str, object] | None, *, isotonic: bool = True
) -> list[Bucket]:
    """This market's curve, thin buckets dropped and (by default) made monotone.

    Sorted by the bucket's *mean claim* rather than by its label, because that
    is the axis a row's own claim is interpolated along. The two orderings agree
    today and there is no reason to depend on their agreeing.
    """
    if not entry:
        return []
    # A missing curve is not the end of the read: ``games_won@BO5`` has no
    # ``calibration_curve`` at all (no single 0.05 bucket reaches
    # MIN_BUCKET_RUNGS on 25 fixtures) and a perfectly good ``at_75`` -- 82
    # rungs claiming 87.5% and realising 64.6%, interval from +6.0%. Returning
    # empty here, as this did, meant every ATP row on the board was corrected
    # by nothing while that measurement sat in the same record.
    raw: list[Bucket] = []
    curve = entry.get("calibration_curve")
    for bucket in (curve.values() if isinstance(curve, Mapping) else ()):
        if not isinstance(bucket, Mapping):
            continue
        claimed = bucket.get("claimed")
        realised = bucket.get("realised")
        if claimed is None or realised is None:
            continue
        fixtures = _bucket_fixtures(bucket, entry)
        if fixtures < MIN_BUCKET_FIXTURES:
            continue
        ci = bucket.get("gap_ci")
        gap = float(claimed) - float(realised)
        half = None
        if isinstance(ci, (list, tuple)) and len(ci) == 2:
            half = (float(ci[1]) - float(ci[0])) / 2.0
        raw.append(
            Bucket(
                claimed=float(claimed),
                gap=gap,
                fixtures=fixtures,
                rungs=float(bucket.get("rungs") or 0.0),
                half=half,
            )
        )
    # Where no bucket reaches three quarters, ``at_75`` is added as one more
    # point. It is the same measurement one resolution coarser -- see
    # ``_tail_bucket`` -- and adding it *here*, before the monotonicity pass
    # and the gate, rather than consulting it separately afterwards, is what
    # keeps the shipped number non-decreasing in the claim. Read as a separate
    # fallback it made ``games_won@BO3`` fall 16.6 points as a claim crossed
    # 0.75, which is the jump ``_isotonic`` and ``corrected_points`` both
    # exist to prevent.
    #
    # Only when the curve stops below the floor, because ``at_75`` pools every
    # rung claiming at least that much: on ``total_games@BO3`` its 93 rungs
    # *include* the 0.75 and 0.80 buckets, and adding it there would weigh the
    # same matches twice. Below the floor the two are disjoint by construction.
    tail = _tail_bucket(entry)
    if (
        tail is not None
        and tail.fixtures >= MIN_BUCKET_FIXTURES
        and not any(b.claimed >= TAIL_FALLBACK_FLOOR for b in raw)
    ):
        raw.append(tail)
    raw.sort()
    if not raw:
        return []
    return _isotonic(raw) if isotonic else raw


def measured_bucket(
    claim: float, entry: Mapping[str, object] | None, *, isotonic: bool = True
) -> Bucket | None:
    """The curve read at this claim, interpolated between the two nearest buckets.

    Interpolated rather than snapped: a row claiming 0.87 sits between the 0.85
    and 0.90 buckets and deserves a blend of the two. Snapping would move the
    correction by whole points as a claim crossed 0.875 and correct two rungs
    one line apart differently for no reason present in the evidence.

    Outside the curve's range the nearest bucket is held flat rather than
    extrapolated: a market measured to 0.90 says nothing about 0.99 beyond the
    last thing seen, and a trend fitted there would put the largest corrections
    exactly where there is no data.
    """
    points = curve_points(entry, isotonic=isotonic)
    if not points or claim < CURVE_FLOOR:
        return None
    if claim <= points[0].claimed:
        return points[0]
    if claim >= points[-1].claimed:
        return points[-1]
    for lo, hi in zip(points, points[1:], strict=False):
        if lo.claimed <= claim <= hi.claimed:
            span = hi.claimed - lo.claimed
            if span <= 0:
                return lo
            t = (claim - lo.claimed) / span

            def blend(a: float | None, b: float | None) -> float | None:
                if a is None or b is None:
                    return None
                return a + t * (b - a)

            return Bucket(
                claimed=claim,
                gap=lo.gap + t * (hi.gap - lo.gap),
                fixtures=lo.fixtures + t * (hi.fixtures - lo.fixtures),
                rungs=lo.rungs + t * (hi.rungs - lo.rungs),
                half=blend(lo.half, hi.half),
            )
    return points[-1]


def measured_gap(
    claim: float, entry: Mapping[str, object] | None, *, isotonic: bool = True
) -> tuple[float, float] | None:
    """``(gap, fixtures behind it)`` at this claim, or ``None`` if unmeasured.

    Kept as the narrow read for callers that only want the raw measured gap.
    Positive means this market has claimed more than it delivered around here.
    """
    bucket = measured_bucket(claim, entry, isotonic=isotonic)
    return None if bucket is None else (bucket.gap, bucket.fixtures)


def _tail_gate(points: list[Bucket]) -> list[bool]:
    """Per bucket: does the overconfidence from here *upward* clear zero?

    Gating each bucket on its own interval reads the top of a curve backwards,
    and ``total_games@BO3`` is the case that found it. Its four buckets run
    +0.0685, +0.1289, +0.1527, +0.1595 -- overconfidence rising steadily across
    the whole range -- and the first three clear zero comfortably (lower bounds
    +0.0074, +0.0650, +0.0509). The fourth stands on 27 matches and comes in at
    -0.0207. Gated bucket by bucket, that one thin bucket exempted every claim
    above 0.826, so a row claiming 0.80 was corrected 6.4 points and a row
    claiming 0.93 was corrected nothing at all. The more it claimed, the less
    we took off.

    So the gate asks the question ``hot_above`` in the measurement pass already
    asks, and for the same stated reason -- "a single bucket is thin, and the
    question a row asks is whether a claim of *at least* this size is
    trustworthy here, which is the pooled one". Buckets are pooled from each
    index upward: rung-weighted gap, half-widths combined in quadrature, and
    the tail passes if it clears zero.

    A pooled tail can only ever include *more* evidence than the bucket alone,
    so this cannot invent a correction out of nothing -- it can only stop one
    thin bucket from cancelling a trend the rest of the curve agrees on.
    """
    gates = [False] * len(points)
    for index in range(len(points)):
        tail = points[index:]
        rungs = sum(b.rungs for b in tail)
        if not rungs or any(b.half is None for b in tail):
            gates[index] = False
            continue
        gap = sum(b.rungs * b.gap for b in tail) / rungs
        half = sum((b.rungs * (b.half or 0.0)) ** 2 for b in tail) ** 0.5 / rungs
        gates[index] = (gap - half) > 0.0
    return gates


def applied_correction(bucket: Bucket, mode: str, *, gate: bool | None = None) -> float:
    """How much of a measured gap to actually subtract. Never negative.

    Three modes. The choice was settled by
    ``scripts/simple/validate_calibration.py`` on held-out dates -- one date out
    at a time, curve refit on the rest, applied blind -- and not by argument.
    Out-of-sample mean |claimed - realised| inside each market's own claim
    buckets, over 165,907 rungs on 762 fixtures, from a baseline of 0.0195:

    ``ci``     -- subtract only what the clustered interval puts beyond zero.
                  Parameter-free and self-shrinking, and it leaves a
                  well-calibrated bucket completely alone. **0.0182.** Too timid
                  to be worth having: refit without one date a bucket holds a
                  dozen matches, the interval is wide, and the lower bound sits
                  near zero even where the overconfidence is plainly real --
                  ``total_games@BO3`` only came in from +0.0960 to +0.0685.
    ``shrink`` -- subtract the point estimate damped by the matches behind it,
                  ``n/(n+K)``. **0.0128**, the best of the three on that
                  measure, and it fixes the markets that needed fixing
                  (``total_games@BO3`` +0.0960 to +0.0071, ``shots_for``
                  +0.0272 to -0.0065, ``player_tackles`` +0.0194 to +0.0010).
                  But it applies to every bucket whose point estimate happens
                  to be positive, and on a perfectly calibrated market half of
                  them are, by noise. It therefore biases the whole board about
                  a point *under* confident (pooled -0.0001 to -0.0104) and
                  moved nineteen scopes that had nothing wrong with them.
    ``gated``  -- **what ships. 0.0145**, the best of the three, and it earns
                  that where it should: ``total_games@BO3`` +0.0960 to +0.0008,
                  ``shots_for`` +0.0272 to -0.0066, ``player_tackles`` +0.0194
                  to +0.0010. The point estimate, damped as in ``shrink``, but
                  only where the pooled tail (see ``_tail_gate``) puts the
                  overconfidence beyond zero.

    The choice between the last two is a judgement and worth stating as one,
    because ``shrink`` is not far behind on the headline figure (0.0128) and
    the two carry almost the same pooled bias (-0.0104 against -0.0101). What
    separates them is *which* markets they touch. Of 27 scopes, ``gated`` moves
    6 closer to calibrated, 7 further, and leaves **14 completely untouched** --
    47,263 rungs on markets with no measured overconfidence, including
    ``goals_total``, ``fouls_total``, ``red_cards_total`` and
    ``player_offsides``, every one of which ``shrink`` pushes further
    under-confident for no reason in the evidence. ``shrink`` moves 19 scopes
    the wrong way. A correction that only touches what has been measured is
    worth 0.0017 of average absolute error.

    The cost ``gated`` does carry is worth naming: ``cards_points_for``
    +0.0007 to -0.0214 and ``cards_points_total`` +0.0001 to -0.0147. Those two
    look near-perfect pooled and are not -- their top buckets claim 0.95 and
    realise 0.887 while their low buckets under-claim -- so a one-sided
    correction fixes the top and cannot fix the bottom, and the pooled number
    gets worse while the bucketed one improves. See the note on that sample's
    competition mix in the measurement pass.

    Brier is flat to four places under all three modes, in the tail as well, so
    it does not decide this. What it does establish is that none of them is
    making the probability itself worse, which a constant subtracted from every
    claim would.

    The gate and the damping answer different questions and that is why both are
    here: the interval decides *whether* this market is measurably hot around
    this claim, and ``n/(n+K)`` decides how much of the point estimate to
    believe once it is.
    """
    shrunk = max(0.0, bucket.gap) * bucket.fixtures / (
        bucket.fixtures + CALIBRATION_SHRINKAGE_K
    )
    if mode == "shrink" or bucket.ci_low is None:
        # No interval available: an older config, or a pooled block whose
        # halves lacked one. Damping is all that is left, and it is better than
        # refusing to correct a market the record says is hot.
        return shrunk
    if mode == "ci":
        return max(0.0, bucket.ci_low)
    # ``gate`` is the pooled tail verdict from _tail_gate, which is the one that
    # ships. Falling back to the bucket's own interval keeps this function
    # answerable on a single bucket, which the tests need.
    passes = bucket.ci_low > 0.0 if gate is None else gate
    return shrunk if passes else 0.0


class Target(NamedTuple):
    """One bucket after the correction: the probability rows there really earn.

    ``value`` is ``claimed - applied_correction(...)``. Kept alongside the
    bucket it came from so the note can still quote what such rows realised and
    on how many matches, which is the audit trail the operator reads.
    """

    claimed: float
    value: float
    bucket: Bucket


def corrected_points(
    entry: Mapping[str, object] | None,
    *,
    mode: str = DEFAULT_MODE,
    isotonic: bool = True,
) -> list[Target]:
    """The curve after correcting each bucket, made monotone a second time.

    There are two monotonicity passes and they are not redundant. The first, in
    ``curve_points``, removes inversions in what the market *did* -- two thin
    buckets landing out of order. This one removes inversions the *correction*
    introduces, which is a different failure and was found by a test rather
    than by thinking:

    ``cards_points_for`` claiming 0.91 came back 0.910 and claiming 0.92 came
    back 0.871, because the gate turned on between those two buckets. A row was
    being punished four points for claiming one point more. The gate is a
    step function by nature, so no amount of care inside a single bucket fixes
    it -- the pass has to run on the corrected values, after the gate.

    Pooling here is weighted by rungs and keeps the higher claim, exactly as in
    ``_isotonic``. Interpolating between the surviving blocks then makes the
    shipped number monotone in the claim by construction, since the value
    between two blocks is a straight line between two non-decreasing endpoints.
    """
    points = curve_points(entry, isotonic=isotonic)
    if not points:
        return []
    gates = _tail_gate(points)
    targets = []
    for bucket, gated in zip(points, gates, strict=True):
        if (
            mode == "gated"
            and bucket.gap > 0.0
            and bucket.ci_low is not None      # no interval -> cannot judge
            and not gated
        ):
            # Measured hot here, but not past the noise. Dropped from the curve
            # rather than recorded as a zero correction, because those are
            # different findings and only one of them is supported: a wide
            # interval around +0.16 is not evidence that the market is
            # calibrated at 0.83, it is evidence of nothing. Dropping it lets
            # the interpolation reach across to the buckets that did clear, so
            # the claim inherits the nearest real measurement instead of an
            # exemption.
            #
            # This is the top of ``total_games@BO3``: three buckets clearing
            # zero on a rising trend, then one 27-match bucket at -0.0207 that
            # used to exempt every claim above 0.826 -- correcting a row
            # claiming 0.80 by 6.4 points and a row claiming 0.93 by nothing.
            #
            # A bucket whose gap is <= 0 is kept, with no correction. That is a
            # real finding: the market under-claims there, and the one-sided
            # rule leaves it alone.
            #
            # A bucket with no interval at all (a config written before
            # per-bucket ``gap_ci``) is also kept, and ``applied_correction``
            # falls back to damping it. Dropping it would silently turn every
            # older config into no correction whatsoever, which is a worse
            # answer than a damped one.
            continue
        targets.append(
            Target(
                claimed=bucket.claimed,
                value=bucket.claimed - applied_correction(bucket, mode, gate=gated),
                bucket=bucket,
            )
        )
    if not targets:
        return []
    if not isotonic:
        return targets
    merged = list(targets)
    index = 0
    while index < len(merged) - 1:
        left, right = merged[index], merged[index + 1]
        if left.value <= right.value:
            index += 1
            continue
        rungs = left.bucket.rungs + right.bucket.rungs
        weight = left.bucket.rungs / rungs if rungs else 0.5
        merged[index : index + 2] = [
            Target(
                claimed=right.claimed,
                value=left.value * weight + right.value * (1.0 - weight),
                # The right-hand bucket is kept as the one quoted, because it
                # is the block's claim and so the record a row landing here is
                # actually being read against.
                bucket=right.bucket,
            )
        ]
        index = max(0, index - 1)
    return merged


def _read_curve(
    claim: float, targets: list[Target]
) -> tuple[float, Bucket] | None:
    """The corrected value at this claim, interpolated, with its bucket.

    Interpolated rather than snapped: a row claiming 0.87 sits between the 0.85
    and 0.90 buckets and deserves a blend. Snapping would move the correction by
    whole points as a claim crossed 0.875 and correct two rungs one line apart
    differently for no reason present in the evidence.

    Outside the range the nearest block is held flat rather than extrapolated: a
    market measured to 0.90 says nothing about 0.99 beyond the last thing seen,
    and a trend fitted there would put the largest corrections exactly where
    there is no data.
    """
    if not targets:
        return None
    # Outside the measured range the *correction* is held flat, not the value.
    # Holding the value flat would cap a claim of 0.95 at whatever rows
    # claiming 0.70 realised on a market whose curve stops at 0.70 -- a large
    # correction justified by no observation at that level at all, and the
    # opposite of the rule everywhere else here. Carrying the amount instead
    # assumes the measured bias continues, which is the weaker assumption, and
    # stays monotone because ``claim - constant`` rises with the claim.
    if claim <= targets[0].claimed:
        first = targets[0]
        return claim - (first.claimed - first.value), first.bucket
    if claim >= targets[-1].claimed:
        last = targets[-1]
        return claim - (last.claimed - last.value), last.bucket
    for lo, hi in zip(targets, targets[1:], strict=False):
        if lo.claimed <= claim <= hi.claimed:
            span = hi.claimed - lo.claimed
            if span <= 0:
                return lo.value, lo.bucket
            t = (claim - lo.claimed) / span
            nearer = hi.bucket if t >= 0.5 else lo.bucket
            return lo.value + t * (hi.value - lo.value), nearer
    return targets[-1].value, targets[-1].bucket


def _tail_bucket(entry: Mapping[str, object] | None) -> Bucket | None:
    """``at_75`` read as a bucket, so the ordinary correction can be applied to it.

    ``curve_points`` needs ``MIN_BUCKET_RUNGS`` inside a *single* 0.05 bucket
    before it will read one, and a market can be measured well above 0.75
    without any one bucket clearing that floor. ``games_won@BO3`` is the case
    that found this: 82 rungs on 28 fixtures claim 0.75 or more, they spread
    across five buckets, none reaches thirty, so the curve stops at 0.7346.
    A row claiming 0.9448 was then corrected by *nothing*, while the
    measurement pass had already recorded those same 82 rungs claiming 85.9%
    and realising 62.2% -- a gap of +23.7 points whose clustered interval
    starts at +9.5.

    That is not a missing measurement. It is a measurement the correction never
    read. ``at_75`` answers exactly the question ``_tail_gate`` asks -- is a
    claim of *at least* this size trustworthy here -- over the whole tail at
    once instead of bucket by bucket, which is the same discipline one
    resolution coarser. So it is used on the same terms: gated on its own
    clustered interval clearing zero, damped by the fixtures behind it, and
    one-sided.

    ``fixtures`` is what damps the correction and ``at_75`` records it
    directly, so unlike ``_bucket_fixtures`` there is nothing to deflate here.
    """
    if not entry:
        return None
    tail = entry.get("at_75")
    if not isinstance(tail, Mapping):
        return None
    claimed = tail.get("claimed")
    realised = tail.get("realised")
    if claimed is None or realised is None:
        return None
    ci = tail.get("gap_ci")
    half = None
    if isinstance(ci, (list, tuple)) and len(ci) == 2:
        half = (float(ci[1]) - float(ci[0])) / 2.0
    return Bucket(
        claimed=float(claimed),
        gap=float(claimed) - float(realised),
        fixtures=float(tail.get("fixtures") or 0.0),
        rungs=float(tail.get("rungs") or 0.0),
        half=half,
    )


def honest_probability(
    claim: float | None,
    entry: Mapping[str, object] | None,
    *,
    isotonic: bool = True,
    mode: str = DEFAULT_MODE,
) -> tuple[float | None, str | None]:
    """``(p_honest, note)`` -- the claim after its own market's measured record.

    The note is operator-facing Polish and is the audit trail: it states what
    such rows really realised, the number of matches behind it and how much was
    actually taken off, so a correction can be argued with rather than merely
    accepted. ``None`` means the number was not touched and the reason is not
    worth a line.
    """
    if claim is None:
        return None, None
    if claim < CURVE_FLOOR:
        # Nothing measured down here, and nothing ranks off it either.
        return claim, None
    read = _read_curve(claim, corrected_points(entry, mode=mode, isotonic=isotonic))
    if read is None:
        # Two different silences, and conflating them once nearly shipped:
        # "nobody ever settled this market" and "every bucket we measured came
        # back hot but inside the noise" are not the same statement to an
        # operator deciding what to trust.
        if curve_points(entry, isotonic=isotonic):
            return claim, (
                "rynek zmierzony, ale w żadnym przedziale przestrzelenie nie "
                "wychodzi poza szum — nie odejmuję nic"
            )
        return claim, "brak zmierzonej kalibracji dla tego rynku"
    target, bucket = read
    # ``min`` is a guarantee rather than a formality: the correction is
    # non-negative per bucket, but a pooled block carries a value averaged with
    # its neighbour's and is read at claims lower than its own.
    honest = max(0.01, min(claim, target))
    applied = claim - honest
    realised = bucket.claimed - bucket.gap
    if applied <= 1e-9:
        if bucket.gap <= 0.0:
            return claim, (
                f"rynek w tym przedziale raczej zaniża (realizował {realised:.1%} "
                f"przy deklaracji {bucket.claimed:.0%}, {bucket.fixtures:.0f} "
                "meczów) — nie podnoszę, korekta działa tylko w dół"
            ).replace(".", ",")
        return claim, (
            f"zmierzone przestrzelenie {bucket.gap:.1%} nie wychodzi poza szum "
            f"({bucket.fixtures:.0f} meczów) — nie odejmuję"
        ).replace(".", ",")
    return honest, (
        f"skorygowane −{applied:.1%}: wiersze tego rynku deklarujące ~"
        f"{bucket.claimed:.0%} realizowały {realised:.1%} "
        f"({bucket.fixtures:.0f} meczów)"
    ).replace(".", ",")
