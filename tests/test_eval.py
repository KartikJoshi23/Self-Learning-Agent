"""Tests for the baseline policies and the evaluation harness."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from rimal.baselines import (
    AlwaysClean,
    FixedInterval,
    NeverClean,
    SoilingThreshold,
    standard_baselines,
)
from rimal.env.cleaning_env import ACTION_CLEAN, ACTION_NOOP
from rimal.eval import analytic_optimal_interval, cvar, summarise


def _obs(soiling_ratio: float = 1.0) -> np.ndarray:
    obs = np.zeros(7, dtype=np.float32)
    obs[0] = soiling_ratio
    return obs


class TestPolicies:
    def test_never_and_always(self):
        assert NeverClean()(0, _obs()) == ACTION_NOOP
        assert AlwaysClean()(0, _obs()) == ACTION_CLEAN

    def test_fixed_interval_fires_on_schedule(self):
        policy = FixedInterval(7)
        policy.reset()
        actions = [policy(day, _obs()) for day in range(22)]
        fired = [i for i, a in enumerate(actions) if a == ACTION_CLEAN]
        assert fired == [7, 14, 21]
        assert actions[0] == ACTION_NOOP, "never clean an already-clean panel on day 0"

    def test_fixed_interval_resets_between_episodes(self):
        policy = FixedInterval(5)
        policy.reset()
        for day in range(7):
            policy(day, _obs())
        policy.reset()
        assert [policy(d, _obs()) for d in range(6)].count(ACTION_CLEAN) == 1

    def test_fixed_interval_rejects_nonpositive(self):
        with pytest.raises(ValueError, match=">= 1"):
            FixedInterval(0)

    def test_threshold_fires_only_below_the_threshold(self):
        policy = SoilingThreshold(0.95)
        assert policy(0, _obs(0.96)) == ACTION_NOOP
        assert policy(0, _obs(0.94)) == ACTION_CLEAN

    def test_threshold_boundary_is_float32_sensitive(self):
        """Observations are float32, so 0.95 stores as 0.949999988.

        The comparison is strictly ``<``, so a nominal-equal ratio fires. This
        is harmless -- it shifts the decision by a fraction of a day's soiling
        -- but it is pinned here so the behaviour is deliberate rather than a
        surprise later.
        """
        policy = SoilingThreshold(0.95)
        stored = float(_obs(0.95)[0])
        assert stored < 0.95
        assert policy(0, _obs(0.95)) == ACTION_CLEAN

    def test_threshold_rejects_out_of_range(self):
        for bad in (0.0, -0.1, 1.5):
            with pytest.raises(ValueError, match="threshold"):
                SoilingThreshold(bad)

    def test_standard_baselines_have_unique_names(self):
        names = [p.name for p in standard_baselines()]
        assert len(names) == len(set(names))


class TestCvar:
    def test_equals_the_mean_at_alpha_one(self):
        values = np.array([1.0, 2.0, 3.0, 4.0])
        assert cvar(values, alpha=1.0) == pytest.approx(values.mean())

    def test_averages_the_lower_tail(self):
        values = np.arange(1.0, 101.0)  # 1..100
        # Lowest 10% is 1..10, mean 5.5.
        assert cvar(values, alpha=0.10) == pytest.approx(5.5, abs=0.6)

    def test_is_never_above_the_mean(self):
        rng = np.random.default_rng(0)
        for _ in range(20):
            sample = rng.normal(size=50)
            assert cvar(sample, 0.2) <= sample.mean() + 1e-12

    def test_rejects_empty_and_bad_alpha(self):
        with pytest.raises(ValueError, match="empty"):
            cvar(np.array([]))
        with pytest.raises(ValueError, match="alpha"):
            cvar(np.array([1.0]), alpha=0.0)


class TestAnalyticInterval:
    def test_grows_with_the_square_root_of_cleaning_cost(self):
        base = analytic_optimal_interval(1.8e6, 0.017, 0.00235, 60.0)
        quadrupled = analytic_optimal_interval(1.8e6, 0.017, 0.00235, 240.0)
        assert quadrupled == pytest.approx(2 * base, rel=1e-9)

    def test_shrinks_as_energy_becomes_more_valuable(self):
        cheap = analytic_optimal_interval(1.8e6, 0.017, 0.00235, 60.0)
        dear = analytic_optimal_interval(1.8e6, 0.068, 0.00235, 60.0)
        assert dear == pytest.approx(cheap / 2, rel=1e-9)

    def test_rejects_nonpositive_inputs(self):
        with pytest.raises(ValueError, match="positive"):
            analytic_optimal_interval(0.0, 0.017, 0.00235, 60.0)


class TestSummarise:
    def test_aggregates_a_frame(self):
        frame = pd.DataFrame(
            {
                "policy": ["p", "p", "p"],
                "net_usd": [100.0, 200.0, 300.0],
                "cleans": [1, 2, 3],
                "soiling_loss_pct": [1.0, 2.0, 3.0],
            }
        )
        summary = summarise(frame)
        assert summary.policy == "p"
        assert summary.mean_net_usd == pytest.approx(200.0)
        assert summary.worst_net_usd == pytest.approx(100.0)
        assert summary.cvar_net_usd == pytest.approx(100.0)
        assert summary.n_years == 3
