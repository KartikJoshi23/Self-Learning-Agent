"""Export everything the live site shows, from the engine and the logs.

The site under ``site/`` is a static Next.js build. It contains no numbers of
its own: every figure, curve and animation is driven by the JSON this script
writes to ``site/public/data/``. That keeps the site honest by construction --
it can only show what the engine produces or what an acceptance log recorded.

Files written:

  weather.json   ten years of daily AOD, rainfall, clean-plant energy and the
                 per-day energy correction ``k`` (as ``export_sim_data.py``,
                 for every year rather than the held-out three). Drives the
                 dust field, the soiled-array shader and the live simulator.
  gate.json      the M3 falsification gate recomputed with the M3 functions
                 and ASSERTED equal to ``results/m3_verify.log``: cost sweep,
                 optimum per cost, closed form, the 1% plateau.
  ppo.json       one PPO seed trained as M4 trained it, with the policy
                 captured untrained, at 10%, 30% and 100% of training: the
                 P(clean) surface over soiling ratio x days-since-clean, the
                 greedy decisions on a held-out year, the learning curve.
  fleet.json     M6's FleetHeuristic driven day by day through a held-out year:
                 its efficacy estimates for the five robots converging on
                 DEWA's band, what it dispatched, what each clean actually
                 removed, the latent health it cannot see, the running bill.
  qrdqn.json     one QR-DQN seed trained as M7 trained it: the return
                 quantiles it predicts for each action on every day of a
                 held-out year, the action each risk level would pick, and the
                 CVaR-by-alpha table.
  results.json   the headline numbers, parsed by regular expression from
                 ``results/*.log``. A number the pattern cannot find in its log
                 is an error, not a default.

Usage:
    python scripts/export_site_data.py                 # everything (~30 min CPU)
    python scripts/export_site_data.py --skip-training # weather, gate, fleet, results only
    python scripts/export_site_data.py --timesteps-scale 0.05   # quick smoke run

Zero cost, laptop only: the two training runs are single seeds on CPU.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from rimal.agents.ppo import ActorCritic, PPOConfig, PPOPolicy, RunningNorm  # noqa: E402
from rimal.agents.ppo import train as train_ppo  # noqa: E402
from rimal.agents.qrdqn import QRDQNConfig, QRDQNPolicy, cvar_scores  # noqa: E402
from rimal.agents.qrdqn import train as train_qrdqn  # noqa: E402
from rimal.baselines import FixedInterval, FleetHeuristic, SoilingThreshold  # noqa: E402
from rimal.config import AOD_CLIMATOLOGY_550NM, DATA, SOILING  # noqa: E402
from rimal.env import DEWA_FLEET, Economics, EnvConfig, RimalCleaningEnv  # noqa: E402
from rimal.eval import analytic_optimal_interval, cvar, evaluate  # noqa: E402

import export_sim_data  # noqa: E402  (fit_k, the same correction the simulator uses)
import m3_verify  # noqa: E402
import m6_verify  # noqa: E402
import m7_verify  # noqa: E402

OUT = ROOT / "site" / "public" / "data"
RESULTS = ROOT / "results"
TRAIN_YEARS = DATA.train_years
HOLDOUT_YEARS = DATA.holdout_years
ALL_YEARS = tuple(range(DATA.default_start_year, DATA.default_end_year + 1))
THRESHOLD = 0.93


def r(x, nd=3):
    return round(float(x), nd)


# --- weather ----------------------------------------------------------------


def export_weather() -> dict:
    env = RimalCleaningEnv(EnvConfig(years=ALL_YEARS, soiling_model="storm"))
    lookup, daily = env._lookup, env._daily
    years = {}
    for year in ALL_YEARS:
        rows = env._episode_starts[year]
        frame = daily.iloc[rows]
        years[str(year)] = {
            "aod": [r(v, 3) for v in frame["AOD_55"].to_numpy()],
            "rain": [r(v, 2) for v in env._rain[rows]],
            "clean": [r(v, 1) for v in lookup.values[rows, -1]],
            "k": [r(export_sim_data.fit_k(lookup.values[i], lookup.ratios), 4) for i in rows],
            "temp": [r(v, 1) for v in frame["T2M"].to_numpy()],
            "wind": [r(v, 2) for v in frame["WS2M"].to_numpy()],
        }
    return {
        "meta": {
            "site": "MBR Solar Park (Seih Al-Dahal), Dubai",
            "latitude": env.config.site.latitude,
            "longitude": env.config.site.longitude,
            "aod_reference": AOD_CLIMATOLOGY_550NM,
            "soiling_rate_mid": SOILING.rate_mid_per_day,
            "assumed_rate": SOILING.rate_mid_per_day,
            "obs_scales": {"aod": RimalCleaningEnv.AOD_SCALE, "temp": RimalCleaningEnv.TEMP_SCALE,
                           "wind": RimalCleaningEnv.WIND_SCALE, "max_days": EnvConfig().max_days_since_cleaning},
            "rate_band": [SOILING.rate_min_per_day, SOILING.rate_max_per_day],
            "storm_exponent": env._model.storm_exponent,
            "max_daily_rate": env._model.rate_bounds[1],
            "rain_wash_mm": env._model.cleaning_threshold_mm,
            "grace_days": env._model.grace_period_days,
            "max_soiling": env._model.max_soiling,
            "price_usd_per_kwh": Economics().energy_price_usd_per_kwh,
            "clean_cost_usd_per_mwp": Economics().cleaning_cost_usd_per_mwp,
            "train_years": list(TRAIN_YEARS),
            "holdout_years": list(HOLDOUT_YEARS),
        },
        "years": years,
    }


# --- falsification gate -----------------------------------------------------


def export_gate() -> dict:
    costs = (25.0, 50.0, 60.0, 75.0, 100.0, 125.0, 150.0)
    clean_energy = evaluate(
        RimalCleaningEnv(EnvConfig(years=TRAIN_YEARS)), FixedInterval(1), TRAIN_YEARS
    )["energy_kwh"].mean()
    rows, curves = [], {}
    for cost in costs:
        series = m3_verify.sweep_intervals(cost, TRAIN_YEARS)
        optimum = int(series.idxmax())
        analytic = analytic_optimal_interval(
            clean_energy, Economics().energy_price_usd_per_kwh, SOILING.rate_mid_per_day, cost
        )
        rows.append({"cost": cost, "optimum": optimum, "analytic": r(analytic, 1), "net": r(series.max(), 0)})
        curves[str(int(cost))] = [r(v, 0) for v in series.to_numpy()]

    default = m3_verify.sweep_intervals(Economics().cleaning_cost_usd_per_mwp, TRAIN_YEARS)
    best = default.max()
    plateau = default[default >= best * 0.99].index
    log = (RESULTS / "m3_verify.log").read_text(encoding="utf-8")
    for row in rows:
        pattern = rf"^\s+{int(row['cost'])}\s+{row['optimum']}\s+{row['analytic']:.1f}\s+"
        if not re.search(pattern, log, re.M):
            raise RuntimeError(
                f"gate row {row} is not in results/m3_verify.log -- the site must not "
                "show a falsification table the acceptance run did not produce"
            )
    return {
        "intervals": list(m3_verify.INTERVALS),
        "costs": rows,
        "curves": curves,
        "published_optimum_days": list(m3_verify.PUBLISHED_OPTIMUM),
        "plateau_days": [int(plateau.min()), int(plateau.max())],
        "default_cost": Economics().cleaning_cost_usd_per_mwp,
    }


# --- PPO: the course of learning -------------------------------------------


def _ppo_surface(agent: ActorCritic, norm: RunningNorm, env: RimalCleaningEnv) -> dict:
    """P(clean) over soiling ratio x days since clean, other features at held-out medians."""
    ratios = np.round(np.arange(0.86, 1.0001, 0.005), 3)
    days = np.arange(0, 61, 2)
    doy = 120  # late April: the dusty season, when the decision matters most
    angle = 2.0 * np.pi * doy / 365.25
    fixed = [
        float(np.median(env._aod)) / env.AOD_SCALE,
        float(np.median(env._temp)) / env.TEMP_SCALE,
        float(np.median(env._wind)) / env.WIND_SCALE,
        float(np.sin(angle)),
        float(np.cos(angle)),
    ]
    grid = np.array(
        [[ratio, d / env.config.max_days_since_cleaning, *fixed] for d in days for ratio in ratios],
        dtype=np.float32,
    )
    with torch.no_grad():
        logits = agent.actor(torch.as_tensor(norm(grid), dtype=torch.float32))
        p_clean = torch.softmax(logits, dim=-1)[:, 1].numpy().reshape(len(days), len(ratios))
    return {"ratios": ratios.tolist(), "days": days.tolist(), "p_clean": np.round(p_clean, 4).tolist()}


def _ppo_rollout(agent: ActorCritic, norm: RunningNorm, env: RimalCleaningEnv, year: int) -> dict:
    policy = PPOPolicy(agent, norm)
    obs, _ = env.reset(seed=0, options={"year": year})
    ratio, p_clean, actions = [], [], []
    energy = cost = 0.0
    day = 0
    while True:
        with torch.no_grad():
            logits = agent.actor(torch.as_tensor(norm(obs), dtype=torch.float32))
            p_clean.append(r(torch.softmax(logits, dim=-1)[1].item(), 4))
        action = policy(day, obs)
        obs, _, terminated, truncated, info = env.step(action)
        ratio.append(r(info["soiling_ratio"], 4))
        actions.append(int(info["cleaned"]))
        energy += info["energy_kwh"]
        cost += info["cleaning_cost_usd"]
        day += 1
        if terminated or truncated:
            break
    net = energy * Economics().energy_price_usd_per_kwh - cost
    return {"year": year, "ratio": ratio, "p_clean": p_clean, "cleaned": actions, "net": r(net, 0), "cleans": int(sum(actions))}


def export_ppo(timesteps: int) -> dict:
    fractions = (0.0, 0.1, 0.3, 1.0)
    targets = [int(f * timesteps) for f in fractions]
    captured: dict[int, tuple[int, dict, dict]] = {}

    def checkpoint(step: int, agent: ActorCritic, norm: RunningNorm) -> None:
        for i, target in enumerate(targets):
            if i not in captured and step >= target:
                captured[i] = (
                    step,
                    copy.deepcopy(agent.state_dict()),
                    {"mean": norm.mean.copy(), "var": norm.var.copy(), "count": float(norm.count)},
                )

    t0 = time.time()
    agent, norm, log = train_ppo(
        EnvConfig(years=TRAIN_YEARS),
        PPOConfig(total_timesteps=timesteps),
        seed=0,
        progress=True,
        checkpoint=checkpoint,
    )
    # Training runs whole batches, so it ends a few steps short of the nominal
    # budget; any stage not reached is the final policy.
    final_step = log.timesteps[-1] if log.timesteps else timesteps
    for i in range(len(targets)):
        if i not in captured:
            captured[i] = (
                final_step,
                copy.deepcopy(agent.state_dict()),
                {"mean": norm.mean.copy(), "var": norm.var.copy(), "count": float(norm.count)},
            )
    print(f"      PPO trained in {time.time() - t0:.0f}s; checkpoints at steps "
          f"{[captured[i][0] for i in sorted(captured)]}")

    holdout = RimalCleaningEnv(EnvConfig(years=HOLDOUT_YEARS))
    threshold_net = evaluate(holdout, SoilingThreshold(THRESHOLD), HOLDOUT_YEARS)["net_usd"].mean()
    stages = []
    for i in sorted(captured):
        step, state, norm_state = captured[i]
        net_i = ActorCritic(agent.actor[0].in_features, 2, agent.actor[0].out_features)  # (obs_dim, n_actions, hidden)
        net_i.load_state_dict(state)
        norm_i = RunningNorm((agent.actor[0].in_features,))
        norm_i.mean, norm_i.var, norm_i.count = norm_state["mean"], norm_state["var"], norm_state["count"]
        held = evaluate(holdout, PPOPolicy(net_i, norm_i), HOLDOUT_YEARS)
        stage_extra = {}
        if i == len(targets) - 1:
            # The trained actor, small enough to run live in the browser:
            # a tanh MLP on the standardised 7-dim observation, argmax = action.
            layers = [m for m in net_i.actor if isinstance(m, torch.nn.Linear)]
            stage_extra["actor"] = {
                "activation": "tanh",
                "layers": [
                    {"w": np.round(m.weight.detach().numpy(), 5).tolist(), "b": np.round(m.bias.detach().numpy(), 5).tolist()}
                    for m in layers
                ],
                "normaliser": {"mean": np.round(norm_i.mean, 6).tolist(), "var": np.round(norm_i.var, 6).tolist()},
                "obs_layout": ["reported_ratio", "days_since_clean/max_days", "aod/aod_scale", "temp/temp_scale",
                               "wind/wind_scale", "sin(doy)", "cos(doy)"],
            }
        stages.append(
            {
                **stage_extra,
                "label": ["untrained", "10% of training", "30% of training", "trained"][i],
                "step": step,
                "fraction": fractions[i],
                "surface": _ppo_surface(net_i, norm_i, holdout),
                "rollout": _ppo_rollout(net_i, norm_i, holdout, HOLDOUT_YEARS[0]),
                "holdout_net": r(held["net_usd"].mean(), 0),
                "holdout_cleans": r(held["cleans"].mean(), 1),
            }
        )
    return {
        "timesteps": timesteps,
        "seed": 0,
        "threshold_rule_net": r(threshold_net, 0),
        "threshold": THRESHOLD,
        "learning_curve": {
            "timesteps": log.timesteps[:: max(1, len(log.timesteps) // 120)],
            "episode_return": [r(v, 0) for v in log.episode_return[:: max(1, len(log.episode_return) // 120)]],
        },
        "stages": stages,
    }


# --- fleet: learning which robot -------------------------------------------


def export_fleet() -> dict:
    env = RimalCleaningEnv(m6_verify.fleet_config(HOLDOUT_YEARS))
    policy = FleetHeuristic(THRESHOLD)
    policy.reset()
    year = HOLDOUT_YEARS[0]
    obs, _ = env.reset(seed=0, options={"year": year})
    days = []
    cost = 0.0
    day = 0
    while True:
        action = policy(day, obs)
        obs, _, terminated, truncated, info = env.step(action)
        cost += info["cleaning_cost_usd"] + info["service_cost_usd"]
        days.append(
            {
                "ratio": r(info["soiling_ratio"], 4),
                "observed": r(info["observed_ratio"], 4),
                "belief": r(1.0 - policy.filter.loss, 4),
                "robot": int(info["robot"]),
                "efficacy": r(info["realised_efficacy"], 3),
                "estimates": [r(v, 3) for v in policy.efficacy_estimates],
                "health": [r(v, 3) for v in info["robot_health"]],
                "cost": r(cost, 0),
            }
        )
        day += 1
        if terminated or truncated:
            break
    return {
        "year": year,
        "threshold": THRESHOLD,
        "robots": [
            {"name": s.name, "nominal": s.nominal_efficacy, "cooldown_days": s.cooldown_days, "wear_per_use": s.wear_per_use}
            for s in DEWA_FLEET
        ],
        "efficacy_band": [0.69, 0.99],
        "days": days,
    }


# --- QR-DQN: the distribution it learnt --------------------------------------


def export_qrdqn(timesteps: int) -> dict:
    t0 = time.time()
    network, norm = train_qrdqn(
        m7_verify.base_config(TRAIN_YEARS), QRDQNConfig(total_timesteps=timesteps), seed=0, progress=True
    )
    print(f"      QR-DQN trained in {time.time() - t0:.0f}s")
    holdout = RimalCleaningEnv(m7_verify.base_config(HOLDOUT_YEARS))
    alphas = (1.0, 0.5, 0.25, 0.1)

    # The stormiest held-out year: where the tail lives.
    year = max(HOLDOUT_YEARS, key=lambda y: float(env_aod_max(holdout, y)))
    obs, _ = holdout.reset(seed=0, options={"year": year})
    keep = list(range(0, network.n_quantiles, 3))  # 17 of 51 quantiles, evenly spaced
    days = []
    day = 0
    while True:
        with torch.no_grad():
            q = network(torch.as_tensor(norm(obs), dtype=torch.float32).unsqueeze(0))[0]
            sorted_q, _ = torch.sort(q, dim=-1)
            choices = {str(a): int(torch.argmax(cvar_scores(q.unsqueeze(0), a), dim=1).item()) for a in alphas}
        action = choices["1.0"]
        obs, _, terminated, truncated, info = holdout.step(action)
        days.append(
            {
                "ratio": r(info["soiling_ratio"], 4),
                "observed": r(info["observed_ratio"], 4),
                "aod": r(holdout._aod[holdout._rows[day]], 3),
                "quantiles": [[r(v, 2) for v in sorted_q[a, keep].tolist()] for a in range(2)],
                "choice": choices,
            }
        )
        day += 1
        if terminated or truncated:
            break

    table = []
    for alpha in alphas:
        nets = m7_verify.episodes(holdout, QRDQNPolicy(network, norm, alpha=alpha), HOLDOUT_YEARS, seeds=10)
        table.append({"alpha": alpha, "mean": r(nets.mean(), 0), "cvar5": r(cvar(nets, 0.05), 0), "episodes": int(len(nets))})
    return {
        "timesteps": timesteps,
        "seed": 0,
        "year": year,
        "quantile_taus": [r((i + 0.5) / network.n_quantiles, 3) for i in keep],
        "reward_scale": QRDQNConfig().reward_scale,
        "days": days,
        "alpha_table": table,
    }


def env_aod_max(env: RimalCleaningEnv, year: int) -> float:
    return float(np.max(env._aod[env._episode_starts[year]]))


# --- results: parsed from the logs ------------------------------------------


def grab(log: str, pattern: str, cast=float, name: str = ""):
    match = re.search(pattern, log, re.M)
    if not match:
        raise RuntimeError(f"results.json: {name or pattern!r} not found in its log")
    value = match.group(1).replace(",", "")
    return cast(value)


def export_results() -> dict:
    logs = {m: (RESULTS / f"m{m}_verify.log").read_text(encoding="utf-8") for m in range(8)}
    m3, m4, m5, m6, m7 = (logs[i] for i in (3, 4, 5, 6, 7))
    belief = (RESULTS / "m5_belief_cleans.log").read_text(encoding="utf-8")

    noise_rows = []
    # The sweep prints noise to one decimal, so rows are matched by order.
    sweep = re.findall(r"^\s+0\.[01]\s+([\d,\.]+)\s+([\d\.]+)\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)$", m5, re.M)
    if len(sweep) != 4:
        raise RuntimeError("results.json: expected four noise rows in results/m5_verify.log")
    belief_cleans = re.findall(r"noise ([\d\.]+): net \$([\d,\.]+)\s+cleans/yr ([\d\.]+)", belief)
    if len(belief_cleans) != 4:
        raise RuntimeError("results.json: expected four rows in results/m5_belief_cleans.log")
    for (naive, naive_cleans, guarded, bel, fixed), (noise, bel_net, bel_cleans) in zip(sweep, belief_cleans):
        if abs(float(bel.replace(",", "")) - float(bel_net.replace(",", ""))) > 0.05:
            raise RuntimeError(f"results.json: belief net {bel} vs {bel_net} disagree at noise {noise}")
        noise_rows.append(
            {
                "noise": float(noise),
                "naive": float(naive.replace(",", "")),
                "naive_cleans": float(naive_cleans),
                "guarded": float(guarded.replace(",", "")),
                "belief": float(bel.replace(",", "")),
                "belief_cleans": float(bel_cleans),
                "fixed": float(fixed.replace(",", "")),
            }
        )

    alpha_rows = re.findall(r"^\s+alpha ([\d\.]+)\s+mean \$([\d,]+)\s+CVaR \$([\d,]+)$", m7, re.M)
    if len(alpha_rows) != 4:
        raise RuntimeError("results.json: expected four alpha rows in results/m7_verify.log")

    return {
        "generated_from": "results/*.log, 2026-09-11/12 runs on the corrected environment",
        "m0": {"checks": grab(logs[0], r"M0 PASSED -- (\d+)/", int)},
        "m1": {"checks": grab(logs[1], r"M1 PASSED -- (\d+)/", int),
               "yield_min": grab(logs[1], r"min (\d+), max \d+, mean \d+ over 10 years", int),
               "yield_max": grab(logs[1], r"min \d+, max (\d+), mean \d+ over 10 years", int),
               "kimber_rate": grab(logs[1], r"Kimber: mean accumulation.*?: ([\d\.]+) %/day"),
               "aod_rate": grab(logs[1], r"AOD-modulated: mean accumulation.*?: ([\d\.]+) %/day"),
               "never_clean_loss_pct": grab(logs[1], r"Kimber: never-clean plant loses energy vs clean: ([\d\.]+)%")},
        "m3": {"checks": grab(m3, r"M3 PASSED -- (\d+)/", int),
               "threshold_net": grab(m3, r"^threshold-0\.93\s+([\d,\.]+)", float, "m3 threshold-0.93"),
               "threshold_cleans": grab(m3, r"^threshold-0\.93\s+[\d,\.]+\s+[\d,\.]+\s+[\d,\.]+\s+[\d,\.]+\s+([\d\.]+)"),
               "never_clean_net": grab(m3, r"^\s+never-clean\s+([\d,\.]+)"),
               "always_clean_net": grab(m3, r"^\s+always-clean\s+([\d,\.]+)"),
               "closed_form_gap_pct": grab(m3, r"mean relative gap ([\d\.]+)%"),
               "plateau": [grab(m3, r"any interval in (\d+)-\d+ d", int), grab(m3, r"any interval in \d+-(\d+) d", int)]},
        "m4": {"checks": grab(m4, r"M4 PASSED -- (\d+)/", int),
               "ppo_mean": grab(m4, r"PPO mean \$([\d,]+) \+/- \d+"),
               "ppo_sd": grab(m4, r"PPO mean \$[\d,]+ \+/- (\d+)"),
               "threshold_net": grab(m4, r"best baseline: threshold-0\.93 \$([\d,]+)"),
               "fixed_net": grab(m4, r"best fixed interval: tuned-fixed-31d \$([\d,]+)"),
               "margin_over_fixed": grab(m4, r"\(\+(\d+)\)"),
               "ppo_cleans": grab(m4, r"mean ([\d\.]+) cleans/yr")},
        "m5": {"rmse_belief": grab(m5, r"RMSE ([\d\.]+) vs raw"),
               "rmse_raw": grab(m5, r"RMSE [\d\.]+ vs raw ([\d\.]+)"),
               "rmse_reduction": grab(m5, r"\(([\d\.]+)x reduction\)"),
               "exact_net": grab(m5, r"threshold-0\.93 \(the M4 winner\): \$([\d,]+)"),
               "collapse_usd": grab(m5, r"vs \$[\d,]+ exact \(-\$([\d,]+)\)"),
               "noise": noise_rows,
               "ppo_belief_net": grab(m5, r"^belief-state\s+([\d,\.]+)", float, "m5 belief-state"),
               "ppo_belief_sd": grab(m5, r"^belief-state\s+[\d,\.]+\s+([\d\.]+)"),
               "ppo_memoryless_net": grab(m5, r"^memoryless\s+([\d,\.]+)", float, "m5 memoryless"),
               "ppo_memoryless_sd": grab(m5, r"^memoryless\s+[\d,\.]+\s+([\d\.]+)"),
               "ppo_gap": grab(m5, r"\(\+(\d+)\); Welch"),
               "ppo_p": grab(m5, r"p=([\d\.]+), n=5"),
               "belief_rule_net": grab(m5, r"vs rule \$([\d,]+) \(-"),
               "declared_failed": "criterion (b): the belief-state agent significantly beats the memoryless agent"},
        "m6": {"partial_cleaning_cost": grab(m6, r"\(-\$(\d+)/MWp/yr\)"),
               "perfect_assumption_min": grab(m6, r"worth \$(\d+)-\$\d+/MWp/yr"),
               "perfect_assumption_max": grab(m6, r"worth \$\d+-\$(\d+)/MWp/yr"),
               "partial_paired_mean": grab(m6, r"at \$60: \+([\d\.]+) \+/- [\d\.]+ paired"),
               "partial_paired_sem": grab(m6, r"at \$60: \+[\d\.]+ \+/- ([\d\.]+) paired"),
               "partial_p": grab(m6, r"paired over 120 episodes, p = ([\d\.]+)"),
               "dispatch_paired_mean": grab(m6, r"at \$60: -([\d\.]+) \+/- [\d\.]+ paired"),
               "dispatch_paired_sem": grab(m6, r"at \$60: -[\d\.]+ \+/- ([\d\.]+) paired"),
               "dispatch_losses": [float(v) for v in re.findall(r"\$-(\d+) at \d+ cleans/yr", m6)],
               "dispatch_cleans": [float(v) for v in re.findall(r"\$-\d+ at (\d+) cleans/yr", m6)],
               "spearman": grab(m6, r"Spearman rho = ([\d\.]+)"),
               "wear30_pct": grab(m6, r"at 30x wear \(([\d\.]+)%\)"),
               "ppo_mean": grab(m6, r"PPO\s+\$([\d,]+) \+/- \d+"),
               "ppo_sd": grab(m6, r"PPO\s+\$[\d,]+ \+/- (\d+)"),
               "rule_net": grab(m6, r"best rule\s+\$([\d,]+)"),
               "ppo_seeds": [{"net": float(a.replace(",", "")), "cleans": float(b)} for a, b in re.findall(r"seed \d: \$([\d,]+), ([\d\.]+) cleans", m6)]},
        "m7": {"clipping_overstated_cvar": grab(m7, r"overstated by \$(\d+)/MWp/yr"),
               "mean_optimal_threshold": grab(m7, r"mean-optimal threshold ([\d\.]+)"),
               "cvar_optimal_threshold": grab(m7, r"CVaR-optimal ([\d\.]+)"),
               "cvar_gain": grab(m7, r"buying \$(\d+) of CVaR"),
               "mean_cost": grab(m7, r"costs \$(\d+) of mean"),
               "water_cost": grab(m7, r"tightest budget costs \$(\d+)/MWp/yr"),
               "water_cost_pct": grab(m7, r"tightest budget costs \$\d+/MWp/yr \(([\d\.]+)%\)"),
               "alpha_table": [{"alpha": float(a), "mean": float(m.replace(",", "")), "cvar5": float(c.replace(",", ""))} for a, m, c in alpha_rows],
               "rule_cvar": grab(m7, r"CVaR-tuned threshold 0\.96 \(tuned on train\): mean \$[\d,]+, CVaR \$([\d,]+)"),
               "rule_mean": grab(m7, r"CVaR-tuned threshold 0\.96 \(tuned on train\): mean \$([\d,]+)"),
               "agent_cvar": grab(m7, r"alpha=0\.25: CVaR \$([\d,]+) vs rule"),
               "agent_margin": grab(m7, r"vs rule \$[\d,]+ \(-(\d+)\)"),
               "agent_sd": grab(m7, r"seed sd \$(\d+) at n=3")},
    }


# --- main -----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-training", action="store_true")
    parser.add_argument("--timesteps-scale", type=float, default=1.0, help="scale both training budgets (smoke runs)")
    parser.add_argument("--only", nargs="*", default=None, help="subset of: weather gate ppo fleet qrdqn results")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)

    wanted = set(args.only or ["weather", "gate", "ppo", "fleet", "qrdqn", "results"])
    if args.skip_training:
        wanted -= {"ppo", "qrdqn"}

    jobs = {
        "weather": export_weather,
        "gate": export_gate,
        "fleet": export_fleet,
        "results": export_results,
        "ppo": lambda: export_ppo(int(1_500_000 * args.timesteps_scale)),
        "qrdqn": lambda: export_qrdqn(int(400_000 * args.timesteps_scale)),
    }
    for name in ("weather", "gate", "fleet", "results", "ppo", "qrdqn"):
        if name not in wanted:
            continue
        t0 = time.time()
        print(f"[{name}]")
        data = jobs[name]()
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        print(f"      wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB) in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
