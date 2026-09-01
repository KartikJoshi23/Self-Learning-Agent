"""Gymnasium environment for PV cleaning dispatch."""

from rimal.env.cleaning_env import (
    ACTION_CLEAN,
    ACTION_NOOP,
    Economics,
    EnvConfig,
    RimalCleaningEnv,
    register,
)
from rimal.env.energy_table import EnergyLookup, build_energy_table
from rimal.env.belief_wrapper import BeliefStateWrapper
from rimal.env.robots import DEWA_FLEET, Fleet, RobotSpec
from rimal.env.observation import ObservationNoise, SoilingKalmanFilter

__all__ = [
    "RimalCleaningEnv",
    "EnvConfig",
    "Economics",
    "ACTION_NOOP",
    "ACTION_CLEAN",
    "register",
    "build_energy_table",
    "EnergyLookup",
    "ObservationNoise",
    "SoilingKalmanFilter",
    "BeliefStateWrapper",
    "Fleet",
    "RobotSpec",
    "DEWA_FLEET",
]
