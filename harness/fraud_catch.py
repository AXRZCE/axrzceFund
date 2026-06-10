"""G0.1 fraud-catch harness — backtesting-framework.md §3, validation-criteria.md G0.1.

The single most important test in the project: it proves the validation machinery
can tell a real edge from an overfit one BEFORE any real strategy is trusted.

Design (after two rounds of review — see validation-criteria.md amendment log):

  * Multi-family research campaign, NOT near-duplicate trials. ~5 strategy families
    (true exogenous factor, momentum, short-term reversal, vol-scaled momentum,
    random linear combos of lagged returns), each with parameter variations. This
    raises EFFECTIVE trial independence — correlated near-duplicates make PBO a
    truthful ~0.5 (few independent trials → little selection bias to detect); a
    diverse campaign is what makes PBO a faithful overfitting detector and matches
    the real research process it exists to police.

  * Seed ENSEMBLE, not a single run. Single-run PBO has high sampling variance, so
    the gate is distributional over the pre-committed seed set {0..19}. Choosing a
    single seed after seeing the distribution would be backtest-tuning the validator.

  * Edge is a realistic 1-day exogenous factor (IC ≈ 0.04). Only the true-factor
    family can capture it (returns carry no autocorrelation), so on the positive
    panel that family wins; on the β=0 negative panel every family is noise.

  * Strategy holds are multi-day (min 2) so the selected strategy has overlapping
    label windows and CPCV purge/embargo do real work (logged as a printed count).

  * Costs zeroed (G0.1 tests signal-detection statistics, not net-of-cost survival).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import skew as _skew, kurtosis as _kurtosis

from harness.cpcv import CombinatorialPurgedCV
from harness.statistics import (
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe_ratio,
)
from harness.synthetic import (
    beta_from_ic,
    generate_panel,
    realized_ic,
    evaluate_score_strategy,
    factor_score,
    momentum_score,
    reversal_score,
    vol_scaled_momentum_score,
    random_linear_score,
)
from harness.trial_registry import TrialRegistry

# ── Construction constants ───────────────────────────────────────────────────
POSITIVE_IC = 0.04
N_ASSETS = 30          # calibrated so the true-factor strategy lands SR ≈ 1 (indep panels)
N_DAYS = 2520          # ~10 trading years
EDGE_HORIZON = 1       # 1-day exogenous edge (multi-day persistence → comically strong)
SEED_ENSEMBLE = list(range(20))   # pre-committed, a-priori — never substituted

# Strategy families. Only "factor" sees the exogenous edge; the rest are decoys.
_FAMILIES = {
    "factor": factor_score,
    "momentum": momentum_score,
    "reversal": reversal_score,
    "vol_mom": vol_scaled_momentum_score,
    "random": random_linear_score,
}

_LOOKBACKS = [1, 2, 3, 5, 10]
_HOLDS = [2, 3, 5, 10]
_DECILES = [0.10, 0.20]
_RANDOM_SEEDS = [0, 1, 2, 3]


@dataclass
class ControlResult:
    name: str
    seed: int
    realized_ic: float
    n_trials: int
    best_family: str
    best_config: dict
    best_sharpe_per_period: float
    best_sharpe_annualized: float
    dsr: float
    dsr_p_value: float
    pbo: float
    cpcv_mean_oos_sharpe: float
    cpcv_total_purged: int
    cpcv_total_embargoed: int


def build_campaign() -> list[dict]:
    """The registered research campaign: a diverse multi-family trial set (~208)."""
    campaign: list[dict] = []
    for fam in ("factor", "momentum", "reversal", "vol_mom"):
        for lb in _LOOKBACKS:
            for h in _HOLDS:
                for q in _DECILES:
                    campaign.append(
                        {"family": fam, "lookback": lb, "hold": h, "decile_frac": q, "rand_seed": 0}
                    )
    # Random linear-combo family varies its seed instead of decile breadth.
    for lb in [3, 5, 10]:
        for h in _HOLDS:
            for rs in _RANDOM_SEEDS:
                campaign.append(
                    {"family": "random", "lookback": lb, "hold": h, "decile_frac": 0.10, "rand_seed": rs}
                )
    return campaign


def _score_for(cfg: dict, signal: np.ndarray, returns: np.ndarray) -> np.ndarray:
    fn = _FAMILIES[cfg["family"]]
    if cfg["family"] == "random":
        return fn(signal, returns, cfg["lookback"], seed=cfg["rand_seed"])
    return fn(signal, returns, cfg["lookback"])


def run_control(
    name: str,
    beta: float,
    seed: int,
    n_assets: int = N_ASSETS,
    n_days: int = N_DAYS,
    edge_horizon: int = EDGE_HORIZON,
    cost_bps: float = 0.0,
) -> ControlResult:
    """Run one planted control on one panel (one seed), end-to-end through the
    Trial Registry, CPCV, DSR and PBO."""
    signal, returns = generate_panel(n_assets, n_days, beta, seed=seed, edge_horizon=edge_horizon)
    ic = realized_ic(signal, returns)

    campaign = build_campaign()
    max_lb = max(c["lookback"] for c in campaign)
    max_hold = max(c["hold"] for c in campaign)
    start, end = max_lb - 1, n_days - 1 - max_hold
    window = slice(start, end + 1)
    n_obs = end - start + 1

    registry = TrialRegistry(":memory:")  # fresh per run → true N == campaign size
    cost = cost_bps / 1e4  # zeroed hook; same code path
    obs_columns = []
    trial_sharpes = []
    for cfg in campaign:
        score = _score_for(cfg, signal, returns)
        obs = evaluate_score_strategy(score, returns, hold=cfg["hold"], decile_frac=cfg["decile_frac"])
        col = np.nan_to_num(obs[window].astype(float), nan=0.0)
        if cost:
            col = col - cost
        sr = sharpe_ratio(col)

        tid = registry.register(
            signal=f"{name}_{cfg['family']}",
            params=cfg,
            universe="SYNTHETIC",
            period_start="0000-01-01",
            period_end="0000-12-31",
            evidence_class="E2",
            hypothesis=f"{name} campaign trial: {cfg}",
        )
        registry.start(tid)
        registry.complete(tid, results={"sharpe": sr})
        trial_sharpes.append(sr)
        obs_columns.append(col)

    trial_sharpes = np.array(trial_sharpes)
    matrix = np.column_stack(obs_columns)

    best_idx = int(np.argmax(trial_sharpes))
    best_cfg = campaign[best_idx]
    best_col = obs_columns[best_idx]
    sr_hat = float(trial_sharpes[best_idx])

    skewness = float(_skew(best_col))
    kurt_raw = float(_kurtosis(best_col, fisher=True)) + 3.0

    n_trials, registry_sharpes = registry.dsr_inputs()
    var_trials = float(np.var(registry_sharpes, ddof=1)) if len(registry_sharpes) > 1 else 0.0
    dsr, dsr_p = deflated_sharpe_ratio(
        sr_hat, n=n_obs, variance_of_trial_sharpes=var_trials,
        n_trials=n_trials, skewness=skewness, kurtosis=kurt_raw,
    )
    registry.close()

    pbo_res = probability_of_backtest_overfitting(matrix, n_splits=16)

    # CPCV on the SELECTED strategy → OOS path distribution + proof purge did work.
    cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=0.01)
    splits = cv.split(n_samples=n_obs, label_horizon=best_cfg["hold"])
    oos_sharpes, total_purged, total_embargoed = [], 0, 0
    for sp in splits:
        oos_sharpes.append(sharpe_ratio(best_col[sp.test_idx]))
        total_purged += sp.n_purged
        total_embargoed += sp.n_embargoed

    return ControlResult(
        name=name, seed=seed, realized_ic=ic, n_trials=n_trials,
        best_family=best_cfg["family"], best_config=best_cfg,
        best_sharpe_per_period=sr_hat, best_sharpe_annualized=sr_hat * np.sqrt(252),
        dsr=dsr, dsr_p_value=dsr_p, pbo=pbo_res["pbo"],
        cpcv_mean_oos_sharpe=float(np.mean(oos_sharpes)),
        cpcv_total_purged=total_purged, cpcv_total_embargoed=total_embargoed,
    )


def run_ensemble(name: str, beta: float, seeds: list[int] | None = None,
                 edge_horizon: int = EDGE_HORIZON, n_assets: int = N_ASSETS,
                 n_days: int = N_DAYS) -> list[ControlResult]:
    """Run a control over the seed ensemble (defaults to the pre-committed {0..19})."""
    seeds = SEED_ENSEMBLE if seeds is None else seeds
    return [run_control(name, beta, seed=s, n_assets=n_assets,
                        n_days=n_days, edge_horizon=edge_horizon) for s in seeds]


def evaluate_gate(neg: list[ControlResult], pos: list[ControlResult]) -> dict:
    """Apply the distributional G0.1 criteria (validation-criteria.md G0.1a/b)."""
    neg_pbo = np.array([r.pbo for r in neg])
    neg_dsr_p = np.array([r.dsr_p_value for r in neg])
    pos_dsr_p = np.array([r.dsr_p_value for r in pos])

    median_pbo = float(np.median(neg_pbo))
    frac_pbo_gt_half = float(np.mean(neg_pbo > 0.50))
    median_neg_dsr_p = float(np.median(neg_dsr_p))
    pos_all_significant = bool(np.all(pos_dsr_p < 0.05))

    g0_1a = (median_pbo >= 0.60) and (frac_pbo_gt_half >= 0.80) and (median_neg_dsr_p >= 0.20)
    g0_1b = pos_all_significant

    return {
        "G0.1a_negative": {
            "median_pbo": median_pbo,
            "frac_pbo_gt_0.50": frac_pbo_gt_half,
            "median_dsr_p": median_neg_dsr_p,
            "pass": bool(g0_1a),
        },
        "G0.1b_positive": {
            "max_dsr_p": float(np.max(pos_dsr_p)),
            "all_seeds_significant": pos_all_significant,
            "pass": bool(g0_1b),
        },
        "pass": bool(g0_1a and g0_1b),
    }


def run_full_gate(seeds: list[int] | None = None) -> dict:
    """Run both controls over the ensemble and return per-seed results + verdict."""
    neg = run_ensemble("negative", beta=0.0, seeds=seeds)
    pos = run_ensemble("positive", beta=beta_from_ic(POSITIVE_IC), seeds=seeds)
    return {"negative": neg, "positive": pos, "verdict": evaluate_gate(neg, pos)}
