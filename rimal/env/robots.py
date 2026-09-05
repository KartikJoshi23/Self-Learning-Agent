"""A fleet of cleaning robots with stochastic efficacy and latent health.

Every formulation in the literature -- including the nearest prior work, An
(arXiv:2603.07518), whose Equation (4) sets soiling to exactly zero -- treats
cleaning as a perfect reset. DEWA's own field trial says otherwise.

Over 13 months at the DEWA Cleaning Test Facility (164 modules rated 445-505 W,
22 Jul 2024 to 26 Aug 2025), five autonomous dry-cleaning robots achieved
**cleaning efficiencies of 69-99%**. The same study documented the robots
degrading in service: battery overheating, corrosion, frame misalignment and UV
degradation, prompting a recommended 12-point evaluation checklist.

So two things are true that no published cleaning-schedule model represents:

1. The *action* is stochastic and heterogeneous. Dispatching robot C is not the
   same decision as dispatching robot A, and neither fully cleans the panel.
2. The *actuator* is a second latent state. Health is not observable -- you see
   only the noisy consequences of the cleaning you asked for -- and it can be
   restored by servicing, at a cost.

Together these make robot selection a restless-bandit problem coupled to the
soiling MDP: the agent must infer which machine is currently effective from the
noisy outcomes of its own past choices. A threshold rule has no way to express
that, which is the structural question M6 exists to test.

**What is grounded and what is assumed.** The 69-99% efficacy band and the
failure modes are measured and published. The *rate* at which health decays,
and the shape of the efficacy distribution, are not -- DEWA published no decay
curves. Those are assumptions, marked below, and they are swept in
``scripts/m6_verify.py`` rather than trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from rimal.config import CLEANING


@dataclass(frozen=True)
class RobotSpec:
    """One cleaning machine.

    ``nominal_efficacy`` is the fraction of accumulated soiling the machine
    removes when in perfect health. The five defaults span DEWA's measured
    69-99% band and are labelled with the hardware types the study describes.

    ``efficacy_dispersion`` is the concentration of the Beta distribution the
    realised efficacy is drawn from: larger is tighter. ASSUMPTION -- DEWA
    reported a range across robots, not a per-clean distribution.

    ``wear_per_use`` is the health lost per cleaning pass. ASSUMPTION.
    """

    name: str
    nominal_efficacy: float
    efficacy_dispersion: float = 60.0
    wear_per_use: float = 0.004
    #: Health lost per day regardless of use: UV, corrosion, standing damage.
    wear_per_day: float = 0.0004
    #: Efficacy floor as health goes to zero, relative to nominal.
    min_health_efficacy: float = 0.45
    #: Days the machine is unavailable after a cleaning pass.
    #:
    #: DEWA's trial documented **battery overheating** among the failure modes
    #: of these robots, so a thermal/charge recovery window is the constraint
    #: their own data points to. The specific durations are an ASSUMPTION, and
    #: they matter: without a cooldown the highest-efficacy machine simply
    #: dominates and there is no dispatch decision to make at all. That was the
    #: first version of this model, and the ablation exposed it -- "always use
    #: robot A" beat efficacy-aware dispatch, because nothing ever made robot A
    #: unavailable. More aggressive cleaning draws more power, so cooldown is
    #: scaled with nominal efficacy.
    cooldown_days: int = 3
    #: Cubic metres of water consumed per cleaning pass, per MWp.
    #:
    #: Zero for the dry robots DEWA is trialling. The wet crew is the reason
    #: this field exists: the Phase 2 audit (RESEARCH.md E2) established that
    #: wet washing uses roughly 8.5 m3/MWp/pass -- about 2,105 modules at DEWA's
    #: 445-505 W rating and ~4 L each -- and that its *energy* content is
    #: negligible (about 1% of the energy recovered). Water therefore belongs in
    #: this model as a scarce-resource CONSTRAINT, not as a term in the reward.
    water_m3_per_mwp: float = 0.0


#: The five robots DEWA evaluated, spanning the measured 69-99% band.
#: Bristle vs microfibre and fixed-tilt vs single-axis tracker are the hardware
#: distinctions the study draws; the efficacy assignment across them is ours.
DEWA_FLEET: tuple[RobotSpec, ...] = (
    RobotSpec("A-bristle-fixed", 0.99, cooldown_days=12, wear_per_use=0.010),
    RobotSpec("B-bristle-fixed", 0.93, cooldown_days=8, wear_per_use=0.007),
    RobotSpec("C-microfibre-tracker", 0.86, cooldown_days=5, wear_per_use=0.005),
    RobotSpec("D-bristle-tracker", 0.78, cooldown_days=3, wear_per_use=0.004),
    RobotSpec("E-microfibre-tracker", 0.69, cooldown_days=2, wear_per_use=0.003),
)

#: The dry fleet plus a wet crew. The crew cleans almost perfectly and is always
#: available, but consumes water from a hard annual budget -- the trade the UAE
#: Water Security Strategy 2036 actually poses at a desert solar plant.
FLEET_WITH_WET_CREW: tuple[RobotSpec, ...] = DEWA_FLEET + (
    RobotSpec(
        "W-wet-crew",
        0.98,
        cooldown_days=0,
        wear_per_use=0.0,
        wear_per_day=0.0,
        water_m3_per_mwp=8.5,
    ),
)


@dataclass
class Fleet:
    """Mutable fleet state: latent health plus the observable service log."""

    specs: tuple[RobotSpec, ...] = DEWA_FLEET
    #: Cost of servicing one robot back to full health, USD per MWp.
    service_cost_usd_per_mwp: float = 25.0
    health: np.ndarray = field(init=False)
    uses_since_service: np.ndarray = field(init=False)
    days_since_service: np.ndarray = field(init=False)
    cooldown_remaining: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        if not self.specs:
            raise ValueError("fleet must contain at least one robot")
        if not all(
            CLEANING.efficacy_min <= s.nominal_efficacy <= CLEANING.efficacy_max
            for s in self.specs
        ):
            raise ValueError(
                "nominal efficacies must lie inside DEWA's measured "
                f"{CLEANING.efficacy_min:.2f}-{CLEANING.efficacy_max:.2f} band"
            )
        self.reset()

    @property
    def size(self) -> int:
        return len(self.specs)

    def reset(self) -> None:
        self.water_used_m3 = 0.0
        self.health = np.ones(self.size, dtype=float)
        self.uses_since_service = np.zeros(self.size, dtype=float)
        self.days_since_service = np.zeros(self.size, dtype=float)
        self.cooldown_remaining = np.zeros(self.size, dtype=float)

    def available(self, index: int) -> bool:
        return self.cooldown_remaining[index] <= 0

    def effective_efficacy(self, index: int) -> float:
        """Mean efficacy of robot ``index`` at its current health.

        Health scales efficacy between ``min_health_efficacy`` and 1.0 of
        nominal, so a worn machine still cleans -- just worse. A robot that
        simply stopped working would be trivially detectable; one that quietly
        under-performs is the interesting case, and the one DEWA's failure
        modes describe.
        """
        spec = self.specs[index]
        scale = spec.min_health_efficacy + (1.0 - spec.min_health_efficacy) * self.health[
            index
        ]
        return spec.nominal_efficacy * scale

    def clean(self, index: int, rng: np.random.Generator) -> float:
        """Dispatch robot ``index``. Returns the realised efficacy in [0, 1].

        The draw is Beta with the mean set by current health, so realised
        efficacy varies clean to clean even for a healthy machine. Wear is
        applied after the draw.
        """
        mean = float(np.clip(self.effective_efficacy(index), 1e-3, 1 - 1e-3))
        concentration = self.specs[index].efficacy_dispersion
        realised = float(rng.beta(mean * concentration, (1.0 - mean) * concentration))

        self.health[index] = max(0.0, self.health[index] - self.specs[index].wear_per_use)
        self.uses_since_service[index] += 1.0
        self.cooldown_remaining[index] = self.specs[index].cooldown_days
        self.water_used_m3 += self.specs[index].water_m3_per_mwp
        return realised

    def service(self, index: int) -> float:
        """Restore one robot to full health. Returns the cost incurred."""
        self.health[index] = 1.0
        self.uses_since_service[index] = 0.0
        self.days_since_service[index] = 0.0
        self.cooldown_remaining[index] = 0.0
        return self.service_cost_usd_per_mwp

    def advance_day(self) -> None:
        for i, spec in enumerate(self.specs):
            self.health[i] = max(0.0, self.health[i] - spec.wear_per_day)
        self.days_since_service += 1.0
        self.cooldown_remaining = np.maximum(0.0, self.cooldown_remaining - 1.0)

    def observation(self, max_days: float = 365.0, max_uses: float = 60.0) -> np.ndarray:
        """What the operator can see: the service log, never the health.

        Health is latent by construction. A plant knows how many times it has
        run each machine and how long since it was serviced; it does not know
        how well the machine currently cleans until it tries.
        """
        max_cooldown = max(s.cooldown_days for s in self.specs) or 1
        return np.concatenate(
            [
                np.clip(self.days_since_service / max_days, 0.0, 1.0),
                np.clip(self.uses_since_service / max_uses, 0.0, 1.0),
                np.clip(self.cooldown_remaining / max_cooldown, 0.0, 1.0),
            ]
        ).astype(np.float32)
