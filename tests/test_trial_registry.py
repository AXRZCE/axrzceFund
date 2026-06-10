"""Tests for the Trial Registry — backtesting-framework.md §3.4.

Key invariants verified:
  1. Cannot run without a registered trial_id.
  2. All state transitions (registered → running → completed/failed) are enforced.
  3. DSR inputs (N, sharpes) are correctly aggregated.
  4. Hypothesis is required — no rationale, no trial.
  5. Invalid evidence_class is rejected.
"""

import tempfile
import gc
import shutil
from pathlib import Path

import pytest

from harness.trial_registry import (
    TrialRegistry,
    Trial,
    UnregisteredTrialError,
    TrialStateError,
)


@pytest.fixture
def registry():
    """Fresh in-memory-equivalent registry for each test."""
    tmpdir = tempfile.mkdtemp()
    reg = TrialRegistry(Path(tmpdir) / "registry.db")
    try:
        yield reg
    finally:
        reg.close()
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)


def _register(registry: TrialRegistry, **overrides) -> str:
    defaults = dict(
        signal="momentum_12_1",
        params={"lookback": 252, "skip": 21},
        universe="SP500",
        period_start="2010-01-01",
        period_end="2020-12-31",
        evidence_class="E2",
        hypothesis="12-1 momentum survives 2x costs over 2010-2020.",
    )
    defaults.update(overrides)
    return registry.register(**defaults)


# ── Gate: unregistered trial blocked ──────────────────────────────────────────

class TestGateEnforcement:
    def test_require_trial_id_blocks_unknown_id(self, registry):
        """Gate check refuses a completely unknown trial_id."""
        with pytest.raises(UnregisteredTrialError, match="not found"):
            registry.require_trial_id("trial_doesnotexist")

    def test_require_trial_id_blocks_registered_but_not_started(self, registry):
        """Registered but not started trials are also blocked — start() required."""
        trial_id = _register(registry)
        with pytest.raises(UnregisteredTrialError, match="start"):
            registry.require_trial_id(trial_id)

    def test_require_trial_id_passes_when_running(self, registry):
        """Gate check passes once start() is called."""
        trial_id = _register(registry)
        registry.start(trial_id)
        trial = registry.require_trial_id(trial_id)
        assert trial.status == "running"

    def test_require_trial_id_blocks_completed(self, registry):
        """Completed trial cannot be used for a new run."""
        trial_id = _register(registry)
        registry.start(trial_id)
        registry.complete(trial_id, results={"sharpe": 0.8})
        with pytest.raises(UnregisteredTrialError, match="start"):
            registry.require_trial_id(trial_id)


# ── Registration validation ────────────────────────────────────────────────────

class TestRegistrationValidation:
    def test_invalid_evidence_class_rejected(self, registry):
        """E5 and other nonsense evidence classes must be rejected."""
        with pytest.raises(ValueError, match="evidence_class"):
            _register(registry, evidence_class="E5")

    def test_missing_hypothesis_rejected(self, registry):
        """hypothesis is required — no rationale, no trial."""
        with pytest.raises(ValueError, match="hypothesis"):
            _register(registry, hypothesis="")

    def test_whitespace_hypothesis_rejected(self, registry):
        """Whitespace-only hypothesis is also not acceptable."""
        with pytest.raises(ValueError, match="hypothesis"):
            _register(registry, hypothesis="   ")

    def test_all_evidence_classes_accepted(self, registry):
        """E1, E2, E3, E4 are all valid."""
        for ec in ("E1", "E2", "E3", "E4"):
            tid = _register(registry, evidence_class=ec, signal=f"sig_{ec}")
            trial = registry.get(tid)
            assert trial.evidence_class == ec


# ── State transitions ──────────────────────────────────────────────────────────

class TestStateTransitions:
    def test_full_happy_path(self, registry):
        """registered → running → completed."""
        trial_id = _register(registry)
        assert registry.get(trial_id).status == "registered"

        registry.start(trial_id)
        assert registry.get(trial_id).status == "running"

        registry.complete(trial_id, results={"sharpe": 0.75, "dsr": 0.58, "pbo": 0.19})
        t = registry.get(trial_id)
        assert t.status == "completed"
        assert t.results["sharpe"] == 0.75
        assert t.completed_at is not None

    def test_failure_path(self, registry):
        """registered → running → failed."""
        trial_id = _register(registry)
        registry.start(trial_id)
        registry.fail(trial_id, error_msg="DivisionByZero in cost model")
        t = registry.get(trial_id)
        assert t.status == "failed"
        assert "DivisionByZero" in t.error_msg

    def test_cannot_start_already_running_trial(self, registry):
        """Double-start is a TrialStateError."""
        trial_id = _register(registry)
        registry.start(trial_id)
        with pytest.raises(TrialStateError):
            registry.start(trial_id)

    def test_cannot_complete_registered_trial(self, registry):
        """Must start before completing."""
        trial_id = _register(registry)
        with pytest.raises(TrialStateError):
            registry.complete(trial_id, results={"sharpe": 0.5})

    def test_cannot_fail_registered_trial(self, registry):
        """Must start before failing."""
        trial_id = _register(registry)
        with pytest.raises(TrialStateError):
            registry.fail(trial_id, error_msg="oops")

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(UnregisteredTrialError):
            registry.get("trial_nonexistent")


# ── DSR inputs ─────────────────────────────────────────────────────────────────

class TestDSRInputs:
    def test_dsr_inputs_empty_registry(self, registry):
        n, sharpes = registry.dsr_inputs()
        assert n == 0
        assert sharpes == []

    def test_dsr_inputs_counts_all_trials(self, registry):
        """N counts all trials, including failed and incomplete ones."""
        t1 = _register(registry, signal="sig_a")
        t2 = _register(registry, signal="sig_a")
        t3 = _register(registry, signal="sig_a")

        registry.start(t1)
        registry.complete(t1, results={"sharpe": 0.9})
        registry.start(t2)
        registry.fail(t2, error_msg="exploded")
        # t3 stays registered

        n, sharpes = registry.dsr_inputs(signal="sig_a")
        assert n == 3          # all 3 count toward N
        assert len(sharpes) == 1  # only completed with sharpe in results
        assert sharpes[0] == 0.9

    def test_dsr_inputs_signal_filter(self, registry):
        """Filter by signal isolates N correctly."""
        _register(registry, signal="momentum")
        _register(registry, signal="reversion")

        n_mom, _ = registry.dsr_inputs(signal="momentum")
        n_rev, _ = registry.dsr_inputs(signal="reversion")
        n_all, _ = registry.dsr_inputs()

        assert n_mom == 1
        assert n_rev == 1
        assert n_all == 2

    def test_dsr_inputs_multiple_sharpes(self, registry):
        """Multiple completed trials contribute multiple sharpes."""
        sharpe_values = [0.5, 0.8, 1.2, -0.1]
        for i, sr in enumerate(sharpe_values):
            tid = _register(registry, signal="test_sig", params={"i": i})
            registry.start(tid)
            registry.complete(tid, results={"sharpe": sr})

        n, sharpes = registry.dsr_inputs(signal="test_sig")
        assert n == 4
        assert sorted(sharpes) == sorted(sharpe_values)


# ── List and query ─────────────────────────────────────────────────────────────

class TestListAndQuery:
    def test_list_all_trials(self, registry):
        _register(registry, signal="a")
        _register(registry, signal="b")
        _register(registry, signal="c")
        trials = registry.list_trials()
        assert len(trials) == 3

    def test_list_filter_by_signal(self, registry):
        _register(registry, signal="mom")
        _register(registry, signal="mom")
        _register(registry, signal="rev")
        mom_trials = registry.list_trials(signal="mom")
        assert len(mom_trials) == 2
        assert all(t.signal == "mom" for t in mom_trials)

    def test_list_filter_by_status(self, registry):
        t1 = _register(registry)
        t2 = _register(registry)
        registry.start(t1)

        running = registry.list_trials(status="running")
        registered = registry.list_trials(status="registered")
        assert len(running) == 1
        assert len(registered) == 1

    def test_duplicate_config_detection(self, registry):
        """Same (signal, params, universe, period) registered twice is flagged."""
        same_params = dict(
            signal="dupecheck",
            params={"x": 1},
            universe="SP500",
            period_start="2020-01-01",
            period_end="2021-01-01",
        )
        _register(registry, **same_params)
        _register(registry, **same_params)

        dupes = registry.count_duplicate_configs()
        assert len(dupes) == 1
        assert dupes[0]["count"] == 2
        assert dupes[0]["signal"] == "dupecheck"
