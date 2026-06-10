"""Authoritative G0.1 gate runner — backtesting-framework.md §3, validation-criteria.md G0.1.

Runs both planted controls over the PRE-COMMITTED seed ensemble {0..19} and prints
the full distributional readout the gate is evaluated on. No seed is chosen after
the fact; the ensemble is fixed a priori.

Usage:  python ops/run_g01_gate.py
"""
import logging
import statistics as st

import structlog

logging.basicConfig(level=logging.WARNING)
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

import numpy as np

from harness.fraud_catch import run_ensemble, evaluate_gate, beta_from_ic, POSITIVE_IC, SEED_ENSEMBLE


def summarize(name, results):
    pbo = [r.pbo for r in results]
    dsr_p = [r.dsr_p_value for r in results]
    ic = [r.realized_ic for r in results]
    sr = [r.best_sharpe_annualized for r in results]
    fams = {}
    for r in results:
        fams[r.best_family] = fams.get(r.best_family, 0) + 1
    print(f"\n=== {name.upper()} CONTROL (n={len(results)} seeds) ===")
    print(f"  PBO        : median={st.median(pbo):.3f}  min={min(pbo):.3f}  max={max(pbo):.3f}  "
          f"frac>0.50={np.mean(np.array(pbo) > 0.5):.0%}")
    print(f"  DSR p      : median={st.median(dsr_p):.4f}  min={min(dsr_p):.4f}  max={max(dsr_p):.4f}")
    print(f"  realized IC: median={st.median(ic):+.4f}  (target: positive≈0.04, negative≈0)")
    print(f"  best SR_ann: median={st.median(sr):.2f}")
    print(f"  best family counts: {fams}")
    print(f"  CPCV purged (seed0): {results[0].cpcv_total_purged}  "
          f"embargoed: {results[0].cpcv_total_embargoed}")
    print(f"  per-seed PBO : {[round(p,3) for p in pbo]}")
    print(f"  per-seed DSRp: {[round(p,4) for p in dsr_p]}")


print(f"Running G0.1 over pre-committed seed ensemble {SEED_ENSEMBLE} ...")
neg = run_ensemble("negative", beta=0.0)
pos = run_ensemble("positive", beta=beta_from_ic(POSITIVE_IC))

summarize("negative", neg)
summarize("positive", pos)

verdict = evaluate_gate(neg, pos)
print("\n=== GATE VERDICT ===")
print(f"  G0.1a (negative): {verdict['G0.1a_negative']}")
print(f"  G0.1b (positive): {verdict['G0.1b_positive']}")
print(f"  OVERALL PASS: {verdict['pass']}")
