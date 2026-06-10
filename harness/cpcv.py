"""Combinatorial Purged Cross-Validation — backtesting-framework.md §3.2.

CPCV (López de Prado, AFML ch. 7 & 12) is the statistical workhorse of the
validation harness. Instead of one train/test split, it partitions time into N
contiguous groups and evaluates all C(N, k) ways of choosing k groups as the test
set — producing a *distribution* of out-of-sample paths rather than a single
anecdote.

Two leakage defenses are applied to the training set on every split:

  Purge:   drop training observations whose label window overlaps any test
           observation's window. With a multi-day holding period the label of a
           training day extends into the future and can leak into an adjacent test
           block — purging removes exactly those observations.

  Embargo: additionally drop a fraction (embargo_pct) of observations immediately
           AFTER each test block, killing serial-correlation leakage that purging
           alone misses.

Critical design note (G0.1): purge/embargo only do meaningful work when the label
window spans more than one observation. A 1-day label makes them near no-ops, so
the synthetic strategy uses a 5-day holding period — see n_purged in the split
output, which proves observations were actually removed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np


@dataclass
class CPCVSplit:
    """One train/test split from CPCV, with leakage-defense accounting."""

    test_groups: tuple[int, ...]
    train_idx: np.ndarray
    test_idx: np.ndarray
    n_purged: int       # training obs removed because their label overlaps the test set
    n_embargoed: int    # training obs removed by the post-test embargo


class CombinatorialPurgedCV:
    """Combinatorial Purged Cross-Validation splitter.

    Args:
        n_groups:      N contiguous time groups (default 10, per configuration.md).
        n_test_groups: k groups held out as test per split (default 2) → C(N, k) paths.
        embargo_pct:   fraction of total observations embargoed after each test block
                       (default 0.01 = 1%).
    """

    def __init__(self, n_groups: int = 10, n_test_groups: int = 2, embargo_pct: float = 0.01):
        if n_test_groups >= n_groups:
            raise ValueError("n_test_groups must be < n_groups")
        if not (0.0 <= embargo_pct < 1.0):
            raise ValueError("embargo_pct must be in [0, 1)")
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.embargo_pct = embargo_pct

    @property
    def n_splits(self) -> int:
        return math.comb(self.n_groups, self.n_test_groups)

    def split(self, n_samples: int, label_horizon: int = 1) -> list[CPCVSplit]:
        """Generate all C(N, k) purged/embargoed train/test splits.

        Args:
            n_samples:     number of observations T (rows in time order).
            label_horizon: how many observations forward each label resolves over
                           (the holding period h). label_end[i] = min(i + h, T - 1).

        Returns:
            List of CPCVSplit, one per combination of test groups.
        """
        if n_samples < self.n_groups:
            raise ValueError("n_samples must be >= n_groups")
        if label_horizon < 1:
            raise ValueError("label_horizon must be >= 1")

        idx = np.arange(n_samples)
        # label end-time for each observation (inclusive), capped at the last obs
        label_end = np.minimum(idx + label_horizon, n_samples - 1)

        # Contiguous, near-equal groups (np.array_split handles non-divisible T).
        groups = np.array_split(idx, self.n_groups)
        embargo = int(math.ceil(self.embargo_pct * n_samples))

        splits: list[CPCVSplit] = []
        for test_combo in combinations(range(self.n_groups), self.n_test_groups):
            test_idx = np.concatenate([groups[g] for g in test_combo])
            test_idx.sort()

            # Test windows as merged contiguous runs: [run_start, run_label_end].
            test_runs = self._contiguous_runs(sorted(test_combo))
            test_intervals = []
            for run in test_runs:
                run_idx = np.concatenate([groups[g] for g in run])
                start = int(run_idx[0])
                end = int(label_end[run_idx[-1]])  # extend by the label horizon
                test_intervals.append((start, end))

            in_test = np.zeros(n_samples, dtype=bool)
            in_test[test_idx] = True

            purged = np.zeros(n_samples, dtype=bool)
            embargoed = np.zeros(n_samples, dtype=bool)

            for (t_start, t_end) in test_intervals:
                # Purge: training obs i whose label window [i, label_end[i]] overlaps
                # the test interval [t_start, t_end].
                overlap = (idx <= t_end) & (label_end >= t_start)
                purged |= overlap
                # Embargo: the `embargo` observations immediately after the test block.
                if embargo > 0:
                    emb_lo = t_end + 1
                    emb_hi = min(t_end + embargo, n_samples - 1)
                    if emb_lo <= emb_hi:
                        embargoed[emb_lo:emb_hi + 1] = True

            # Test observations themselves are never training; don't count them as purged.
            purged &= ~in_test
            embargoed &= ~in_test
            # An observation counted as purged shouldn't be double-counted as embargoed.
            embargoed &= ~purged

            train_mask = ~in_test & ~purged & ~embargoed
            train_idx = idx[train_mask]

            splits.append(
                CPCVSplit(
                    test_groups=tuple(test_combo),
                    train_idx=train_idx,
                    test_idx=test_idx,
                    n_purged=int(purged.sum()),
                    n_embargoed=int(embargoed.sum()),
                )
            )
        return splits

    @staticmethod
    def _contiguous_runs(sorted_groups: list[int]) -> list[list[int]]:
        """Split a sorted list of group ids into runs of consecutive ids."""
        runs: list[list[int]] = []
        current: list[int] = []
        for g in sorted_groups:
            if current and g == current[-1] + 1:
                current.append(g)
            else:
                if current:
                    runs.append(current)
                current = [g]
        if current:
            runs.append(current)
        return runs
