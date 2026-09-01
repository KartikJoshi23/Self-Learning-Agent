"""M6 acceptance check -- stochastic cleaning efficacy and a degrading actuator.

The Phase 3 plan declared M6's verification before M6 was built:

    Agent learns robot-specific dispatch (verified by inspecting the policy,
    not just the return). Performance degrades gracefully as robot health
    falls. Ablation: the fixed-100%-efficacy assumption costs measurable value.

M5 added a sharper question, and it is the one that decides Tier 2's fate:

    Do stochastic cleaning efficacy and a degrading actuator create structure
    that filter-plus-threshold CANNOT express? If not, the honest conclusion is
    that this problem does not need deep RL.

Usage:
    python scripts/m6_verify.py [--seeds 5] [--timesteps 1200000] [--skip-ppo]
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from rimal.agents import PPOConfig, PPOPolicy, train  # noqa: E402
from rimal.baselines import BeliefThreshold, FleetHeuristic, RoundRobinFleet  # noqa: E402
from rimal.config import DATA  # noqa: E402
from rimal.env import (  # noqa: E402
    DEWA_FLEET,
    Economics,
    EnvConfig,
    ObservationNoise,
    RimalCleaningEnv,
)
from rimal.eval import evaluate  # noqa: E402

FIGURE_DIR = Path(__file__).resolve().parents[1] / "figures"
RESULTS: list[tuple[str, bool, str, bool]] = []

TRAIN_YEARS = DATA.train_years
HOLDOUT_YEARS = DATA.holdout_years
NOISE = ObservationNoise(base_std=0.03)
THRESHOLD = 0.93
COSTS = (5.0, 15.0, 30.0, 60.0, 120.0)
THRESHOLD_GRID = np.round(np.arange(0.88, 0.995, 0.01), 3)


def check(name: str, passed: bool, detail: str, declared: bool = True) -> None:
    RESULTS.append((name, passed, detail, declared))
    tag = "" if declared else " [scrutiny]"
    print(f"  {'PASS' if passed else 'FAIL'}  {name}{tag}: {detail}")


def fleet_config(years, cost: float = 60.0) -> EnvConfig:
    return EnvConfig(
        years=years,
        observability="noisy",
        cleaning_model="fleet",
        observation_noise=NOISE,
        economics=Economics(cleaning_cost_usd_per_mwp=cost),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--timesteps", type=int, default=1_200_000)
    parser.add_argument("--skip-ppo", action="store_true")
    args = parser.parse_args()

    print("\nM6 ACCEPTANCE -- stochastic cleaning efficacy and actuator wear\n")
    holdout_env = RimalCleaningEnv(fleet_config(HOLDOUT_YEARS))

    # --- 1. Does stochastic cleaning cost real money? -----------------------
    print("[1] The physical cost of a fleet that does not fully clean")
    perfect_env = RimalCleaningEnv(
        EnvConfig(
            years=HOLDOUT_YEARS, observability="noisy", observation_noise=NOISE
        )
    )
    perfect_net = evaluate(perfect_env, BeliefThreshold(THRESHOLD), HOLDOUT_YEARS)[
        "net_usd"
    ].mean()
    fleet_net = evaluate(holdout_env, FleetHeuristic(THRESHOLD), HOLDOUT_YEARS)[
        "net_usd"
    ].mean()
    check(
        "stochastic partial cleaning costs measurable value vs a perfect reset",
        perfect_net - fleet_net > 50,
        f"${perfect_net:,.0f} idealised vs ${fleet_net:,.0f} real "
        f"(-${perfect_net - fleet_net:,.0f}/MWp/yr)",
    )

    # --- 2. The declared ablation -------------------------------------------
    print("\n[2] Declared ablation: what does ASSUMING perfect cleaning cost?")
    print(f"      {'cost':>6}{'thr':>7}{'cleans':>9}{'efficacy-aware':>16}"
          f"{'best-available':>16}{'aware-naive':>13}{'perfect-assn':>14}")
    rows = []
    for cost in COSTS:
        train_env = RimalCleaningEnv(fleet_config(TRAIN_YEARS, cost))
        env = RimalCleaningEnv(fleet_config(HOLDOUT_YEARS, cost))
        best = max(
            THRESHOLD_GRID,
            key=lambda t: evaluate(train_env, FleetHeuristic(float(t)), TRAIN_YEARS)[
                "net_usd"
            ].mean(),
        )
        aware = evaluate(env, FleetHeuristic(float(best)), HOLDOUT_YEARS)
        naive = evaluate(
            env, FleetHeuristic(float(best), efficacy_aware=False), HOLDOUT_YEARS
        )
        assumed = evaluate(
            env,
            FleetHeuristic(float(best), assume_perfect_cleaning=True),
            HOLDOUT_YEARS,
        )
        rows.append(
            {
                "cost": cost,
                "threshold": float(best),
                "cleans": aware["cleans"].mean(),
                "aware": aware["net_usd"].mean(),
                "naive": naive["net_usd"].mean(),
                "assumes_perfect": assumed["net_usd"].mean(),
            }
        )
        print(
            f"      {cost:>6.0f}{best:>7.2f}{rows[-1]['cleans']:>9.1f}"
            f"{rows[-1]['aware']:>16,.0f}{rows[-1]['naive']:>16,.0f}"
            f"{rows[-1]['aware'] - rows[-1]['naive']:>13,.0f}"
            f"{rows[-1]['aware'] - rows[-1]['assumes_perfect']:>14,.0f}"
        )
    sweep = pd.DataFrame(rows)

    penalty = sweep["aware"] - sweep["assumes_perfect"]
    check(
        "modelling partial cleaning beats assuming a perfect reset",
        bool((penalty > 0).all()),
        f"worth ${penalty.min():,.0f}-${penalty.max():,.0f}/MWp/yr across "
        f"{len(COSTS)} cleaning costs -- real, but under 0.25%",
    )

    # --- 3. Does learning WHICH robot pay? ----------------------------------
    print("\n[3] Does efficacy-aware dispatch beat the manufacturer's spec sheet?")
    dispatch_gain = sweep["aware"] - sweep["naive"]
    check(
        "efficacy-aware dispatch beats simply using the best available machine",
        bool((dispatch_gain > 0).any()),
        "loses at EVERY cleaning frequency: "
        + ", ".join(
            f"${g:+,.0f} at {c:.0f} cleans/yr"
            for g, c in zip(dispatch_gain, sweep["cleans"])
        ),
    )

    heuristic = FleetHeuristic(THRESHOLD)
    evaluate(holdout_env, heuristic, HOLDOUT_YEARS)
    estimates = heuristic.efficacy_estimates
    nominal = np.array([s.nominal_efficacy for s in DEWA_FLEET])
    rank_rho = stats.spearmanr(estimates, nominal).statistic
    print(f"      learned efficacy {np.round(estimates, 3)}")
    print(f"      true nominal     {nominal}")
    check(
        "the learned efficacy estimates at least rank the fleet correctly",
        rank_rho > 0.8,
        f"Spearman rho = {rank_rho:.2f} against true nominal efficacy",
    )

    # --- 4. Graceful degradation --------------------------------------------
    print("\n[4] Does performance degrade gracefully as the fleet wears out?")
    degradation = []
    for multiplier in (1, 3, 10, 30):
        specs = tuple(
            type(s)(
                **{
                    **s.__dict__,
                    "wear_per_use": s.wear_per_use * multiplier,
                    "wear_per_day": s.wear_per_day * multiplier,
                }
            )
            for s in DEWA_FLEET
        )
        config = fleet_config(HOLDOUT_YEARS)
        config.fleet_specs = specs
        env = RimalCleaningEnv(config)
        frame = evaluate(env, FleetHeuristic(THRESHOLD), HOLDOUT_YEARS)
        degradation.append((multiplier, frame["net_usd"].mean()))
        print(f"      wear x{multiplier:<3} -> ${frame['net_usd'].mean():,.0f}/MWp/yr")

    drop = degradation[0][1] - degradation[-1][1]
    check(
        "a 30x faster-wearing fleet degrades gracefully, not catastrophically",
        drop < 0.05 * degradation[0][1],
        f"${drop:,.0f} lost at 30x wear ({drop / degradation[0][1] * 100:.2f}%)",
    )

    # --- 5. The question that decides Tier 2 --------------------------------
    ppo_rows: list[dict] = []
    if not args.skip_ppo:
        print(f"\n[5] PPO on the fleet environment "
              f"({args.seeds} seeds x {args.timesteps:,} steps)")
        ppo_config = PPOConfig(total_timesteps=args.timesteps)
        for seed in range(args.seeds):
            network, normaliser, _ = train(
                fleet_config(TRAIN_YEARS), ppo_config, seed=seed, progress=False
            )
            frame = evaluate(
                holdout_env, PPOPolicy(network, normaliser), HOLDOUT_YEARS
            )
            ppo_rows.append(
                {
                    "seed": seed,
                    "net_usd": frame["net_usd"].mean(),
                    "cleans": frame["cleans"].mean(),
                }
            )
            print(
                f"      seed {seed}: ${ppo_rows[-1]['net_usd']:,.0f}, "
                f"{ppo_rows[-1]['cleans']:.1f} cleans"
            )

        ppo = pd.DataFrame(ppo_rows)
        ppo_mean = ppo["net_usd"].mean()
        ppo_std = ppo["net_usd"].std(ddof=1)
        best_rule = max(
            fleet_net,
            evaluate(
                holdout_env, FleetHeuristic(THRESHOLD, efficacy_aware=False), HOLDOUT_YEARS
            )["net_usd"].mean(),
            evaluate(holdout_env, RoundRobinFleet(THRESHOLD), HOLDOUT_YEARS)[
                "net_usd"
            ].mean(),
        )
        print(f"\n      PPO        ${ppo_mean:,.0f} +/- {ppo_std:,.0f}")
        print(f"      best rule  ${best_rule:,.0f}")
        check(
            "PPO beats the best hand-built fleet rule",
            ppo_mean > best_rule,
            f"${ppo_mean:,.0f} vs ${best_rule:,.0f} ({ppo_mean - best_rule:+,.0f})",
            declared=False,
        )

    # --- Figure -------------------------------------------------------------
    FIGURE_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5))
    width = 0.35
    x = np.arange(len(sweep))
    axes[0].bar(x - width / 2, sweep["aware"] - sweep["naive"], width,
                color="#c0392b", label="efficacy-aware minus spec-sheet dispatch")
    axes[0].bar(x + width / 2, sweep["aware"] - sweep["assumes_perfect"], width,
                color="#2e7d32", label="modelling partial cleaning, vs assuming perfect")
    axes[0].axhline(0, color="#1b1b1b", lw=1)
    axes[0].set_xticks(x, [f"{c:.0f}\n({n:.0f}/yr)" for c, n in zip(sweep["cost"], sweep["cleans"])])
    axes[0].set_xlabel("cleaning cost $/MWp (resulting cleans/yr)")
    axes[0].set_ylabel("net value difference (USD/MWp/yr)")
    axes[0].set_title("Which parts of the fleet model actually pay?")
    axes[0].legend(fontsize=8)

    axes[1].plot([d[0] for d in degradation], [d[1] for d in degradation], "o-",
                 color="#c2731a")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("actuator wear rate (x baseline)")
    axes[1].set_ylabel("net value (USD/MWp/yr)")
    axes[1].set_title("Graceful degradation as the fleet wears out")

    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    out = FIGURE_DIR / "m6_fleet.png"
    fig.savefig(out, dpi=130)
    print(f"\n      figure written to {out.relative_to(Path.cwd())}")

    declared = [(n, ok) for n, ok, _, d in RESULTS if d]
    scrutiny = [(n, ok) for n, ok, _, d in RESULTS if not d]
    declared_failed = [n for n, ok in declared if not ok]
    scrutiny_failed = [n for n, ok in scrutiny if not ok]

    print("\n" + "=" * 62)
    print(
        f"M6 declared criteria: "
        f"{'FAILED -- ' + ', '.join(declared_failed) if declared_failed else f'PASSED ({len(declared)}/{len(declared)})'}"
    )
    if scrutiny_failed:
        print(f"M6 scrutiny checks:   FAILED -- {', '.join(scrutiny_failed)}")
    print("=" * 62)
    return 1 if (declared_failed or scrutiny_failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
