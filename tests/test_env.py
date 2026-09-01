"""Tests for the cleaning environment and the energy lookup.

These need the parquet caches built by M0-M2 (data + energy table), so they are
marked ``network``: on a cold clone they will fetch, and afterwards they run
offline.
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
import pandas as pd
import pytest

from rimal.env import (
    ACTION_CLEAN,
    ACTION_NOOP,
    EnergyLookup,
    Economics,
    EnvConfig,
    RimalCleaningEnv,
    register,
)


class TestEnergyLookup:
    @staticmethod
    def _table() -> pd.DataFrame:
        dates = pd.date_range("2020-01-01", periods=3, freq="D", tz="Asia/Dubai")
        # Energy rises linearly with ratio; deliberately different per day.
        return pd.DataFrame(
            {0.70: [70.0, 140.0, 7.0], 0.85: [85.0, 170.0, 8.5], 1.0: [100.0, 200.0, 10.0]},
            index=dates,
        )

    def test_interpolates_between_grid_points(self):
        lookup = EnergyLookup(self._table())
        assert lookup.energy_kwh(0, 0.85) == pytest.approx(85.0)
        assert lookup.energy_kwh(0, 0.775) == pytest.approx(77.5)
        assert lookup.energy_kwh(1, 0.925) == pytest.approx(185.0)

    def test_clamps_outside_the_grid(self):
        lookup = EnergyLookup(self._table())
        assert lookup.energy_kwh(0, 0.2) == pytest.approx(70.0)
        assert lookup.energy_kwh(0, 1.4) == pytest.approx(100.0)

    def test_clean_energy_is_the_top_of_the_grid(self):
        lookup = EnergyLookup(self._table())
        assert lookup.clean_energy_kwh(2) == pytest.approx(10.0)

    def test_unsorted_ratio_columns_rejected(self):
        table = self._table()[[1.0, 0.70, 0.85]]
        with pytest.raises(ValueError, match="strictly increasing"):
            EnergyLookup(table)


@pytest.mark.network
class TestCleaningEnv:
    @staticmethod
    def _env(**kwargs) -> RimalCleaningEnv:
        return RimalCleaningEnv(EnvConfig(years=(2020, 2021), **kwargs))

    def test_spaces(self):
        env = self._env()
        assert env.action_space.n == 2
        assert env.observation_space.shape == (7,)

    def test_reset_returns_an_observation_inside_the_space(self):
        env = self._env()
        obs, info = env.reset(seed=0, options={"year": 2020})
        assert env.observation_space.contains(obs)
        assert info["year"] == 2020
        assert obs[0] == pytest.approx(1.0), "episodes start with a clean panel"

    def test_step_before_reset_raises(self):
        with pytest.raises(RuntimeError, match="reset"):
            self._env().step(ACTION_NOOP)

    def test_invalid_action_raises(self):
        env = self._env()
        env.reset(seed=0)
        with pytest.raises(ValueError, match="invalid action"):
            env.step(7)

    def test_unknown_year_raises(self):
        env = self._env()
        with pytest.raises(ValueError, match="not in config.years"):
            env.reset(options={"year": 1999})

    def test_cleaning_restores_the_panel_and_costs_money(self):
        env = self._env()
        env.reset(seed=0, options={"year": 2020})
        for _ in range(40):
            env.step(ACTION_NOOP)
        _, _, _, _, dirty = env.step(ACTION_NOOP)
        assert dirty["soiling_ratio"] < 1.0

        _, reward, _, _, cleaned = env.step(ACTION_CLEAN)
        assert cleaned["soiling_ratio"] == pytest.approx(1.0)
        assert cleaned["cleaned"] is True
        assert cleaned["cleaning_cost_usd"] > 0
        # Default reward_mode is "negative_cost"; a clean day on an already
        # clean panel costs exactly the cleaning fee and nothing else.
        assert reward == pytest.approx(-cleaned["cleaning_cost_usd"])

    def test_net_value_reward_mode(self):
        env = self._env(reward_mode="net_value")
        env.reset(seed=0, options={"year": 2020})
        _, reward, _, _, info = env.step(ACTION_CLEAN)
        assert reward == pytest.approx(
            info["revenue_usd"] - info["cleaning_cost_usd"]
        )

    def test_reward_modes_differ_only_by_an_action_independent_constant(self):
        """The two modes must share an optimal policy.

        They differ by the day's clean-plant revenue, which depends on the day
        but not on the action -- a state-dependent baseline. If that ever stops
        holding, the variance-reduced reward would be optimising something else.
        """
        price = Economics().energy_price_usd_per_kwh
        for mode in ("net_value", "negative_cost"):
            env = self._env(reward_mode=mode)
            env.reset(seed=0, options={"year": 2020})
            for _ in range(25):
                _, reward, _, _, info = env.step(ACTION_NOOP)
                offset = info["clean_energy_kwh"] * price
                expected = (
                    info["revenue_usd"] - info["cleaning_cost_usd"]
                    if mode == "net_value"
                    else info["revenue_usd"] - info["cleaning_cost_usd"] - offset
                )
                assert reward == pytest.approx(expected, rel=1e-9)

    def test_unknown_reward_mode_rejected(self):
        with pytest.raises(ValueError, match="unknown reward_mode"):
            RimalCleaningEnv(EnvConfig(years=(2020,), reward_mode="nope"))

    def test_soiling_never_leaves_physical_bounds(self):
        env = self._env()
        env.reset(seed=0, options={"year": 2020})
        while True:
            _, _, terminated, _, info = env.step(ACTION_NOOP)
            assert 0.0 < info["soiling_ratio"] <= 1.0
            if terminated:
                break

    def test_episode_terminates_after_one_year(self):
        env = self._env()
        env.reset(seed=0, options={"year": 2021})
        steps = 0
        while True:
            _, _, terminated, truncated, _ = env.step(ACTION_NOOP)
            steps += 1
            if terminated or truncated:
                break
        assert steps == 365  # 2021 is not a leap year

    def test_free_cleaning_makes_always_clean_optimal(self):
        """A control on the reward wiring: with cleaning free, cleaning daily
        must beat never cleaning, because it strictly adds energy."""
        env = self._env(economics=Economics(cleaning_cost_usd_per_mwp=0.0))

        def total(action: int) -> float:
            env.reset(seed=0, options={"year": 2020})
            out = 0.0
            while True:
                _, reward, terminated, _, _ = env.step(action)
                out += reward
                if terminated:
                    break
            return out

        assert total(ACTION_CLEAN) > total(ACTION_NOOP)

    def test_prohibitive_cleaning_cost_makes_never_clean_optimal(self):
        env = self._env(economics=Economics(cleaning_cost_usd_per_mwp=1e6))

        def total(action: int) -> float:
            env.reset(seed=0, options={"year": 2020})
            out = 0.0
            while True:
                _, reward, terminated, _, _ = env.step(action)
                out += reward
                if terminated:
                    break
            return out

        assert total(ACTION_NOOP) > total(ACTION_CLEAN)

    def test_unknown_soiling_model_rejected(self):
        with pytest.raises(ValueError, match="unknown soiling_model"):
            RimalCleaningEnv(EnvConfig(years=(2020,), soiling_model="nope"))

    def test_empty_years_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            RimalCleaningEnv(EnvConfig(years=()))

    def test_registers_for_gym_make(self):
        register()
        env = gym.make("Rimal-Cleaning-v0")
        obs, _ = env.reset(seed=0)
        assert obs.shape == (7,)
        env.close()

    def test_same_seed_gives_the_same_episode_year(self):
        a, b = self._env(), self._env()
        assert a.reset(seed=123)[1]["year"] == b.reset(seed=123)[1]["year"]
