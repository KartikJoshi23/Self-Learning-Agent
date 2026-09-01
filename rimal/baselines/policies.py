"""Rule-based cleaning policies.

These are the bar any learned agent has to clear. They are deliberately the
policies the industry and the literature actually use: clean on a fixed
calendar interval, or clean when measured performance drops past a threshold.

A policy is a callable object with a ``reset()``. It sees the same observation
the agent does, so no baseline gets information the agent lacks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rimal.env.cleaning_env import ACTION_CLEAN, ACTION_NOOP

#: Index of the soiling ratio in the v0 observation vector.
OBS_SOILING_RATIO = 0


class Policy:
    """Base class. Subclasses implement :meth:`act`."""

    name: str = "policy"

    def reset(self) -> None:
        """Clear any per-episode state."""

    def act(self, day: int, observation: np.ndarray) -> int:
        raise NotImplementedError

    def __call__(self, day: int, observation: np.ndarray) -> int:
        return self.act(day, observation)


class NeverClean(Policy):
    """Lower bound on cost, lower bound on energy."""

    name = "never-clean"

    def act(self, day: int, observation: np.ndarray) -> int:
        return ACTION_NOOP


class AlwaysClean(Policy):
    """Upper bound on energy, and on cost. Rarely economic."""

    name = "always-clean"

    def act(self, day: int, observation: np.ndarray) -> int:
        return ACTION_CLEAN


@dataclass
class FixedInterval(Policy):
    """Clean every ``interval_days``, the standard industry practice.

    The published optima this project is checked against are of this family:
    28 days as the commonly recommended interval for the UAE, and 34 days as
    the value reported optimal for Abu Dhabi.
    """

    interval_days: int = 30

    def __post_init__(self) -> None:
        if self.interval_days < 1:
            raise ValueError("interval_days must be >= 1")
        self.name = f"fixed-{self.interval_days}d"
        self._since = 0

    def reset(self) -> None:
        self._since = 0

    def act(self, day: int, observation: np.ndarray) -> int:
        if day == 0:
            self._since = 0
            return ACTION_NOOP
        self._since += 1
        if self._since >= self.interval_days:
            self._since = 0
            return ACTION_CLEAN
        return ACTION_NOOP


@dataclass
class SoilingThreshold(Policy):
    """Clean once the soiling ratio falls below ``threshold``.

    This is the condition-based policy DEWA's Autonomous Soiling Detector
    enables: it measures actual versus expected production and flags when the
    drop justifies a clean. In v0 the ratio is observed exactly; from M5 it
    will have to be inferred, which is where this baseline starts to struggle.
    """

    threshold: float = 0.95

    def __post_init__(self) -> None:
        if not 0.0 < self.threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        self.name = f"threshold-{self.threshold:.2f}"

    def act(self, day: int, observation: np.ndarray) -> int:
        ratio = float(observation[OBS_SOILING_RATIO])
        return ACTION_CLEAN if ratio < self.threshold else ACTION_NOOP


def standard_baselines() -> list[Policy]:
    """The comparison set used throughout the project."""
    return [
        NeverClean(),
        AlwaysClean(),
        FixedInterval(28),  # commonly recommended UAE interval
        FixedInterval(34),  # reported optimal for Abu Dhabi
        SoilingThreshold(0.97),
        SoilingThreshold(0.95),
        SoilingThreshold(0.93),  # the tuned optimum; see tune_threshold()
        SoilingThreshold(0.92),
    ]


def tune_threshold(
    evaluate_fn, candidates: np.ndarray | None = None
) -> SoilingThreshold:
    """Select the best soiling threshold on TRAINING data.

    This exists because of a mistake worth not repeating. M3 compared against a
    hand-picked grid of thresholds (0.97, 0.95, 0.92) and reported 0.95 as the
    bar. A fine sweep later showed the true optimum is **0.93**, worth about $50
    per MWp per year more -- roughly twice the entire margin PPO had appeared to
    win by. An under-tuned baseline does not make a learned agent look good; it
    makes the comparison worthless.

    ``evaluate_fn`` takes a policy and returns its mean net value on the
    *training* years, so the baseline is selected under exactly the protocol the
    learned agent gets: tuned on train, reported on held-out.
    """
    if candidates is None:
        candidates = np.round(np.arange(0.86, 0.995, 0.005), 3)

    scored = [(float(evaluate_fn(SoilingThreshold(float(t)))), float(t)) for t in candidates]
    best = max(scored)[1]
    policy = SoilingThreshold(best)
    policy.name = f"tuned-threshold-{best:.3f}"
    return policy


def tune_fixed_interval(evaluate_fn, candidates: range | None = None) -> FixedInterval:
    """Select the best fixed interval on TRAINING data, same protocol."""
    if candidates is None:
        candidates = range(15, 71)
    scored = [(float(evaluate_fn(FixedInterval(t))), t) for t in candidates]
    best = max(scored)[1]
    policy = FixedInterval(best)
    policy.name = f"tuned-fixed-{best}d"
    return policy
