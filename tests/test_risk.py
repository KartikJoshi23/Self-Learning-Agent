"""Tests for the M7 machinery: storm soiling, water budget, QR-DQN."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from rimal.agents.qrdqn import (
    QRDQNConfig,
    QuantileNetwork,
    ReplayBuffer,
    cvar_scores,
    quantile_huber_loss,
)
from rimal.config import SOILING
from rimal.env.robots import DEWA_FLEET, FLEET_WITH_WET_CREW, Fleet
from rimal.physics.soiling import AodModulatedSoiling, storm_soiling


def _daily(days: int = 400, aod: np.ndarray | None = None):
    import pandas as pd

    idx = pd.date_range("2020-01-01", periods=days, freq="D", tz="Asia/Dubai")
    values = np.full(days, 0.4) if aod is None else aod
    return pd.DataFrame({"PRECTOTCORR": np.zeros(days), "AOD_55": values}, index=idx)


class TestStormSoiling:
    def test_default_model_still_clips_so_earlier_milestones_reproduce(self):
        """M1-M6 must not move. The tail-preserving model is opt-in."""
        model = AodModulatedSoiling()
        assert model.storm_exponent == 1.0
        assert model.rate_bounds == (SOILING.rate_min_per_day, SOILING.rate_max_per_day)

    def test_storm_model_permits_storm_scale_deposition(self):
        """The clipped model caps a dust storm at DEWA's average rate, which is
        the defect M7 exists to correct."""
        frame = _daily(3, aod=np.array([0.4, 0.4, 3.2]))
        clipped = AodModulatedSoiling().daily_rate(frame)
        storm = storm_soiling(storm_exponent=2.0).daily_rate(frame)
        assert clipped.max() == pytest.approx(SOILING.rate_max_per_day)
        assert storm.max() > 10 * clipped.max()

    def test_storm_ceiling_matches_one_cleaning_cycle(self):
        frame = _daily(3, aod=np.array([0.4, 0.4, 50.0]))
        assert storm_soiling(max_daily_rate=0.07).daily_rate(frame).max() == pytest.approx(0.07)

    def test_superlinear_scaling_amplifies_dusty_days(self):
        frame = _daily(2, aod=np.array([0.4, 0.8]))
        linear = storm_soiling(storm_exponent=1.0).daily_rate(frame)
        quadratic = storm_soiling(storm_exponent=2.0).daily_rate(frame)
        assert quadratic.iloc[1] / quadratic.iloc[0] == pytest.approx(
            (linear.iloc[1] / linear.iloc[0]) ** 2, rel=1e-6
        )

    def test_nonpositive_exponent_rejected(self):
        with pytest.raises(ValueError, match="storm_exponent"):
            AodModulatedSoiling(storm_exponent=0.0).daily_rate(_daily(3))


class TestWaterBudget:
    def test_dry_robots_use_no_water(self):
        assert all(s.water_m3_per_mwp == 0.0 for s in DEWA_FLEET)

    def test_wet_crew_uses_the_audited_figure(self):
        crew = FLEET_WITH_WET_CREW[-1]
        assert crew.water_m3_per_mwp == pytest.approx(8.5)
        assert crew.cooldown_days == 0

    def test_water_accumulates_only_for_the_wet_crew(self):
        fleet = Fleet(specs=FLEET_WITH_WET_CREW)
        rng = np.random.default_rng(0)
        fleet.clean(0, rng)
        assert fleet.water_used_m3 == 0.0
        fleet.clean(len(FLEET_WITH_WET_CREW) - 1, rng)
        assert fleet.water_used_m3 == pytest.approx(8.5)

    def test_reset_clears_water(self):
        fleet = Fleet(specs=FLEET_WITH_WET_CREW)
        fleet.clean(len(FLEET_WITH_WET_CREW) - 1, np.random.default_rng(0))
        fleet.reset()
        assert fleet.water_used_m3 == 0.0


class TestCvarScores:
    def test_alpha_one_is_the_mean(self):
        q = torch.tensor([[[0.0, 1.0, 2.0, 3.0]]])
        assert cvar_scores(q, 1.0).item() == pytest.approx(1.5)

    def test_small_alpha_reads_the_left_tail(self):
        q = torch.tensor([[[0.0, 1.0, 2.0, 3.0]]])
        assert cvar_scores(q, 0.25).item() == pytest.approx(0.0)
        assert cvar_scores(q, 0.5).item() == pytest.approx(0.5)

    def test_order_of_quantiles_does_not_matter(self):
        a = torch.tensor([[[3.0, 0.0, 2.0, 1.0]]])
        b = torch.tensor([[[0.0, 1.0, 2.0, 3.0]]])
        assert cvar_scores(a, 0.5).item() == pytest.approx(cvar_scores(b, 0.5).item())

    def test_risk_aversion_is_monotone(self):
        """Lower alpha must never score a skewed action higher."""
        q = torch.tensor([[[-10.0, 0.0, 1.0, 2.0, 3.0]]])
        scores = [cvar_scores(q, a).item() for a in (0.2, 0.4, 0.6, 0.8, 1.0)]
        assert scores == sorted(scores)

    def test_invalid_alpha_rejected(self):
        q = torch.zeros((1, 1, 4))
        for bad in (0.0, -0.1, 1.5):
            with pytest.raises(ValueError, match="alpha"):
                cvar_scores(q, bad)


class TestQuantileNetwork:
    def test_output_shape(self):
        net = QuantileNetwork(obs_dim=9, n_actions=2, n_quantiles=51, hidden=32)
        out = net(torch.zeros((4, 9)))
        assert out.shape == (4, 2, 51)

    def test_quantile_huber_loss_is_zero_on_a_perfect_fit(self):
        taus = (torch.arange(4, dtype=torch.float32) + 0.5) / 4
        q = torch.zeros((2, 4))
        assert quantile_huber_loss(q, q, taus, 1.0).item() == pytest.approx(0.0)

    def test_quantile_huber_loss_is_positive_when_wrong(self):
        taus = (torch.arange(4, dtype=torch.float32) + 0.5) / 4
        predicted = torch.zeros((2, 4))
        target = torch.ones((2, 4))
        assert quantile_huber_loss(predicted, target, taus, 1.0).item() > 0


class TestReplayBuffer:
    def test_stores_and_samples(self):
        buffer = ReplayBuffer(capacity=10, obs_dim=3)
        for i in range(5):
            buffer.add(np.full(3, i), i % 2, float(i), np.full(3, i + 1), 0.0)
        assert len(buffer) == 5
        obs, actions, rewards, next_obs, dones = buffer.sample(4, np.random.default_rng(0))
        assert obs.shape == (4, 3) and actions.shape == (4,)

    def test_wraps_at_capacity(self):
        buffer = ReplayBuffer(capacity=3, obs_dim=1)
        for i in range(10):
            buffer.add(np.array([i]), 0, 0.0, np.array([i]), 0.0)
        assert len(buffer) == 3


class TestQRDQNConfig:
    def test_gamma_covers_a_full_year(self):
        assert 1.0 / (1.0 - QRDQNConfig().gamma) >= 365

    def test_quantile_count_supports_a_five_percent_tail(self):
        """CVaR@5% needs at least one quantile inside the lowest 5%."""
        assert QRDQNConfig().n_quantiles * 0.05 >= 1.0
