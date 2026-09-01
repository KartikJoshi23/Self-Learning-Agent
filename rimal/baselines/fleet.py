"""Rule-based policies for the multi-robot, partially observed environment.

M5 ended with a warning worth acting on: three milestones in a row, a
model-based rule beat model-free deep RL, partly because the rules were good
and partly because the problems were simple. So M6's baselines are built to be
as strong as a competent engineer would make them, not as weak as would flatter
an agent.

``FleetHeuristic`` is that opponent. It combines everything the earlier
milestones established works:

* a Kalman filter for the latent soiling (M5);
* a threshold on the belief for *when* to clean (M3/M4);
* a per-robot efficacy estimate for *which* machine to dispatch;
* a service rule for *when* a machine has degraded enough to be worth fixing.

The efficacy estimate is the interesting part, and it is obtainable without
privileged information. The policy knows its own belief about soiling before it
cleans and after, so ``1 - loss_after / loss_before`` is a noisy per-clean
observation of that robot's realised efficacy. Averaging those over time is a
bandit estimator built from quantities an operator genuinely has.

If PPO cannot beat this, the honest conclusion is that the problem does not
need deep RL -- and that is the result, not a reason to weaken the baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from rimal.baselines.belief import (
    NOISE_SCALE,
    OBS_NOISE_SCALED,
    OBS_RAIN_SCALED,
    OBS_REPORTED_RATIO,
    RAIN_SCALE,
)
from rimal.baselines.policies import Policy
from rimal.config import SOILING
from rimal.env.observation import SoilingKalmanFilter
from rimal.env.robots import DEWA_FLEET, RobotSpec

ACTION_NOOP = 0

#: Fleet observation layout, appended after the 9 noisy base features:
#: days-since-service, uses-since-service, then cooldown-remaining, one per robot.
FLEET_OBS_START = 9


def cooldown_slice(n_robots: int) -> slice:
    start = FLEET_OBS_START + 2 * n_robots
    return slice(start, start + n_robots)


@dataclass
class FleetHeuristic(Policy):
    """Belief threshold for *when*, learned efficacy estimates for *which*.

    ``service_ratio`` is the fraction of a robot's initial observed efficacy
    below which it is sent for service. ``explore_uses`` is how many times each
    robot is tried before the policy starts exploiting -- without it the policy
    would lock onto whichever machine happened to look best on one noisy draw.
    """

    threshold: float = 0.93
    specs: tuple[RobotSpec, ...] = DEWA_FLEET
    service_ratio: float = 0.80
    explore_uses: int = 2
    assumed_rate: float = SOILING.rate_mid_per_day
    rain_reset_mm: float = 6.0
    #: Set False to ablate efficacy-aware dispatch: always pick robot 0.
    efficacy_aware: bool = True
    #: Set False to ablate servicing entirely.
    service_enabled: bool = True
    #: Prior spread on a robot's per-clean efficacy. ASSUMPTION.
    efficacy_uncertainty: float = 0.12
    #: Set True to ablate the central M6 claim: pretend cleaning is a PERFECT
    #: reset, exactly as every published formulation assumes (An's Eq. 4 sets
    #: soiling to zero). The policy then believes the panel is spotless after
    #: every dispatch, while the environment leaves 1-99% of the soiling
    #: behind. This is the assumption M6 exists to price.
    assume_perfect_cleaning: bool = False
    filter: SoilingKalmanFilter = field(init=False)

    def __post_init__(self) -> None:
        self.n = len(self.specs)
        suffix = "" if self.efficacy_aware else "-naive-dispatch"
        if not self.service_enabled:
            suffix += "-noservice"
        if self.assume_perfect_cleaning:
            suffix += "-assumes-perfect"
        self.name = f"fleet-heuristic-{self.threshold:.2f}{suffix}"
        self.filter = SoilingKalmanFilter()
        self.reset()

    def reset(self) -> None:
        self.filter.reset()
        self._cleaned_last_step = False
        self._rain_last_step = 0.0
        self._pending_robot: int | None = None
        self._loss_before = 0.0
        # Running mean of observed efficacy, and how many samples it holds.
        self._efficacy = np.array([s.nominal_efficacy for s in self.specs], dtype=float)
        self._samples = np.zeros(self.n, dtype=int)
        self._baseline = np.full(self.n, np.nan)

    # -- efficacy estimation ------------------------------------------------

    def _record_outcome(self) -> None:
        """Turn the belief before/after a clean into an efficacy sample."""
        index = self._pending_robot
        if index is None:
            return
        self._pending_robot = None
        if self._loss_before <= 1e-4:
            return  # cleaning an already-clean panel says nothing about efficacy

        observed = 1.0 - self.filter.loss / self._loss_before
        observed = float(np.clip(observed, 0.0, 1.0))

        self._samples[index] += 1
        weight = 1.0 / min(self._samples[index], 12)
        self._efficacy[index] += weight * (observed - self._efficacy[index])
        if np.isnan(self._baseline[index]) and self._samples[index] >= self.explore_uses:
            self._baseline[index] = self._efficacy[index]

    def _choose_robot(self, available: np.ndarray) -> int | None:
        """Pick among the machines that are not cooling down.

        Cooldown is what makes dispatch a real decision: the best machine is
        often unavailable, and the choice is between a weaker robot now and the
        strong one in a few days.
        """
        idle = np.flatnonzero(available)
        if idle.size == 0:
            return None
        if not self.efficacy_aware:
            return int(idle[0])
        untried = [i for i in idle if self._samples[i] < self.explore_uses]
        if untried:
            return int(untried[0])
        return int(idle[np.argmax(self._efficacy[idle])])

    def _robot_needing_service(self) -> int | None:
        if not self.service_enabled:
            return None
        for i in range(self.n):
            if np.isnan(self._baseline[i]):
                continue
            if self._efficacy[i] < self.service_ratio * self._baseline[i]:
                return i
        return None

    # -- policy -------------------------------------------------------------

    def act(self, day: int, observation: np.ndarray) -> int:
        reported = float(observation[OBS_REPORTED_RATIO])
        rain_mm = float(observation[OBS_RAIN_SCALED]) * RAIN_SCALE
        noise_std = float(observation[OBS_NOISE_SCALED]) * NOISE_SCALE

        if self._rain_last_step > self.rain_reset_mm:
            self.filter.on_reset_event(grace=True)
            self._pending_robot = None
        elif self._cleaned_last_step:
            # Partial clean: scale the belief by the robot's expected efficacy
            # and widen it. The measurement update then corrects it, and that
            # correction is the efficacy observation.
            index = self._pending_robot
            if self.assume_perfect_cleaning:
                self.filter.on_reset_event(grace=False)
            else:
                expected = self._efficacy[index] if index is not None else 0.9
                self.filter.apply_partial_clean(expected, self.efficacy_uncertainty)
            self.filter.predict(self.assumed_rate)
        elif day > 0:
            self.filter.predict(self.assumed_rate)
        self._rain_last_step = rain_mm

        self.filter.update(reported, max(noise_std, 1e-3))
        self._record_outcome()

        self._cleaned_last_step = False

        needing = self._robot_needing_service()
        if needing is not None:
            self._efficacy[needing] = self._baseline[needing]
            self._samples[needing] = max(self._samples[needing], self.explore_uses)
            return 1 + self.n + needing

        if self.filter.believed_ratio < self.threshold:
            available = observation[cooldown_slice(self.n)] <= 1e-6
            index = self._choose_robot(available)
            if index is not None:
                self._pending_robot = index
                self._loss_before = self.filter.loss
                self._cleaned_last_step = True
                return 1 + index

        return ACTION_NOOP

    @property
    def efficacy_estimates(self) -> np.ndarray:
        return self._efficacy.copy()


@dataclass
class RoundRobinFleet(Policy):
    """Belief threshold for *when*, round-robin for *which*.

    The policy an operator writes on day one: rotate the machines evenly, ignore
    how well each is working. It isolates the value of efficacy-aware dispatch.
    """

    threshold: float = 0.93
    n_robots: int = 5
    #: Mean nominal efficacy of the fleet, used to propagate the belief.
    assumed_efficacy: float = 0.85
    assumed_rate: float = SOILING.rate_mid_per_day
    rain_reset_mm: float = 6.0
    filter: SoilingKalmanFilter = field(init=False)

    def __post_init__(self) -> None:
        self.name = f"round-robin-{self.threshold:.2f}"
        self.filter = SoilingKalmanFilter()
        self.reset()

    def reset(self) -> None:
        self.filter.reset()
        self._next = 0
        self._cleaned_last_step = False
        self._rain_last_step = 0.0

    def act(self, day: int, observation: np.ndarray) -> int:
        reported = float(observation[OBS_REPORTED_RATIO])
        rain_mm = float(observation[OBS_RAIN_SCALED]) * RAIN_SCALE
        noise_std = float(observation[OBS_NOISE_SCALED]) * NOISE_SCALE

        if self._rain_last_step > self.rain_reset_mm:
            self.filter.on_reset_event(grace=True)
        elif self._cleaned_last_step:
            self.filter.apply_partial_clean(self.assumed_efficacy, 0.12)
            self.filter.predict(self.assumed_rate)
        elif day > 0:
            self.filter.predict(self.assumed_rate)
        self._rain_last_step = rain_mm

        self.filter.update(reported, max(noise_std, 1e-3))
        self._cleaned_last_step = False

        if self.filter.believed_ratio < self.threshold:
            available = observation[cooldown_slice(self.n_robots)] <= 1e-6
            for _ in range(self.n_robots):
                index = self._next
                self._next = (self._next + 1) % self.n_robots
                if available[index]:
                    self._cleaned_last_step = True
                    return 1 + index
        return ACTION_NOOP
