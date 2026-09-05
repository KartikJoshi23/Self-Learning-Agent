"""Evaluation harness and metrics.

Every policy in RIMAL -- rule-based or learned -- is scored the same way, on
the same years, through this module. The headline number is **net value**:
revenue from delivered energy minus cleaning cost, in USD per MWp per year.

Alongside the mean, the harness reports **CVaR** on the lower tail of the
annual outcome distribution. A policy that is good on average but occasionally
catastrophic is not a policy a utility will accept, and expected-value
comparisons hide exactly that. CVaR becomes central at M7; it is computed from
M3 so the number is comparable across every milestone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from rimal.env.cleaning_env import RimalCleaningEnv


@dataclass(frozen=True)
class EpisodeResult:
    """Outcome of one policy on one year, per MWp."""

    policy: str
    year: int
    energy_kwh: float
    clean_energy_kwh: float
    revenue_usd: float
    cleaning_cost_usd: float
    cleans: int
    mean_soiling_ratio: float
    min_soiling_ratio: float
    days: int
    #: Water drawn over the episode, m3 per MWp. Zero unless a wet crew is in
    #: the fleet; tracked separately from cost because the water budget is a
    #: CONSTRAINT, not a price (see RESEARCH.md E2).
    water_used_m3: float = 0.0

    @property
    def net_usd(self) -> float:
        return self.revenue_usd - self.cleaning_cost_usd

    @property
    def soiling_loss_kwh(self) -> float:
        """Energy the plant failed to deliver because it was dirty."""
        return self.clean_energy_kwh - self.energy_kwh

    @property
    def soiling_loss_pct(self) -> float:
        return 100.0 * self.soiling_loss_kwh / self.clean_energy_kwh


def run_episode(env: RimalCleaningEnv, policy, year: int, *, seed: int = 0) -> EpisodeResult:
    """Run one policy for one calendar year."""
    if hasattr(policy, "reset"):
        policy.reset()
    observation, _ = env.reset(seed=seed, options={"year": year})

    energy = clean_energy = revenue = cost = 0.0
    cleans = days = 0
    water = 0.0
    ratios: list[float] = []

    while True:
        action = policy(days, observation)
        observation, _, terminated, truncated, info = env.step(action)
        energy += info["energy_kwh"]
        clean_energy += info["clean_energy_kwh"]
        revenue += info["revenue_usd"]
        cost += info["cleaning_cost_usd"]
        cleans += int(info["cleaned"])
        ratios.append(info["soiling_ratio"])
        water = info.get("water_used_m3", water)
        days += 1
        if terminated or truncated:
            break

    return EpisodeResult(
        policy=getattr(policy, "name", policy.__class__.__name__),
        year=year,
        energy_kwh=energy,
        clean_energy_kwh=clean_energy,
        revenue_usd=revenue,
        cleaning_cost_usd=cost,
        cleans=cleans,
        mean_soiling_ratio=float(np.mean(ratios)),
        min_soiling_ratio=float(np.min(ratios)),
        days=days,
        water_used_m3=float(water),
    )


def evaluate(env: RimalCleaningEnv, policy, years: tuple[int, ...]) -> pd.DataFrame:
    """Run a policy across ``years`` and return one row per year."""
    rows = []
    for year in years:
        result = run_episode(env, policy, year)
        rows.append(
            {
                "policy": result.policy,
                "year": result.year,
                "net_usd": result.net_usd,
                "revenue_usd": result.revenue_usd,
                "cleaning_cost_usd": result.cleaning_cost_usd,
                "energy_kwh": result.energy_kwh,
                "soiling_loss_pct": result.soiling_loss_pct,
                "cleans": result.cleans,
                "mean_soiling_ratio": result.mean_soiling_ratio,
                "min_soiling_ratio": result.min_soiling_ratio,
            }
        )
    return pd.DataFrame(rows)


def cvar(values: np.ndarray | pd.Series, alpha: float = 0.05) -> float:
    """Conditional Value at Risk on the **lower** tail, for returns.

    ``CVaR_alpha(X) = E[X | X <= VaR_alpha(X)]`` -- the mean of the worst
    ``alpha`` fraction of outcomes. Higher is better, as for the mean.

    With few samples this is a crude estimate: at ``alpha=0.05`` over ten years
    it is simply the worst year. That is reported honestly rather than smoothed,
    and the sample count is always shown beside it.
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError("cannot compute CVaR of an empty sample")

    threshold = np.quantile(array, alpha)
    tail = array[array <= threshold]
    if tail.size == 0:  # pragma: no cover - quantile always includes one point
        tail = np.array([array.min()])
    return float(tail.mean())


@dataclass
class Summary:
    """Aggregate of one policy over a set of years."""

    policy: str
    mean_net_usd: float
    std_net_usd: float
    worst_net_usd: float
    cvar_net_usd: float
    mean_cleans: float
    mean_soiling_loss_pct: float
    n_years: int
    frame: pd.DataFrame = field(repr=False)


def summarise(frame: pd.DataFrame, alpha: float = 0.05) -> Summary:
    net = frame["net_usd"]
    return Summary(
        policy=str(frame["policy"].iloc[0]),
        mean_net_usd=float(net.mean()),
        std_net_usd=float(net.std(ddof=1)) if len(net) > 1 else 0.0,
        worst_net_usd=float(net.min()),
        cvar_net_usd=cvar(net, alpha),
        mean_cleans=float(frame["cleans"].mean()),
        mean_soiling_loss_pct=float(frame["soiling_loss_pct"].mean()),
        n_years=len(frame),
        frame=frame,
    )


def compare(env: RimalCleaningEnv, policies, years: tuple[int, ...]) -> pd.DataFrame:
    """Evaluate several policies on the same years and rank by mean net value."""
    summaries = [summarise(evaluate(env, policy, years)) for policy in policies]
    table = pd.DataFrame(
        [
            {
                "policy": s.policy,
                "mean_net_usd": s.mean_net_usd,
                "std_net_usd": s.std_net_usd,
                "worst_net_usd": s.worst_net_usd,
                "cvar5_net_usd": s.cvar_net_usd,
                "mean_cleans": s.mean_cleans,
                "soiling_loss_pct": s.mean_soiling_loss_pct,
                "n_years": s.n_years,
            }
            for s in summaries
        ]
    )
    return table.sort_values("mean_net_usd", ascending=False).reset_index(drop=True)


def analytic_optimal_interval(
    annual_clean_energy_kwh: float,
    energy_price_usd_per_kwh: float,
    soiling_rate_per_day: float,
    cleaning_cost_usd_per_mwp: float,
) -> float:
    """Closed-form optimal fixed cleaning interval, in days.

    For a constant soiling rate ``r`` and interval ``T``, mean loss over a cycle
    is ``r*T/2``, so annual cost is::

        E * p * r * T / 2  +  C * 365 / T

    Setting the derivative to zero gives ``T* = sqrt(730 * C / (E * p * r))``.

    This ignores rain resets and seasonality, so it is not the truth -- it is an
    independent check that the simulator's swept optimum is the right order of
    magnitude. A large disagreement means one of the two is wrong.
    """
    denominator = annual_clean_energy_kwh * energy_price_usd_per_kwh * soiling_rate_per_day
    if denominator <= 0:
        raise ValueError("energy, price and soiling rate must all be positive")
    return float(np.sqrt(730.0 * cleaning_cost_usd_per_mwp / denominator))
