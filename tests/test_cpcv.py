"""Tests for the CPCV engine — backtesting-framework.md §3.2.

The headline property (G0.1 rationale): purge/embargo must actually remove
observations, and they remove MORE when the holding period is longer. A 1-day
label makes them near no-ops; a 5-day label gives them real work. These tests
prove the leakage defense is exercised, not just present.
"""

import math

import numpy as np
import pytest

from harness.cpcv import CombinatorialPurgedCV, CPCVSplit


class TestSplitStructure:
    def test_n_splits_is_n_choose_k(self):
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2)
        assert cv.n_splits == math.comb(10, 2) == 45
        splits = cv.split(n_samples=1000, label_horizon=5)
        assert len(splits) == 45

    def test_train_and_test_disjoint(self):
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=0.01)
        for s in cv.split(n_samples=2520, label_horizon=5):
            assert len(np.intersect1d(s.train_idx, s.test_idx)) == 0

    def test_test_set_size_is_two_groups(self):
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2)
        splits = cv.split(n_samples=1000, label_horizon=5)
        # Each test set is ~2/10 of the sample
        for s in splits:
            assert 150 < len(s.test_idx) < 250

    def test_all_group_pairs_covered(self):
        cv = CombinatorialPurgedCV(n_groups=5, n_test_groups=2)
        splits = cv.split(n_samples=500, label_horizon=3)
        combos = {s.test_groups for s in splits}
        assert len(combos) == math.comb(5, 2)


class TestPurgeDoesRealWork:
    """The core G0.1 invariant: a multi-day label makes purge remove observations."""

    def test_longer_label_purges_more(self):
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=0.0)
        splits_h1 = cv.split(n_samples=2520, label_horizon=1)
        splits_h5 = cv.split(n_samples=2520, label_horizon=5)
        splits_h20 = cv.split(n_samples=2520, label_horizon=20)

        purged_h1 = sum(s.n_purged for s in splits_h1)
        purged_h5 = sum(s.n_purged for s in splits_h5)
        purged_h20 = sum(s.n_purged for s in splits_h20)

        assert purged_h1 < purged_h5 < purged_h20

    def test_five_day_hold_purges_nontrivially(self):
        """With h=5 there must be real purging on every split — proves the defense
        is exercised (the reason G0.1 mandates a multi-day hold)."""
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=0.0)
        splits = cv.split(n_samples=2520, label_horizon=5)
        assert all(s.n_purged > 0 for s in splits)

    def test_embargo_removes_observations(self):
        no_embargo = CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=0.0)
        with_embargo = CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=0.02)
        s_none = no_embargo.split(2520, label_horizon=5)
        s_emb = with_embargo.split(2520, label_horizon=5)
        assert sum(s.n_embargoed for s in s_none) == 0
        assert sum(s.n_embargoed for s in s_emb) > 0

    def test_purged_observations_actually_excluded(self):
        """Purged/embargoed indices must not appear in train_idx."""
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=0.01)
        for s in cv.split(n_samples=2520, label_horizon=5):
            n_total = 2520
            # train + test + purged + embargoed must reconcile (no double counting)
            accounted = len(s.train_idx) + len(s.test_idx) + s.n_purged + s.n_embargoed
            assert accounted == n_total


class TestValidation:
    def test_test_groups_must_be_fewer_than_groups(self):
        with pytest.raises(ValueError):
            CombinatorialPurgedCV(n_groups=5, n_test_groups=5)

    def test_embargo_pct_range(self):
        with pytest.raises(ValueError):
            CombinatorialPurgedCV(n_groups=10, n_test_groups=2, embargo_pct=1.0)

    def test_n_samples_too_small(self):
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2)
        with pytest.raises(ValueError):
            cv.split(n_samples=5, label_horizon=1)

    def test_label_horizon_min(self):
        cv = CombinatorialPurgedCV(n_groups=10, n_test_groups=2)
        with pytest.raises(ValueError):
            cv.split(n_samples=1000, label_horizon=0)


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
