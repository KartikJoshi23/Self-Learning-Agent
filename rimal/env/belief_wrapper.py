"""Give a memoryless agent a sufficient statistic instead of a raw reading.

A feed-forward policy sees one observation at a time. Under
``observability="noisy"`` that single reading carries a per-day signal-to-noise
ratio below one, so no memoryless policy can do well on it however it is
trained -- the information simply is not in the input.

There are two standard remedies. Give the policy memory (a recurrent network),
or give it a **belief state**: run a filter outside the policy and feed it the
posterior, which for a linear-Gaussian system is a sufficient statistic for the
whole observation history. This wrapper does the second. It is the cheaper of
the two on a CPU budget, and the resulting agent is far easier to inspect --
you can plot what it believes and check that belief against the truth, which a
hidden LSTM state does not permit.

The wrapper uses only what an operator has: the reading, the day's noise scale,
observed rainfall, and the action the agent just took.
"""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np

from rimal.config import SOILING
from rimal.env.cleaning_env import ACTION_CLEAN
from rimal.env.observation import (
    NOISE_SCALE,
    OBS_NOISE_SCALED,
    OBS_RAIN_SCALED,
    OBS_REPORTED_RATIO,
    RAIN_SCALE,
    SoilingKalmanFilter,
)


class BeliefStateWrapper(gym.ObservationWrapper):
    """Replace the noisy reading with a Kalman posterior, and expose its spread.

    The observation keeps its layout; slot 0 becomes the filtered estimate
    rather than the raw reading, and one dimension is appended carrying the
    posterior standard deviation, so the policy knows how much to trust it.
    """

    def __init__(
        self,
        env: gym.Env,
        assumed_rate: float = SOILING.rate_mid_per_day,
        process_std: float = 0.0008,
        rain_reset_mm: float = 6.0,
    ):
        super().__init__(env)
        if env.observation_space.shape[0] < 9:
            raise ValueError("BeliefStateWrapper requires the noisy observation")

        self.assumed_rate = assumed_rate
        self.rain_reset_mm = rain_reset_mm
        self.filter = SoilingKalmanFilter(process_std=process_std)
        self._cleaned_last_step = False
        self._rain_last_step = 0.0
        self._step = 0

        low = np.concatenate([env.observation_space.low, [0.0]])
        high = np.concatenate([env.observation_space.high, [1.0]])
        self.observation_space = gym.spaces.Box(low=low, high=high, dtype=np.float32)

    def reset(self, **kwargs) -> tuple[np.ndarray, dict[str, Any]]:
        self.filter.reset()
        self._cleaned_last_step = False
        self._rain_last_step = 0.0
        self._step = 0
        return super().reset(**kwargs)

    def step(self, action):
        self._cleaned_last_step = int(action) == ACTION_CLEAN
        observation, reward, terminated, truncated, info = self.env.step(action)
        self._step += 1
        info["believed_ratio"] = self.filter.believed_ratio
        return self.observation(observation), reward, terminated, truncated, info

    def observation(self, observation: np.ndarray) -> np.ndarray:
        reported = float(observation[OBS_REPORTED_RATIO])
        rain_mm = float(observation[OBS_RAIN_SCALED]) * RAIN_SCALE
        noise_std = float(observation[OBS_NOISE_SCALED]) * NOISE_SCALE

        # The environment applies a day's rain to the FOLLOWING day's soiling,
        # so the filter must react to yesterday's rain, not today's. Resetting
        # on today's reading runs the belief one day ahead of the truth.
        if self._rain_last_step > self.rain_reset_mm:
            self.filter.on_reset_event(grace=True)
        elif self._cleaned_last_step:
            self.filter.on_reset_event(grace=False)
        elif self._step > 0:
            self.filter.predict(self.assumed_rate)
        self._rain_last_step = rain_mm

        self.filter.update(reported, max(noise_std, 1e-3))

        out = np.concatenate(
            [observation, [min(np.sqrt(self.filter.var) / NOISE_SCALE, 1.0)]]
        ).astype(np.float32)
        out[OBS_REPORTED_RATIO] = np.float32(self.filter.believed_ratio)
        return out
