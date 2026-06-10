"""Authoritative G0.1 gate runner — backtesting-framework.md §3, validation-criteria.md G0.1.

Runs both planted controls over the pre-committed gate seed ensemble (campaign v2:
seeds {20..39}; seeds {0..19} were consumed by the v1 run + effective-N diagnosis
and may never be reused for gating — see the amendment log) and prints the full
distributional readout. Results are written to a JSON artifact FIRST so no
print/encoding failure can lose a completed run.

ASCII output only (Windows cp1252 console).

Usage:  python ops/run_g01_gate.py
"""
import dataclasses
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import structlog

logging.basicConfig(level=logging.WARNING)
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

import numpy as np

from harness.fraud_catch import (
    run_ensemble,
    evaluate_gate,
    beta_from_ic,
    POSITIVE_IC,
    SEED_ENSEMBLE,
)

ARTIFACT_DIR = Path("var/g01")


def to_jsonable(results):
    return [dataclasses.asdict(r) for r in results]


def summarize(name, results):
    import statistics as st
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
    print(f"  realized IC: median={st.median(ic):+.4f}  (target: positive ~0.04, negative ~0)")
    print(f"  best SR_ann: median={st.median(sr):.2f}")
    print(f"  best family counts: {fams}")
    print(f"  CPCV purged (first seed): {results[0].cpcv_total_purged}  "
          f"embargoed: {results[0].cpcv_total_embargoed}")
    print(f"  per-seed PBO : {[round(p, 3) for p in pbo]}")
    print(f"  per-seed DSRp: {[round(p, 4) for p in dsr_p]}")


def main():
    print(f"Running G0.1 (campaign v2) over pre-committed gate seeds {SEED_ENSEMBLE} ...")
    neg = run_ensemble("negative", beta=0.0)
    pos = run_ensemble("positive", beta=beta_from_ic(POSITIVE_IC))
    verdict = evaluate_gate(neg, pos)

    # Artifact FIRST — a print failure must never lose a completed run.
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact = ARTIFACT_DIR / f"g01_readout_{stamp}.json"
    artifact.write_text(json.dumps({
        "campaign": "v2",
        "seeds": SEED_ENSEMBLE,
        "negative": to_jsonable(neg),
        "positive": to_jsonable(pos),
        "verdict": verdict,
        "generated_at": stamp,
    }, indent=2), encoding="utf-8")
    print(f"artifact: {artifact}")

    summarize("negative", neg)
    summarize("positive", pos)

    print("\n=== GATE VERDICT ===")
    print(f"  G0.1a (negative): {verdict['G0.1a_negative']}")
    print(f"  G0.1b (positive): {verdict['G0.1b_positive']}")
    print(f"  OVERALL PASS: {verdict['pass']}")


if __name__ == "__main__":
    main()
