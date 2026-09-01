"""Tests for the partial-observability machinery (M5)."""

from __future__ import annotations

import numpy as np
import pytest

from rimal.env.observation import ObservationNoise, SoilingKalmanFilter


class TestObservationNoise:
    def test_noise_grows_as_irradiance_falls(self):
        noise = ObservationNoise(base_std=0.03)
        bright = noise.std_for(clean_energy_kwh=5000.0, reference_kwh=5000.0)
        dim = noise.std_for(clean_energy_kwh=1250.0, reference_kwh=5000.0)
        assert bright == pytest.approx(0.03)
        assert dim == pytest.approx(0.06)  # sqrt(4) = 2x

    def test_noise_multiplier_is_capped(self):
        noise = ObservationNoise(base_std=0.03, max_std_multiplier=4.0)
        assert noise.std_for(1e-9, 5000.0) == pytest.approx(0.12)
        assert noise.std_for(0.0, 5000.0) == pytest.approx(0.12)

    def test_noise_never_falls_below_base(self):
        noise = ObservationNoise(base_std=0.03)
        assert noise.std_for(clean_energy_kwh=50_000.0, reference_kwh=5000.0) == pytest.approx(0.03)

    def test_observations_are_unbiased(self):
        noise = ObservationNoise(base_std=0.05)
        rng = np.random.default_rng(0)
        samples = [noise.observe(0.9, 5000.0, 5000.0, rng)[0] for _ in range(20_000)]
        assert np.mean(samples) == pytest.approx(0.9, abs=0.002)

    def test_observations_are_clipped(self):
        noise = ObservationNoise(base_std=5.0, clip=(0.3, 1.3))
        rng = np.random.default_rng(0)
        values = [noise.observe(0.9, 5000.0, 5000.0, rng)[0] for _ in range(500)]
        assert min(values) >= 0.3 and max(values) <= 1.3


class TestSoilingKalmanFilter:
    def test_tracks_a_noiseless_ramp_exactly(self):
        kf = SoilingKalmanFilter()
        truth = 0.0
        for day in range(50):
            if day:
                kf.predict(0.002)
                truth += 0.002
            kf.update(1.0 - truth, 0.03)
        assert kf.loss == pytest.approx(truth, abs=1e-3)

    def test_recovers_the_signal_from_noisy_readings(self):
        rng = np.random.default_rng(0)
        kf = SoilingKalmanFilter()
        truth = 0.0
        errors = []
        for day in range(120):
            if day:
                kf.predict(0.002)
                truth += 0.002
            kf.update((1.0 - truth) * (1 + rng.normal(0, 0.03)), 0.03)
            errors.append(kf.loss - truth)
        rmse = float(np.sqrt(np.mean(np.square(errors[20:]))))
        assert rmse < 0.01, "filter should beat the 0.03 per-reading noise"

    def test_reset_event_zeroes_the_belief(self):
        kf = SoilingKalmanFilter()
        for _ in range(30):
            kf.predict(0.002)
        assert kf.loss > 0.05
        kf.on_reset_event()
        assert kf.loss == 0.0
        assert kf.believed_ratio == pytest.approx(1.0)

    def test_rain_reset_grants_a_grace_period(self):
        """Rain leaves the surface damp; the Kimber model does not re-soil
        during the grace window, and neither may the filter."""
        kf = SoilingKalmanFilter(grace_period_days=14)
        kf.on_reset_event(grace=True)
        for _ in range(14):
            kf.predict(0.002)
        assert kf.loss == pytest.approx(0.0), "no accumulation during grace"
        kf.predict(0.002)
        assert kf.loss == pytest.approx(0.002), "accumulation resumes after grace"

    def test_machine_cleaning_grants_no_grace(self):
        kf = SoilingKalmanFilter(grace_period_days=14)
        kf.on_reset_event(grace=False)
        kf.predict(0.002)
        assert kf.loss == pytest.approx(0.002)

    def test_belief_saturates_at_the_cap(self):
        kf = SoilingKalmanFilter(max_loss=0.3)
        for _ in range(500):
            kf.predict(0.002)
        assert kf.loss == pytest.approx(0.3)

    def test_belief_never_goes_negative(self):
        kf = SoilingKalmanFilter()
        for _ in range(50):
            kf.update(1.4, 0.03)  # readings implying negative soiling
        assert kf.loss >= 0.0

    def test_a_confident_reading_moves_the_belief_more(self):
        precise, vague = SoilingKalmanFilter(), SoilingKalmanFilter()
        for kf in (precise, vague):
            for _ in range(10):
                kf.predict(0.002)
        before = precise.loss
        precise.update(0.90, 0.005)
        vague.update(0.90, 0.20)
        assert abs(precise.loss - before) > abs(vague.loss - before)
