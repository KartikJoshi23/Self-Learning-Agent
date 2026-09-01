"""Precomputed daily energy as a function of soiling ratio.

The environment needs daily AC energy for whatever soiling ratio the agent's
history produces, and it needs it thousands of times per second. Running pvlib
inside ``step()`` is far too slow.

The obvious shortcut -- scaling clean-plant energy linearly by the soiling
ratio -- is **not** accurate enough. Measured over 2020-2021 at this site, a
plant at ratio 0.70 produces **2.0% more** than linear scaling predicts, and
even at 0.90 the gap is 0.7%. The effect is physical and systematic: a soiled
array clips less against the inverter and runs cooler, so it recovers part of
the loss. Two percent is the same order as the entire margin an optimised
cleaning policy is competing for, so a linear reward would be measuring mostly
its own approximation error.

Instead the true pvlib chain is evaluated once on a grid of soiling ratios and
the result is interpolated at step time: exact where it matters, O(1) per step,
and cached to parquet so it is computed once per site and year range.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from rimal.config import MBR_SOLAR_PARK, Site
from rimal.data import power
from rimal.physics.plant import PlantConfig, hourly_ac_energy

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "cache"

#: Soiling-ratio grid. The lower bound matches the 0.3 max-soiling cap used by
#: the soiling models; the spacing is set by the interpolation-error budget
#: checked in tests (well under 0.05%).
RATIO_GRID = np.round(np.arange(0.70, 1.0001, 0.02), 4)


def _cache_path(site: Site, start_year: int, end_year: int, cache_dir: Path) -> Path:
    slug = site.name.split("(")[0].strip().lower().replace(" ", "-")
    return cache_dir / f"energy_{slug}_{start_year}_{end_year}.parquet"


def build_energy_table(
    start_year: int,
    end_year: int,
    *,
    site: Site = MBR_SOLAR_PARK,
    config: PlantConfig | None = None,
    ratios: np.ndarray = RATIO_GRID,
    cache_dir: Path = CACHE_DIR,
    force_rebuild: bool = False,
) -> pd.DataFrame:
    """Daily AC energy (kWh) indexed by date, one column per soiling ratio.

    Columns are the ratio values as floats. Cached to parquet.
    """
    path = _cache_path(site, start_year, end_year, cache_dir)
    if path.exists() and not force_rebuild:
        table = pd.read_parquet(path)
        table.columns = table.columns.astype(float)
        return table

    config = config or PlantConfig()
    hourly = power.fetch_years(start_year, end_year, site)
    daily_index = power.daily_summary(hourly, site).index

    columns = {}
    for ratio in ratios:
        logger.info("evaluating soiling ratio %.2f", ratio)
        series = pd.Series(float(ratio), index=daily_index)
        ac = hourly_ac_energy(hourly, soiling_ratio=series, config=config, site=site)
        columns[float(ratio)] = ac.resample("D").sum() / 1000.0  # Wh -> kWh

    table = pd.DataFrame(columns)
    table.index.name = "date_local"

    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path)
    return table


class EnergyLookup:
    """Interpolates daily energy for an arbitrary soiling ratio."""

    def __init__(self, table: pd.DataFrame):
        self.dates = table.index
        self.ratios = np.asarray(table.columns, dtype=float)
        self.values = table.to_numpy(dtype=float)  # (n_days, n_ratios)

        if not np.all(np.diff(self.ratios) > 0):
            raise ValueError("ratio columns must be strictly increasing")

        self._row_of = {date: i for i, date in enumerate(self.dates)}

    def __len__(self) -> int:
        return len(self.dates)

    def energy_kwh(self, day_index: int, soiling_ratio: float) -> float:
        """Energy on ``day_index`` at ``soiling_ratio``, linearly interpolated.

        Ratios outside the grid are clamped: the grid spans the full physically
        reachable range, so clamping only guards against float drift at the
        endpoints.
        """
        ratio = float(np.clip(soiling_ratio, self.ratios[0], self.ratios[-1]))
        return float(np.interp(ratio, self.ratios, self.values[day_index]))

    def clean_energy_kwh(self, day_index: int) -> float:
        return float(self.values[day_index, -1])

    def row_for_date(self, date: pd.Timestamp) -> int:
        return self._row_of[date]
