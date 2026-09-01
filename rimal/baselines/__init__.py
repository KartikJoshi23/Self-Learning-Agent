"""Rule-based cleaning policies used as baselines."""

from rimal.baselines.policies import (
    AlwaysClean,
    FixedInterval,
    NeverClean,
    Policy,
    SoilingThreshold,
    standard_baselines,
)

__all__ = [
    "Policy",
    "NeverClean",
    "AlwaysClean",
    "FixedInterval",
    "SoilingThreshold",
    "standard_baselines",
]
