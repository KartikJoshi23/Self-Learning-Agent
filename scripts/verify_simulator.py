"""Verify the browser simulator against the Python engine.

``web/simulator.html`` carries a JavaScript port of the physics so the project
can be *shown* and not only read. A port is a second implementation, and a
second implementation drifts, so this script checks the one that actually
ships: it slices the physics block and the embedded data out of
``simulator.html`` itself, runs them under ``node``, and compares the result
against ``rimal`` on the same years. Nothing is copied into a test double.

Checks, with tolerances declared here rather than tuned to pass:

  constants   every physical and economic constant hard-coded in the port
              equals the engine's (tariff, cleaning cost, rain threshold,
              grace period, soiling cap, storm exponent, rate cap, Kalman
              process/initial/reset variances, assumed rate);
  soiling     never-clean soiling-ratio trajectory, max |JS - Python|
              <= 1e-4 on every held-out year;
  rain        rain-wash days identical;
  clean       clean-plant annual energy within 5e-5 relative (the data carries
              0.1 kWh rounding);
  energy      soiled annual energy within 1e-3 relative -- the browser uses a
              per-day linear correction in place of the pvlib table;
  policies    with an exact reading, the naive threshold, the belief
              (Kalman) threshold and the fixed-31-day rule must clean on
              exactly the same days as the Python baselines.

The belief comparison is run at zero observation noise because the two sides
draw noise from different generators (mulberry32 vs numpy); what is being
checked is the filter and the decision rule, which are deterministic.

Usage:
    python scripts/verify_simulator.py                                  # web/simulator.html
    python scripts/verify_simulator.py --module site/src/lib/physics/rimal.js

With ``--module`` the same checks run against the site's ES-module port, fed
``site/public/data/weather.json``, and two more rules are compared: the
``guarded`` rule (``ScheduleAwareThreshold``) and, when ``ppo.json`` carries
the trained actor, the ``ppo`` policy -- the module's tanh-MLP forward pass
against torch on the same held-out days.

Requires ``node`` on PATH (any recent LTS). Exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rimal.agents.ppo import ActorCritic, PPOPolicy, RunningNorm  # noqa: E402
from rimal.baselines.belief import BeliefThreshold, ScheduleAwareThreshold  # noqa: E402
from rimal.baselines.policies import FixedInterval, NeverClean, SoilingThreshold  # noqa: E402
from rimal.config import DATA, SOILING  # noqa: E402
from rimal.env.cleaning_env import Economics, EnvConfig, RimalCleaningEnv  # noqa: E402
from rimal.env.observation import ObservationNoise, SoilingKalmanFilter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "web" / "simulator.html"
SITE_DATA = ROOT / "site" / "public" / "data" / "weather.json"
SITE_PPO = ROOT / "site" / "public" / "data" / "ppo.json"
YEARS = DATA.holdout_years
THRESHOLD = 0.93
FIXED_DAYS = 31

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")


# --- the shipped JavaScript --------------------------------------------------

DRIVER = r"""
const OUT = {};
for (const year of YEARS) {
  OUT[year] = {};
  for (const [key, policy] of [['never','never'],['naive','naive'],['belief','belief'],['fixed','fixed']]) {
    const r = simulate(year, policy, 0, THRESHOLD, 0);
    OUT[year][key] = {
      ratio: r.tTrue, cleanDays: r.cleanDays, rainDays: r.rainDays,
      energy: r.energy, cleanEnergy: r.cleanEnergy, cleans: r.cleans,
    };
  }
}
OUT.constants = {
  PRICE, CLEAN_COST, RAIN_THRESHOLD, GRACE, MAX_SOILING, STORM_EXP, MAX_RATE,
  assumed_rate: M.assumed_rate, aod_reference: M.aod_reference,
  kalman: (() => { const k = new Kalman(); const q = k.q; k.reset(); const v0 = k.v;
                   k.resetEvent(false); const vr = k.v; return {q, v0, vr}; })(),
};
process.stdout.write(JSON.stringify(OUT));
"""


MODULE_DRIVER = r"""
import * as R from MODULE_URL;
import { readFileSync } from 'node:fs';
const DATA = JSON.parse(readFileSync(WEATHER_PATH, 'utf8'));
const ACTOR = ACTOR_JSON;
const OUT = {};
const POLICIES = ['never', 'naive', 'belief', 'fixed', 'guarded'].concat(ACTOR ? ['ppo'] : []);
for (const year of YEARS) {
  OUT[year] = {};
  for (const policy of POLICIES) {
    const r = R.simulate(DATA, year, policy, 0, THRESHOLD, 0, { actor: ACTOR });
    OUT[year][policy] = {
      ratio: r.tTrue, cleanDays: r.cleanDays, rainDays: r.rainDays,
      energy: r.energy, cleanEnergy: r.cleanEnergy, cleans: r.cleans,
    };
  }
}
OUT.constants = {
  PRICE: R.PRICE, CLEAN_COST: R.CLEAN_COST, RAIN_THRESHOLD: R.RAIN_THRESHOLD, GRACE: R.GRACE,
  MAX_SOILING: R.MAX_SOILING, STORM_EXP: R.STORM_EXP, MAX_RATE: R.MAX_RATE,
  assumed_rate: DATA.meta.assumed_rate, aod_reference: DATA.meta.aod_reference,
  kalman: (() => { const k = new R.Kalman(); const q = k.q; k.reset(); const v0 = k.v;
                   k.resetEvent(false); const vr = k.v; return {q, v0, vr}; })(),
};
process.stdout.write(JSON.stringify(OUT));
"""


def load_site_actor() -> dict | None:
    """The trained actor exported by export_site_data.py, if the full run exists."""
    if not SITE_PPO.exists():
        return None
    stages = json.loads(SITE_PPO.read_text(encoding="utf-8")).get("stages", [])
    return next((s["actor"] for s in reversed(stages) if "actor" in s), None)


def actor_policy(actor: dict) -> PPOPolicy:
    """Rebuild the exported actor in torch so the two forward passes can be compared."""
    layers = actor["layers"]
    obs_dim, hidden = len(layers[0]["w"][0]), len(layers[0]["w"])
    net = ActorCritic(obs_dim, len(layers[-1]["w"]), hidden)
    linear = [m for m in net.actor if isinstance(m, torch.nn.Linear)]
    with torch.no_grad():
        for module, layer in zip(linear, layers):
            module.weight.copy_(torch.tensor(layer["w"], dtype=torch.float32))
            module.bias.copy_(torch.tensor(layer["b"], dtype=torch.float32))
    norm = RunningNorm((obs_dim,))
    norm.mean = np.asarray(actor["normaliser"]["mean"], dtype=np.float64)
    norm.var = np.asarray(actor["normaliser"]["var"], dtype=np.float64)
    return PPOPolicy(net, norm, name="ppo-exported")


def extract_port(html: str) -> str:
    """The data line plus the physics block, exactly as shipped."""
    data = re.search(r"^const DATA = \{.*\};$", html, re.M)
    start = html.find("/* ---------------- physics")
    end = html.find("/* ---------------- drawing")
    if not data or start < 0 or end < 0 or end <= start:
        raise RuntimeError("simulator.html no longer has the expected physics/drawing markers")
    return data.group(0) + "\n" + html[start:end]


def run_port(module: Path | None = None, actor: dict | None = None) -> dict:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node is required on PATH to run the shipped JavaScript")
    header = f"const YEARS = {json.dumps(list(YEARS))};\nconst THRESHOLD = {THRESHOLD};\n"
    if module is None:
        script = header + extract_port(SIMULATOR.read_text(encoding="utf-8")) + DRIVER
    else:
        script = header + (
            MODULE_DRIVER.replace("MODULE_URL", json.dumps(module.resolve().as_uri()))
            .replace("WEATHER_PATH", json.dumps(str(SITE_DATA)))
            .replace("ACTOR_JSON", json.dumps(actor))
        )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "port.mjs"
        path.write_text(script, encoding="utf-8")
        completed = subprocess.run([node, str(path)], capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"node failed:\n{completed.stderr}")
    return json.loads(completed.stdout)


# --- the Python engine -------------------------------------------------------


def run_engine(env: RimalCleaningEnv, policy, year: int) -> dict:
    if hasattr(policy, "reset"):
        policy.reset()
    observation, _ = env.reset(seed=0, options={"year": year})
    ratio, clean_days, rain_days = [], [], []
    energy = clean_energy = 0.0
    day = 0
    while True:
        observation, _, terminated, truncated, info = env.step(policy(day, observation))
        ratio.append(info["soiling_ratio"])
        if info["cleaned"]:
            clean_days.append(day)
        if info["rain_reset"]:
            rain_days.append(day)
        energy += info["energy_kwh"]
        clean_energy += info["clean_energy_kwh"]
        day += 1
        if terminated or truncated:
            break
    return {
        "ratio": ratio,
        "cleanDays": clean_days,
        "rainDays": rain_days,
        "energy": energy,
        "cleanEnergy": clean_energy,
        "cleans": len(clean_days),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, default=None, help="verify an ES-module port instead of web/simulator.html")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    target = args.module if args.module else SIMULATOR
    actor = load_site_actor() if args.module else None
    print(f"\nSIMULATOR VERIFICATION -- {target} vs rimal, years {YEARS}\n")

    print("[1] Running the shipped JavaScript under node")
    port = run_port(args.module, actor)

    exact = RimalCleaningEnv(EnvConfig(years=YEARS, soiling_model="storm"))
    # The belief policy reads rain and noise-scale slots that only the noisy
    # observation carries; zero base noise keeps the reading exact.
    belief_env = RimalCleaningEnv(
        EnvConfig(
            years=YEARS,
            soiling_model="storm",
            observability="noisy",
            observation_noise=ObservationNoise(base_std=0.0),
        )
    )

    # --- constants ---------------------------------------------------------
    print("\n[2] Constants hard-coded in the port")
    c = port["constants"]
    economics = Economics()
    model = exact._model
    kalman = SoilingKalmanFilter(process_std=BeliefThreshold().process_std)
    expected = {
        "PRICE": economics.energy_price_usd_per_kwh,
        "CLEAN_COST": economics.cleaning_cost_usd_per_mwp,
        "RAIN_THRESHOLD": model.cleaning_threshold_mm,
        "GRACE": model.grace_period_days,
        "MAX_SOILING": model.max_soiling,
        "STORM_EXP": model.storm_exponent,
        "MAX_RATE": model.rate_bounds[1],
        "assumed_rate": SOILING.rate_mid_per_day,
        "aod_reference": model.aod_reference,
    }
    mismatches = [
        f"{k}: js {c[k]} vs py {v}" for k, v in expected.items() if not np.isclose(c[k], v)
    ]
    kal = {"q": kalman.process_var, "v0": kalman.initial_var, "vr": kalman.reset_var}
    mismatches += [
        f"kalman.{k}: js {c['kalman'][k]} vs py {v}"
        for k, v in kal.items()
        if not np.isclose(c["kalman"][k], v)
    ]
    check(
        "every port constant equals the engine's",
        not mismatches,
        "; ".join(mismatches) if mismatches else f"{len(expected) + len(kal)} constants agree",
    )

    # --- physics -----------------------------------------------------------
    print("\n[3] Never-clean physics, year by year")
    worst_ratio = worst_clean = worst_energy = 0.0
    rain_ok = True
    for year in YEARS:
        js = port[str(year)]["never"]
        py = run_engine(exact, NeverClean(), year)
        n = min(len(js["ratio"]), len(py["ratio"]))
        same_len = len(js["ratio"]) == len(py["ratio"])
        d_ratio = float(np.abs(np.array(js["ratio"][:n]) - np.array(py["ratio"][:n])).max())
        d_clean = abs(js["cleanEnergy"] / py["cleanEnergy"] - 1.0)
        d_energy = abs(js["energy"] / py["energy"] - 1.0)
        rain_same = js["rainDays"] == py["rainDays"]
        rain_ok &= rain_same
        worst_ratio, worst_clean, worst_energy = (
            max(worst_ratio, d_ratio), max(worst_clean, d_clean), max(worst_energy, d_energy)
        )
        print(
            f"      {year}: {len(py['ratio'])} days{'' if same_len else ' (LENGTH MISMATCH)'}, "
            f"ratio max|d| {d_ratio:.1e}, clean energy {d_clean:.1e} rel, "
            f"soiled energy {d_energy:.1e} rel, rain washes js {len(js['rainDays'])} / "
            f"py {len(py['rainDays'])}{'' if rain_same else ' (DIFFERENT DAYS)'}"
        )
        if not same_len:
            worst_ratio = float("inf")
    check("soiling trajectory matches (max |diff| <= 1e-4)", worst_ratio <= 1e-4, f"worst {worst_ratio:.2e}")
    check("rain-wash days identical", rain_ok, "same days in every year" if rain_ok else "differ")
    check("clean-plant energy matches (<= 5e-5 rel)", worst_clean <= 5e-5, f"worst {worst_clean:.2e}")
    check("soiled energy matches (<= 1e-3 rel)", worst_energy <= 1e-3, f"worst {worst_energy:.2e}")

    # --- policies ----------------------------------------------------------
    print(f"\n[4] Decision rules with an exact reading (threshold {THRESHOLD}, fixed {FIXED_DAYS}d)")
    rules = {
        "naive": (exact, lambda: SoilingThreshold(THRESHOLD)),
        "belief": (belief_env, lambda: BeliefThreshold(THRESHOLD)),
        "fixed": (exact, lambda: FixedInterval(FIXED_DAYS)),
    }
    if args.module:
        rules["guarded"] = (exact, lambda: ScheduleAwareThreshold(THRESHOLD))
        if actor is not None:
            rules["ppo"] = (exact, lambda: actor_policy(actor))
        else:
            print("      (ppo.json carries no trained actor yet -- ppo rule not compared)")
    for key, (env, make) in rules.items():
        all_same = True
        detail = []
        for year in YEARS:
            js = port[str(year)][key]
            py = run_engine(env, make(), year)
            same = js["cleanDays"] == py["cleanDays"]
            all_same &= same
            detail.append(f"{year}: js {js['cleans']} / py {py['cleans']}{'' if same else ' DIFFERENT DAYS'}")
        check(f"{key} rule cleans on the same days as the engine", all_same, "; ".join(detail))

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 62)
    if failed:
        print(f"SIMULATOR FAILED -- {len(failed)} check(s): {', '.join(failed)}")
        return 1
    print(f"SIMULATOR VERIFIED -- {len(RESULTS)}/{len(RESULTS)} checks")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
