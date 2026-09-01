"""Soiling accumulation models.

Soiling is expressed throughout RIMAL as a **soiling ratio**: the fraction of
incident irradiance still reaching the cell, so 1.0 is a perfectly clean panel
and 0.9 means a 10% transmission loss. This is the IEA-PVPS convention and the
one pvlib's ``soiling_ratio`` uses. Internally the models track soiling *loss*
(1 - ratio) because accumulation is naturally expressed that way.

Two models share one accumulation core:

``KimberSoiling``
    Constant deposition rate, reset by rain above a threshold. The literature
    standard (Kimber et al.), and the model pvlib implements. Calibrated here
    to DEWA's measured 0.14-0.33 %/day at MBR Solar Park.

``AodModulatedSoiling``
    Identical mechanics, but the daily deposition rate scales with aerosol
    optical depth relative to its climatological mean, so dusty days soil
    faster than clean ones. Physically better motivated, and it uses the
    AOD_55 series the M0 data layer already provides.

The two exist to test robustness to model choice: a policy conclusion that
holds under both is not an artefact of the soiling model.

**Deviation from the Phase 3 plan.** The plan named pvlib's HSU model as the
cross-check. HSU requires PM2.5 and PM10 concentrations, and NASA POWER serves
neither (verified 2026-08-29 against both the hourly and daily parameter
catalogues). Sourcing PM would mean adding a registration-gated dataset and
breaking the zero-friction data path established in M0. ``AodModulatedSoiling``
replaces HSU as the cross-check; it serves the same purpose -- an independent
deposition mechanism to test model-choice robustness -- using available data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from rimal.config import SOILING


def _accumulate(
    rate_per_day: pd.Series,
    rainfall_mm: pd.Series,
    *,
    cleaning_threshold_mm: float,
    grace_period_days: int,
    max_soiling: float,
    initial_soiling: float = 0.0,
) -> pd.Series:
    """Accumulate soiling loss day by day, resetting on rain.

    One code path serves both models: ``rate_per_day`` is constant for Kimber
    and time-varying for the AOD-modulated variant.

    Rules follow Kimber et al.: loss grows by the daily rate; rainfall above
    ``cleaning_threshold_mm`` washes the panel clean; for ``grace_period_days``
    afterwards the surface stays damp and does not re-soil; loss never exceeds
    ``max_soiling``.
    """
    if not rate_per_day.index.equals(rainfall_mm.index):
        raise ValueError("rate and rainfall must share an index")
    if (rate_per_day < 0).any():
        raise ValueError("soiling rate must be non-negative")

    rates = rate_per_day.to_numpy(dtype=float)
    rain = rainfall_mm.to_numpy(dtype=float)
    loss = np.empty(len(rates), dtype=float)

    current = float(initial_soiling)
    grace_remaining = 0

    for i in range(len(rates)):
        if rain[i] > cleaning_threshold_mm:
            current = 0.0
            grace_remaining = grace_period_days
        elif grace_remaining > 0:
            grace_remaining -= 1
        else:
            current = min(current + rates[i], max_soiling)
        loss[i] = current

    return pd.Series(loss, index=rate_per_day.index, name="soiling_loss")


@dataclass(frozen=True)
class KimberSoiling:
    """Constant-rate soiling with rain resets.

    ``soiling_loss_rate`` is a fraction of transmission lost per day. The
    default is the midpoint of DEWA's measured 0.14-0.33 %/day band at MBR
    Solar Park.
    """

    soiling_loss_rate: float = SOILING.rate_mid_per_day
    cleaning_threshold_mm: float = 6.0
    grace_period_days: int = 14
    max_soiling: float = 0.3

    def daily_rate(self, daily: pd.DataFrame) -> pd.Series:
        return pd.Series(
            self.soiling_loss_rate, index=daily.index, name="soiling_rate"
        )

    def soiling_ratio(
        self, daily: pd.DataFrame, *, initial_soiling: float = 0.0
    ) -> pd.Series:
        """Return the transmission fraction retained, 1.0 == clean."""
        loss = _accumulate(
            self.daily_rate(daily),
            daily["PRECTOTCORR"],
            cleaning_threshold_mm=self.cleaning_threshold_mm,
            grace_period_days=self.grace_period_days,
            max_soiling=self.max_soiling,
            initial_soiling=initial_soiling,
        )
        return (1.0 - loss).rename("soiling_ratio")


@dataclass(frozen=True)
class AodModulatedSoiling:
    """Soiling whose daily rate scales with aerosol optical depth.

    The daily deposition rate is ``mean_loss_rate * (AOD / AOD_reference)``,
    clipped to ``rate_bounds``. With ``AOD_reference`` set to the series' own
    mean, the long-run average rate reproduces ``mean_loss_rate`` while dusty
    days soil faster and clear days slower.

    ``rate_bounds`` defaults to DEWA's measured band, so no individual day can
    imply a rate outside what was actually observed at the site.
    """

    mean_loss_rate: float = SOILING.rate_mid_per_day
    rate_bounds: tuple[float, float] = (
        SOILING.rate_min_per_day,
        SOILING.rate_max_per_day,
    )
    aod_reference: float | None = None
    cleaning_threshold_mm: float = 6.0
    grace_period_days: int = 14
    max_soiling: float = 0.3

    def daily_rate(self, daily: pd.DataFrame) -> pd.Series:
        aod = daily["AOD_55"]
        reference = self.aod_reference if self.aod_reference is not None else aod.mean()
        if not np.isfinite(reference) or reference <= 0:
            raise ValueError(f"AOD reference must be positive and finite, got {reference}")
        low, high = self.rate_bounds
        scaled = self.mean_loss_rate * (aod / reference)
        return scaled.clip(lower=low, upper=high).rename("soiling_rate")

    def soiling_ratio(
        self, daily: pd.DataFrame, *, initial_soiling: float = 0.0
    ) -> pd.Series:
        loss = _accumulate(
            self.daily_rate(daily),
            daily["PRECTOTCORR"],
            cleaning_threshold_mm=self.cleaning_threshold_mm,
            grace_period_days=self.grace_period_days,
            max_soiling=self.max_soiling,
            initial_soiling=initial_soiling,
        )
        return (1.0 - loss).rename("soiling_ratio")


def observed_accumulation_rate(soiling_ratio: pd.Series) -> pd.Series:
    """Daily loss increments during accumulation, for calibration checks.

    Days on which soiling fell (a rain reset) or stayed flat (grace period, or
    the max-soiling cap) are excluded, leaving only genuine accumulation. The
    mean of this series is what should be compared against DEWA's measured
    0.14-0.33 %/day.
    """
    increments = (1.0 - soiling_ratio).diff()
    return increments[increments > 0]
