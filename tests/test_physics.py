"""Tests for the soiling and plant physics.

All offline: synthetic weather, no network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pvlib import soiling as pvlib_soiling

from rimal.config import AOD_CLIMATOLOGY_550NM, SOILING
from rimal.physics.soiling import (
    AodModulatedSoiling,
    KimberSoiling,
    _accumulate,
    observed_accumulation_rate,
)


def _daily(days: int = 120, rain_mm: float = 0.0, aod: float = 0.4) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=days, freq="D", tz="Asia/Dubai")
    return pd.DataFrame(
        {"PRECTOTCORR": np.full(days, rain_mm), "AOD_55": np.full(days, aod)}, index=idx
    )


class TestAccumulationCore:
    def test_dry_spell_accumulates_linearly(self):
        frame = _daily(10)
        rate = pd.Series(0.002, index=frame.index)
        loss = _accumulate(
            rate,
            frame["PRECTOTCORR"],
            cleaning_threshold_mm=6.0,
            grace_period_days=14,
            max_soiling=0.3,
        )
        assert loss.iloc[0] == pytest.approx(0.002)
        assert loss.iloc[9] == pytest.approx(0.020)

    def test_rain_above_threshold_resets_and_grants_grace(self):
        frame = _daily(10)
        frame.iloc[3, frame.columns.get_loc("PRECTOTCORR")] = 12.0
        rate = pd.Series(0.002, index=frame.index)
        loss = _accumulate(
            rate,
            frame["PRECTOTCORR"],
            cleaning_threshold_mm=6.0,
            grace_period_days=3,
            max_soiling=0.3,
        )
        assert loss.iloc[3] == 0.0, "rain day washes the panel clean"
        # Grace period: no re-soiling for the next three days.
        assert loss.iloc[4] == 0.0
        assert loss.iloc[6] == 0.0
        assert loss.iloc[7] > 0.0, "accumulation resumes after grace"

    def test_rain_below_threshold_does_not_clean(self):
        frame = _daily(6, rain_mm=2.0)
        rate = pd.Series(0.002, index=frame.index)
        loss = _accumulate(
            rate,
            frame["PRECTOTCORR"],
            cleaning_threshold_mm=6.0,
            grace_period_days=3,
            max_soiling=0.3,
        )
        assert loss.is_monotonic_increasing and loss.iloc[-1] > 0

    def test_max_soiling_caps_accumulation(self):
        frame = _daily(500)
        rate = pd.Series(0.002, index=frame.index)
        loss = _accumulate(
            rate,
            frame["PRECTOTCORR"],
            cleaning_threshold_mm=6.0,
            grace_period_days=14,
            max_soiling=0.3,
        )
        assert loss.max() == pytest.approx(0.3)

    def test_negative_rate_rejected(self):
        frame = _daily(5)
        with pytest.raises(ValueError, match="non-negative"):
            _accumulate(
                pd.Series(-0.001, index=frame.index),
                frame["PRECTOTCORR"],
                cleaning_threshold_mm=6.0,
                grace_period_days=14,
                max_soiling=0.3,
            )

    def test_mismatched_index_rejected(self):
        frame = _daily(5)
        with pytest.raises(ValueError, match="share an index"):
            _accumulate(
                pd.Series(0.001, index=frame.index[:4]),
                frame["PRECTOTCORR"],
                cleaning_threshold_mm=6.0,
                grace_period_days=14,
                max_soiling=0.3,
            )


class TestKimber:
    def test_matches_pvlib_reference_on_a_dry_spell(self):
        """Our accumulation core must agree with pvlib's Kimber implementation.

        Compared on a rain-free window, where the two share identical
        semantics and any divergence is a bug in ours.
        """
        frame = _daily(60)
        ours = 1.0 - KimberSoiling(soiling_loss_rate=0.0015).soiling_ratio(frame)

        hourly_rain = pd.Series(
            0.0, index=pd.date_range(frame.index[0], periods=60 * 24, freq="h")
        )
        reference = pvlib_soiling.kimber(hourly_rain, soiling_loss_rate=0.0015)
        reference_daily = reference.resample("D").last()

        assert ours.iloc[-1] == pytest.approx(reference_daily.iloc[-1], abs=2e-3)

    def test_default_rate_is_inside_the_dewa_band(self):
        rate = KimberSoiling().soiling_loss_rate
        assert SOILING.rate_min_per_day <= rate <= SOILING.rate_max_per_day

    def test_soiling_ratio_is_a_retained_fraction(self):
        ratio = KimberSoiling().soiling_ratio(_daily(30))
        assert ratio.iloc[0] < 1.0
        assert (ratio > 0).all() and (ratio <= 1.0).all()
        assert ratio.is_monotonic_decreasing


class TestAodModulated:
    def test_aod_at_the_climatological_reference_gives_the_mean_rate(self):
        """The reference is a FIXED climatological constant, not the frame's own
        mean. A window whose dust happens to sit at the climatological average
        soils at the mean rate; a dustier window soils faster, which is the
        point. Using the frame's mean instead made a year's dynamics depend on
        which other years were loaded alongside it -- see AOD_CLIMATOLOGY_550NM.
        """
        model = AodModulatedSoiling(mean_loss_rate=0.002)
        at_reference = _daily(50, aod=AOD_CLIMATOLOGY_550NM)
        assert model.daily_rate(at_reference).to_numpy() == pytest.approx(0.002)

    def test_a_dustier_window_soils_faster_than_the_climatology(self):
        # Bounds widened: the default clip at DEWA's 0.33 %/day would mask the
        # scaling this test is about.
        model = AodModulatedSoiling(mean_loss_rate=0.002, rate_bounds=(0.0, 1.0))
        dusty = model.daily_rate(_daily(10, aod=2 * AOD_CLIMATOLOGY_550NM))
        assert dusty.to_numpy() == pytest.approx(0.004)

    def test_the_reference_does_not_depend_on_the_window(self):
        """The same dust must imply the same rate however it is sliced."""
        model = AodModulatedSoiling(mean_loss_rate=0.002)
        short = model.daily_rate(_daily(10, aod=0.6))
        long = model.daily_rate(_daily(400, aod=0.6))
        assert short.iloc[0] == pytest.approx(long.iloc[0])

    def test_dusty_days_soil_faster_than_clean_days(self):
        frame = _daily(4)
        frame["AOD_55"] = [0.2, 0.4, 0.6, 0.8]
        rates = AodModulatedSoiling(
            mean_loss_rate=0.002, rate_bounds=(0.0, 1.0)
        ).daily_rate(frame)
        assert rates.is_monotonic_increasing

    def test_rate_is_clipped_to_the_dewa_band(self):
        frame = _daily(4)
        frame["AOD_55"] = [0.01, 0.4, 0.5, 5.0]
        rates = AodModulatedSoiling().daily_rate(frame)
        assert rates.min() >= SOILING.rate_min_per_day
        assert rates.max() <= SOILING.rate_max_per_day

    def test_nonpositive_reference_rejected(self):
        with pytest.raises(ValueError, match="positive and finite"):
            AodModulatedSoiling(aod_reference=0.0).daily_rate(_daily(5))


class TestObservedRate:
    def test_excludes_resets_and_flat_days(self):
        frame = _daily(20)
        frame.iloc[10, frame.columns.get_loc("PRECTOTCORR")] = 20.0
        ratio = KimberSoiling(soiling_loss_rate=0.002).soiling_ratio(frame)
        increments = observed_accumulation_rate(ratio)
        assert (increments > 0).all(), "only genuine accumulation should survive"
        assert increments.max() == pytest.approx(0.002, abs=1e-9)
