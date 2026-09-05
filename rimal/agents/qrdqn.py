"""QR-DQN with CVaR action selection.

Every agent in this project so far has optimised the *mean* return. That is the
right objective only if the return distribution is well behaved, and M7 showed
it is not: once dust storms are modelled without the clipping that M1 wrongly
imposed, the annual return grows a left tail, and the threshold that maximises
the mean is no longer the threshold that maximises CVaR.

Quantile-regression DQN learns the full return *distribution* rather than its
expectation, by predicting a fixed set of quantiles and training them with the
quantile Huber loss. Having the distribution makes risk sensitivity a matter of
how the greedy action is chosen rather than a change to the objective:

* averaging **all** quantiles selects the risk-neutral (expected-value) action;
* averaging only the **lowest** fraction selects the action that maximises CVaR
  at that level -- it maximises the average of the worst outcomes.

The same trained network therefore yields a whole family of policies from
risk-neutral to strongly risk-averse, and the frontier they trace can be
compared directly against the frontier the tuned threshold rules trace. That
comparison is the point of M7.

Reference: Dabney et al., "Distributional Reinforcement Learning with Quantile
Regression" (QR-DQN).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gymnasium as gym
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from rimal.agents.ppo import RunningNorm
from rimal.env import EnvConfig, RimalCleaningEnv


@dataclass
class QRDQNConfig:
    """Hyperparameters. Defaults follow the QR-DQN paper, scaled to a CPU budget."""

    total_timesteps: int = 400_000
    n_quantiles: int = 51
    learning_rate: float = 5e-4
    buffer_size: int = 100_000
    batch_size: int = 128
    gamma: float = 0.999
    train_frequency: int = 4
    target_update_frequency: int = 1_000
    learning_starts: int = 5_000
    #: Epsilon-greedy exploration, annealed over this fraction of training.
    start_epsilon: float = 1.0
    end_epsilon: float = 0.02
    exploration_fraction: float = 0.4
    hidden_size: int = 128
    reward_scale: float = 5e-2
    torch_threads: int = 4
    #: Huber threshold in the quantile loss.
    kappa: float = 1.0


class QuantileNetwork(nn.Module):
    """Predicts ``n_quantiles`` return quantiles for each action."""

    def __init__(self, obs_dim: int, n_actions: int, n_quantiles: int, hidden: int):
        super().__init__()
        self.n_actions = n_actions
        self.n_quantiles = n_quantiles
        self.body = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, n_actions * n_quantiles),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Return shape (batch, n_actions, n_quantiles)."""
        return self.body(x).view(-1, self.n_actions, self.n_quantiles)


def cvar_scores(quantiles: torch.Tensor, alpha: float) -> torch.Tensor:
    """Score each action by the mean of its lowest ``alpha`` fraction of quantiles.

    ``alpha=1.0`` averages every quantile and so reproduces the risk-neutral
    expected value; smaller alpha averages only the left tail, which is exactly
    CVaR at that level. This is the whole mechanism by which one trained network
    yields a family of policies at different risk appetites.
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    n_quantiles = quantiles.shape[-1]
    k = max(1, int(round(alpha * n_quantiles)))
    lowest, _ = torch.sort(quantiles, dim=-1)
    return lowest[..., :k].mean(dim=-1)


class QRDQNPolicy:
    """Greedy policy at a chosen risk level, in the baseline ``Policy`` interface."""

    def __init__(
        self,
        network: QuantileNetwork,
        normaliser: RunningNorm,
        alpha: float = 1.0,
        name: str | None = None,
    ):
        self.network = network
        self.normaliser = normaliser
        self.alpha = alpha
        self.name = name or (
            "qrdqn-risk-neutral" if alpha >= 1.0 else f"qrdqn-cvar{alpha:.2f}"
        )

    def reset(self) -> None:
        pass

    def __call__(self, day: int, observation: np.ndarray) -> int:
        obs = self.normaliser(observation)
        with torch.no_grad():
            quantiles = self.network(torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0))
            return int(torch.argmax(cvar_scores(quantiles, self.alpha), dim=1).item())


@dataclass
class ReplayBuffer:
    capacity: int
    obs_dim: int
    obs: np.ndarray = field(init=False)
    next_obs: np.ndarray = field(init=False)
    actions: np.ndarray = field(init=False)
    rewards: np.ndarray = field(init=False)
    dones: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.obs = np.zeros((self.capacity, self.obs_dim), dtype=np.float32)
        self.next_obs = np.zeros((self.capacity, self.obs_dim), dtype=np.float32)
        self.actions = np.zeros(self.capacity, dtype=np.int64)
        self.rewards = np.zeros(self.capacity, dtype=np.float32)
        self.dones = np.zeros(self.capacity, dtype=np.float32)
        self._index = 0
        self._size = 0

    def add(self, obs, action, reward, next_obs, done) -> None:
        i = self._index
        self.obs[i] = obs
        self.actions[i] = action
        self.rewards[i] = reward
        self.next_obs[i] = next_obs
        self.dones[i] = done
        self._index = (i + 1) % self.capacity
        self._size = min(self._size + 1, self.capacity)

    def __len__(self) -> int:
        return self._size

    def sample(self, batch_size: int, rng: np.random.Generator) -> tuple:
        idx = rng.integers(0, self._size, size=batch_size)
        return (
            torch.as_tensor(self.obs[idx]),
            torch.as_tensor(self.actions[idx]),
            torch.as_tensor(self.rewards[idx]),
            torch.as_tensor(self.next_obs[idx]),
            torch.as_tensor(self.dones[idx]),
        )


def quantile_huber_loss(
    predicted: torch.Tensor, target: torch.Tensor, taus: torch.Tensor, kappa: float
) -> torch.Tensor:
    """Quantile Huber loss between predicted and target quantiles."""
    # predicted (batch, n_quantiles, 1) vs target (batch, 1, n_target)
    diff = target.unsqueeze(1) - predicted.unsqueeze(2)
    huber = torch.where(
        diff.abs() <= kappa, 0.5 * diff.pow(2), kappa * (diff.abs() - 0.5 * kappa)
    )
    weight = (taus.view(1, -1, 1) - (diff.detach() < 0).float()).abs()
    return (weight * huber / kappa).sum(dim=1).mean()


def train(
    env_config: EnvConfig,
    config: QRDQNConfig | None = None,
    *,
    seed: int = 0,
    progress: bool = True,
    wrapper=None,
) -> tuple[QuantileNetwork, RunningNorm]:
    """Train QR-DQN and return the network plus its observation normaliser."""
    config = config or QRDQNConfig()
    torch.set_num_threads(config.torch_threads)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)

    env = RimalCleaningEnv(env_config)
    if wrapper is not None:
        env = wrapper(env)
    env = gym.wrappers.RecordEpisodeStatistics(env)

    obs_dim = int(np.prod(env.observation_space.shape))
    n_actions = int(env.action_space.n)

    normaliser = RunningNorm((obs_dim,))
    online = QuantileNetwork(obs_dim, n_actions, config.n_quantiles, config.hidden_size)
    target = QuantileNetwork(obs_dim, n_actions, config.n_quantiles, config.hidden_size)
    target.load_state_dict(online.state_dict())
    optimizer = torch.optim.Adam(online.parameters(), lr=config.learning_rate)

    # Midpoint quantile fractions.
    taus = (torch.arange(config.n_quantiles, dtype=torch.float32) + 0.5) / config.n_quantiles

    buffer = ReplayBuffer(config.buffer_size, obs_dim)
    raw_obs, _ = env.reset(seed=seed)
    normaliser.update(raw_obs.reshape(1, -1))
    obs = normaliser(raw_obs)

    anneal_steps = max(1, int(config.exploration_fraction * config.total_timesteps))

    for step in range(config.total_timesteps):
        epsilon = max(
            config.end_epsilon,
            config.start_epsilon
            + (config.end_epsilon - config.start_epsilon) * step / anneal_steps,
        )
        if rng.random() < epsilon:
            action = int(rng.integers(n_actions))
        else:
            with torch.no_grad():
                q = online(torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0))
                action = int(torch.argmax(cvar_scores(q, 1.0), dim=1).item())

        raw_next, reward, terminated, truncated, _ = env.step(action)
        normaliser.update(raw_next.reshape(1, -1))
        next_obs = normaliser(raw_next)
        done = terminated or truncated

        buffer.add(obs, action, reward * config.reward_scale, next_obs, float(terminated))
        obs = next_obs
        if done:
            raw_obs, _ = env.reset()
            obs = normaliser(raw_obs)

        if len(buffer) >= config.learning_starts and step % config.train_frequency == 0:
            b_obs, b_actions, b_rewards, b_next, b_dones = buffer.sample(
                config.batch_size, rng
            )
            with torch.no_grad():
                next_quantiles = target(b_next)
                best = torch.argmax(cvar_scores(next_quantiles, 1.0), dim=1)
                next_selected = next_quantiles[torch.arange(len(best)), best]
                target_quantiles = (
                    b_rewards.unsqueeze(1)
                    + config.gamma * (1.0 - b_dones).unsqueeze(1) * next_selected
                )

            predicted = online(b_obs)[torch.arange(config.batch_size), b_actions]
            loss = quantile_huber_loss(predicted, target_quantiles, taus, config.kappa)

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(online.parameters(), 10.0)
            optimizer.step()

        if step % config.target_update_frequency == 0:
            target.load_state_dict(online.state_dict())

        if progress and step % max(1, config.total_timesteps // 5) == 0:
            print(f"      step {step:>8,}  epsilon {epsilon:.3f}")

    env.close()
    return online, normaliser
