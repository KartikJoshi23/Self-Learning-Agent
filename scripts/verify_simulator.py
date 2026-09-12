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
    python scripts/verify_simulator.py

Requires ``node`` on PATH (any recent LTS). Exits non-zero on any failure.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rimal.baselines.belief import BeliefThreshold  # noqa: E402
from rimal.baselines.policies import FixedInterval, NeverClean, SoilingThreshold  # noqa: E402
from rimal.config import DATA, SOILING  # noqa: E402
from rimal.env.cleaning_env import Economics, EnvConfig, RimalCleaningEnv  # noqa: E402
from rimal.env.observation import ObservationNoise, SoilingKalmanFilter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "web" / "simulator.html"
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


def extract_port(html: str) -> str:
    """The data line plus the physics block, exactly as shipped."""
    data = re.search(r"^const DATA = \{.*\};$", html, re.M)
    start = html.find("/* ---------------- physics")
    end = html.find("/* ---------------- drawing")
    if not data or start < 0 or end < 0 or end <= start:
        raise RuntimeError("simulator.html no longer has the expected physics/drawing markers")
    return data.group(0) + "\n" + html[start:end]


def run_port() -> dict:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node is required on PATH to run the shipped JavaScript")
    source = extract_port(SIMULATOR.read_text(encoding="utf-8"))
    script = (
        f"const YEARS = {json.dumps(list(YEARS))};\nconst THRESHOLD = {THRESHOLD};\n"
        + source
        + DRIVER
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
    logging.disable(logging.CRITICAL)
    print(f"\nSIMULATOR VERIFICATION -- {SIMULATOR} vs rimal, years {YEARS}\n")

    print("[1] Running the shipped JavaScript under node")
    port = run_port()

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
