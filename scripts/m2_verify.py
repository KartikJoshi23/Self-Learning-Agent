"""M2 acceptance check.

The Phase 3 plan declared M2's verification before M2 was built:

    gymnasium.utils.env_checker passes. Sanity ordering holds: always-clean >
    periodic > never-clean on energy, and the reverse on cost.

Two further checks are added because M2 introduced machinery the plan did not
anticipate: the precomputed energy lookup must agree with the true pvlib chain,
and the environment's internal soiling must match the standalone soiling model
exactly. Both are places where a silent divergence would poison every later
milestone.

Usage:
    python scripts/m2_verify.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import gymnasium as gym  # noqa: E402
from gymnasium.utils.env_checker import check_env  # noqa: E402

from rimal.data import power  # noqa: E402
from rimal.env import (  # noqa: E402
    ACTION_CLEAN,
    ACTION_NOOP,
    EnergyLookup,
    EnvConfig,
    RimalCleaningEnv,
    build_energy_table,
    register,
)
from rimal.physics import KimberSoiling, hourly_ac_energy  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")


def rollout(env: RimalCleaningEnv, policy, year: int) -> dict:
    obs, _ = env.reset(seed=0, options={"year": year})
    energy = cost = revenue = 0.0
    cleans = 0
    ratios = []
    day = 0
    while True:
        action = policy(day, obs)
        obs, reward, terminated, truncated, info = env.step(action)
        energy += info["energy_kwh"]
        cost += info["cleaning_cost_usd"]
        revenue += info["revenue_usd"]
        cleans += int(info["cleaned"])
        ratios.append(info["soiling_ratio"])
        day += 1
        if terminated or truncated:
            break
    return {
        "energy_kwh": energy,
        "cost_usd": cost,
        "revenue_usd": revenue,
        "net_usd": revenue - cost,
        "cleans": cleans,
        "mean_ratio": float(np.mean(ratios)),
        "days": day,
    }


def main() -> int:
    print("\nM2 ACCEPTANCE -- Gymnasium environment v0\n")
    config = EnvConfig()
    env = RimalCleaningEnv(config)

    # --- 1. Gymnasium API compliance ---------------------------------------
    print("[1] Gymnasium API compliance")
    try:
        check_env(RimalCleaningEnv(config), skip_render_check=True)
        check("gymnasium.utils.env_checker passes", True, "no violations reported")
    except Exception as exc:  # noqa: BLE001
        check("gymnasium.utils.env_checker passes", False, f"{type(exc).__name__}: {exc}")

    register()
    try:
        made = gym.make("Rimal-Cleaning-v0")
        made.reset(seed=0)
        made.close()
        check("registers and builds via gym.make", True, "Rimal-Cleaning-v0")
    except Exception as exc:  # noqa: BLE001
        check("registers and builds via gym.make", False, str(exc))

    # --- 2. Energy lookup fidelity -----------------------------------------
    print("\n[2] Precomputed energy lookup vs the true pvlib chain")
    lookup = EnergyLookup(build_energy_table(2016, 2025))
    hourly = power.fetch_years(2020, 2020)
    daily_index = power.daily_summary(hourly).index

    worst = 0.0
    for probe in (0.73, 0.81, 0.87, 0.95, 0.99):
        series = pd.Series(probe, index=daily_index)
        truth = hourly_ac_energy(hourly, soiling_ratio=series).resample("D").sum() / 1000.0
        approx = np.array(
            [lookup.energy_kwh(lookup.row_for_date(d), probe) for d in daily_index]
        )
        rel = abs(approx.sum() - truth.sum()) / truth.sum()
        worst = max(worst, rel)
    check(
        "interpolated energy within 0.1% of pvlib at off-grid ratios",
        worst < 0.001,
        f"worst annual error {worst * 100:.4f}% across five off-grid ratios",
    )

    # --- 3. Environment soiling matches the standalone model ---------------
    print("\n[3] Environment soiling matches the standalone soiling model")
    # The reference must be built from the SAME fetch span the environment
    # uses. A year's daily frame depends on the span: the first local day of a
    # year is only complete when the previous year's final UTC hours are
    # present, so fetching 2020 alone yields 365 days from 02 Jan while
    # fetching 2016-2025 yields 366 from 01 Jan.
    # The model is run on the 2020 slice, not on the full span sliced afterwards:
    # an episode starts with a clean panel, whereas a continuous 2016-2025 run
    # would carry December 2019's soiling into 01 January 2020.
    span = power.daily_summary(power.fetch_years(min(config.years), max(config.years)))
    reference = KimberSoiling().soiling_ratio(span[span.index.year == 2020])

    obs, _ = env.reset(seed=0, options={"year": 2020})
    observed: dict[pd.Timestamp, float] = {}
    while True:
        obs, _, terminated, _, info = env.step(ACTION_NOOP)
        observed[info["date"]] = info["soiling_ratio"]
        if terminated:
            break

    # The env reports the ratio *before* the day's accumulation; the standalone
    # model reports it after. Align on dates, then shift one day.
    dates = sorted(observed)
    pairs = [
        (observed[today], reference.loc[yesterday])
        for yesterday, today in zip(dates, dates[1:])
    ]
    deviation = max(abs(a - b) for a, b in pairs)
    check(
        "never-clean trajectory reproduces KimberSoiling exactly",
        deviation < 1e-9,
        f"max absolute deviation {deviation:.2e} over {len(pairs)} aligned days",
    )

    # --- 4. The declared sanity ordering -----------------------------------
    print("\n[4] Policy ordering (the check the plan declared)")
    policies = {
        "never-clean": lambda d, o: ACTION_NOOP,
        "clean every 30d": lambda d, o: ACTION_CLEAN if d % 30 == 0 else ACTION_NOOP,
        "always-clean": lambda d, o: ACTION_CLEAN,
    }
    results = {name: rollout(env, fn, 2020) for name, fn in policies.items()}

    print(f"      {'policy':<18}{'energy kWh':>13}{'cleans':>9}{'cost $':>11}{'net $':>11}")
    for name, r in results.items():
        print(
            f"      {name:<18}{r['energy_kwh']:>13,.0f}{r['cleans']:>9}"
            f"{r['cost_usd']:>11,.0f}{r['net_usd']:>11,.0f}"
        )

    check(
        "energy: always-clean > periodic > never-clean",
        results["always-clean"]["energy_kwh"]
        > results["clean every 30d"]["energy_kwh"]
        > results["never-clean"]["energy_kwh"],
        f"{results['always-clean']['energy_kwh']:,.0f} > "
        f"{results['clean every 30d']['energy_kwh']:,.0f} > "
        f"{results['never-clean']['energy_kwh']:,.0f} kWh",
    )
    check(
        "cost: always-clean > periodic > never-clean",
        results["always-clean"]["cost_usd"]
        > results["clean every 30d"]["cost_usd"]
        > results["never-clean"]["cost_usd"],
        f"{results['always-clean']['cost_usd']:,.0f} > "
        f"{results['clean every 30d']['cost_usd']:,.0f} > "
        f"{results['never-clean']['cost_usd']:,.0f} USD",
    )
    check(
        "never-clean incurs no cleaning cost and never cleans",
        results["never-clean"]["cost_usd"] == 0.0
        and results["never-clean"]["cleans"] == 0,
        "0 cleans, $0",
    )
    check(
        "always-clean holds the panel clean",
        results["always-clean"]["mean_ratio"] > 0.999,
        f"mean soiling ratio {results['always-clean']['mean_ratio']:.4f}",
    )

    # --- 5. Determinism -----------------------------------------------------
    print("\n[5] Determinism and episode length")
    again = rollout(env, policies["clean every 30d"], 2020)
    check(
        "same seed and year reproduce the same rollout",
        np.isclose(again["net_usd"], results["clean every 30d"]["net_usd"]),
        f"net ${again['net_usd']:,.2f} on both runs",
    )
    check(
        "episode covers a full year",
        results["never-clean"]["days"] in (365, 366),
        f"{results['never-clean']['days']} steps for 2020 (a leap year)",
    )

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 62)
    if failed:
        print(f"M2 FAILED -- {len(failed)} check(s): {', '.join(failed)}")
        return 1
    print(f"M2 PASSED -- {len(RESULTS)}/{len(RESULTS)} checks")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
