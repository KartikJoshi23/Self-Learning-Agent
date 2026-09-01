"""PV plant energy model.

Wraps pvlib's PVWatts chain to turn the M0 weather record into AC energy. The
PVWatts model is used rather than a module-database model because it needs only
two plant parameters that are actually known for a generic utility-scale
c-Si plant, which keeps the assumptions few and inspectable.

Soiling enters as a multiplicative derate on plane-of-array irradiance, which
is how soiling is physically expressed: dust attenuates incident light before
the cell sees it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pvlib
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import Array, FixedMount, PVSystem
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

from rimal.config import MBR_SOLAR_PARK, Site
from rimal.data.power import complete_local_days

#: pvlib expects these canonical names; NASA POWER uses its own.
POWER_TO_PVLIB = {
    "ALLSKY_SFC_SW_DWN": "ghi",
    "ALLSKY_SFC_SW_DNI": "dni",
    "ALLSKY_SFC_SW_DIFF": "dhi",
    "T2M": "temp_air",
    "WS2M": "wind_speed",
}


@dataclass(frozen=True)
class PlantConfig:
    """A generic fixed-tilt utility-scale c-Si plant.

    Tilt defaults to site latitude, the standard rule of thumb for a
    yield-maximising fixed array, and azimuth to due south.

    ``dc_capacity_w`` is nameplate DC. Results are reported per kWp so the
    absolute value only matters for readability.
    """

    dc_capacity_w: float = 1_000_000.0  # 1 MWp
    dc_ac_ratio: float = 1.2
    #: Power temperature coefficient for crystalline silicon, per degC.
    gamma_pdc: float = -0.0035
    #: PVWatts loss stack, percent. Soiling is zero because RIMAL models it
    #: explicitly upstream; snow is zero because this is Dubai. The rest are
    #: pvlib defaults, combining to roughly 12.3%.
    losses_pct: dict[str, float] = field(
        default_factory=lambda: {
            "soiling": 0.0,
            "snow": 0.0,
            "shading": 3.0,
            "mismatch": 2.0,
            "wiring": 2.0,
            "connections": 0.5,
            "lid": 1.5,
            "nameplate_rating": 1.0,
            "age": 0.0,
            "availability": 3.0,
        }
    )
    #: Optimum fixed tilt for Dubai, per Global Solar Atlas (26 degrees).
    surface_tilt: float | None = 26.0
    surface_azimuth: float = 180.0

    def tilt_for(self, site: Site) -> float:
        return site.latitude if self.surface_tilt is None else self.surface_tilt


def to_pvlib_weather(
    hourly: pd.DataFrame,
    site: Site = MBR_SOLAR_PARK,
    *,
    decomposition: str = "erbs",
) -> pd.DataFrame:
    """Rename and localise a NASA POWER frame for pvlib.

    ``decomposition`` selects where the direct and diffuse components come from:

    ``"erbs"`` (default)
        Derive DNI and DHI from the measured GHI using pvlib's Erbs model.
        POWER's own components do not close against POWER's own GHI: measured
        over 2016-2025 at this site, DHI + DNI*cos(zenith) recovers only
        **95.1%** of GHI, and that deficit propagates straight into a ~5% low
        plane-of-array irradiance. GHI is POWER's best-validated radiation
        product, so decomposing from it is both self-consistent (closure
        1.0000) and closer to truth -- the resulting annual POA of
        ~2323 kWh/m2 sits within **0.6%** of Global Solar Atlas's
        independently modelled GTI of 2336.2 kWh/m2 for Dubai.

    ``"native"``
        Use POWER's ALLSKY_SFC_SW_DNI and ALLSKY_SFC_SW_DIFF as served.
        Retained so the difference stays measurable rather than assumed.

    The frame is trimmed to whole local days first; see
    :func:`rimal.data.power.complete_local_days`.
    """
    missing = sorted(set(POWER_TO_PVLIB) - set(hourly.columns))
    if missing:
        raise ValueError(f"weather frame is missing {missing}")
    if decomposition not in ("erbs", "native"):
        raise ValueError(f"unknown decomposition {decomposition!r}")

    trimmed = complete_local_days(hourly, site)
    weather = trimmed[list(POWER_TO_PVLIB)].rename(columns=POWER_TO_PVLIB)

    if decomposition == "erbs":
        location = Location(site.latitude, site.longitude, site.timezone, site.altitude)
        zenith = location.get_solarposition(weather.index)["zenith"]
        derived = pvlib.irradiance.erbs(weather["ghi"], zenith, weather.index)
        weather = weather.assign(dni=derived["dni"], dhi=derived["dhi"])

    return weather


def build_model_chain(
    config: PlantConfig | None = None, site: Site = MBR_SOLAR_PARK
) -> ModelChain:
    config = config or PlantConfig()
    location = Location(
        latitude=site.latitude,
        longitude=site.longitude,
        altitude=site.altitude,
        tz=site.timezone,
    )
    array = Array(
        mount=FixedMount(
            surface_tilt=config.tilt_for(site),
            surface_azimuth=config.surface_azimuth,
        ),
        module_parameters={
            "pdc0": config.dc_capacity_w,
            "gamma_pdc": config.gamma_pdc,
        },
        temperature_model_parameters=TEMPERATURE_MODEL_PARAMETERS["sapm"][
            "open_rack_glass_glass"
        ],
    )
    system = PVSystem(
        arrays=[array],
        inverter_parameters={"pdc0": config.dc_capacity_w / config.dc_ac_ratio},
        losses_parameters=dict(config.losses_pct),  # soiling handled upstream
    )
    return ModelChain(
        system,
        location,
        dc_model="pvwatts",
        ac_model="pvwatts",
        aoi_model="physical",
        spectral_model="no_loss",
        losses_model="pvwatts",
    )


def hourly_ac_energy(
    hourly: pd.DataFrame,
    *,
    soiling_ratio: pd.Series | None = None,
    config: PlantConfig | None = None,
    site: Site = MBR_SOLAR_PARK,
    decomposition: str = "erbs",
) -> pd.Series:
    """Return hourly AC energy in Wh.

    ``soiling_ratio`` is a *daily* series of retained transmission (1.0 clean).
    It is broadcast to the hourly index and applied to the three irradiance
    components before transposition, matching the physical mechanism: dust
    attenuates incident light, and the cell then behaves normally.

    Passing ``None`` models a permanently clean plant, which is the upper
    bound every cleaning policy is measured against.
    """
    config = config or PlantConfig()
    weather = to_pvlib_weather(hourly, site, decomposition=decomposition)

    if soiling_ratio is not None:
        ratio = soiling_ratio.reindex(weather.index.normalize())
        ratio.index = weather.index
        if ratio.isna().any():
            raise ValueError("soiling_ratio does not cover every weather day")
        for component in ("ghi", "dni", "dhi"):
            weather[component] = weather[component] * ratio

    chain = build_model_chain(config, site)
    chain.run_model(weather)

    ac = chain.results.ac.clip(lower=0.0)
    # PVWatts returns power in W; hourly steps make Wh numerically identical.
    return ac.rename("ac_energy_wh")


def specific_yield_kwh_per_kwp(
    ac_energy_wh: pd.Series, config: PlantConfig | None = None
) -> float:
    """Total AC energy per kW of installed DC capacity."""
    dc_capacity_kw = (config or PlantConfig()).dc_capacity_w / 1000.0
    return float(ac_energy_wh.sum() / 1000.0 / dc_capacity_kw)


def annual_specific_yield(
    ac_energy_wh: pd.Series, config: PlantConfig | None = None
) -> pd.Series:
    """Specific yield per calendar year, kWh/kWp."""
    dc_capacity_kw = (config or PlantConfig()).dc_capacity_w / 1000.0
    return ac_energy_wh.groupby(ac_energy_wh.index.year).sum() / 1000.0 / dc_capacity_kw


def check_irradiance_closure(
    hourly: pd.DataFrame, site: Site = MBR_SOLAR_PARK, *, decomposition: str = "erbs"
) -> pd.Series:
    """Relative error of the GHI = DHI + DNI*cos(zenith) identity.

    An independent check that the three POWER irradiance components are
    mutually consistent, computed only for hours with meaningful sun.
    """
    weather = to_pvlib_weather(hourly, site, decomposition=decomposition)
    location = Location(site.latitude, site.longitude, site.timezone, site.altitude)
    solar = location.get_solarposition(weather.index)

    cos_zenith = pvlib.tools.cosd(solar["zenith"]).clip(lower=0.0)
    reconstructed = weather["dhi"] + weather["dni"] * cos_zenith

    daylight = weather["ghi"] > 50.0
    return ((reconstructed[daylight] - weather["ghi"][daylight])
            / weather["ghi"][daylight]).rename("ghi_closure_error")
