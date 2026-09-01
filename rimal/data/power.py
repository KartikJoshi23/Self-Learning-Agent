"""NASA POWER hourly data fetcher.

NASA POWER is the single upstream source for RIMAL: it serves both the
irradiance/weather needed to simulate energy yield and the aerosol optical
depth (AOD_55) that drives dust deposition. It requires no registration and
places no restrictions on redistribution, which keeps the project zero-cost.

Two constraints were established empirically against the live API and are
encoded here:

1. Hourly JSON responses are capped by total payload size -- roughly the
   product of parameter count and year span -- not by span alone. Measured
   2026-08-29: 9 parameters x 3 years succeeds, 9 x 5 is rejected with
   HTTP 422 ("please shorten your requested time extent"), while 4 x 5
   succeeds. The cap therefore sits between 27 and 45 parameter-years.
   Requests are chunked one calendar year at a time (9 parameter-years),
   which stays comfortably inside the cap and keeps cache keys simple.
2. Missing values are returned as the sentinel -999, not as null.

Fetches are cached to parquet keyed by site and year, so the first call needs
network access and every subsequent call does not.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from rimal.config import DATA, MBR_SOLAR_PARK, Site

logger = logging.getLogger(__name__)

POWER_HOURLY_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"

#: NASA POWER's sentinel for a missing value.
FILL_VALUE = -999.0

#: Default on-disk cache. Git-ignored; regenerate with fetch_years().
CACHE_DIR = Path(__file__).resolve().parent / "cache"

REQUEST_TIMEOUT_S = 180

#: A complete local day. Used to drop the truncated days that the UTC->local
#: conversion leaves at each end of the record.
HOURS_PER_DAY = 24


class PowerFetchError(RuntimeError):
    """Raised when NASA POWER returns something we cannot use."""


def _cache_path(site: Site, year: int, cache_dir: Path) -> Path:
    slug = site.name.split("(")[0].strip().lower().replace(" ", "-")
    return cache_dir / f"{slug}_{year}.parquet"


def _parse_response(payload: dict) -> pd.DataFrame:
    """Turn a NASA POWER JSON payload into a tidy UTC-indexed frame."""
    try:
        parameters = payload["properties"]["parameter"]
    except (KeyError, TypeError) as exc:  # pragma: no cover - defensive
        raise PowerFetchError(f"unexpected payload shape: {exc}") from exc

    if not parameters:
        raise PowerFetchError("payload contained no parameters")

    frame = pd.DataFrame({name: pd.Series(values) for name, values in parameters.items()})
    frame.index = pd.to_datetime(frame.index, format="%Y%m%d%H", utc=True)
    frame = frame.sort_index().astype("float64")
    frame.index.name = "timestamp_utc"
    # NaN rather than pd.NA: these columns stay float64 so pvlib and numpy can
    # consume them directly without an object-dtype detour.
    return frame.replace(FILL_VALUE, np.nan)


def fetch_year(
    year: int,
    site: Site = MBR_SOLAR_PARK,
    *,
    parameters: tuple[str, ...] = DATA.power_parameters,
    cache_dir: Path = CACHE_DIR,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return one calendar year of hourly data for ``site``.

    Reads from the parquet cache when available. Only reaches the network on a
    cache miss or when ``force_refresh`` is set, which makes repeat calls both
    idempotent and offline-replayable.
    """
    path = _cache_path(site, year, cache_dir)
    if path.exists() and not force_refresh:
        logger.debug("cache hit for %s %d", site.name, year)
        return pd.read_parquet(path)

    logger.info("fetching NASA POWER for %s %d", site.name, year)
    response = requests.get(
        POWER_HOURLY_URL,
        params={
            "parameters": ",".join(parameters),
            "community": "RE",
            "latitude": site.latitude,
            "longitude": site.longitude,
            "start": f"{year}0101",
            "end": f"{year}1231",
            "format": "JSON",
            "time-standard": "UTC",
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    if not response.ok:
        raise PowerFetchError(
            f"NASA POWER returned HTTP {response.status_code} for {year}: "
            f"{response.text[:300]}"
        )

    frame = _parse_response(response.json())

    missing = sorted(set(parameters) - set(frame.columns))
    if missing:
        raise PowerFetchError(f"NASA POWER omitted requested parameters: {missing}")

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    return frame


def fetch_years(
    start_year: int = DATA.default_start_year,
    end_year: int = DATA.default_end_year,
    site: Site = MBR_SOLAR_PARK,
    *,
    parameters: tuple[str, ...] = DATA.power_parameters,
    cache_dir: Path = CACHE_DIR,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return a continuous hourly frame spanning ``start_year``..``end_year``.

    Chunked one year per request to stay inside the API's payload-size cap
    (see the module docstring); the cap is on size, not span.
    """
    if end_year < start_year:
        raise ValueError(f"end_year {end_year} precedes start_year {start_year}")

    frames = [
        fetch_year(
            year,
            site,
            parameters=parameters,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
        )
        for year in range(start_year, end_year + 1)
    ]
    combined = pd.concat(frames).sort_index()

    duplicated = combined.index.duplicated().sum()
    if duplicated:
        raise PowerFetchError(f"{duplicated} duplicate timestamps across year chunks")

    return combined


def to_local(frame: pd.DataFrame, site: Site = MBR_SOLAR_PARK) -> pd.DataFrame:
    """Convert a UTC-indexed frame to the site's local timezone.

    Energy yield and cleaning decisions are both local-time concepts, so the
    simulation works in site-local time even though POWER serves UTC.
    """
    local = frame.tz_convert(site.timezone)
    local.index.name = "timestamp_local"
    return local


def daily_summary(
    frame: pd.DataFrame,
    site: Site = MBR_SOLAR_PARK,
    *,
    complete_days_only: bool = True,
) -> pd.DataFrame:
    """Aggregate hourly data to the daily step the cleaning agent acts on.

    Irradiance is summed to Wh/m2/day; drivers are averaged; rainfall is summed
    because it is the natural-cleaning trigger in the Kimber soiling model.

    POWER serves UTC, and Dubai is UTC+4, so converting to local time leaves a
    truncated day at each end of the record -- including a phantom day in the
    following calendar year holding only four hours. Those partial days would
    understate daily irradiance and leak a spurious year into any groupby, so
    by default only days with a full 24 hours are returned. Pass
    ``complete_days_only=False`` to keep them.
    """
    local = to_local(frame, site)
    aggregations = {
        "ALLSKY_SFC_SW_DWN": "sum",
        "ALLSKY_SFC_SW_DNI": "sum",
        "ALLSKY_SFC_SW_DIFF": "sum",
        "CLRSKY_SFC_SW_DWN": "sum",
        "T2M": "mean",
        "WS2M": "mean",
        "RH2M": "mean",
        "PRECTOTCORR": "sum",
        "AOD_55": "mean",
    }
    present = {k: v for k, v in aggregations.items() if k in local.columns}
    resampled = local.resample("D")
    daily = resampled.agg(present)

    if complete_days_only:
        daily = daily.loc[resampled.size() == HOURS_PER_DAY]

    daily.index.name = "date_local"
    return daily
