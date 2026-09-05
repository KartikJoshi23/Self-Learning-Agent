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

from rimal.config import AOD_CLIMATOLOGY_550NM, SOILING


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

    The daily deposition rate is
    ``mean_loss_rate * (AOD / AOD_reference) ** storm_exponent``, clipped to
    ``rate_bounds``. With ``AOD_reference`` set to the series' own mean, the
    long-run average reproduces ``mean_loss_rate`` while dusty days soil faster.

    **On ``rate_bounds``, and a correction to M1.** This model originally
    clipped the rate to DEWA's measured 0.14-0.33 %/day band, on the reasoning
    that no day should imply a rate outside what was observed at the site. That
    was wrong, and it mattered. DEWA's band describes *average* accumulation
    over a 13-month trial, not a per-day ceiling, and the soiling literature is
    explicit that a dust storm "can undo a cleaning cycle overnight" -- a
    single-day deposition of order 7%, roughly thirty times the mean daily
    rate. Clipping at 0.33 %/day pinned 18.7% of days at the cap and compressed
    an 8x spread in measured AOD into a 1.5x spread in soiling. It removed
    precisely the tail that risk-sensitive control exists to manage, and it
    means every CVaR figure reported before M7 understates tail risk.

    ``storm_exponent`` is an ASSUMPTION. Deposition flux rises with both
    airborne concentration and settling velocity, and both increase during a
    storm, so superlinear scaling is physically motivated; the specific value is
    calibrated so the most extreme observed days reproduce the documented
    overnight-cycle-loss effect. It is swept in ``scripts/m7_verify.py``.
    Leaving it at 1.0 with the tight bounds reproduces the pre-M7 behaviour.
    """

    mean_loss_rate: float = SOILING.rate_mid_per_day
    rate_bounds: tuple[float, float] = (
        SOILING.rate_min_per_day,
        SOILING.rate_max_per_day,
    )
    #: Fixed climatological reference. ``None`` falls back to the passed
    #: frame's own mean, which makes the dynamics depend on the window and is
    #: retained only for backwards compatibility -- see AOD_CLIMATOLOGY_550NM.
    aod_reference: float | None = AOD_CLIMATOLOGY_550NM
    cleaning_threshold_mm: float = 6.0
    grace_period_days: int = 14
    max_soiling: float = 0.3
    storm_exponent: float = 1.0

    def daily_rate(self, daily: pd.DataFrame) -> pd.Series:
        aod = daily["AOD_55"]
        reference = self.aod_reference if self.aod_reference is not None else aod.mean()
        if not np.isfinite(reference) or reference <= 0:
            raise ValueError(f"AOD reference must be positive and finite, got {reference}")
        if self.storm_exponent <= 0:
            raise ValueError("storm_exponent must be positive")
        low, high = self.rate_bounds
        scaled = self.mean_loss_rate * (aod / reference) ** self.storm_exponent
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


def storm_soiling(
    mean_loss_rate: float = SOILING.rate_mid_per_day,
    storm_exponent: float = 2.0,
    max_daily_rate: float = 0.07,
) -> AodModulatedSoiling:
    """The tail-preserving configuration used from M7 onwards.

    ``max_daily_rate`` of 7% is one cleaning cycle's worth of soiling
    (30 days at ~0.235 %/day) deposited in a single day -- the literature's
    "a storm can undo a cleaning cycle overnight", used as the physical ceiling
    rather than DEWA's average-rate band.

    The *mean* rate must still land inside DEWA's measured band, which
    ``scripts/m1_verify.py`` checks; storms are rare enough (about 0.6% of days
    exceed three times the median AOD) that they move the mean very little.
    """
    return AodModulatedSoiling(
        mean_loss_rate=mean_loss_rate,
        rate_bounds=(0.0, max_daily_rate),
        storm_exponent=storm_exponent,
        aod_reference=AOD_CLIMATOLOGY_550NM,
    )


def observed_accumulation_rate(soiling_ratio: pd.Series) -> pd.Series:
    """Daily loss increments during accumulation, for calibration checks.

    Days on which soiling fell (a rain reset) or stayed flat (grace period, or
    the max-soiling cap) are excluded, leaving only genuine accumulation. The
    mean of this series is what should be compared against DEWA's measured
    0.14-0.33 %/day.
    """
    increments = (1.0 - soiling_ratio).diff()
    return increments[increments > 0]
