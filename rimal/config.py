"""Site and simulation constants for RIMAL.

Values here are grounded in published sources; see RESEARCH.md for citations.
Anything that is an assumption rather than a measurement is marked ASSUMPTION.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Site:
    """A physical PV site."""

    name: str
    latitude: float
    longitude: float
    altitude: float
    timezone: str


# Mohammed bin Rashid Al Maktoum Solar Park, Seih Al-Dahal, Dubai.
# Coordinates are the solar park area; altitude is approximate desert plateau.
MBR_SOLAR_PARK = Site(
    name="MBR Solar Park (Seih Al-Dahal)",
    latitude=24.75,
    longitude=55.35,
    altitude=90.0,
    timezone="Asia/Dubai",
)


@dataclass(frozen=True)
class SoilingCalibration:
    """Soiling accumulation rates measured by DEWA at MBR Solar Park.

    Source: DEWA cleaning-robot field study, 164 crystalline-silicon modules
    (445-505 W), 22 Jul 2024 - 26 Aug 2025, reported via pv magazine 2026-08-14.

    Rates are fractional transmission loss per day (0.0014 == 0.14 %/day).
    """

    rate_min_per_day: float = 0.0014
    rate_max_per_day: float = 0.0033
    #: Soiling rate achieved under daily robotic cleaning (< 0.02 %/day).
    rate_under_daily_cleaning: float = 0.0002

    @property
    def rate_mid_per_day(self) -> float:
        return (self.rate_min_per_day + self.rate_max_per_day) / 2.0


@dataclass(frozen=True)
class CleaningCalibration:
    """Cleaning-action efficacy measured by DEWA across five dry robots.

    Source: same DEWA field study. Cleaning efficiency 69-99% across robots
    A-E. This is the empirical basis for treating the cleaning action as
    stochastic rather than a perfect reset to zero soiling.
    """

    efficacy_min: float = 0.69
    efficacy_max: float = 0.99


#: Climatological mean AOD at 550 nm over the full 2016-2025 record at this
#: site, used as a FIXED reference by the AOD-driven soiling models.
#:
#: It must be fixed rather than taken from whatever frame is passed. Using the
#: frame's own mean makes the soiling rate for a given dust level depend on
#: which years are in the window: the 2016-2022 training mean is 0.4158 and the
#: 2023-2025 holdout mean is 0.4968, an 18.4% difference, which at a storm
#: exponent of 2 scales the rate by 0.70x between the training and evaluation
#: environments for identical dust. That is a train/eval mismatch invented by
#: the code, not a property of the site, and it biases any agent-versus-rule
#: comparison: an online filter re-estimates conditions as it goes, while a
#: trained policy carries the training dynamics with it.
AOD_CLIMATOLOGY_550NM: float = 0.4401

#: Modules per MW, derived from DEWA's test-field module rating of 445-505 W.
#: 1e6 W / 475 W ~= 2105 modules per MW.
MODULES_PER_MW: int = 2105

#: Water use for wet cleaning, cubic metres per MWh of production.
#: Source: published utility-scale washing figures, 0.08-0.15 m3/MWh.
#: Only relevant to the wet-crew action; the DEWA robots tested are dry.
WATER_M3_PER_MWH: tuple[float, float] = (0.08, 0.15)

#: Specific energy of SWRO desalination, kWh per cubic metre.
#: Used to price the water constraint, not to dominate the reward. See
#: RESEARCH.md section 6 (E2) for why this is a constraint and not a reward term.
DESAL_KWH_PER_M3: float = 3.5

#: Expected annual specific yield for a fixed-tilt system in Dubai, kWh/kWp.
#: Used as the M1 physics acceptance band, not as a model input.
EXPECTED_SPECIFIC_YIELD_KWH_PER_KWP: tuple[float, float] = (1700.0, 1900.0)


@dataclass(frozen=True)
class DataConfig:
    """Defaults for the data layer."""

    #: NASA POWER hourly parameters. AOD_55 is the dust driver; the ALLSKY /
    #: CLRSKY pair gives both measured irradiance and a clear-sky reference.
    power_parameters: tuple[str, ...] = (
        "ALLSKY_SFC_SW_DWN",   # GHI
        "ALLSKY_SFC_SW_DNI",   # DNI
        "ALLSKY_SFC_SW_DIFF",  # DHI
        "CLRSKY_SFC_SW_DWN",   # clear-sky GHI reference
        "T2M",                 # air temperature, degC
        "WS2M",                # wind speed at 2 m, m/s
        "RH2M",                # relative humidity, %
        "PRECTOTCORR",         # precipitation, mm/hour
        "AOD_55",              # aerosol optical depth at 550 nm
    )
    default_start_year: int = 2016
    default_end_year: int = 2025

    #: Years reserved for evaluation. Never train on these.
    holdout_years: tuple[int, ...] = (2023, 2024, 2025)

    @property
    def train_years(self) -> tuple[int, ...]:
        return tuple(
            y
            for y in range(self.default_start_year, self.default_end_year + 1)
            if y not in self.holdout_years
        )


DATA = DataConfig()
SOILING = SoilingCalibration()
CLEANING = CleaningCalibration()
