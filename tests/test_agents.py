"""Tests for the PPO components.

Training itself is exercised by ``scripts/m4_verify.py``; these cover the
pieces where a silent bug would be invisible in a learning curve.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from rimal.agents import ActorCritic, PPOConfig, PPOPolicy, RunningNorm


class TestRunningNorm:
    def test_recovers_mean_and_variance_of_a_batch(self):
        rng = np.random.default_rng(0)
        data = rng.normal(loc=[5.0, -2.0], scale=[3.0, 0.5], size=(20_000, 2))
        norm = RunningNorm((2,))
        for chunk in np.array_split(data, 40):
            norm.update(chunk)
        assert norm.mean == pytest.approx(data.mean(axis=0), abs=0.02)
        assert np.sqrt(norm.var) == pytest.approx(data.std(axis=0), rel=0.02)

    def test_standardises_to_roughly_zero_mean_unit_variance(self):
        rng = np.random.default_rng(1)
        data = rng.normal(loc=100.0, scale=7.0, size=(5_000, 1))
        norm = RunningNorm((1,))
        norm.update(data)
        standardised = norm(data)
        assert standardised.mean() == pytest.approx(0.0, abs=0.02)
        assert standardised.std() == pytest.approx(1.0, rel=0.02)

    def test_gives_a_narrow_feature_real_dynamic_range(self):
        """The reason this class exists.

        Soiling ratio arrives in [0.70, 1.00] -- a narrow band near 1.0, which
        a tanh network resolves poorly. Standardisation must spread it out.
        """
        ratios = np.linspace(0.70, 1.00, 500).reshape(-1, 1)
        norm = RunningNorm((1,))
        norm.update(ratios)
        spread = np.ptp(norm(ratios))
        assert np.ptp(ratios) == pytest.approx(0.30, abs=1e-6)
        assert spread > 3.0, "standardised feature should span several units"

    def test_handles_a_constant_feature_without_dividing_by_zero(self):
        constant = np.full((100, 1), 4.0)
        norm = RunningNorm((1,))
        norm.update(constant)
        assert np.isfinite(norm(constant)).all()


class TestActorCritic:
    def test_shapes(self):
        net = ActorCritic(obs_dim=7, n_actions=2, hidden=32)
        obs = torch.zeros((5, 7))
        action, logprob, entropy, value = net.action_and_value(obs)
        assert action.shape == (5,)
        assert logprob.shape == (5,)
        assert entropy.shape == (5,)
        assert value.shape == (5,)

    def test_initial_policy_is_near_uniform(self):
        """The small final-layer gain should stop the policy committing to one
        action before it has learned anything."""
        net = ActorCritic(obs_dim=7, n_actions=2, hidden=64)
        probs = torch.softmax(net.actor(torch.randn(256, 7)), dim=-1)
        assert probs.mean(dim=0).min() > 0.4

    def test_evaluating_a_given_action_returns_its_logprob(self):
        net = ActorCritic(obs_dim=7, n_actions=2, hidden=32)
        obs = torch.randn((8, 7))
        chosen = torch.zeros(8, dtype=torch.long)
        _, logprob, _, _ = net.action_and_value(obs, chosen)
        expected = torch.log_softmax(net.actor(obs), dim=-1)[:, 0]
        assert torch.allclose(logprob, expected, atol=1e-6)


class TestPPOPolicy:
    def test_acts_greedily(self):
        net = ActorCritic(obs_dim=7, n_actions=2, hidden=16)
        with torch.no_grad():
            net.actor[-1].bias.copy_(torch.tensor([-5.0, 5.0]))
        policy = PPOPolicy(net)
        assert policy(0, np.zeros(7, dtype=np.float32)) == 1

        with torch.no_grad():
            net.actor[-1].bias.copy_(torch.tensor([5.0, -5.0]))
        assert policy(0, np.zeros(7, dtype=np.float32)) == 0

    def test_applies_the_normaliser_when_given_one(self):
        net = ActorCritic(obs_dim=2, n_actions=2, hidden=8)
        norm = RunningNorm((2,))
        norm.update(np.array([[0.0, 0.0], [10.0, 10.0]]))
        seen: list[np.ndarray] = []

        original = net.actor.forward

        def spy(x):
            seen.append(x.numpy().copy())
            return original(x)

        net.actor.forward = spy  # type: ignore[method-assign]
        PPOPolicy(net, norm)(0, np.array([10.0, 10.0], dtype=np.float32))
        assert seen and not np.allclose(seen[0], [10.0, 10.0])


class TestPPOConfig:
    def test_batch_and_minibatch_sizes_are_consistent(self):
        config = PPOConfig(num_envs=8, num_steps=256, num_minibatches=4)
        assert config.batch_size == 2048
        assert config.minibatch_size == 512
        assert config.batch_size % config.minibatch_size == 0

    def test_gamma_gives_a_horizon_covering_a_full_year(self):
        """gamma=0.99 would give a ~100-day horizon on a 365-day episode."""
        horizon = 1.0 / (1.0 - PPOConfig().gamma)
        assert horizon >= 365
