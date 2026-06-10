"""Verify-the-tool tests for harness/statistics.py.

Per the G0.1 spec: pin every calculator against closed-form reductions and
independently-computed values BEFORE using it on synthetic data. A subtly-wrong
DSR or PBO would make the fraud-catch gate lie quietly, so these tests use
mathematically-certain anchors (Gaussian reductions, exact identities, limiting
cases) — values more trustworthy than a possibly-misremembered paper constant,
with scipy as the independent oracle.
"""

import math

import numpy as np
import pytest
from scipy.stats import norm

from harness.statistics import (
    EULER_MASCHERONI,
    sharpe_ratio,
    probabilistic_sharpe_ratio,
    expected_max_sharpe,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    information_coefficient,
)


# ── Sharpe ratio ─────────────────────────────────────────────────────────────

class TestSharpeRatio:
    def test_known_value(self):
        # mean=1, std(ddof=1)=... construct returns with known mean/std
        returns = [1.0, -1.0, 1.0, -1.0]  # mean 0 → SR 0
        assert sharpe_ratio(returns) == 0.0

    def test_positive_drift(self):
        rng = np.random.default_rng(0)
        returns = rng.normal(0.001, 0.01, size=1000)
        sr = sharpe_ratio(returns)
        assert sr > 0

    def test_annualization(self):
        rng = np.random.default_rng(1)
        returns = rng.normal(0.0005, 0.01, size=2520)
        sr_daily = sharpe_ratio(returns)
        sr_ann = sharpe_ratio(returns, periods_per_year=252)
        assert math.isclose(sr_ann, sr_daily * math.sqrt(252), rel_tol=1e-9)

    def test_zero_variance_is_zero(self):
        assert sharpe_ratio([3.0, 3.0, 3.0]) == 0.0


# ── PSR ──────────────────────────────────────────────────────────────────────

class TestPSR:
    def test_gaussian_hand_computed(self):
        """sr_hat=0.5, n=10, sr*=0, Gaussian: denom=sqrt(1.125), z=1.5/1.06066."""
        psr = probabilistic_sharpe_ratio(0.5, n=10, sr_benchmark=0.0)
        denom = math.sqrt(1.125)
        z = 1.5 / denom
        expected = float(norm.cdf(z))
        assert math.isclose(psr, expected, rel_tol=1e-12)
        assert math.isclose(psr, 0.9213503964, rel_tol=1e-8)  # independently computed

    def test_psr_half_at_observed(self):
        """PSR evaluated at the observed Sharpe itself is exactly 0.5."""
        psr = probabilistic_sharpe_ratio(0.8, n=50, sr_benchmark=0.8)
        assert math.isclose(psr, 0.5, abs_tol=1e-12)

    def test_gaussian_reduction(self):
        """For skew=0, kurt=3, (kurt-1)/4 = 0.5, so denom = sqrt(1 + 0.5·sr²)."""
        sr_hat, n, bench = 1.2, 100, 0.3
        psr = probabilistic_sharpe_ratio(sr_hat, n, sr_benchmark=bench)
        z = (sr_hat - bench) * math.sqrt(n - 1) / math.sqrt(1 + 0.5 * sr_hat ** 2)
        assert math.isclose(psr, float(norm.cdf(z)), rel_tol=1e-12)

    def test_positive_skew_raises_psr(self):
        """Positive skew shrinks the denominator (when sr>0) → higher PSR."""
        base = probabilistic_sharpe_ratio(0.5, n=100, skewness=0.0)
        pos = probabilistic_sharpe_ratio(0.5, n=100, skewness=0.5)
        neg = probabilistic_sharpe_ratio(0.5, n=100, skewness=-0.5)
        assert pos > base > neg

    def test_fat_tails_lower_psr(self):
        """Excess kurtosis inflates the SE of the Sharpe → lower PSR."""
        base = probabilistic_sharpe_ratio(0.5, n=100, kurtosis=3.0)
        fat = probabilistic_sharpe_ratio(0.5, n=100, kurtosis=9.0)
        assert fat < base

    def test_requires_two_observations(self):
        with pytest.raises(ValueError):
            probabilistic_sharpe_ratio(0.5, n=1)


# ── Expected max Sharpe (SR0) ─────────────────────────────────────────────────

class TestExpectedMaxSharpe:
    def test_matches_independent_formula(self):
        v, n = 0.25, 10
        sr0 = expected_max_sharpe(v, n)
        g = EULER_MASCHERONI
        expected = math.sqrt(v) * (
            (1 - g) * norm.ppf(1 - 1 / n) + g * norm.ppf(1 - 1 / (n * math.e))
        )
        assert math.isclose(sr0, expected, rel_tol=1e-12)
        # Independently computed ballpark
        assert 0.78 < sr0 < 0.80

    def test_increases_with_trial_count(self):
        """More trials → higher 'luckiest of N' bar."""
        assert expected_max_sharpe(0.25, 1000) > expected_max_sharpe(0.25, 10)

    def test_increases_with_variance(self):
        assert expected_max_sharpe(1.0, 50) > expected_max_sharpe(0.25, 50)

    def test_zero_variance_zero_benchmark(self):
        assert expected_max_sharpe(0.0, 50) == 0.0

    def test_requires_two_trials(self):
        with pytest.raises(ValueError):
            expected_max_sharpe(0.25, 1)


# ── DSR ───────────────────────────────────────────────────────────────────────

class TestDSR:
    def test_p_value_is_one_minus_dsr(self):
        dsr, p = deflated_sharpe_ratio(
            sr_hat=0.4, n=500, variance_of_trial_sharpes=0.04, n_trials=50
        )
        assert math.isclose(p, 1.0 - dsr, rel_tol=1e-12)

    def test_strong_edge_is_significant(self):
        """A high per-period Sharpe over many obs, modest trial count → p < 0.05."""
        dsr, p = deflated_sharpe_ratio(
            sr_hat=0.30, n=2520, variance_of_trial_sharpes=0.01, n_trials=20
        )
        assert p < 0.05

    def test_weak_edge_under_many_trials_insignificant(self):
        """A weak Sharpe deflated by a large trial count → not significant."""
        dsr, p = deflated_sharpe_ratio(
            sr_hat=0.03, n=2520, variance_of_trial_sharpes=0.04, n_trials=500
        )
        assert p >= 0.20

    def test_more_trials_reduce_significance(self):
        _, p_few = deflated_sharpe_ratio(0.1, 2520, 0.02, n_trials=5)
        _, p_many = deflated_sharpe_ratio(0.1, 2520, 0.02, n_trials=500)
        assert p_many > p_few


# ── PBO via CSCV ───────────────────────────────────────────────────────────────

class TestPBO:
    def test_dominant_trial_gives_zero_pbo(self):
        """If one trial dominates IS and OOS everywhere, it is never below the
        OOS median → PBO = 0."""
        rng = np.random.default_rng(42)
        T, N = 600, 8
        noise = rng.normal(0.0, 0.01, size=(T, N))
        means = np.array([1.0] + [0.05] * (N - 1))  # trial 0 dominates
        M = noise + means
        result = probability_of_backtest_overfitting(M, n_splits=10)
        assert result["pbo"] == 0.0

    def test_pure_noise_is_flagged_overfit(self):
        """Selecting the IS-best among pure-noise trials reverts OOS (regression to
        the mean), so CSCV correctly flags it as overfit: PBO sits ABOVE 0.5, not
        at 0. A PBO near 0 here would mean noise wrongly looks robust — a real bug."""
        rng = np.random.default_rng(7)
        T, N = 1000, 12
        M = rng.normal(0.0, 1.0, size=(T, N))
        result = probability_of_backtest_overfitting(M, n_splits=10)
        assert 0.5 <= result["pbo"] < 0.95

    def test_n_combinations_correct(self):
        rng = np.random.default_rng(3)
        M = rng.normal(0, 1, size=(320, 5))
        result = probability_of_backtest_overfitting(M, n_splits=8)
        assert result["n_combinations"] == math.comb(8, 4)

    def test_odd_splits_rejected(self):
        M = np.random.default_rng(0).normal(0, 1, size=(100, 4))
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(M, n_splits=7)

    def test_too_many_splits_rejected(self):
        M = np.random.default_rng(0).normal(0, 1, size=(10, 4))
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(M, n_splits=16)

    def test_needs_two_trials(self):
        M = np.random.default_rng(0).normal(0, 1, size=(100, 1))
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(M, n_splits=4)


# ── Information coefficient ──────────────────────────────────────────────────

class TestIC:
    def test_perfect_correlation(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert math.isclose(information_coefficient(x, 2 * x + 1), 1.0, rel_tol=1e-12)

    def test_perfect_anticorrelation(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert math.isclose(information_coefficient(x, -x), -1.0, rel_tol=1e-12)

    def test_independent_near_zero(self):
        rng = np.random.default_rng(11)
        x = rng.normal(size=10000)
        y = rng.normal(size=10000)
        assert abs(information_coefficient(x, y)) < 0.05

    def test_constant_signal_zero(self):
        assert information_coefficient([2.0, 2.0, 2.0], [1.0, 2.0, 3.0]) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            information_coefficient([1, 2, 3], [1, 2])


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
