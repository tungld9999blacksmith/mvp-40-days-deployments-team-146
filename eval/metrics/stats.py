"""Statistical utilities for evaluation: confidence intervals and A/B tests.

Every reported rate should come with a confidence interval, not a bare point
estimate (testing-strategy spec #5). This module is pure standard library.

- wilson_interval      : 95% CI for a proportion (robust for small n / p near 0,1).
- bootstrap_ci         : percentile bootstrap CI for the mean of any sample.
- two_proportion_ztest : A/B test for two success rates (H0: equal).
- holm_bonferroni      : multiple-comparison correction across metrics.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import fmean

# Normal quantiles for common confidence levels.
_Z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054, 0.99: 2.5758293035489004}


def _z_for(confidence: float) -> float:
    return _Z.get(round(confidence, 2), 1.959963984540054)


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float
    n: int

    def __str__(self) -> str:
        return f"{self.point:.3f} (95% CI {self.low:.3f}-{self.high:.3f}, n={self.n})"


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because it stays inside [0, 1] and
    behaves well for small samples and extreme rates.
    """
    if n <= 0:
        return Interval(0.0, 0.0, 0.0, 0)
    z = _z_for(confidence)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return Interval(point=p, low=max(0.0, center - margin), high=min(1.0, center + margin), n=n)


def bootstrap_ci(
    sample: list[float],
    *,
    confidence: float = 0.95,
    resamples: int = 10_000,
    seed: int | None = 42,
) -> Interval:
    """Percentile bootstrap CI for the mean of a numeric sample."""
    n = len(sample)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, 0)
    if n == 1:
        v = float(sample[0])
        return Interval(v, v, v, 1)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        resample = [sample[rng.randrange(n)] for _ in range(n)]
        means.append(fmean(resample))
    means.sort()
    alpha = (1 - confidence) / 2
    lo = means[int(alpha * resamples)]
    hi = means[min(int((1 - alpha) * resamples), resamples - 1)]
    return Interval(point=fmean(sample), low=lo, high=hi, n=n)


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass(frozen=True)
class ABResult:
    rate_a: float
    rate_b: float
    diff: float          # rate_b - rate_a (B is usually the new variant)
    z: float
    p_value: float       # two-sided
    significant: bool
    n_a: int
    n_b: int

    def summary(self) -> str:
        verdict = "SIGNIFICANT" if self.significant else "not significant"
        return (
            f"A={self.rate_a:.3f} (n={self.n_a}) vs B={self.rate_b:.3f} (n={self.n_b}) | "
            f"Δ={self.diff:+.3f} | z={self.z:.2f} p={self.p_value:.4f} → {verdict}"
        )


def two_proportion_ztest(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
    *,
    alpha: float = 0.05,
) -> ABResult:
    """Two-sided two-proportion z-test. H0: rate_a == rate_b.

    Use for A/B comparisons on a binary primary metric (e.g. task success,
    faithful-or-not). Report Δ and p-value together (spec #5.3).
    """
    if n_a <= 0 or n_b <= 0:
        return ABResult(0.0, 0.0, 0.0, 0.0, 1.0, False, n_a, n_b)
    p_a, p_b = successes_a / n_a, successes_b / n_b
    p_pool = (successes_a + successes_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        z = 0.0
        p_value = 1.0
    else:
        z = (p_b - p_a) / se
        p_value = 2 * (1 - _normal_cdf(abs(z)))
    return ABResult(
        rate_a=p_a,
        rate_b=p_b,
        diff=p_b - p_a,
        z=z,
        p_value=p_value,
        significant=p_value < alpha,
        n_a=n_a,
        n_b=n_b,
    )


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm-Bonferroni step-down correction for multiple metrics.

    Returns {metric: reject_H0}. Use when an A/B run tracks several metrics so a
    single lucky metric does not get called significant by chance (spec #5.3).
    """
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    results: dict[str, bool] = {}
    still_rejecting = True
    for rank, (name, p) in enumerate(ordered):
        threshold = alpha / (m - rank)
        if still_rejecting and p <= threshold:
            results[name] = True
        else:
            still_rejecting = False
            results[name] = False
    return results
