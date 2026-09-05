"""M7 acceptance check -- risk sensitivity and the water constraint.

The Phase 3 plan declared M7's verification before M7 was built:

    Constraint satisfaction rate >= target with minimal return sacrifice.
    CVaR@5% improves versus the risk-neutral agent under injected shamals, at a
    quantified cost in mean return.

M7 also had to fix a defect in M1 before any of that could be measured. The
AOD-modulated soiling model clipped its daily rate to DEWA's 0.14-0.33 %/day
band, on the reasoning that no day should exceed what was observed at the site.
But that band is an *average* over a 13-month trial, not a per-day ceiling, and
the clip pinned 18.7% of days at the cap, compressing an 8x spread in measured
AOD into a 1.5x spread in soiling. It removed the tail that risk-sensitive
control exists to manage. Quantifying that is check [1].

Usage:
    python scripts/m7_verify.py [--seeds 3] [--timesteps 400000] [--skip-agents]
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from rimal.agents import QRDQNConfig, QRDQNPolicy, train_qrdqn  # noqa: E402
from rimal.baselines import BeliefThreshold, FleetHeuristic  # noqa: E402
from rimal.config import DATA  # noqa: E402
from rimal.env import (  # noqa: E402
    FLEET_WITH_WET_CREW,
    EnvConfig,
    ObservationNoise,
    RimalCleaningEnv,
)
from rimal.eval import cvar, run_episode  # noqa: E402

FIGURE_DIR = Path(__file__).resolve().parents[1] / "figures"
RESULTS: list[tuple[str, bool, str, bool]] = []

ALL_YEARS = tuple(range(2016, 2026))
TRAIN_YEARS = DATA.train_years
HOLDOUT_YEARS = DATA.holdout_years
NOISE = ObservationNoise(base_std=0.03)
EVAL_SEEDS = 25
#: Seeds per held-out year for the like-for-like comparison, so a 5% tail has
#: several samples rather than one.
FAIR_SEEDS = 60
THRESHOLDS = (0.88, 0.90, 0.92, 0.94, 0.96, 0.97)


def check(name: str, passed: bool, detail: str, declared: bool = True) -> None:
    RESULTS.append((name, passed, detail, declared))
    tag = "" if declared else " [scrutiny]"
    print(f"  {'PASS' if passed else 'FAIL'}  {name}{tag}: {detail}")


def base_config(years, soiling_model="storm", **kwargs) -> EnvConfig:
    return EnvConfig(
        years=years,
        observability="noisy",
        soiling_model=soiling_model,
        observation_noise=NOISE,
        **kwargs,
    )


def episodes(env, policy, years, seeds=EVAL_SEEDS) -> np.ndarray:
    """Many episodes so a 5% tail has enough samples to mean anything."""
    return np.array(
        [run_episode(env, policy, y, seed=s).net_usd for y in years for s in range(seeds)]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--timesteps", type=int, default=400_000)
    parser.add_argument("--skip-agents", action="store_true")
    args = parser.parse_args()

    print("\nM7 ACCEPTANCE -- risk sensitivity and the water constraint\n")
    print(f"      {len(ALL_YEARS)} years x {EVAL_SEEDS} seeds = "
          f"{len(ALL_YEARS) * EVAL_SEEDS} episodes per policy\n")

    # --- 1. What did the M1 clipping bug hide? ------------------------------
    print("[1] The tail M1 clipped away")
    frontier = {}
    for model in ("aod", "storm"):
        env = RimalCleaningEnv(base_config(ALL_YEARS, model))
        rows = []
        for threshold in THRESHOLDS:
            nets = episodes(env, BeliefThreshold(threshold), ALL_YEARS)
            rows.append(
                {
                    "threshold": threshold,
                    "mean": nets.mean(),
                    "std": nets.std(ddof=1),
                    "cvar5": cvar(nets, 0.05),
                }
            )
        frontier[model] = pd.DataFrame(rows)

    clipped, storms = frontier["aod"], frontier["storm"]
    cvar_overstated = clipped["cvar5"].max() - storms["cvar5"].max()
    check(
        "clipping the soiling rate materially overstated CVaR",
        cvar_overstated > 100,
        f"best CVaR@5% ${clipped['cvar5'].max():,.0f} clipped vs "
        f"${storms['cvar5'].max():,.0f} with storms -- overstated by "
        f"${cvar_overstated:,.0f}/MWp/yr",
    )

    # --- 2. Is there a risk/return trade-off at all? ------------------------
    print("\n[2] Risk/return frontier over threshold rules")
    print(storms.to_string(index=False, float_format=lambda v: f"{v:,.1f}"))
    mean_optimal = storms.loc[storms["mean"].idxmax(), "threshold"]
    cvar_optimal = storms.loc[storms["cvar5"].idxmax(), "threshold"]
    mean_cost = storms["mean"].max() - storms.loc[storms["cvar5"].idxmax(), "mean"]
    cvar_gain = storms["cvar5"].max() - storms.loc[storms["mean"].idxmax(), "cvar5"]
    check(
        "the mean-optimal and CVaR-optimal policies genuinely differ",
        mean_optimal != cvar_optimal,
        f"mean-optimal threshold {mean_optimal:.2f}, CVaR-optimal {cvar_optimal:.2f}; "
        f"buying ${cvar_gain:,.0f} of CVaR costs ${mean_cost:,.0f} of mean",
    )
    check(
        "clipping destroyed that trade-off entirely",
        clipped.loc[clipped["mean"].idxmax(), "threshold"]
        == clipped.loc[clipped["cvar5"].idxmax(), "threshold"],
        f"under clipping both optima sit at "
        f"{clipped.loc[clipped['mean'].idxmax(), 'threshold']:.2f} -- no trade-off to study",
    )

    # --- 3. The water CMDP ---------------------------------------------------
    print("\n[3] Water budget as a constrained MDP")
    water_rows = []
    for budget in (None, 60.0, 30.0, 15.0):
        config = base_config(
            HOLDOUT_YEARS,
            cleaning_model="fleet",
            fleet_specs=FLEET_WITH_WET_CREW,
            water_budget_m3_per_mwp=budget,
        )
        env = RimalCleaningEnv(config)
        results = [
            run_episode(env, FleetHeuristic(0.94, specs=FLEET_WITH_WET_CREW), y, seed=s)
            for y in HOLDOUT_YEARS
            for s in range(10)
        ]
        nets = np.array([r.net_usd for r in results])
        water = np.array([r.water_used_m3 for r in results])
        satisfied = 1.0 if budget is None else float((water <= budget + 1e-9).mean())
        water_rows.append(
            {
                "budget": np.inf if budget is None else budget,
                "mean_net": nets.mean(),
                "water_p95": np.percentile(water, 95),
                "satisfaction": satisfied,
            }
        )
        label = "unconstrained" if budget is None else f"{budget:.0f} m3/MWp"
        print(
            f"      {label:<16} net ${nets.mean():>10,.0f}   "
            f"water p95 {np.percentile(water, 95):>6.1f} m3   "
            f"satisfied {satisfied * 100:>5.1f}%"
        )
    water_frame = pd.DataFrame(water_rows)
    constrained = water_frame[np.isfinite(water_frame["budget"])]
    check(
        "the water constraint is satisfied whenever it is imposed",
        bool((constrained["satisfaction"] >= 0.999).all()),
        f"{constrained['satisfaction'].min() * 100:.1f}% minimum satisfaction "
        f"across {len(constrained)} budgets",
    )
    sacrifice = water_frame["mean_net"].iloc[0] - constrained["mean_net"].min()
    check(
        "constraint satisfaction costs little return",
        sacrifice < 0.02 * water_frame["mean_net"].iloc[0],
        f"tightest budget costs ${sacrifice:,.0f}/MWp/yr "
        f"({sacrifice / water_frame['mean_net'].iloc[0] * 100:.2f}%)",
    )

    # --- 4. The declared agent criterion ------------------------------------
    agent_rows: list[dict] = []
    if not args.skip_agents:
        print(f"\n[4] QR-DQN: does CVaR selection beat risk-neutral selection? "
              f"({args.seeds} seeds x {args.timesteps:,} steps)")
        holdout_env = RimalCleaningEnv(base_config(HOLDOUT_YEARS))
        for seed in range(args.seeds):
            network, normaliser = train_qrdqn(
                base_config(TRAIN_YEARS),
                QRDQNConfig(total_timesteps=args.timesteps),
                seed=seed,
                progress=False,
            )
            for alpha in (1.0, 0.5, 0.25, 0.1):
                policy = QRDQNPolicy(network, normaliser, alpha=alpha)
                nets = episodes(holdout_env, policy, HOLDOUT_YEARS, seeds=10)
                agent_rows.append(
                    {
                        "seed": seed,
                        "alpha": alpha,
                        "mean": nets.mean(),
                        "cvar5": cvar(nets, 0.05),
                    }
                )
            done = [r for r in agent_rows if r["seed"] == seed]
            print(
                f"      seed {seed}: "
                + "  ".join(
                    f"a={r['alpha']:.2f} mean ${r['mean']:,.0f} cvar ${r['cvar5']:,.0f}"
                    for r in done
                )
            )

        agents = pd.DataFrame(agent_rows).groupby("alpha")[["mean", "cvar5"]].mean()
        print("\n", agents.to_string(float_format=lambda v: f"{v:,.1f}"))

        # The declared criterion is deliberately NOT evaluated by picking the
        # best alpha after seeing the results. With four risk levels, three
        # seeds and a seed sd of order $50, the maximum of four noisy numbers
        # will beat the reference by chance -- a garden of forking paths. An
        # earlier version of this check did exactly that and reported a PASS
        # that the better-powered evaluation in [5] then contradicted.
        #
        # The real claim is that risk aversion buys tail protection, which
        # implies CVaR should rise *monotonically* as alpha falls. That is a
        # single pre-specified prediction, and it either holds or it does not.
        ordered = agents.sort_index(ascending=False)  # alpha 1.0 -> 0.1
        monotone = bool(ordered["cvar5"].is_monotonic_increasing)
        print("      CVaR by risk level (alpha 1.00 = risk-neutral):")
        for alpha, row in ordered.iterrows():
            print(f"        alpha {alpha:.2f}  mean ${row['mean']:,.0f}  CVaR ${row['cvar5']:,.0f}")
        check(
            "CVaR@5% rises monotonically as risk aversion increases",
            monotone,
            "monotone in alpha"
            if monotone
            else "NOT monotone -- "
            + " -> ".join(f"${c:,.0f}" for c in ordered["cvar5"])
            + f" as alpha falls 1.00 -> {ordered.index.min():.2f}; "
            "the ordering is noise, not risk sensitivity",
        )
        # A LIKE-FOR-LIKE comparison. The frontier in [2] is not one: it sweeps
        # thresholds over all ten years and picks the best on the same data the
        # score is read from, which is oracle selection, and it uses 250
        # episodes against the agent's 30. Here the threshold is tuned on the
        # TRAINING years only and both are scored on the same held-out episodes,
        # with enough seeds that a 5% tail is not one or two samples.
        print("\n[5] Like-for-like: threshold tuned on TRAIN, both scored on HELD-OUT")
        train_env = RimalCleaningEnv(base_config(TRAIN_YEARS))
        tuned = max(
            THRESHOLDS,
            key=lambda t: cvar(
                episodes(train_env, BeliefThreshold(t), TRAIN_YEARS), 0.05
            ),
        )
        rule_nets = episodes(
            holdout_env, BeliefThreshold(tuned), HOLDOUT_YEARS, seeds=FAIR_SEEDS
        )
        rule_cvar, rule_mean = cvar(rule_nets, 0.05), rule_nets.mean()

        fair_rows = []
        for seed in range(args.seeds):
            network, normaliser = train_qrdqn(
                base_config(TRAIN_YEARS),
                QRDQNConfig(total_timesteps=args.timesteps),
                seed=seed + 100,
                progress=False,
            )
            for alpha in (1.0, 0.25, 0.1):
                nets = episodes(
                    holdout_env,
                    QRDQNPolicy(network, normaliser, alpha=alpha),
                    HOLDOUT_YEARS,
                    seeds=FAIR_SEEDS,
                )
                fair_rows.append(
                    {"seed": seed, "alpha": alpha, "mean": nets.mean(), "cvar5": cvar(nets, 0.05)}
                )
        fair = pd.DataFrame(fair_rows)
        fair_summary = fair.groupby("alpha")[["mean", "cvar5"]].agg(["mean", "std"])
        print(f"      CVaR-tuned threshold {tuned:.2f} (tuned on train): "
              f"mean ${rule_mean:,.0f}, CVaR ${rule_cvar:,.0f}  "
              f"[{len(rule_nets)} episodes]")
        print(fair_summary.to_string(float_format=lambda v: f"{v:,.1f}"))

        best_fair_alpha = fair.groupby("alpha")["cvar5"].mean().idxmax()
        best_fair = fair[fair["alpha"] == best_fair_alpha]
        margin = best_fair["cvar5"].mean() - rule_cvar
        seed_sd = best_fair["cvar5"].std(ddof=1)
        check(
            "the risk-sensitive agent beats the CVaR-tuned rule, like for like",
            margin > 0 and margin > 2 * seed_sd,
            f"alpha={best_fair_alpha:.2f}: CVaR ${best_fair['cvar5'].mean():,.0f} vs rule "
            f"${rule_cvar:,.0f} ({margin:+,.0f}), seed sd ${seed_sd:,.0f} at n={args.seeds}"
            f"; mean ${best_fair['mean'].mean():,.0f} vs ${rule_mean:,.0f}",
            declared=False,
        )

    # --- Figure ---------------------------------------------------------------
    FIGURE_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5))
    for model, label, colour in (
        ("aod", "M1 clipped rate (no tail)", "#5a6b7b"),
        ("storm", "M7 storms preserved", "#c0392b"),
    ):
        f = frontier[model]
        axes[0].plot(f["mean"], f["cvar5"], "o-", color=colour, label=label)
        for _, row in f.iterrows():
            axes[0].annotate(f"{row['threshold']:.2f}", (row["mean"], row["cvar5"]),
                             fontsize=7, xytext=(3, 3), textcoords="offset points")
    if agent_rows:
        agents = pd.DataFrame(agent_rows).groupby("alpha")[["mean", "cvar5"]].mean()
        axes[0].plot(agents["mean"], agents["cvar5"], "s--", color="#2e7d32",
                     label="QR-DQN, risk level alpha")
    axes[0].set_xlabel("mean net value (USD/MWp/yr)")
    axes[0].set_ylabel("CVaR@5% (USD/MWp/yr)")
    axes[0].set_title("Risk/return frontier")
    axes[0].legend(fontsize=8, loc="lower right")

    axes[1].plot(water_frame["budget"].replace(np.inf, 90), water_frame["mean_net"],
                 "o-", color="#c2731a")
    axes[1].set_xlabel("water budget (m$^3$/MWp/yr; rightmost = unconstrained)")
    axes[1].set_ylabel("mean net value (USD/MWp/yr)")
    axes[1].set_title("Cost of the water constraint")

    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    out = FIGURE_DIR / "m7_risk.png"
    fig.savefig(out, dpi=130)
    print(f"\n      figure written to {out.relative_to(Path.cwd())}")

    declared = [(n, ok) for n, ok, _, d in RESULTS if d]
    scrutiny = [(n, ok) for n, ok, _, d in RESULTS if not d]
    declared_failed = [n for n, ok in declared if not ok]
    scrutiny_failed = [n for n, ok in scrutiny if not ok]

    print("\n" + "=" * 62)
    print(
        "M7 declared criteria: "
        + (
            "FAILED -- " + ", ".join(declared_failed)
            if declared_failed
            else f"PASSED ({len(declared)}/{len(declared)})"
        )
    )
    if scrutiny_failed:
        print(f"M7 scrutiny checks:   FAILED -- {', '.join(scrutiny_failed)}")
    print("=" * 62)
    return 1 if (declared_failed or scrutiny_failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
