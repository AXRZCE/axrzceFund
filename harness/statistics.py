"""Skill-vs-luck statistics — backtesting-framework.md §3.4 and §4.

Implemented from first principles (Bailey & López de Prado), NOT a borrowed
library: mlfinlab-lineage implementations have drifted across versions, and a
subtly-wrong DSR is exactly the failure that makes the G0.1 gate lie quietly.

Every calculator here is pinned by tests/test_statistics.py against closed-form
reductions and independently-computed values BEFORE it is used on synthetic data
(verify the tool, then use the tool).

Calculators:
  sharpe_ratio                       — per-period or annualized
  probabilistic_sharpe_ratio (PSR)   — P(true SR > benchmark | observed moments)
  expected_max_sharpe (SR0)          — multiple-testing benchmark for DSR
  deflated_sharpe_ratio (DSR)        — PSR at the deflated benchmark; returns (dsr, p)
  probability_of_backtest_overfitting (PBO) — via CSCV over a trial matrix
  information_coefficient (IC)        — cross-sectional signal/forward-return corr

References:
  Bailey & López de Prado (2012), "The Sharpe Ratio Efficient Frontier" (PSR).
  Bailey & López de Prado (2014), "The Deflated Sharpe Ratio" (DSR, SR0).
  Bailey, Borwein, López de Prado, Zhu (2017), "The Probability of Backtest
    Overfitting" (CSCV / PBO).
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Optional

import numpy as np
from scipy.stats import norm

# Euler–Mascheroni constant, used in the expected-maximum-Sharpe benchmark.
EULER_MASCHERONI = 0.5772156649015329


def sharpe_ratio(returns, periods_per_year: Optional[int] = None) -> float:
    """Sharpe ratio of a return series.

    Args:
        returns: 1-D array-like of per-period returns.
        periods_per_year: if given, annualize by sqrt(periods_per_year).
                          Leave None for the per-period Sharpe that PSR/DSR expect.

    Returns:
        Sharpe ratio (0.0 if the series has zero variance).
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0
    sr = r.mean() / sd
    if periods_per_year:
        sr *= math.sqrt(periods_per_year)
    return float(sr)


def probabilistic_sharpe_ratio(
    sr_hat: float,
    n: int,
    sr_benchmark: float = 0.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Probabilistic Sharpe Ratio: P(true SR > sr_benchmark | observed).

    Bailey & López de Prado (2012). `sr_hat` and `sr_benchmark` are PER-PERIOD
    Sharpe ratios at the same frequency as the `n` observations. `kurtosis` is the
    non-excess (raw) kurtosis — Gaussian = 3.

    The non-normality adjustment lives in the denominator: negative skew and fat
    tails inflate the standard error of the Sharpe estimate, lowering PSR.
    """
    if n < 2:
        raise ValueError("PSR requires n >= 2 observations")
    denom = math.sqrt(1.0 - skewness * sr_hat + ((kurtosis - 1.0) / 4.0) * sr_hat ** 2)
    z = (sr_hat - sr_benchmark) * math.sqrt(n - 1) / denom
    return float(norm.cdf(z))


def expected_max_sharpe(variance_of_trial_sharpes: float, n_trials: int) -> float:
    """Expected maximum Sharpe under the null of zero true skill — the DSR benchmark SR0.

    Bailey & López de Prado (2014), eq. for E[max]. With N independent trials whose
    Sharpe estimates have variance V, the best one is expected to reach roughly:

        SR0 = sqrt(V) * [ (1 - γ) * Z(1 - 1/N) + γ * Z(1 - 1/(N·e)) ]

    where γ is Euler–Mascheroni, e is Euler's number, Z is the standard-normal
    quantile. This is the bar a strategy must clear to be more than the luckiest
    of N coin-flips.
    """
    if n_trials < 2:
        raise ValueError("expected_max_sharpe requires n_trials >= 2")
    if variance_of_trial_sharpes < 0:
        raise ValueError("variance_of_trial_sharpes must be non-negative")
    sigma = math.sqrt(variance_of_trial_sharpes)
    g = EULER_MASCHERONI
    z1 = norm.ppf(1.0 - 1.0 / n_trials)
    z2 = norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(sigma * ((1.0 - g) * z1 + g * z2))


def deflated_sharpe_ratio(
    sr_hat: float,
    n: int,
    variance_of_trial_sharpes: float,
    n_trials: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> tuple[float, float]:
    """Deflated Sharpe Ratio = PSR evaluated at the multiple-testing benchmark SR0.

    Args:
        sr_hat: observed per-period Sharpe of the selected strategy.
        n: number of return observations behind sr_hat.
        variance_of_trial_sharpes: variance of the Sharpe ratios across all trials.
        n_trials: the TRUE trial count N (from the Trial Registry — the whole point
                  of forcing registration is to deflate by the real N).
        skewness, kurtosis: moments of the selected strategy's returns.

    Returns:
        (dsr, p_value) where dsr = P(true SR > SR0) and p_value = 1 - dsr.
        Admission requires p_value < 0.05 (i.e. dsr > 0.95).
    """
    sr0 = expected_max_sharpe(variance_of_trial_sharpes, n_trials)
    dsr = probabilistic_sharpe_ratio(
        sr_hat, n, sr_benchmark=sr0, skewness=skewness, kurtosis=kurtosis
    )
    return dsr, 1.0 - dsr


def _column_sharpes(matrix: np.ndarray) -> np.ndarray:
    """Per-column (per-trial) Sharpe ratios of a (rows × trials) matrix."""
    mu = matrix.mean(axis=0)
    sd = matrix.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sr = np.where(sd == 0, 0.0, mu / sd)
    return np.nan_to_num(sr, nan=0.0)


def probability_of_backtest_overfitting(
    returns_matrix, n_splits: int = 16
) -> dict:
    """PBO via Combinatorially Symmetric Cross-Validation (Bailey et al. 2017).

    Args:
        returns_matrix: shape (T, N) — T time observations × N trials. Column j is
                        the per-period return series of trial j.
        n_splits: number of contiguous time sub-blocks S (must be even). The method
                  evaluates all C(S, S/2) ways of splitting blocks into in-sample
                  (IS) and out-of-sample (OOS) halves.

    Returns:
        dict with:
          pbo: probability that the IS-best trial lands below the OOS median.
          logits: the array of per-combination logits λ.
          n_combinations: C(S, S/2).

    Interpretation: a strategy-selection process that overfits picks an IS winner
    that is no better than a coin flip OOS — so it falls below the OOS median about
    half the time or more, driving PBO up. PBO ≥ 25% fails signal admission;
    a pure-noise grid should land well above that (≈0.5+).
    """
    M = np.asarray(returns_matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("returns_matrix must be 2-D (T observations × N trials)")
    T, N = M.shape
    if N < 2:
        raise ValueError("PBO needs at least 2 trials")
    if n_splits % 2 != 0:
        raise ValueError("n_splits must be even")
    if n_splits > T:
        raise ValueError(f"n_splits ({n_splits}) cannot exceed T ({T})")

    block = T // n_splits
    usable = block * n_splits
    M = M[:usable]

    # Precompute per-block sufficient statistics so each combination's IS/OOS
    # Sharpe is an O(N) aggregation rather than an O(rows×N) recompute.
    block_n = np.full(n_splits, block, dtype=float)
    block_s1 = np.empty((n_splits, N), dtype=float)   # sum per block, per trial
    block_s2 = np.empty((n_splits, N), dtype=float)   # sum of squares
    for i in range(n_splits):
        seg = M[i * block:(i + 1) * block]
        block_s1[i] = seg.sum(axis=0)
        block_s2[i] = (seg * seg).sum(axis=0)

    def _agg_sharpe(block_ids: list[int]) -> np.ndarray:
        n = block_n[block_ids].sum()
        s1 = block_s1[block_ids].sum(axis=0)
        s2 = block_s2[block_ids].sum(axis=0)
        mean = s1 / n
        var = (s2 - n * mean ** 2) / (n - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sr = np.where(var <= 0, 0.0, mean / np.sqrt(var))
        return np.nan_to_num(sr, nan=0.0)

    indices = list(range(n_splits))
    logits = []
    for is_combo in combinations(indices, n_splits // 2):
        is_ids = list(is_combo)
        oos_ids = [i for i in indices if i not in is_combo]

        is_perf = _agg_sharpe(is_ids)
        oos_perf = _agg_sharpe(oos_ids)

        n_star = int(np.argmax(is_perf))
        # Relative rank of the IS-best trial within the OOS performance distribution.
        # rank in [1..N]; omega in (0,1) via the (N+1) denominator to avoid 0/1.
        order = np.argsort(oos_perf, kind="mergesort")  # ascending, stable
        rank = int(np.where(order == n_star)[0][0]) + 1
        omega = rank / (N + 1)
        logits.append(math.log(omega / (1.0 - omega)))

    logits_arr = np.array(logits, dtype=float)
    pbo = float(np.mean(logits_arr <= 0.0))
    return {
        "pbo": pbo,
        "logits": logits_arr,
        "n_combinations": len(logits),
    }


def information_coefficient(signal, forward_returns) -> float:
    """Cross-sectional information coefficient: Pearson corr(signal, forward returns).

    Accepts flattened arrays (e.g. all (asset, day) pairs stacked). Returns 0.0 if
    either series is constant.
    """
    s = np.asarray(signal, dtype=float).ravel()
    r = np.asarray(forward_returns, dtype=float).ravel()
    if s.size != r.size:
        raise ValueError("signal and forward_returns must have the same length")
    if s.std() == 0 or r.std() == 0:
        return 0.0
    return float(np.corrcoef(s, r)[0, 1])
