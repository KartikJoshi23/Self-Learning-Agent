"""PPO for the cleaning environment, in the CleanRL single-file style.

Deliberately one readable file rather than a framework: the whole algorithm is
inspectable in one screen-scroll, which is the point of a portfolio artefact
and also makes it obvious that nothing is hidden in a config.

PPO is used rather than SAC for two reasons. It is the algorithm the nearest
prior work (An, arXiv:2603.07518) selected after finding SAC unstable on this
problem, so using it keeps the comparison honest. And the action space is
discrete, where PPO is the natural fit.

Two departures from that prior work matter here. It used a **sparse reward,
paid once per 20-year episode**, and diagnosed that as a cause of SAC's
instability; RIMAL pays a dense daily reward. And it trained on synthetic
weather drawn independently from fitted monthly distributions, whereas this
trains on measured years and evaluates on **held-out** years, so the reported
number is generalisation rather than fit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gymnasium as gym
import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical

from rimal.env import EnvConfig, RimalCleaningEnv


@dataclass
class PPOConfig:
    """Hyperparameters. Defaults are CleanRL's, with three deliberate changes.

    ``gamma`` is 0.999 rather than 0.99: an episode is one year of daily steps
    and the objective is the undiscounted annual total, so a 100-day effective
    horizon would systematically undervalue the back half of the year.

    ``reward_scale`` multiplies the reward before it reaches the optimiser.
    With the environment's ``negative_cost`` reward a daily value is order
    -$2.50, rising to order -$60 on a cleaning day; this brings the episode
    return into a range the value head fits comfortably. It rescales only the
    learning signal -- every reported number is computed from the environment's
    own ``info``, never from the reward.

    ``ent_coef`` is *below* CleanRL's 0.01 default. Cleaning is the right
    action on roughly 3% of days, and an entropy bonus pushes a binary policy
    toward P=0.5; too much of it and the agent settles on a constant cleaning
    probability instead of a state-dependent rule.
    """

    total_timesteps: int = 1_500_000
    num_envs: int = 8
    num_steps: int = 256
    learning_rate: float = 3e-4
    anneal_lr: bool = True
    gamma: float = 0.999
    gae_lambda: float = 0.95
    num_minibatches: int = 4
    update_epochs: int = 4
    clip_coef: float = 0.2
    ent_coef: float = 0.001
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    reward_scale: float = 5e-2
    hidden_size: int = 64
    torch_threads: int = 4

    @property
    def batch_size(self) -> int:
        return self.num_envs * self.num_steps

    @property
    def minibatch_size(self) -> int:
        return self.batch_size // self.num_minibatches


def layer_init(layer: nn.Linear, std: float = np.sqrt(2), bias: float = 0.0) -> nn.Linear:
    """Orthogonal initialisation, as in the PPO reference implementations."""
    nn.init.orthogonal_(layer.weight, std)
    nn.init.constant_(layer.bias, bias)
    return layer


class ActorCritic(nn.Module):
    """Two-layer MLP actor and critic with separate trunks."""

    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 64):
        super().__init__()
        self.critic = nn.Sequential(
            layer_init(nn.Linear(obs_dim, hidden)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden, hidden)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden, 1), std=1.0),
        )
        self.actor = nn.Sequential(
            layer_init(nn.Linear(obs_dim, hidden)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden, hidden)),
            nn.Tanh(),
            # Small final-layer gain keeps the initial policy near-uniform
            # rather than committing to one action before it has learned.
            layer_init(nn.Linear(hidden, n_actions), std=0.01),
        )

    def value(self, x: torch.Tensor) -> torch.Tensor:
        return self.critic(x).squeeze(-1)

    def action_and_value(
        self, x: torch.Tensor, action: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        logits = self.actor(x)
        distribution = Categorical(logits=logits)
        if action is None:
            action = distribution.sample()
        return (
            action,
            distribution.log_prob(action),
            distribution.entropy(),
            self.value(x),
        )


class RunningNorm:
    """Running mean/variance for observation standardisation.

    The raw observation is badly scaled for a tanh network: the soiling ratio
    lives in [0.70, 1.00], a narrow band near 1.0, so the very feature the
    policy must threshold on arrives with almost no dynamic range. Standardising
    each dimension gives it comparable resolution to the rest.
    """

    def __init__(self, shape: tuple[int, ...], epsilon: float = 1e-4):
        self.mean = np.zeros(shape, dtype=np.float64)
        self.var = np.ones(shape, dtype=np.float64)
        self.count = epsilon

    def update(self, batch: np.ndarray) -> None:
        batch_mean = batch.mean(axis=0)
        batch_var = batch.var(axis=0)
        batch_count = batch.shape[0]

        delta = batch_mean - self.mean
        total = self.count + batch_count
        self.mean += delta * batch_count / total
        m_a = self.var * self.count
        m_b = batch_var * batch_count
        self.var = (m_a + m_b + delta**2 * self.count * batch_count / total) / total
        self.count = total

    def __call__(self, observation: np.ndarray) -> np.ndarray:
        return (observation - self.mean) / np.sqrt(self.var + 1e-8)


class PPOPolicy:
    """Wraps a trained network in the baseline ``Policy`` interface.

    Acts greedily -- the evaluation number must reflect the policy the agent has
    actually learned, not a lucky sample from it. A stochastic policy that
    cleans with constant probability can post a decent return while having
    learned no rule at all; greedy evaluation exposes that immediately.
    """

    def __init__(
        self, network: ActorCritic, normaliser: "RunningNorm | None" = None, name: str = "ppo"
    ):
        self.network = network
        self.normaliser = normaliser
        self.name = name

    def reset(self) -> None:
        pass

    def __call__(self, day: int, observation: np.ndarray) -> int:
        obs = observation if self.normaliser is None else self.normaliser(observation)
        with torch.no_grad():
            logits = self.network.actor(torch.as_tensor(obs, dtype=torch.float32))
            return int(torch.argmax(logits).item())


def make_env(env_config: EnvConfig, seed: int, index: int, wrapper=None):
    """Build one environment, optionally wrapped.

    ``wrapper`` is applied before the statistics recorder so that a wrapper
    which alters the observation (e.g. ``BeliefStateWrapper``) is part of what
    the policy sees, while episode returns stay those of the raw environment.
    """

    def thunk():
        env = RimalCleaningEnv(env_config)
        if wrapper is not None:
            env = wrapper(env)
        env = gym.wrappers.RecordEpisodeStatistics(env)
        env.action_space.seed(seed + index)
        return env

    return thunk


@dataclass
class TrainingLog:
    updates: list[int] = field(default_factory=list)
    timesteps: list[int] = field(default_factory=list)
    episode_return: list[float] = field(default_factory=list)


def train(
    env_config: EnvConfig,
    config: PPOConfig | None = None,
    *,
    seed: int = 0,
    progress: bool = True,
    wrapper=None,
) -> tuple[ActorCritic, RunningNorm, TrainingLog]:
    """Train PPO and return the network, its observation normaliser and a log."""
    config = config or PPOConfig()

    torch.set_num_threads(config.torch_threads)
    np.random.seed(seed)
    torch.manual_seed(seed)

    envs = gym.vector.SyncVectorEnv(
        [make_env(env_config, seed, i, wrapper) for i in range(config.num_envs)]
    )
    obs_dim = int(np.prod(envs.single_observation_space.shape))
    n_actions = int(envs.single_action_space.n)

    normaliser = RunningNorm((obs_dim,))
    agent = ActorCritic(obs_dim, n_actions, config.hidden_size)
    optimizer = torch.optim.Adam(agent.parameters(), lr=config.learning_rate, eps=1e-5)

    obs_buf = torch.zeros((config.num_steps, config.num_envs, obs_dim))
    act_buf = torch.zeros((config.num_steps, config.num_envs), dtype=torch.long)
    logp_buf = torch.zeros((config.num_steps, config.num_envs))
    rew_buf = torch.zeros((config.num_steps, config.num_envs))
    done_buf = torch.zeros((config.num_steps, config.num_envs))
    val_buf = torch.zeros((config.num_steps, config.num_envs))

    next_obs_np, _ = envs.reset(seed=seed)
    normaliser.update(next_obs_np)
    next_obs = torch.as_tensor(normaliser(next_obs_np), dtype=torch.float32)
    next_done = torch.zeros(config.num_envs)

    log = TrainingLog()
    num_updates = config.total_timesteps // config.batch_size
    global_step = 0
    recent: list[float] = []

    for update in range(1, num_updates + 1):
        if config.anneal_lr:
            frac = 1.0 - (update - 1.0) / num_updates
            optimizer.param_groups[0]["lr"] = frac * config.learning_rate

        for step in range(config.num_steps):
            global_step += config.num_envs
            obs_buf[step] = next_obs
            done_buf[step] = next_done

            with torch.no_grad():
                action, logprob, _, value = agent.action_and_value(next_obs)
            act_buf[step] = action
            logp_buf[step] = logprob
            val_buf[step] = value

            next_obs_np, reward, terminations, truncations, infos = envs.step(
                action.numpy()
            )
            done = np.logical_or(terminations, truncations)
            rew_buf[step] = torch.as_tensor(reward, dtype=torch.float32) * config.reward_scale
            normaliser.update(next_obs_np)
            next_obs = torch.as_tensor(normaliser(next_obs_np), dtype=torch.float32)
            next_done = torch.as_tensor(done, dtype=torch.float32)

            if "episode" in infos:
                finished = infos["_episode"] if "_episode" in infos else done
                returns = np.asarray(infos["episode"]["r"])[np.asarray(finished, dtype=bool)]
                recent.extend(float(r) for r in np.atleast_1d(returns))

        with torch.no_grad():
            next_value = agent.value(next_obs)
            advantages = torch.zeros_like(rew_buf)
            last_gae = 0.0
            for t in reversed(range(config.num_steps)):
                if t == config.num_steps - 1:
                    next_nonterminal = 1.0 - next_done
                    next_values = next_value
                else:
                    next_nonterminal = 1.0 - done_buf[t + 1]
                    next_values = val_buf[t + 1]
                delta = (
                    rew_buf[t]
                    + config.gamma * next_values * next_nonterminal
                    - val_buf[t]
                )
                last_gae = (
                    delta
                    + config.gamma * config.gae_lambda * next_nonterminal * last_gae
                )
                advantages[t] = last_gae
            returns_buf = advantages + val_buf

        b_obs = obs_buf.reshape(-1, obs_dim)
        b_actions = act_buf.reshape(-1)
        b_logprobs = logp_buf.reshape(-1)
        b_advantages = advantages.reshape(-1)
        b_returns = returns_buf.reshape(-1)
        b_values = val_buf.reshape(-1)

        indices = np.arange(config.batch_size)
        for _ in range(config.update_epochs):
            np.random.shuffle(indices)
            for start in range(0, config.batch_size, config.minibatch_size):
                mb = indices[start : start + config.minibatch_size]

                _, newlogprob, entropy, newvalue = agent.action_and_value(
                    b_obs[mb], b_actions[mb]
                )
                logratio = newlogprob - b_logprobs[mb]
                ratio = logratio.exp()

                mb_adv = b_advantages[mb]
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)

                pg_loss = torch.max(
                    -mb_adv * ratio,
                    -mb_adv * torch.clamp(ratio, 1 - config.clip_coef, 1 + config.clip_coef),
                ).mean()

                v_clipped = b_values[mb] + torch.clamp(
                    newvalue - b_values[mb], -config.clip_coef, config.clip_coef
                )
                v_loss = 0.5 * torch.max(
                    (newvalue - b_returns[mb]) ** 2, (v_clipped - b_returns[mb]) ** 2
                ).mean()

                loss = pg_loss - config.ent_coef * entropy.mean() + config.vf_coef * v_loss

                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), config.max_grad_norm)
                optimizer.step()

        if recent:
            log.updates.append(update)
            log.timesteps.append(global_step)
            log.episode_return.append(float(np.mean(recent[-20:])))
            if progress and update % max(1, num_updates // 10) == 0:
                print(
                    f"      update {update:4d}/{num_updates}  "
                    f"step {global_step:>9,}  "
                    f"episode return {log.episode_return[-1]:>10,.0f}"
                )

    envs.close()
    return agent, normaliser, log
