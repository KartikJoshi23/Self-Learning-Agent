"""M5 acceptance check -- partial observability.

The Phase 3 plan declared M5's verification before M5 was built:

    (a) Belief RMSE against the true latent soiling.
    (b) The recurrent/belief agent beats the memoryless agent under observation
        noise, and the gap widens as noise rises.
    (c) Memoryless PPO degrades -- confirming partial observability is genuinely
        binding, not decorative.

Point (c) is the one that matters. M4 ended in a null result: with soiling
observed exactly and cleaning a perfect reset, a one-parameter threshold rule
beat PPO, because the optimal policy simply *is* a threshold on an observed
scalar. If making soiling latent does not break that rule, the whole Tier 2
premise is wrong and should be abandoned rather than defended.

Usage:
    python scripts/m5_verify.py [--seeds 3] [--timesteps 800000] [--skip-ppo]
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

from rimal.agents import PPOConfig, PPOPolicy, train  # noqa: E402
from rimal.baselines import (  # noqa: E402
    BeliefThreshold,
    FixedInterval,
    ScheduleAwareThreshold,
    SoilingThreshold,
)
from rimal.config import DATA  # noqa: E402
from rimal.env import (  # noqa: E402
    BeliefStateWrapper,
    EnvConfig,
    ObservationNoise,
    RimalCleaningEnv,
)
from rimal.eval import evaluate  # noqa: E402

FIGURE_DIR = Path(__file__).resolve().parents[1] / "figures"
RESULTS: list[tuple[str, bool, str]] = []

TRAIN_YEARS = DATA.train_years
HOLDOUT_YEARS = DATA.holdout_years
NOISE_LEVELS = (0.01, 0.03, 0.06, 0.10)
THRESHOLD = 0.93


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")


def noisy_config(years, noise: float) -> EnvConfig:
    return EnvConfig(
        years=years,
        observability="noisy",
        observation_noise=ObservationNoise(base_std=noise),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--timesteps", type=int, default=800_000)
    parser.add_argument("--skip-ppo", action="store_true")
    args = parser.parse_args()

    print("\nM5 ACCEPTANCE -- partial observability\n")

    # --- (a) Belief accuracy ------------------------------------------------
    print("[1] Belief accuracy against the true latent soiling")
    raw_errors, belief_errors = [], []
    for year in HOLDOUT_YEARS:
        env = BeliefStateWrapper(RimalCleaningEnv(noisy_config(HOLDOUT_YEARS, 0.03)))
        env.reset(seed=0, options={"year": year})
        while True:
            _, _, terminated, _, info = env.step(0)
            raw_errors.append(info["observed_ratio"] - info["soiling_ratio"])
            belief_errors.append(info["believed_ratio"] - info["soiling_ratio"])
            if terminated:
                break
    raw_rmse = float(np.sqrt(np.mean(np.square(raw_errors))))
    belief_rmse = float(np.sqrt(np.mean(np.square(belief_errors))))

    check(
        "the Kalman belief is substantially more accurate than the raw reading",
        belief_rmse < raw_rmse / 3.0,
        f"RMSE {belief_rmse:.5f} vs raw {raw_rmse:.5f} "
        f"({raw_rmse / belief_rmse:.1f}x reduction)",
    )
    check(
        "the belief is unbiased",
        abs(float(np.mean(belief_errors))) < 0.002,
        f"mean error {np.mean(belief_errors):+.5f}",
    )

    # --- (c) Does partial observability actually bite? ----------------------
    print("\n[2] Does partial observability break the M4-winning rule?")
    rows = []
    for noise in NOISE_LEVELS:
        env = RimalCleaningEnv(noisy_config(HOLDOUT_YEARS, noise))
        entry = {"noise": noise}
        for policy in (
            SoilingThreshold(THRESHOLD),
            ScheduleAwareThreshold(THRESHOLD),
            BeliefThreshold(THRESHOLD),
            FixedInterval(31),
        ):
            frame = evaluate(env, policy, HOLDOUT_YEARS)
            key = (
                "naive"
                if policy.name.startswith("threshold")
                else "guarded"
                if "guarded" in policy.name
                else "belief"
                if "belief" in policy.name
                else "blind_fixed"
            )
            entry[key] = frame["net_usd"].mean()
            entry[f"{key}_cleans"] = frame["cleans"].mean()
        rows.append(entry)
    sweep = pd.DataFrame(rows)

    exact_env = RimalCleaningEnv(EnvConfig(years=HOLDOUT_YEARS))
    exact_net = evaluate(exact_env, SoilingThreshold(THRESHOLD), HOLDOUT_YEARS)[
        "net_usd"
    ].mean()

    print(f"      exact-observability threshold-{THRESHOLD} (the M4 winner): ${exact_net:,.0f}")
    print(
        sweep[["noise", "naive", "naive_cleans", "guarded", "belief", "blind_fixed"]]
        .to_string(index=False, float_format=lambda v: f"{v:,.1f}")
    )

    worst = sweep.iloc[-1]
    check(
        "the naive threshold degrades badly as noise rises",
        worst["naive"] < exact_net - 2000,
        f"${worst['naive']:,.0f} at noise {worst['noise']:.2f} vs "
        f"${exact_net:,.0f} exact (-${exact_net - worst['naive']:,.0f})",
    )
    check(
        "it degrades by over-cleaning, not under-cleaning",
        worst["naive_cleans"] > 4 * sweep.iloc[0]["naive_cleans"],
        f"{sweep.iloc[0]['naive_cleans']:.1f} -> {worst['naive_cleans']:.1f} cleans/yr",
    )
    check(
        "beyond some noise a BLIND fixed interval beats the sensor-driven rule",
        bool((sweep["blind_fixed"] > sweep["naive"]).any()),
        "first at noise "
        f"{sweep.loc[sweep['blind_fixed'] > sweep['naive'], 'noise'].min():.2f}",
    )

    # --- (b) Belief recovers it ---------------------------------------------
    print("\n[3] Does belief tracking recover the loss?")
    check(
        "the belief policy stays within 0.5% of exact observability at every noise level",
        bool(((exact_net - sweep["belief"]) / exact_net < 0.005).all()),
        f"worst gap ${(exact_net - sweep['belief']).max():,.0f} "
        f"({(exact_net - sweep['belief']).max() / exact_net * 100:.2f}%)",
    )
    check(
        "the belief-vs-naive gap widens as noise rises",
        bool(
            (sweep["belief"] - sweep["naive"]).is_monotonic_increasing
            and (sweep["belief"] - sweep["naive"]).iloc[-1]
            > (sweep["belief"] - sweep["naive"]).iloc[0]
        ),
        "gap "
        + " -> ".join(f"${g:,.0f}" for g in (sweep["belief"] - sweep["naive"]))
        + " across noise "
        + " -> ".join(f"{n:.2f}" for n in sweep["noise"]),
    )
    check(
        "filtering beats the cheap guard, so the filter earns its place",
        bool((sweep["belief"] > sweep["guarded"]).all()),
        f"belief exceeds guarded by ${(sweep['belief'] - sweep['guarded']).min():,.0f}"
        f"-${(sweep['belief'] - sweep['guarded']).max():,.0f}",
    )

    # --- PPO: memoryless vs belief-state ------------------------------------
    ppo_rows: list[dict] = []
    if not args.skip_ppo:
        print(f"\n[4] PPO at noise 0.03: memoryless vs belief-state "
              f"({args.seeds} seeds x {args.timesteps:,} steps)")
        train_config = noisy_config(TRAIN_YEARS, 0.03)
        holdout_config = noisy_config(HOLDOUT_YEARS, 0.03)
        ppo_config = PPOConfig(total_timesteps=args.timesteps)

        for label, wrapper in (("memoryless", None), ("belief-state", BeliefStateWrapper)):
            for seed in range(args.seeds):
                network, normaliser, _ = train(
                    train_config, ppo_config, seed=seed, progress=False, wrapper=wrapper
                )
                env = RimalCleaningEnv(holdout_config)
                if wrapper is not None:
                    env = wrapper(env)
                frame = evaluate(env, PPOPolicy(network, normaliser), HOLDOUT_YEARS)
                ppo_rows.append(
                    {
                        "agent": label,
                        "seed": seed,
                        "net_usd": frame["net_usd"].mean(),
                        "cleans": frame["cleans"].mean(),
                    }
                )
                print(
                    f"      {label:<13} seed {seed}: ${ppo_rows[-1]['net_usd']:,.0f}, "
                    f"{ppo_rows[-1]['cleans']:.1f} cleans"
                )

        ppo = pd.DataFrame(ppo_rows)
        summary = ppo.groupby("agent")["net_usd"].agg(["mean", "std"])
        print("\n", summary.to_string(float_format=lambda v: f"{v:,.1f}"))

        memoryless = summary.loc["memoryless", "mean"]
        belief_state = summary.loc["belief-state", "mean"]
        check(
            "the belief-state agent beats the memoryless agent under noise",
            belief_state > memoryless,
            f"${belief_state:,.0f} vs ${memoryless:,.0f} "
            f"({belief_state - memoryless:+,.0f})",
        )

    # --- Figure -------------------------------------------------------------
    FIGURE_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5))

    axes[0].axhline(exact_net, ls="--", color="#1b1b1b",
                    label=f"exact observability (${exact_net:,.0f})")
    for key, label, colour in (
        ("naive", "naive threshold", "#c0392b"),
        ("guarded", "guarded threshold", "#c2731a"),
        ("belief", "Kalman belief threshold", "#2e7d32"),
        ("blind_fixed", "blind fixed-31d", "#5a6b7b"),
    ):
        axes[0].plot(sweep["noise"], sweep[key], "o-", color=colour, label=label)
    axes[0].set_xlabel("observation noise (relative std)")
    axes[0].set_ylabel("net value (USD/MWp/yr), held-out")
    axes[0].set_title("Partial observability breaks the threshold rule")
    axes[0].legend(fontsize=8, loc="lower left")

    axes[1].plot(sweep["noise"], sweep["naive_cleans"], "o-", color="#c0392b",
                 label="naive threshold")
    axes[1].plot(sweep["noise"], sweep["belief_cleans"], "o-", color="#2e7d32",
                 label="Kalman belief threshold")
    axes[1].set_xlabel("observation noise (relative std)")
    axes[1].set_ylabel("cleans per year")
    axes[1].set_title("The failure mode is chatter, not neglect")
    axes[1].legend(fontsize=8)

    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    out = FIGURE_DIR / "m5_partial_observability.png"
    fig.savefig(out, dpi=130)
    print(f"\n      figure written to {out.relative_to(Path.cwd())}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 62)
    if failed:
        print(f"M5 FAILED -- {len(failed)} check(s): {', '.join(failed)}")
        return 1
    print(f"M5 PASSED -- {len(RESULTS)}/{len(RESULTS)} checks")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
