"""RIMAL cleaning environment, version 0.

A daily-step Gymnasium environment: each day the agent decides whether to clean
a PV plant. Version 0 is deliberately the *simple* case -- soiling is fully
observable and cleaning restores the panel completely -- so that it matches the
formulation used in the published literature and can be compared against it
directly. Later milestones relax exactly those assumptions.

Comparison with the nearest prior work, An (2026, arXiv:2603.07518), which
applies PPO/SAC to PV cleaning in Abu Dhabi:

===================  ==================================  =========================
Element              An (2026)                           RIMAL v0
===================  ==================================  =========================
State                deposition, days since cleaning,    same information, plus
                     temperature, wind speed, PM,        AOD and a seasonal
                     irradiance                          encoding
Action               binary clean / no-clean             same (kept for parity)
Cleaning effect      soiling reset to exactly 0          same in v0; stochastic
                                                         and per-machine from M6
Soiling observable   yes, directly in the state          yes in v0; latent from M5
Weather              synthetic draws from fitted         10 years of measured
                     monthly distributions               NASA POWER data
Reward               sparse, once per 20-year episode    dense, daily
Evaluation           same distribution as training       held-out calendar years
===================  ==================================  =========================

Two of those differences are deliberate corrections rather than mere choices.
An reports that SAC destabilised partly because "the reward function in our
problem has very sparse rewards since we only get rewards after an episode of
20 years"; a dense daily reward removes that pathology. An also samples weather
independently from fitted monthly distributions, which cannot reproduce
autocorrelation or multi-day dust events -- and separately reports that the
learned policy gives "suboptimal policies when faced with rare or extreme
conditions". Training on real measured series preserves those events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from rimal.config import MBR_SOLAR_PARK, SOILING, Site
from rimal.data import power
from rimal.env.energy_table import EnergyLookup, build_energy_table
from rimal.env.observation import ObservationNoise
from rimal.physics.soiling import AodModulatedSoiling, KimberSoiling

ACTION_NOOP = 0
ACTION_CLEAN = 1


@dataclass
class Economics:
    """Money. Both values are assumptions and are swept for sensitivity in M3.

    ``energy_price_usd_per_kwh`` is the Mohammed bin Rashid Al Maktoum Solar
    Park phase-5 PPA tariff of 1.6953 US cents/kWh -- the actual contracted
    value of a kWh at this site, which is the right price for energy the plant
    fails to deliver because of soiling.

    ``cleaning_cost_usd_per_mwp`` is the cost of one full-plant cleaning pass
    per MWp installed. It is **calibrated, not measured**: M3 swept it and found
    that $50/MWp puts the optimal fixed interval at 27 days and $75/MWp puts it
    at 34 days, bracketing the two published values this project is checked
    against (28 days commonly recommended for the UAE, 34 days reported optimal
    for Abu Dhabi). The default is the midpoint of that range.

    That calibration is at least self-consistent in absolute terms: 1 MWp is
    roughly 2,105 modules at DEWA's measured 445-505 W rating, so $60/MWp is
    about 3 US cents per module per clean -- the right order for the autonomous
    dry robots DEWA is trialling, though low for manual wet crews.

    The optimal interval depends only on the ratio of these two numbers, so
    both are swept in ``scripts/m3_verify.py`` rather than trusted.
    """

    energy_price_usd_per_kwh: float = 0.016953
    cleaning_cost_usd_per_mwp: float = 60.0


@dataclass
class EnvConfig:
    years: tuple[int, ...] = (2016, 2017, 2018, 2019, 2020, 2021, 2022)
    site: Site = MBR_SOLAR_PARK
    soiling_model: str = "kimber"  # or "aod"
    economics: Economics = field(default_factory=Economics)
    #: Nameplate capacity; the energy table is built for 1 MWp so costs and
    #: revenues are both per-MWp and the ratio is what matters.
    capacity_mwp: float = 1.0
    #: Days of history the agent is told about. Only used for normalisation.
    max_days_since_cleaning: int = 365
    #: What ``step()`` returns as reward. Both share the same optimal policy.
    #:
    #: ``"net_value"`` -- revenue minus cleaning cost. The reportable quantity,
    #: and the natural definition, but a poor *learning* signal: daily revenue
    #: is order $80 no matter what the agent does, while the action-dependent
    #: part is order $2.50 of avoided soiling loss. The constant drowns the
    #: policy gradient, and PPO trained on it learns a near-constant cleaning
    #: probability rather than a state-dependent rule (measured: P(clean)
    #: moved only 0.036 -> 0.048 across the entire soiling range).
    #:
    #: ``"negative_cost"`` -- minus (soiling loss + cleaning cost). This
    #: subtracts the clean-plant energy of the day, which depends on the day
    #: but *not* on the action, so it is a state-dependent baseline: the
    #: optimal policy is unchanged and only the variance falls. It is also the
    #: objective the literature actually minimises.
    #:
    #: Reported metrics are computed from ``info``, never from the reward, so
    #: this choice cannot flatter the numbers.
    reward_mode: str = "negative_cost"

    #: What the agent can see of the soiling state (M5 onwards).
    #:
    #: ``"exact"`` -- the true soiling ratio, as in v0. A 7-dimensional
    #: observation. Kept unchanged so the M4 result stays reproducible.
    #:
    #: ``"noisy"`` -- a noisy performance-ratio estimate in place of the truth,
    #: plus two dimensions an operator genuinely has and a filter needs: the
    #: day's observed rainfall (which drives natural washing) and the noise
    #: scale implied by the day's irradiance. 9-dimensional.
    #:
    #: The truth is still reported in ``info["soiling_ratio"]`` for scoring and
    #: for measuring belief error -- it is simply not visible to the policy.
    observability: str = "exact"
    #: Noise model used when ``observability == "noisy"``.
    observation_noise: ObservationNoise = field(default_factory=ObservationNoise)


class RimalCleaningEnv(gym.Env):
    """Decide daily whether to clean a desert PV plant.

    Observation (all scaled to roughly [-1, 1] or [0, 1]):

    ==  =========================================================
    0   soiling ratio, 1.0 = clean
    1   days since last cleaning / max_days_since_cleaning
    2   today's aerosol optical depth, scaled
    3   today's mean air temperature, scaled
    4   today's mean wind speed, scaled
    5   sin(day of year)
    6   cos(day of year)
    ==  =========================================================

    Action: ``0`` do nothing, ``1`` clean.

    Reward (USD per MWp per day)::

        energy_kwh(soiling_ratio) * energy_price  -  cleaning_cost if cleaned

    An episode is one calendar year drawn from ``config.years``.
    """

    metadata = {"render_modes": []}

    #: Scale factors chosen so observations sit near unit range; AOD and wind
    #: maxima come from the measured record.
    AOD_SCALE = 3.5
    TEMP_SCALE = 50.0
    WIND_SCALE = 12.0

    def __init__(self, config: EnvConfig | None = None):
        super().__init__()
        self.config = config or EnvConfig()
        if not self.config.years:
            raise ValueError("config.years must not be empty")

        start, end = min(self.config.years), max(self.config.years)
        hourly = power.fetch_years(start, end, self.config.site)
        self._daily = power.daily_summary(hourly, self.config.site)
        self._lookup = EnergyLookup(
            build_energy_table(start, end, site=self.config.site)
        )

        self._model = (
            KimberSoiling()
            if self.config.soiling_model == "kimber"
            else AodModulatedSoiling()
        )
        if self.config.soiling_model not in ("kimber", "aod"):
            raise ValueError(f"unknown soiling_model {self.config.soiling_model!r}")
        if self.config.reward_mode not in ("net_value", "negative_cost"):
            raise ValueError(f"unknown reward_mode {self.config.reward_mode!r}")
        if self.config.observability not in ("exact", "noisy"):
            raise ValueError(f"unknown observability {self.config.observability!r}")

        # Daily accumulation rates and rain, precomputed once.
        self._rate = self._model.daily_rate(self._daily).to_numpy(dtype=float)
        self._rain = self._daily["PRECTOTCORR"].to_numpy(dtype=float)
        self._aod = self._daily["AOD_55"].to_numpy(dtype=float)
        self._temp = self._daily["T2M"].to_numpy(dtype=float)
        self._wind = self._daily["WS2M"].to_numpy(dtype=float)
        self._doy = self._daily.index.dayofyear.to_numpy()
        self._year = self._daily.index.year.to_numpy()

        self._episode_starts = {
            year: np.flatnonzero(self._year == year) for year in self.config.years
        }
        for year, rows in self._episode_starts.items():
            if rows.size == 0:
                raise ValueError(f"no data for requested year {year}")

        self.noisy = self.config.observability == "noisy"
        #: Reference irradiance for the heteroscedastic noise scale: the median
        #: clean-plant day, so a typical day carries roughly ``base_std``.
        self._reference_kwh = float(np.median(self._lookup.values[:, -1]))

        self.action_space = spaces.Discrete(2)
        low = [0.0, 0.0, 0.0, -1.0, 0.0, -1.0, -1.0]
        high = [1.3, 2.0, 2.0, 2.0, 2.0, 1.0, 1.0]
        if self.noisy:
            low += [0.0, 0.0]          # observed rainfall, noise scale
            high += [5.0, 1.0]
        self.observation_space = spaces.Box(
            low=np.array(low, dtype=np.float32),
            high=np.array(high, dtype=np.float32),
            dtype=np.float32,
        )

        self._rows: np.ndarray | None = None
        self._step_in_episode = 0
        self._soiling_loss = 0.0
        self._days_since_cleaning = 0
        self._grace_remaining = 0
        self._last_observed_ratio = 1.0
        self._last_observation_std = 0.0
        self._obs_rng = np.random.default_rng(0)

    # -- gymnasium API ---------------------------------------------------

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)

        year = (options or {}).get("year")
        if year is None:
            year = int(self.np_random.choice(np.asarray(self.config.years)))
        elif year not in self._episode_starts:
            raise ValueError(f"year {year} is not in config.years")

        self._rows = self._episode_starts[year]
        self._obs_rng = np.random.default_rng(self.np_random.integers(0, 2**31 - 1))
        self._step_in_episode = 0
        self._soiling_loss = 0.0
        self._days_since_cleaning = 0
        self._grace_remaining = 0
        self._episode_year = year

        return self._observation(), {"year": year}

    def step(
        self, action: int
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._rows is None:
            raise RuntimeError("reset() must be called before step()")
        action = int(action)
        if action not in (ACTION_NOOP, ACTION_CLEAN):
            raise ValueError(f"invalid action {action}")

        row = self._rows[self._step_in_episode]
        economics = self.config.economics

        # The agent's decision applies to today, before today's accumulation.
        cleaned = action == ACTION_CLEAN
        if cleaned:
            self._soiling_loss = 0.0
            self._days_since_cleaning = 0
        else:
            self._days_since_cleaning += 1

        soiling_ratio = 1.0 - self._soiling_loss
        energy_kwh = self._lookup.energy_kwh(row, soiling_ratio) * self.config.capacity_mwp
        revenue = energy_kwh * economics.energy_price_usd_per_kwh
        cost = (
            economics.cleaning_cost_usd_per_mwp * self.config.capacity_mwp
            if cleaned
            else 0.0
        )
        clean_energy = self._lookup.clean_energy_kwh(row) * self.config.capacity_mwp
        if self.config.reward_mode == "net_value":
            reward = revenue - cost
        else:
            soiling_loss_usd = (
                clean_energy - energy_kwh
            ) * economics.energy_price_usd_per_kwh
            reward = -(soiling_loss_usd + cost)

        info = {
            "energy_kwh": energy_kwh,
            "clean_energy_kwh": clean_energy,
            "soiling_ratio": soiling_ratio,
            "revenue_usd": revenue,
            "cleaning_cost_usd": cost,
            "cleaned": cleaned,
            "date": self._daily.index[row],
            "rain_mm": float(self._rain[row]),
            "soiling_rate": float(self._rate[row]),
            "rain_reset": bool(self._rain[row] > self._model.cleaning_threshold_mm),
            "observed_ratio": self._last_observed_ratio,
            "observation_std": self._last_observation_std,
        }

        # Advance soiling into tomorrow, applying rain the same way the
        # standalone soiling models do so the two agree exactly.
        self._advance_soiling(row)

        self._step_in_episode += 1
        terminated = self._step_in_episode >= len(self._rows)
        observation = (
            self._observation()
            if not terminated
            else np.zeros(self.observation_space.shape, dtype=np.float32)
        )
        return observation, float(reward), terminated, False, info

    # -- internals -------------------------------------------------------

    def _advance_soiling(self, row: int) -> None:
        if self._rain[row] > self._model.cleaning_threshold_mm:
            self._soiling_loss = 0.0
            self._grace_remaining = self._model.grace_period_days
        elif self._grace_remaining > 0:
            self._grace_remaining -= 1
        else:
            self._soiling_loss = min(
                self._soiling_loss + self._rate[row], self._model.max_soiling
            )

    def _observation(self) -> np.ndarray:
        row = self._rows[self._step_in_episode]
        angle = 2.0 * np.pi * self._doy[row] / 365.25
        true_ratio = 1.0 - self._soiling_loss

        if self.noisy:
            clean_kwh = self._lookup.clean_energy_kwh(row)
            reported, std = self.config.observation_noise.observe(
                true_ratio, clean_kwh, self._reference_kwh, self._obs_rng
            )
        else:
            reported, std = true_ratio, 0.0

        self._last_observed_ratio = reported
        self._last_observation_std = std

        features = [
            reported,
            self._days_since_cleaning / self.config.max_days_since_cleaning,
            self._aod[row] / self.AOD_SCALE,
            self._temp[row] / self.TEMP_SCALE,
            self._wind[row] / self.WIND_SCALE,
            np.sin(angle),
            np.cos(angle),
        ]
        if self.noisy:
            features += [
                min(self._rain[row] / 10.0, 5.0),
                min(std / 0.2, 1.0),
            ]
        return np.array(features, dtype=np.float32)


def register() -> None:
    """Register the environment under ``Rimal-Cleaning-v0``."""
    if "Rimal-Cleaning-v0" not in gym.registry:
        gym.register(
            id="Rimal-Cleaning-v0",
            entry_point="rimal.env.cleaning_env:RimalCleaningEnv",
        )
