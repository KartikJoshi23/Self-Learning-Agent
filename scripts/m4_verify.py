"""M4 acceptance check -- the final Tier 1 milestone.

The Phase 3 plan declared M4's verification before M4 was built:

    Beats every fixed-interval baseline on HELD-OUT years (train 2016-2022,
    test 2023-2025). Seed variance reported over >=5 seeds. This is the
    "does it learn at all" gate.

That declared criterion is the PASS/FAIL gate here, because it is what was
approved.

But it is not the whole truth, and the fuller comparison is reported alongside
it. M3 found that a condition-based soiling-threshold policy beats every fixed
interval, and named ``threshold-0.95`` as the bar. That bar was **under-tuned**:
a fine sweep shows the true optimum is 0.93. Both the tuned threshold and the
tuned fixed interval are selected here on the *training* years -- exactly the
protocol PPO gets -- so the comparison is like for like.

Usage:
    python scripts/m4_verify.py [--seeds 5] [--timesteps 1500000]
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from rimal.agents import PPOConfig, PPOPolicy, train  # noqa: E402
from rimal.baselines import (  # noqa: E402
    standard_baselines,
    tune_fixed_interval,
    tune_threshold,
)
from rimal.config import DATA  # noqa: E402
from rimal.env import EnvConfig, RimalCleaningEnv  # noqa: E402
from rimal.eval import compare, evaluate  # noqa: E402

FIGURE_DIR = Path(__file__).resolve().parents[1] / "figures"
RESULTS: list[tuple[str, bool, str]] = []

TRAIN_YEARS = DATA.train_years
HOLDOUT_YEARS = DATA.holdout_years


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--timesteps", type=int, default=1_500_000)
    args = parser.parse_args()

    print("\nM4 ACCEPTANCE -- PPO agent\n")
    print(f"      train    {TRAIN_YEARS}")
    print(f"      held-out {HOLDOUT_YEARS}")
    print(f"      {args.seeds} seeds x {args.timesteps:,} timesteps\n")

    # --- Baselines (the bar) ------------------------------------------------
    holdout_env = RimalCleaningEnv(EnvConfig(years=HOLDOUT_YEARS))
    train_env = RimalCleaningEnv(EnvConfig(years=TRAIN_YEARS))

    print("[1] Tuning the baselines on TRAINING years (same protocol as PPO)")

    def on_train(policy):
        return evaluate(train_env, policy, TRAIN_YEARS)["net_usd"].mean()

    tuned_threshold = tune_threshold(on_train)
    tuned_fixed = tune_fixed_interval(on_train)
    print(f"      {tuned_threshold.name}  and  {tuned_fixed.name}")

    policies = standard_baselines() + [tuned_threshold, tuned_fixed]
    baseline_table = compare(holdout_env, policies, HOLDOUT_YEARS)
    best_baseline = baseline_table.iloc[0]
    fixed_rows = baseline_table[baseline_table["policy"].str.contains("fixed-")]
    best_fixed = fixed_rows.iloc[0]

    print("\n      Baselines on held-out years (the bar to beat)")
    print(baseline_table.to_string(index=False, float_format=lambda v: f"{v:,.1f}"))

    # --- Train --------------------------------------------------------------
    print(f"\n[2] Training PPO on {TRAIN_YEARS}")
    train_config = EnvConfig(years=TRAIN_YEARS)
    ppo_config = PPOConfig(total_timesteps=args.timesteps)

    rows, logs, policies = [], [], []
    for seed in range(args.seeds):
        print(f"\n    seed {seed}")
        started = time.time()
        network, normaliser, log = train(train_config, ppo_config, seed=seed)
        policy = PPOPolicy(network, normaliser, name=f"ppo-s{seed}")
        policies.append(policy)
        logs.append(log)

        frame = evaluate(holdout_env, policy, HOLDOUT_YEARS)
        rows.append(
            {
                "seed": seed,
                "net_usd": frame["net_usd"].mean(),
                "cleans": frame["cleans"].mean(),
                "soiling_loss_pct": frame["soiling_loss_pct"].mean(),
                "worst_year_usd": frame["net_usd"].min(),
            }
        )
        print(
            f"      trained in {time.time() - started:.0f}s -> held-out "
            f"${rows[-1]['net_usd']:,.0f}/MWp/yr, {rows[-1]['cleans']:.1f} cleans"
        )

    seeds_frame = pd.DataFrame(rows)

    # --- Results ------------------------------------------------------------
    print("\n[3] PPO on held-out years, per seed")
    print(seeds_frame.to_string(index=False, float_format=lambda v: f"{v:,.1f}"))

    mean_net = seeds_frame["net_usd"].mean()
    std_net = seeds_frame["net_usd"].std(ddof=1)
    worst_seed = seeds_frame["net_usd"].min()

    print(
        f"\n      PPO mean ${mean_net:,.0f} +/- {std_net:,.0f} "
        f"(worst seed ${worst_seed:,.0f}) over {args.seeds} seeds"
    )
    print(
        f"      best baseline: {best_baseline['policy']} "
        f"${best_baseline['mean_net_usd']:,.0f}"
    )
    print(f"      best fixed interval: {best_fixed['policy']} ${best_fixed['mean_net_usd']:,.0f}")

    check(
        "PPO beats the best FIXED-INTERVAL baseline (the plan's declared bar)",
        mean_net > best_fixed["mean_net_usd"],
        f"${mean_net:,.0f} vs ${best_fixed['mean_net_usd']:,.0f} "
        f"({mean_net - best_fixed['mean_net_usd']:+,.0f})",
    )
    check(
        "the margin over fixed intervals exceeds seed noise",
        mean_net - std_net > best_fixed["mean_net_usd"],
        f"mean - 1 sd = ${mean_net - std_net:,.0f} vs "
        f"${best_fixed['mean_net_usd']:,.0f}",
    )
    check(
        "every seed beats never-cleaning",
        bool(
            (
                seeds_frame["net_usd"]
                > baseline_table.loc[
                    baseline_table["policy"] == "never-clean", "mean_net_usd"
                ].iloc[0]
            ).all()
        ),
        f"worst seed ${worst_seed:,.0f}",
    )
    check(
        "seed variance is reported",
        args.seeds >= 5,
        f"{args.seeds} seeds, sd ${std_net:,.0f} "
        f"({std_net / abs(mean_net) * 100:.2f}% of mean)",
    )
    check(
        "the learned policy is not degenerate",
        bool(0 < seeds_frame["cleans"].mean() < 365),
        f"mean {seeds_frame['cleans'].mean():.1f} cleans/yr "
        f"(range {seeds_frame['cleans'].min():.0f}-{seeds_frame['cleans'].max():.0f})",
    )

    # --- Figure -------------------------------------------------------------
    FIGURE_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5))

    for seed, log in enumerate(logs):
        axes[0].plot(log.timesteps, log.episode_return, lw=1.0, alpha=0.85, label=f"seed {seed}")
    axes[0].axhline(
        best_baseline["mean_net_usd"], ls="--", color="#1b1b1b",
        label=f"best baseline ({best_baseline['policy']})",
    )
    axes[0].set_xlabel("environment steps")
    axes[0].set_ylabel("episode return (USD/MWp/yr, training years)")
    axes[0].set_title("PPO learning curves")
    axes[0].legend(fontsize=8, loc="lower right")

    labels = list(baseline_table["policy"]) + ["PPO (mean)"]
    values = list(baseline_table["mean_net_usd"]) + [mean_net]
    errors = [0.0] * len(baseline_table) + [std_net]
    colours = ["#c2731a"] * len(baseline_table) + ["#2e7d32"]
    order = np.argsort(values)
    axes[1].barh(
        [labels[i] for i in order],
        [values[i] for i in order],
        xerr=[errors[i] for i in order],
        color=[colours[i] for i in order],
    )
    axes[1].set_xlabel("mean net value (USD/MWp/yr), held-out 2023-2025")
    axes[1].set_title("PPO vs baselines on unseen years")

    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    out = FIGURE_DIR / "m4_ppo.png"
    fig.savefig(out, dpi=130)
    print(f"\n      figure written to {out.relative_to(Path.cwd())}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 62)
    if failed:
        print(f"M4 FAILED -- {len(failed)} check(s): {', '.join(failed)}")
        return 1
    print(f"M4 PASSED -- {len(RESULTS)}/{len(RESULTS)} checks")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
