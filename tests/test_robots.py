"""Tests for the cleaning-robot fleet (M6)."""

from __future__ import annotations

import numpy as np
import pytest

from rimal.config import CLEANING
from rimal.env.robots import DEWA_FLEET, Fleet, RobotSpec


def _rng() -> np.random.Generator:
    return np.random.default_rng(0)


class TestFleetSpecs:
    def test_default_fleet_sits_inside_dewas_measured_band(self):
        for spec in DEWA_FLEET:
            assert CLEANING.efficacy_min <= spec.nominal_efficacy <= CLEANING.efficacy_max

    def test_fleet_rejects_efficacy_outside_the_measured_band(self):
        with pytest.raises(ValueError, match="measured"):
            Fleet(specs=(RobotSpec("impossible", 1.0),))

    def test_empty_fleet_rejected(self):
        with pytest.raises(ValueError, match="at least one"):
            Fleet(specs=())

    def test_cooldown_rises_with_cleaning_aggressiveness(self):
        """Without this ordering the strongest machine simply dominates and
        there is no dispatch decision at all -- the flaw the first version of
        this model had."""
        by_efficacy = sorted(DEWA_FLEET, key=lambda s: s.nominal_efficacy)
        cooldowns = [s.cooldown_days for s in by_efficacy]
        assert cooldowns == sorted(cooldowns)


class TestCleaning:
    def test_realised_efficacy_is_stochastic(self):
        fleet = Fleet()
        rng = _rng()
        draws = {fleet.clean(0, rng) for _ in range(1)}
        fleet.reset()
        more = [fleet.clean(0, rng) for _ in range(50)]
        assert len(set(more)) > 40, "efficacy must vary clean to clean"

    def test_realised_efficacy_centres_on_nominal_when_healthy(self):
        fleet = Fleet()
        rng = _rng()
        draws = []
        for _ in range(400):
            fleet.reset()
            draws.append(fleet.clean(0, rng))
        assert np.mean(draws) == pytest.approx(DEWA_FLEET[0].nominal_efficacy, abs=0.03)

    def test_efficacy_stays_in_the_unit_interval(self):
        fleet = Fleet()
        rng = _rng()
        for i in range(fleet.size):
            for _ in range(50):
                fleet.reset()
                assert 0.0 <= fleet.clean(i, rng) <= 1.0

    def test_cleaning_wears_the_machine(self):
        fleet = Fleet()
        rng = _rng()
        before = fleet.health[0]
        fleet.clean(0, rng)
        assert fleet.health[0] < before

    def test_worn_machines_clean_worse_but_still_clean(self):
        fleet = Fleet()
        healthy = fleet.effective_efficacy(0)
        fleet.health[0] = 0.0
        worn = fleet.effective_efficacy(0)
        assert worn < healthy
        assert worn > 0.0, "a dead robot would be trivially detectable"
        assert worn == pytest.approx(
            DEWA_FLEET[0].nominal_efficacy * DEWA_FLEET[0].min_health_efficacy
        )


class TestCooldown:
    def test_cleaning_puts_the_machine_on_cooldown(self):
        fleet = Fleet()
        assert fleet.available(0)
        fleet.clean(0, _rng())
        assert not fleet.available(0)

    def test_cooldown_expires_after_the_specified_days(self):
        fleet = Fleet()
        fleet.clean(0, _rng())
        for _ in range(DEWA_FLEET[0].cooldown_days):
            assert not fleet.available(0)
            fleet.advance_day()
        assert fleet.available(0)

    def test_cooldown_is_per_machine(self):
        fleet = Fleet()
        fleet.clean(0, _rng())
        assert not fleet.available(0)
        assert all(fleet.available(i) for i in range(1, fleet.size))


class TestService:
    def test_service_restores_health_and_clears_cooldown(self):
        fleet = Fleet()
        rng = _rng()
        for _ in range(20):
            fleet.reset() if False else None
            fleet.clean(0, rng)
            fleet.cooldown_remaining[0] = 0.0
        assert fleet.health[0] < 1.0
        cost = fleet.service(0)
        assert fleet.health[0] == 1.0
        assert fleet.uses_since_service[0] == 0.0
        assert fleet.available(0)
        assert cost == fleet.service_cost_usd_per_mwp

    def test_daily_wear_applies_without_use(self):
        fleet = Fleet()
        for _ in range(100):
            fleet.advance_day()
        assert fleet.health[0] < 1.0

    def test_health_never_goes_negative(self):
        fleet = Fleet()
        for _ in range(10_000):
            fleet.advance_day()
        assert (fleet.health >= 0.0).all()


class TestObservation:
    def test_observation_excludes_health(self):
        """Health is latent by construction: an operator sees the service log
        and the cooldown clock, never how well a machine currently cleans."""
        fleet = Fleet()
        fleet.health[:] = 0.3
        baseline = fleet.observation().copy()
        fleet.health[:] = 0.9
        assert np.allclose(baseline, fleet.observation())

    def test_observation_shape_and_bounds(self):
        fleet = Fleet()
        observation = fleet.observation()
        assert observation.shape == (3 * fleet.size,)
        assert (observation >= 0.0).all() and (observation <= 1.0).all()

    def test_cooldown_appears_in_the_observation(self):
        fleet = Fleet()
        before = fleet.observation()[2 * fleet.size :].copy()
        fleet.clean(0, _rng())
        after = fleet.observation()[2 * fleet.size :]
        assert after[0] > before[0]
