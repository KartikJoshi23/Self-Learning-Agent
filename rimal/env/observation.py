"""Observation models: what the operator can actually see.

In v0 the agent reads the soiling ratio exactly. No plant can do that. What a
plant measures is daily energy, which it divides by a *modelled* clean-plant
expectation to get a performance ratio. Every term in that division carries
error -- the clear-sky model, temperature and spectral corrections, inverter
behaviour, and long-run degradation, which is confounded with soiling because
both look like a slow decline in yield.

NREL's own stochastic rate-and-recovery method is documented to "falsely
identify soiling in noisy signals, making unsupervised applications
challenging". That is the problem this module reproduces.

The noise is **heteroscedastic**, and deliberately so. The performance ratio is
a quotient, so on a low-irradiance day the same absolute error in energy is a
much larger relative error in the ratio. Winter and dust-storm days -- exactly
the days a cleaning decision matters most -- are the days the signal is worst.
A homoscedastic model would make the problem uniformly easy and would flatter
any filter applied to it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ObservationNoise:
    """Multiplicative, irradiance-dependent noise on the performance ratio.

    ``base_std`` is the relative standard deviation on a reference (high
    irradiance) day. A daily performance-ratio estimate carrying a few percent
    of error is the normal case in the field; the default of 3% sits in that
    range and is swept in ``scripts/m5_verify.py`` rather than trusted.

    For scale: soiling accumulates at roughly 0.235 %/day, so a month of
    accumulation is about 7% while a single day's noise is 3%. The per-day
    signal-to-noise ratio is well below one, which is precisely why a single
    reading cannot be thresholded and some form of filtering or memory is
    required.
    """

    base_std: float = 0.03
    #: Noise grows as irradiance falls; capped so a near-zero-energy day does
    #: not produce an unbounded estimate.
    max_std_multiplier: float = 4.0
    #: Clip on the reported ratio. Noise can legitimately push an estimate
    #: above 1.0 -- a plant can appear to out-produce its model -- and hiding
    #: that would leak information about the true state.
    clip: tuple[float, float] = (0.3, 1.3)

    def std_for(self, clean_energy_kwh: float, reference_kwh: float) -> float:
        """Relative standard deviation for a day of this irradiance."""
        if clean_energy_kwh <= 0.0:
            return self.base_std * self.max_std_multiplier
        ratio = reference_kwh / clean_energy_kwh
        multiplier = min(float(np.sqrt(max(ratio, 1e-9))), self.max_std_multiplier)
        return self.base_std * max(multiplier, 1.0)

    def observe(
        self,
        true_ratio: float,
        clean_energy_kwh: float,
        reference_kwh: float,
        rng: np.random.Generator,
    ) -> tuple[float, float]:
        """Return a noisy performance-ratio estimate and its own noise scale.

        The scale is returned because it is genuinely available to an operator:
        you know how much irradiance you had, so you know how much to trust
        today's reading. A filter is entitled to use it; a naive threshold
        typically does not.
        """
        std = self.std_for(clean_energy_kwh, reference_kwh)
        observed = true_ratio * (1.0 + rng.normal(0.0, std))
        return float(np.clip(observed, *self.clip)), std


class SoilingKalmanFilter:
    """Tracks latent soiling loss from noisy performance-ratio readings.

    The dynamics are close to linear-Gaussian, which makes a Kalman filter the
    right tool rather than a fashionable one:

    * soiling loss grows by a known daily rate, with process noise covering the
      fact that the rate itself is uncertain;
    * cleaning and heavy rain reset it to zero, and both are *observed* events,
      so they enter as known control inputs rather than something to infer;
    * the reading is ``1 - loss`` plus noise whose variance is known for the day.

    Belief is over soiling **loss** (0 = clean) rather than ratio, because that
    is the quantity with the simple additive dynamics.
    """

    def __init__(
        self,
        process_std: float = 0.0008,
        initial_loss: float = 0.0,
        initial_var: float = 1e-6,
        reset_var: float = 1e-8,
        grace_period_days: int = 14,
        max_loss: float = 0.3,
    ):
        self.process_var = process_std**2
        self.initial_loss = initial_loss
        self.initial_var = initial_var
        self.reset_var = reset_var
        self.grace_period_days = grace_period_days
        self.max_loss = max_loss
        self.loss = initial_loss
        self.var = initial_var
        self.grace_remaining = 0

    def reset(self) -> None:
        self.loss = self.initial_loss
        self.var = self.initial_var
        self.grace_remaining = 0

    def on_reset_event(self, grace: bool = False) -> None:
        """A cleaning or a heavy rain wash: the panel is known to be clean.

        ``grace`` marks a *rain* wash. Rain leaves the surface damp, and a damp
        surface does not re-soil for a while -- the Kimber model holds soiling
        at zero for a grace period afterwards. A filter that ignores this keeps
        integrating its daily rate through the grace window and drifts by up to
        ``grace_period_days * rate``, which for this site is about 0.033: the
        same order as the observation noise it is supposed to be removing.
        Cleaning by machine leaves no damp surface, so it grants no grace.
        """
        self.loss = 0.0
        self.var = self.reset_var
        self.grace_remaining = self.grace_period_days if grace else 0

    def apply_partial_clean(self, expected_efficacy: float, efficacy_std: float) -> None:
        """Fold in a cleaning that removes only *part* of the soiling.

        ``on_reset_event`` assumes the panel ends perfectly clean, which is what
        every published formulation assumes and what DEWA's field data
        contradicts: their five robots achieved 69-99%. After dispatching a
        machine of uncertain efficacy the belief must be scaled, not zeroed --
        and its variance must *grow*, because how much was actually removed is
        now uncertain on top of everything else. The subsequent measurement
        updates then correct the estimate, and the size of that correction is
        what reveals the robot's true efficacy.
        """
        efficacy = float(np.clip(expected_efficacy, 0.0, 1.0))
        loss_before = self.loss
        self.loss = loss_before * (1.0 - efficacy)
        # Uncertainty in the removed fraction maps to uncertainty in the
        # remaining loss, proportional to how much there was to remove.
        self.var = self.var * (1.0 - efficacy) ** 2 + (efficacy_std * loss_before) ** 2

    def predict(self, daily_rate: float) -> None:
        if self.grace_remaining > 0:
            self.grace_remaining -= 1
            return
        # Soiling saturates; so must the belief, or it drifts past the cap on a
        # long dry spell and reads as a phantom decline.
        self.loss = min(self.loss + daily_rate, self.max_loss)
        self.var += self.process_var

    def update(self, observed_ratio: float, observation_std: float) -> None:
        """Fold in one performance-ratio reading."""
        measured_loss = 1.0 - observed_ratio
        measurement_var = max(observation_std**2, 1e-12)

        gain = self.var / (self.var + measurement_var)
        self.loss += gain * (measured_loss - self.loss)
        self.var = (1.0 - gain) * self.var
        # Loss cannot be negative; clamping keeps the belief physical without
        # distorting the variance.
        self.loss = max(self.loss, 0.0)

    @property
    def believed_ratio(self) -> float:
        return 1.0 - self.loss
