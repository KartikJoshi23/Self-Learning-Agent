"""Belief-tracking policies for the partially observed environment.

``SoilingThreshold`` reads the soiling slot of the observation and cleans when
it drops below a threshold. Under ``observability="exact"`` that slot is the
truth and the rule is near-optimal -- M4 showed it beating PPO. Under
``observability="noisy"`` the same rule reads a noisy estimate, and its
behaviour changes character: a single unlucky reading triggers a clean that was
not needed, and because cleaning is expensive relative to a day of soiling, the
chatter is costly.

``BeliefThreshold`` keeps the same decision rule but applies it to a Kalman
estimate of the latent soiling rather than to the raw reading. It uses only
what an operator has: the reading, the day's noise scale, observed rainfall,
and its own cleaning actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from rimal.baselines.policies import Policy
from rimal.config import SOILING
from rimal.env.cleaning_env import ACTION_CLEAN, ACTION_NOOP
from rimal.env.observation import (
    NOISE_SCALE,
    OBS_NOISE_SCALED,
    OBS_RAIN_SCALED,
    OBS_REPORTED_RATIO,
    RAIN_SCALE,
    SoilingKalmanFilter,
)


@dataclass
class BeliefThreshold(Policy):
    """Kalman-filter the noisy reading, then threshold the belief.

    ``assumed_rate`` is the soiling rate the filter propagates between
    readings. It is a modelling assumption, not privileged information: the
    midpoint of DEWA's published 0.14-0.33 %/day band is exactly what an
    operator would use.
    """

    threshold: float = 0.93
    assumed_rate: float = SOILING.rate_mid_per_day
    process_std: float = 0.0008
    rain_reset_mm: float = 6.0
    filter: SoilingKalmanFilter = field(init=False)

    def __post_init__(self) -> None:
        if not 0.0 < self.threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        self.name = f"belief-threshold-{self.threshold:.3f}"
        self.filter = SoilingKalmanFilter(process_std=self.process_std)
        self._cleaned_last_step = False

    def reset(self) -> None:
        self.filter.reset()
        self._cleaned_last_step = False
        self._rain_last_step = 0.0
        self._rain_last_step = 0.0

    def act(self, day: int, observation: np.ndarray) -> int:
        reported = float(observation[OBS_REPORTED_RATIO])
        rain_mm = float(observation[OBS_RAIN_SCALED]) * RAIN_SCALE
        noise_std = float(observation[OBS_NOISE_SCALED]) * NOISE_SCALE

        # A cleaning or a heavy wash is a known event: the panel is clean.
        # The environment applies a day's rain to the FOLLOWING day's soiling,
        # so the filter must react to yesterday's rain, not today's. Resetting
        # on today's reading runs the belief one day ahead of the truth.
        if self._rain_last_step > self.rain_reset_mm:
            self.filter.on_reset_event(grace=True)
        elif self._cleaned_last_step:
            self.filter.on_reset_event(grace=False)
        elif day > 0:
            self.filter.predict(self.assumed_rate)
        self._rain_last_step = rain_mm

        self.filter.update(reported, max(noise_std, 1e-3))

        clean = self.filter.believed_ratio < self.threshold
        self._cleaned_last_step = clean
        return ACTION_CLEAN if clean else ACTION_NOOP

    @property
    def believed_ratio(self) -> float:
        return self.filter.believed_ratio


@dataclass
class ScheduleAwareThreshold(Policy):
    """A cheaper alternative to filtering: never clean twice in quick succession.

    Included so the comparison is fair. Much of a naive threshold's loss under
    noise is chatter -- repeated cleans triggered by consecutive unlucky
    readings -- and a plant operator would impose a minimum interval long before
    reaching for a Kalman filter. If this simple guard recovers most of the gap,
    the filter has to justify itself against *it*, not against the naive rule.
    """

    threshold: float = 0.93
    min_days_between_cleans: int = 7

    def __post_init__(self) -> None:
        self.name = f"guarded-threshold-{self.threshold:.3f}"
        self._since = 10_000

    def reset(self) -> None:
        self._since = 10_000

    def act(self, day: int, observation: np.ndarray) -> int:
        self._since += 1
        if float(observation[OBS_REPORTED_RATIO]) < self.threshold and (
            self._since >= self.min_days_between_cleans
        ):
            self._since = 0
            return ACTION_CLEAN
        return ACTION_NOOP
