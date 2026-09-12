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
3. The units of hourly ``PRECTOTCORR`` are not stable upstream. Between
   2026-08-29 and 2026-09-11 the hourly endpoint switched this one parameter
   from a mm/day *rate* to a per-hour *depth* while every other column stayed
   byte-identical (2020: ``old == 24 * new`` to within the 0.005 mm rounding
   of the new product; annual mean x days went from 171.5 mm to 7.1 mm while
   the daily product stayed at 171.4 mm). Every fetch therefore establishes
   the units it was served against POWER's own daily product for the same
   year and normalises to the project's canonical form -- see
   ``RAIN_CANONICAL_UNITS`` -- before anything is cached. A fetch whose units
   cannot be established is refused.

Fetches are cached to parquet keyed by site and year, so the first call needs
network access and every subsequent call does not. Cached files hold canonical
units and are re-validated against physical bounds every time they are read.
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
POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

#: NASA POWER's documented sentinel for a missing value.
FILL_VALUE = -999.0

#: Canonical units for hourly ``PRECTOTCORR`` throughout this project: a
#: **mm/day rate**, the form the endpoint served when every cached year and
#: every published result was produced. ``daily_summary`` averages it.
#:
#: The hourly endpoint has served the same parameter as a per-hour depth since
#: at least 2026-09-11 (module docstring, point 3). Rather than move the
#: project onto whichever form the endpoint serves today -- which would
#: invalidate every cached year and fail again the next time it changes --
#: each fetch is classified against POWER's daily product for the same year
#: and converted to this form before it is cached.
RAIN_CANONICAL_UNITS = "mm/day rate"

#: Hourly values in mm/day-rate form sum, over a year, to 24x the daily
#: product's annual total; per-hour depths sum to 1x. The two forms are
#: distinguished by that ratio and converted by this factor.
RAIN_RATE_PER_DEPTH = 24.0

#: How far the hourly/daily annual-total ratio may sit from 24 (rate) or 1
#: (depth) and still be classified. The two forms differ by a factor of 24, so
#: this is generous without being ambiguous; the rounding loss of the depth
#: product (drizzle hours below 0.005 mm round to zero) was measured at 0.7%.
RAIN_UNITS_TOLERANCE = 0.10

#: Physically impossible values, rejected regardless of the sentinel used.
#:
#: Relying on the documented -999 alone is not enough. Observed 2026-09-10: the
#: hourly endpoint served PRECTOTCORR as roughly -99,000 for every hour of 2020
#: while every other parameter was healthy and the daily product was correct.
#: Nothing about that value is -999, so it passed straight through -- and since
#: rainfall drives the natural-cleaning resets, a fresh clone would have run the
#: whole soiling model with zero rain washes and produced quietly wrong results.
#: Validate on physics, not on a magic number, and fail loudly.
PHYSICAL_FLOOR: dict[str, float] = {
    "ALLSKY_SFC_SW_DWN": 0.0,
    "ALLSKY_SFC_SW_DNI": 0.0,
    "ALLSKY_SFC_SW_DIFF": 0.0,
    "CLRSKY_SFC_SW_DWN": 0.0,
    "PRECTOTCORR": 0.0,
    "AOD_55": 0.0,
    "WS2M": 0.0,
    "RH2M": 0.0,
    "T2M": -90.0,
}

#: Refuse a parameter whose values are missing more often than this.
MAX_MISSING_FRACTION = 0.05

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
    return _clean(frame)


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    """Turn sentinels and physically impossible values into NaN.

    Applied to fresh payloads and to cached files alike: a file written before
    a guard existed must not bypass it. Observed 2026-09-11 -- the lead-in year
    2015 had been cached with PRECTOTCORR at -99,000 for every hour, nine
    minutes before the physical-floor guard was committed, and read back
    unchecked into the training environment as a -16,498 mm/day rain on
    1 January 2016.
    """
    # NaN rather than pd.NA: these columns stay float64 so pvlib and numpy can
    # consume them directly without an object-dtype detour.
    frame = frame.replace(FILL_VALUE, np.nan)

    # Then reject anything physically impossible, whatever sentinel produced it.
    for column, floor in PHYSICAL_FLOOR.items():
        if column in frame.columns:
            frame.loc[frame[column] < floor, column] = np.nan
    return frame


def _validate(frame: pd.DataFrame, year: int, source: str = "NASA POWER") -> None:
    """Refuse a frame that is too incomplete to use.

    Failing here is the point: a silently wrong rainfall series is far worse
    than a fetch that stops and says so.
    """
    missing = frame.isna().mean()
    bad = missing[missing > MAX_MISSING_FRACTION]
    if not bad.empty:
        detail = ", ".join(f"{name} {share:.0%} missing" for name, share in bad.items())
        raise PowerFetchError(
            f"{source} holds unusable data for {year}: {detail}. "
            "Values outside physical bounds are treated as missing; this usually "
            "means an upstream fault on those parameters rather than a bug here. "
            "If the source is a cached file, delete it and fetch again."
        )


def _fetch_daily_rain_total_mm(year: int, site: Site) -> float:
    """Annual rainfall for ``year`` from POWER's *daily* product, in mm.

    The daily product is the units reference for the hourly one: its
    ``PRECTOTCORR`` has stayed a mm/day depth throughout, and its annual total
    is what any correct reading of the hourly series must reproduce.
    """
    response = requests.get(
        POWER_DAILY_URL,
        params={
            "parameters": "PRECTOTCORR",
            "community": "RE",
            "latitude": site.latitude,
            "longitude": site.longitude,
            "start": f"{year}0101",
            "end": f"{year}1231",
            "format": "JSON",
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    if not response.ok:
        raise PowerFetchError(
            f"NASA POWER daily product returned HTTP {response.status_code} for "
            f"{year}; cannot establish the units of the hourly rainfall"
        )
    try:
        values = response.json()["properties"]["parameter"]["PRECTOTCORR"]
    except (KeyError, TypeError, ValueError) as exc:
        raise PowerFetchError(
            f"NASA POWER daily product for {year} had no PRECTOTCORR: {exc}"
        ) from exc
    daily = pd.Series(values, dtype="float64").replace(FILL_VALUE, np.nan)
    daily[daily < 0.0] = np.nan
    return float(daily.sum())


def _rain_units_factor(hourly_total: float, daily_total_mm: float, year: int) -> float:
    """Return the factor that puts an hourly rainfall series into canonical units.

    ``hourly_total`` is the plain sum of the hourly values over the year;
    ``daily_total_mm`` is the daily product's annual total. Their ratio is
    ~24 when the hourly series is a mm/day rate (canonical: factor 1) and ~1
    when it is a per-hour depth (factor 24). Anything else is refused.
    """
    if not daily_total_mm > 0.0:
        raise PowerFetchError(
            f"NASA POWER daily product reports no rainfall for {year}; the units "
            "of the hourly series cannot be established"
        )
    ratio = hourly_total / daily_total_mm
    if abs(ratio / RAIN_RATE_PER_DEPTH - 1.0) <= RAIN_UNITS_TOLERANCE:
        return 1.0
    if abs(ratio - 1.0) <= RAIN_UNITS_TOLERANCE:
        return RAIN_RATE_PER_DEPTH
    raise PowerFetchError(
        f"NASA POWER hourly PRECTOTCORR for {year} sums to {ratio:.2f}x the daily "
        f"product's annual total ({daily_total_mm:.1f} mm); expected ~24 (mm/day "
        "rate) or ~1 (per-hour depth). Refusing to guess the units."
    )


def _normalise_rain_units(frame: pd.DataFrame, year: int, site: Site) -> pd.DataFrame:
    """Convert a freshly fetched frame's rainfall to ``RAIN_CANONICAL_UNITS``."""
    if "PRECTOTCORR" not in frame.columns:
        return frame
    factor = _rain_units_factor(
        float(frame["PRECTOTCORR"].sum()),
        _fetch_daily_rain_total_mm(year, site),
        year,
    )
    if factor != 1.0:
        logger.info(
            "NASA POWER served hourly PRECTOTCORR for %d as a per-hour depth; "
            "converted x%g to the canonical %s",
            year,
            factor,
            RAIN_CANONICAL_UNITS,
        )
        frame = frame.copy()
        frame["PRECTOTCORR"] = frame["PRECTOTCORR"] * factor
    return frame


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
    idempotent and offline-replayable. A cached file is re-validated on every
    read and refused, naming the file, if it fails -- it holds canonical
    rainfall units by construction, but the physical-bounds guard must not be
    bypassable by a file written before the guard existed.
    """
    path = _cache_path(site, year, cache_dir)
    if path.exists() and not force_refresh:
        logger.debug("cache hit for %s %d", site.name, year)
        frame = _clean(pd.read_parquet(path))
        _validate(frame, year, source=f"cached file {path}")
        return frame

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

    # Validate BEFORE caching, so a bad fetch is never written to disk. Bounds
    # first, then units: a corrupt series has no units worth establishing.
    _validate(frame, year)
    frame = _normalise_rain_units(frame, year, site)

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


def complete_local_days(
    frame: pd.DataFrame, site: Site = MBR_SOLAR_PARK
) -> pd.DataFrame:
    """Trim an hourly frame to whole local days.

    POWER serves UTC and Dubai is UTC+4, so tz-converting the record leaves a
    truncated day at the start and a phantom four-hour day in the *following*
    calendar year. Left in place, the phantom leaks a spurious near-zero year
    into any annual groupby and understates the first day's irradiation. Every
    consumer that groups by day or by year must trim first.
    """
    local = to_local(frame, site)
    hours = local.resample("D").size()
    whole = hours[hours == HOURS_PER_DAY].index
    return local[local.index.normalize().isin(whole)]


def daily_summary(
    frame: pd.DataFrame,
    site: Site = MBR_SOLAR_PARK,
    *,
    complete_days_only: bool = True,
) -> pd.DataFrame:
    """Aggregate hourly data to the daily step the cleaning agent acts on.

    Irradiance is summed to Wh/m2/day, because POWER serves it as W/m2 and an
    hourly step makes the sum an energy. Drivers are averaged.

    Rainfall is **averaged, not summed**. Hourly ``PRECTOTCORR`` reaches this
    function in the project's canonical form -- a mm/day *rate*, which is what
    POWER served on 2026-08-29 -- so summing the 24 hourly values overcounts by
    24x. Verified 2026-08-29 for 2020: the hourly mean totals 171.5 mm/yr
    against POWER's own daily product at 171.4 mm/yr, while the sum gives
    4116 mm. This matters a great deal: rainfall is the natural-cleaning
    trigger, and the 24x error turned 4 washing days per year into 40.

    The endpoint has since switched to serving a per-hour depth (module
    docstring, point 3), which averaged here would be 24x too *low* -- 7.1 mm
    for 2020. ``fetch_year`` establishes the served units against the daily
    product and converts to the canonical rate before caching, so this
    function's contract does not move with the endpoint.

    POWER serves UTC, and Dubai is UTC+4, so converting to local time leaves a
    truncated day at each end of the record -- including a phantom day in the
    following calendar year holding only four hours. Those partial days would
    understate daily irradiance and leak a spurious year into any groupby, so
    by default only days with a full 24 hours are returned. Pass
    ``complete_days_only=False`` to keep them.
    """
    local = (
        complete_local_days(frame, site)
        if complete_days_only
        else to_local(frame, site)
    )
    aggregations = {
        "ALLSKY_SFC_SW_DWN": "sum",
        "ALLSKY_SFC_SW_DNI": "sum",
        "ALLSKY_SFC_SW_DIFF": "sum",
        "CLRSKY_SFC_SW_DWN": "sum",
        "T2M": "mean",
        "WS2M": "mean",
        "RH2M": "mean",
        "PRECTOTCORR": "mean",  # canonical mm/day rate - see docstring; NOT summed
        "AOD_55": "mean",
    }
    present = {k: v for k, v in aggregations.items() if k in local.columns}
    daily = local.resample("D").agg(present)
    daily.index.name = "date_local"
    return daily
