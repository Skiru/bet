"""Pricing for markets that are about BOTH sides of a fixture at once.

Everything the engine priced before this module is a question about one
number: a total, or one side's own count. A ladder of those is one marginal
distribution and a tail probability, which is what `engine.py` does.

The markets here are different in kind. "Każda z drużyn powyżej 3.5 rzutów
rożnych", "Najwięcej kartek", "Rzuty rożne handicap" and their tennis
equivalents are all questions about the *joint* distribution of the two sides,
and no marginal can answer them. Multiplying the two marginals is the obvious
thing to try and it is wrong: measured over 926 historical matches the two
teams' corner counts correlate at **-0.279**, shots at **-0.439**. Corners and
shots are largely a contest over the same possession, so one side having many
is evidence the other had few. Independence overstates
P(both teams >= 4 corners) by about 9% relative, and it overstates it in the
direction that makes a "tak" look cheap.

So the joint is built explicitly: each side's own marginal from its own
sample, and the dependence from a correlation measured per metric across
history (config/sofa_side_correlations.json, written by
scripts/sofa/measure_side_correlations.py).

Construction
------------
A Gaussian copula over two count marginals. The marginal is Poisson when the
sample's variance does not exceed its mean and negative binomial when it does,
so overdispersion is carried rather than flattened. The copula's parameter is
solved so that the *observed* correlation of the resulting joint matches the
measured one — a Gaussian copula applied to discrete margins attenuates
correlation, and using the measured value directly as the latent parameter
would quietly price a weaker dependence than the one that was measured.

The joint PMF is computed exactly on the count grid, not simulated. There is no
numpy and no scipy in this project, which rules out fast Monte Carlo, but it
also rules out Monte Carlo noise: every probability here is reproducible to the
quadrature's accuracy (~1e-8) rather than to a seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

# Gauss-Legendre nodes/weights on [-1, 1], 20 point. Enough for the smooth
# one-dimensional integrand below to ~1e-10, which is far finer than any
# probability this module reports.
_GL_NODES: tuple[float, ...] = (
    -0.9931285991850949, -0.9639719272779138, -0.9122344282513259,
    -0.8391169718222188, -0.7463319064601508, -0.6360536807265150,
    -0.5108670019508271, -0.3737060887154195, -0.2277858511416451,
    -0.0765265211334973, 0.0765265211334973, 0.2277858511416451,
    0.3737060887154195, 0.5108670019508271, 0.6360536807265150,
    0.7463319064601508, 0.8391169718222188, 0.9122344282513259,
    0.9639719272779138, 0.9931285991850949,
)
_GL_WEIGHTS: tuple[float, ...] = (
    0.0176140071391521, 0.0406014298003869, 0.0626720483341091,
    0.0832767415767048, 0.1019301198172404, 0.1181945319615184,
    0.1316886384491766, 0.1420961093183820, 0.1491729864726037,
    0.1527533871307258, 0.1527533871307258, 0.1491729864726037,
    0.1420961093183820, 0.1316886384491766, 0.1181945319615184,
    0.1019301198172404, 0.0832767415767048, 0.0626720483341091,
    0.0406014298003869, 0.0176140071391521,
)


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# Acklam's rational approximation, refined by one Halley step. Accurate to
# about 1e-15, which matters because this is applied to marginal CDF values
# that can sit very close to 0 or 1.
_A = (
    -3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
    1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00,
)
_B = (
    -5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
    6.680131188771972e01, -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
    -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00,
)
_D = (
    7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW = 0.02425


def normal_ppf(p: float) -> float:
    """Inverse standard normal CDF."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf

    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        num = ((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q
        den = (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        x = (num + _C[5]) / den
    elif p <= 1.0 - _P_LOW:
        q = p - 0.5
        r = q * q
        num = ((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r
        den = ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
        x = (num + _A[5]) * q / den
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        num = ((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q
        den = (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        x = -(num + _C[5]) / den

    e = normal_cdf(x) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - u / (1.0 + x * u / 2.0)


def bivariate_normal_cdf(h: float, k: float, rho: float) -> float:
    """P(Z1 <= h, Z2 <= k) for a standard bivariate normal with correlation rho.

    Uses the identity that differentiating the bivariate CDF with respect to
    rho gives the bivariate density, so

        Phi2(h, k, rho) = Phi(h) * Phi(k) + integral_0^rho phi2(h, k, r) dr

    which turns a two-dimensional problem into one smooth one-dimensional
    integral that Gauss-Legendre handles in twenty points.
    """
    if rho <= -1.0:
        return max(0.0, normal_cdf(h) + normal_cdf(k) - 1.0)
    if rho >= 1.0:
        return min(normal_cdf(h), normal_cdf(k))
    if h == -math.inf or k == -math.inf:
        return 0.0
    if h == math.inf:
        return normal_cdf(k)
    if k == math.inf:
        return normal_cdf(h)
    if rho == 0.0:
        return normal_cdf(h) * normal_cdf(k)

    half = rho / 2.0
    total = 0.0
    for node, weight in zip(_GL_NODES, _GL_WEIGHTS, strict=True):
        r = half * (node + 1.0)
        one_minus = 1.0 - r * r
        density = math.exp(
            -(h * h - 2.0 * r * h * k + k * k) / (2.0 * one_minus)
        ) / (2.0 * math.pi * math.sqrt(one_minus))
        total += weight * density
    return normal_cdf(h) * normal_cdf(k) + half * total


def count_pmf(mean: float, variance: float, kmax: int) -> list[float]:
    """PMF of a count variable on 0..kmax, renormalised to sum to 1.

    Poisson when variance <= mean, negative binomial when it exceeds it. A
    sample whose spread is wider than Poisson describes a quantity that varies
    for reasons beyond counting noise, and flattening that onto a Poisson would
    understate every tail this module goes on to price.
    """
    if mean <= 0.0:
        pmf = [0.0] * (kmax + 1)
        pmf[0] = 1.0
        return pmf

    if variance <= mean * 1.0000001:
        log_pmf = []
        for k in range(kmax + 1):
            log_pmf.append(-mean + k * math.log(mean) - math.lgamma(k + 1))
    else:
        # var = mean + mean^2 / r  =>  r = mean^2 / (var - mean)
        r = mean * mean / (variance - mean)
        p = r / (r + mean)
        log_pmf = []
        for k in range(kmax + 1):
            log_pmf.append(
                math.lgamma(k + r)
                - math.lgamma(r)
                - math.lgamma(k + 1)
                + r * math.log(p)
                + k * math.log1p(-p)
            )

    pmf = [math.exp(v) for v in log_pmf]
    total = sum(pmf)
    if total <= 0.0:
        out = [0.0] * (kmax + 1)
        out[0] = 1.0
        return out
    return [v / total for v in pmf]


def _grid_size(mean_a: float, var_a: float, mean_b: float, var_b: float) -> int:
    span = max(
        mean_a + 6.0 * math.sqrt(max(var_a, mean_a, 1.0)),
        mean_b + 6.0 * math.sqrt(max(var_b, mean_b, 1.0)),
    )
    return max(12, min(80, int(math.ceil(span))))


def _cdf(pmf: list[float]) -> list[float]:
    out = []
    acc = 0.0
    for v in pmf:
        acc = min(1.0, acc + v)
        out.append(acc)
    out[-1] = 1.0
    return out


@dataclass(frozen=True)
class JointCounts:
    """The exact joint PMF of the two sides' counts on a finite grid."""

    pmf: tuple[tuple[float, ...], ...]
    mean_a: float
    mean_b: float

    @property
    def kmax(self) -> int:
        return len(self.pmf) - 1

    def p_both_at_least(self, a_min: int, b_min: int) -> float:
        total = 0.0
        for i in range(a_min, self.kmax + 1):
            row = self.pmf[i]
            total += sum(row[b_min:])
        return min(1.0, max(0.0, total))

    def p_a_greater(self) -> float:
        total = 0.0
        for i in range(self.kmax + 1):
            row = self.pmf[i]
            total += sum(row[:i])
        return min(1.0, max(0.0, total))

    def p_equal(self) -> float:
        return min(1.0, max(0.0, sum(self.pmf[i][i] for i in range(self.kmax + 1))))

    def p_b_greater(self) -> float:
        return min(1.0, max(0.0, 1.0 - self.p_a_greater() - self.p_equal()))

    def p_diff_greater(self, threshold: float) -> float:
        """P(A - B > threshold). The handicap question."""
        total = 0.0
        for i in range(self.kmax + 1):
            row = self.pmf[i]
            for j in range(self.kmax + 1):
                if i - j > threshold:
                    total += row[j]
        return min(1.0, max(0.0, total))

    def min_moments(self) -> tuple[float, float]:
        """Mean and sd of min(A, B) — the variable a both-teams ladder is on.

        "Każda z drużyn powyżej n" is exactly "min(A, B) > n", so the ladder's
        scale is the spread of the minimum, not of the sum and not of either
        side. Using the sum's sd here understates every disagreement by about
        a factor of two, which is enough to walk a whole ladder past the gate.
        """
        mean = 0.0
        second = 0.0
        for i in range(self.kmax + 1):
            row = self.pmf[i]
            for j in range(self.kmax + 1):
                p = row[j]
                if p == 0.0:
                    continue
                v = float(min(i, j))
                mean += p * v
                second += p * v * v
        var = max(0.0, second - mean * mean)
        return mean, math.sqrt(var)

    def diff_moments(self) -> tuple[float, float]:
        """Mean and sd of A - B — the variable a handicap ladder is on."""
        mean = 0.0
        second = 0.0
        for i in range(self.kmax + 1):
            row = self.pmf[i]
            for j in range(self.kmax + 1):
                p = row[j]
                if p == 0.0:
                    continue
                v = float(i - j)
                mean += p * v
                second += p * v * v
        var = max(0.0, second - mean * mean)
        return mean, math.sqrt(var)

    def p_total_at_least(self, n: int) -> float:
        total = 0.0
        for i in range(self.kmax + 1):
            row = self.pmf[i]
            lo = max(0, n - i)
            if lo <= self.kmax:
                total += sum(row[lo:])
        return min(1.0, max(0.0, total))


def _build(
    mean_a: float, var_a: float, mean_b: float, var_b: float, latent_rho: float
) -> JointCounts:
    kmax = _grid_size(mean_a, var_a, mean_b, var_b)
    pmf_a = count_pmf(mean_a, var_a, kmax)
    pmf_b = count_pmf(mean_b, var_b, kmax)
    cdf_a = _cdf(pmf_a)
    cdf_b = _cdf(pmf_b)

    z_a = [normal_ppf(v) for v in cdf_a]
    z_b = [normal_ppf(v) for v in cdf_b]

    # Corner values of the copula, shared between the four cells that touch
    # each corner — this is what keeps the grid affordable in pure Python.
    corners: list[list[float]] = []
    for i in range(kmax + 1):
        row = []
        for j in range(kmax + 1):
            row.append(bivariate_normal_cdf(z_a[i], z_b[j], latent_rho))
        corners.append(row)

    joint: list[tuple[float, ...]] = []
    for i in range(kmax + 1):
        row = []
        for j in range(kmax + 1):
            c11 = corners[i][j]
            c01 = corners[i - 1][j] if i > 0 else 0.0
            c10 = corners[i][j - 1] if j > 0 else 0.0
            c00 = corners[i - 1][j - 1] if i > 0 and j > 0 else 0.0
            row.append(max(0.0, c11 - c01 - c10 + c00))
        joint.append(tuple(row))

    total = sum(sum(r) for r in joint)
    if total > 0.0:
        joint = [tuple(v / total for v in r) for r in joint]

    return JointCounts(pmf=tuple(joint), mean_a=mean_a, mean_b=mean_b)


def observed_correlation(joint: JointCounts) -> float:
    kmax = joint.kmax
    mean_a = sum(i * sum(joint.pmf[i]) for i in range(kmax + 1))
    mean_b = sum(
        j * sum(joint.pmf[i][j] for i in range(kmax + 1)) for j in range(kmax + 1)
    )
    cov = 0.0
    var_a = 0.0
    var_b = 0.0
    for i in range(kmax + 1):
        for j in range(kmax + 1):
            p = joint.pmf[i][j]
            cov += p * (i - mean_a) * (j - mean_b)
            var_a += p * (i - mean_a) ** 2
            var_b += p * (j - mean_b) ** 2
    if var_a <= 0.0 or var_b <= 0.0:
        return 0.0
    return cov / math.sqrt(var_a * var_b)


@lru_cache(maxsize=4096)
def _solve_latent_rho(
    mean_a: float, var_a: float, mean_b: float, var_b: float, target: float
) -> float:
    """Latent copula rho whose joint reproduces `target` observed correlation.

    Discrete margins attenuate a Gaussian copula's correlation, and the
    attenuation depends on how coarse the margins are — it is largest exactly
    where the counts are small, which is where the "both teams over 0.5" lines
    live. Using the measured value as the latent parameter would therefore
    price a dependence weaker than the one measured, and would do it worst on
    the rungs with the shortest prices.
    """
    if target == 0.0:
        return 0.0

    lo, hi = (-0.999, 0.0) if target < 0 else (0.0, 0.999)
    for _ in range(24):
        mid = (lo + hi) / 2.0
        got = observed_correlation(_build(mean_a, var_a, mean_b, var_b, mid))
        if abs(got - target) < 1e-4:
            return mid
        if got < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def build_joint(
    mean_a: float,
    var_a: float,
    mean_b: float,
    var_b: float,
    target_correlation: float,
) -> JointCounts:
    """The joint distribution of the two sides' counts for one metric."""
    mean_a = max(1e-6, mean_a)
    mean_b = max(1e-6, mean_b)
    var_a = max(0.0, var_a)
    var_b = max(0.0, var_b)
    # Rounded so the cache is reached: two fixtures whose samples agree to
    # three places do not need the bisection run twice.
    key = (
        round(mean_a, 3),
        round(var_a, 3),
        round(mean_b, 3),
        round(var_b, 3),
        round(target_correlation, 3),
    )
    latent = _solve_latent_rho(*key)
    return _build(mean_a, var_a, mean_b, var_b, latent)


def latent_rho(
    mean_a: float,
    var_a: float,
    mean_b: float,
    var_b: float,
    target_correlation: float,
) -> float:
    """The copula parameter `build_joint` would use for these moments."""
    return _solve_latent_rho(
        round(max(1e-6, mean_a), 3),
        round(max(0.0, var_a), 3),
        round(max(1e-6, mean_b), 3),
        round(max(0.0, var_b), 3),
        round(target_correlation, 3),
    )


def joint_tail_from_marginal_tails(
    p_a_tail: float, p_b_tail: float, rho: float
) -> float:
    """P(A >= n AND B >= n) from each side's own tail probability at n.

    This is the whole feature stated in one line. Given what the market itself
    says about each side separately, and a dependence measured from history,
    it says what the both-teams price *should* be — without using our sample's
    view of the level at all.

    That separation matters more than it looks. A both-teams row can beat its
    bar for two completely different reasons: because our sample disagrees
    with the market about how many corners a team takes, or because our
    measured dependence disagrees with the market's. Only the second is
    measured on 909 matches; the first is the same uncalibrated marginal the
    rest of the sheet already rests on. Priced together they are
    indistinguishable, and on Brentford-Chelsea they pointed in *opposite*
    directions - the sample said back it, the correlation said lay it.
    """
    p_a_tail = min(1.0 - 1e-9, max(1e-9, p_a_tail))
    p_b_tail = min(1.0 - 1e-9, max(1e-9, p_b_tail))
    z_a = normal_ppf(1.0 - p_a_tail)
    z_b = normal_ppf(1.0 - p_b_tail)
    # P(A>=n, B>=n) = 1 - F_A - F_B + Phi2(F_A, F_B)
    both = 1.0 - (1.0 - p_a_tail) - (1.0 - p_b_tail) + bivariate_normal_cdf(
        z_a, z_b, rho
    )
    return min(min(p_a_tail, p_b_tail), max(0.0, both))
