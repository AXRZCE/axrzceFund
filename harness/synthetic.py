"""Synthetic data generator for the G0.1 fraud-catch controls.

Construction (cross-sectional, per the agreed spec):

    signal[t, i]   ~ N(0, 1)                          # standardized factor, known at t
    eps[t, i]      ~ N(0, sigma_eps**2)               # idiosyncratic noise
    returns[t, i]  = beta * signal[t-1, i] + eps[t, i]   # STRICTLY lagged

The edge is injected via the information coefficient, never by tuning a Sharpe on
the data we then test:

    IC   = corr(signal, forward return) = beta / sqrt(beta**2 + sigma_eps**2)
    beta = IC / sqrt(1 - IC**2)            (with sigma_eps = 1)

A realistic a-priori IC (0.03–0.05) pins beta analytically. Breadth (n_assets,
hold) is then tuned on INDEPENDENT panels until the realized annualized Sharpe of
the canonical strategy lands ≈ 1.0 — calibration data and test data disjoint by
construction, which keeps the positive control falsifiable.

The cross-sectional decile strategy with a multi-day hold gives each formation
day a label window [f, f+hold] that overlaps its neighbours — so CPCV's purge and
embargo have real work to do (the whole reason the hold is multi-day).
"""

from __future__ import annotations

import math

import numpy as np


def beta_from_ic(ic: float, sigma_eps: float = 1.0) -> float:
    """Analytic beta for a target information coefficient (a-priori, no data peeking).

    IC = beta / sqrt(beta**2 + sigma_eps**2)  ⟹  beta = IC * sigma_eps / sqrt(1 - IC**2).
    """
    if not (-1.0 < ic < 1.0):
        raise ValueError("ic must be in (-1, 1)")
    return float(ic * sigma_eps / math.sqrt(1.0 - ic ** 2))


def generate_panel(
    n_assets: int,
    n_days: int,
    beta: float,
    sigma_eps: float = 1.0,
    seed: int = 0,
    edge_horizon: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a (signal, returns) panel with a STRICTLY LAGGED, possibly multi-day edge.

    returns[t] = beta * (signal[t-1] + signal[t-2] + ... + signal[t-H]) + eps[t]

    where H = edge_horizon. Each signal[t] therefore influences returns[t+1..t+H],
    so a strategy holding H days captures the full edge and H is the optimal hold —
    which is what makes the genuine strategy a multi-day-hold strategy with
    overlapping label windows, giving CPCV's purge/embargo real work to do.

    With H=1 this reduces to the simple returns[t] = beta*signal[t-1] + eps[t].

    Returns:
        signal:  shape (n_days, n_assets), N(0,1).
        returns: shape (n_days, n_assets).
    """
    if edge_horizon < 1:
        raise ValueError("edge_horizon must be >= 1")
    rng = np.random.default_rng(seed)
    signal = rng.standard_normal((n_days, n_assets))
    eps = rng.normal(0.0, sigma_eps, size=(n_days, n_assets))

    returns = eps.copy()
    for k in range(1, edge_horizon + 1):
        # returns[t] += beta * signal[t-k] for all t >= k
        returns[k:] += beta * signal[:n_days - k]

    # No-leak invariant, asserted in code: returns[t] depends only on signal[t-1..t-H],
    # NEVER on signal[t]. Reconstruct the noise by subtracting the lagged edge.
    recon = returns.copy()
    for k in range(1, edge_horizon + 1):
        recon[k:] -= beta * signal[:n_days - k]
    assert np.allclose(recon, eps), "lag invariant broken: returns[t] leaked signal[t]"

    return signal, returns


def _decile_weights(scores: np.ndarray, decile_frac: float) -> np.ndarray:
    """Dollar-neutral long-short weights for one cross-section of scores.

    Long the top `decile_frac`, short the bottom `decile_frac`, equal-weighted,
    gross exposure 1.0 (longs sum +0.5, shorts sum -0.5), net 0.
    """
    n = scores.size
    k = max(1, int(round(decile_frac * n)))
    order = np.argsort(scores, kind="mergesort")  # ascending
    w = np.zeros(n, dtype=float)
    short_idx = order[:k]
    long_idx = order[-k:]
    w[long_idx] = 0.5 / k
    w[short_idx] = -0.5 / k
    return w


def strategy_obs_returns(
    signal: np.ndarray,
    returns: np.ndarray,
    hold: int = 5,
    decile_frac: float = 0.1,
    lookback: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Cross-sectional decile long-short strategy returns, per formation day.

    On each formation day f, rank assets by the (optionally lookback-smoothed)
    signal, take a dollar-neutral top/bottom-decile spread, and hold `hold` days.
    The observation return for day f is the mean daily spread return over its
    holding window f+1 .. f+hold. The label window of f is [f, f+hold].

    Args:
        signal:      (T, B) signal panel.
        returns:     (T, B) realized returns.
        hold:        holding period in days (>= 1). Multi-day → overlapping labels.
        decile_frac: top/bottom fraction traded (0.1 = deciles).
        lookback:    days of trailing signal smoothing (1 = use signal[f] directly).

    Returns:
        obs_returns: length-T array; obs_returns[f] is the strategy return for a
                     position formed on day f, or np.nan where f is outside the
                     valid range (warmup < lookback-1, or f+hold beyond the panel).
        label_end:   length-T int array; label_end[f] = f + hold (capped at T-1).
    """
    T, B = signal.shape
    obs_returns = np.full(T, np.nan, dtype=float)
    label_end = np.minimum(np.arange(T) + hold, T - 1)

    first_f = lookback - 1
    last_f = T - 1 - hold  # need returns up to f+hold
    for f in range(first_f, last_f + 1):
        if lookback == 1:
            scores = signal[f]
        else:
            scores = signal[f - lookback + 1:f + 1].mean(axis=0)
        w = _decile_weights(scores, decile_frac)
        # mean daily spread return over the holding window
        window = returns[f + 1:f + 1 + hold]  # shape (hold, B)
        daily_spread = window @ w  # shape (hold,)
        obs_returns[f] = float(daily_spread.mean())

    return obs_returns, label_end


def evaluate_score_strategy(
    score: np.ndarray,
    returns: np.ndarray,
    hold: int,
    decile_frac: float,
) -> np.ndarray:
    """Realized DAILY P&L of the continuously-rebalanced decile long-short strategy.

    Each day f with a valid score opens a dollar-neutral top/bottom-decile spread,
    held `hold` days. The strategy's return on day d is the average daily return of
    all cohorts still held — formations in [d-hold, d-1] — each weighted 1/hold.

    Returning the realized DAILY series (length T, one value per day) rather than a
    per-formation forward return is deliberate: per-formation returns overlap by
    hold-1 days, so a lucky stretch would bleed across CSCV blocks and make a noise
    strategy's in-sample winner persist out-of-sample — artificially depressing PBO.
    The daily series has autocorrelation bounded by `hold` (≪ a CSCV block), so PBO
    stays a faithful overfitting detector. Days with no live cohort are 0.0.

    The CALLER must build `score` from strictly-lagged information (data ≤ day f) —
    no look-ahead.
    """
    T, B = score.shape
    # Precompute each formation day's daily spread contribution to the days it is held.
    daily = np.zeros(T, dtype=float)
    held_count = np.zeros(T, dtype=float)
    last_f = T - 1
    for f in range(last_f):
        sc = score[f]
        if np.isnan(sc).any():
            continue
        w = _decile_weights(sc, decile_frac)
        d_hi = min(f + hold, T - 1)
        # cohort formed at f is held on days f+1 .. f+hold
        seg = returns[f + 1:d_hi + 1] @ w        # daily spread returns over the hold
        daily[f + 1:d_hi + 1] += seg
        held_count[f + 1:d_hi + 1] += 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(held_count > 0, daily / held_count, 0.0)
    return out


def _trailing_mean(x: np.ndarray, lookback: int) -> np.ndarray:
    """Trailing mean over [t-lookback+1, t] per column; NaN before warmup.
    Uses only rows <= t (no look-ahead)."""
    T, B = x.shape
    out = np.full((T, B), np.nan, dtype=float)
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    csum = np.cumsum(x, axis=0)
    for t in range(lookback - 1, T):
        total = csum[t] - (csum[t - lookback] if t - lookback >= 0 else 0.0)
        out[t] = total / lookback
    return out


def _trailing_std(x: np.ndarray, lookback: int) -> np.ndarray:
    """Trailing std over [t-lookback+1, t] per column; NaN before warmup."""
    T, B = x.shape
    out = np.full((T, B), np.nan, dtype=float)
    for t in range(lookback - 1, T):
        window = x[t - lookback + 1:t + 1]
        out[t] = window.std(axis=0, ddof=1) if lookback > 1 else 1.0
    return out


# ── Strategy-family score builders (all strictly lagged — known at day t) ────────

def factor_score(signal: np.ndarray, returns: np.ndarray, lookback: int) -> np.ndarray:
    """True-factor family: trailing mean of the EXOGENOUS signal. The only family
    that can capture the injected edge (returns carry no autocorrelation)."""
    return _trailing_mean(signal, lookback)


def momentum_score(signal: np.ndarray, returns: np.ndarray, lookback: int) -> np.ndarray:
    """Momentum family: trailing mean of past returns."""
    return _trailing_mean(returns, lookback)


def reversal_score(signal: np.ndarray, returns: np.ndarray, lookback: int) -> np.ndarray:
    """Short-term reversal family: negative trailing return."""
    return -_trailing_mean(returns, lookback)


def vol_scaled_momentum_score(signal: np.ndarray, returns: np.ndarray, lookback: int) -> np.ndarray:
    """Volatility-scaled momentum: trailing mean / trailing std."""
    mean = _trailing_mean(returns, lookback)
    std = _trailing_std(returns, lookback)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where((std == 0) | np.isnan(std), np.nan, mean / std)
    return out


def random_linear_score(
    signal: np.ndarray, returns: np.ndarray, lookback: int, seed: int = 0
) -> np.ndarray:
    """Random seeded linear combination of the last `lookback` daily returns —
    a decoy 'feature' a data-mining campaign would try. Strictly lagged.

    Dimensionality note: every returns-based linear feature lives in lag-space of
    dimension <= lookback, so a campaign of these can never exceed ~max-lookback
    effective independent trials. Use junk_indicator_score for an independent-
    by-construction decoy family."""
    T, B = returns.shape
    rng = np.random.default_rng(seed)
    weights = rng.standard_normal(lookback)
    out = np.full((T, B), np.nan, dtype=float)
    for t in range(lookback - 1, T):
        window = returns[t - lookback + 1:t + 1]      # (lookback, B), rows <= t
        out[t] = weights @ window                      # combine lagged returns
    return out


def junk_indicator_score(
    signal: np.ndarray, returns: np.ndarray, lookback: int, seed: int = 0
) -> np.ndarray:
    """An independent junk data source: an iid-noise indicator panel of its own
    (synthetic 'alt-data' — moon phases, social counts, weather...), trailing-mean
    smoothed over `lookback`. Each seed is a fully independent channel, which is
    what a real multi-source data-mining campaign looks like and what gives the
    negative-control campaign genuinely independent trials (no lag-space ceiling).

    Strictly lagged trivially: the indicator is independent of returns entirely,
    and only values <= t enter the score at t."""
    T, B = returns.shape
    rng = np.random.default_rng(seed)
    indicator = rng.standard_normal((T, B))
    return _trailing_mean(indicator, lookback)


def realized_ic(signal: np.ndarray, returns: np.ndarray) -> float:
    """Realized information coefficient: corr(signal[t], returns[t+1]) over all
    (day, asset) pairs. Diagnostic — should match the construction's target IC."""
    s = signal[:-1].ravel()
    r = returns[1:].ravel()
    if s.std() == 0 or r.std() == 0:
        return 0.0
    return float(np.corrcoef(s, r)[0, 1])


def annualized_strategy_sharpe(
    beta: float,
    n_assets: int,
    n_days: int,
    hold: int = 5,
    decile_frac: float = 0.1,
    seed: int = 999,
    periods_per_year: int = 252,
    edge_horizon: int = 1,
) -> float:
    """Annualized Sharpe of the canonical strategy on a FRESH (independent) panel.

    Used only for calibration verification — never on the panel a control will be
    tested on. Generates its own panel from `seed`.
    """
    signal, returns = generate_panel(n_assets, n_days, beta, seed=seed, edge_horizon=edge_horizon)
    obs, _ = strategy_obs_returns(signal, returns, hold=hold, decile_frac=decile_frac, lookback=1)
    obs = obs[~np.isnan(obs)]
    if obs.size < 2 or obs.std(ddof=1) == 0:
        return 0.0
    return float(obs.mean() / obs.std(ddof=1) * math.sqrt(periods_per_year))
