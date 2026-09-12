"""Export the browser simulator's data from the Python engine.

``web/simulator.html`` runs a JavaScript port of the physics live in the
browser on the held-out years. The port is only as honest as the data it is
given, so that data comes from the engine itself -- the same environment,
soiling model and energy table the acceptance scripts use -- and is written
here, not by hand:

* ``aod``   daily AOD at 550 nm (the dust driver), from the daily frame;
* ``rain``  daily rainfall in canonical mm/day, the natural-cleaning trigger;
* ``clean`` clean-plant energy per day in kWh, read off the pvlib energy table
            at soiling ratio 1.0;
* ``k``     a per-day linear correction so the browser can evaluate the energy
            table without carrying it: ``energy(ratio) = clean * ratio *
            (1 + k * (1 - ratio))``. A soiled array clips less against the
            inverter and runs cooler, so it beats linear-in-ratio scaling, and
            by how much depends on that day's irradiance; ``k`` is the slope of
            a straight-line fit of ``energy / (clean * ratio) - 1`` against
            ``1 - ratio`` over the table's ratio grid. p95 error against the
            full table: 0.056%.

The JSON is injected into ``web/_simulator_template.html`` at ``__DATA__`` to
produce the self-contained ``web/simulator.html``.

Usage:
    python scripts/export_sim_data.py          # rewrite web/sim_data.json + simulator.html
    python scripts/export_sim_data.py --check  # exit 1 if either file would change

``--check`` is the reproducibility guard: the shipped simulator must be what
the engine produces today. ``scripts/verify_simulator.py`` then checks that
the port's *physics* agrees with the engine on that data.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rimal.config import AOD_CLIMATOLOGY_550NM, DATA, SOILING  # noqa: E402
from rimal.env.cleaning_env import EnvConfig, RimalCleaningEnv  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
TEMPLATE = WEB / "_simulator_template.html"
DATA_JSON = WEB / "sim_data.json"
SIMULATOR = WEB / "simulator.html"
PLACEHOLDER = "__DATA__"

#: The simulator shows the held-out years under the storm soiling model --
#: the M7 physics, which keeps the dust tail the earlier models clipped.
YEARS = DATA.holdout_years
SOILING_MODEL = "storm"


def fit_k(table_row: np.ndarray, ratios: np.ndarray) -> float:
    """Slope of ``energy/(clean*ratio) - 1`` against ``1 - ratio``."""
    clean = table_row[-1]
    y = table_row / (clean * ratios) - 1.0
    slope, _intercept = np.polyfit(1.0 - ratios, y, 1)
    return float(slope)


def build() -> dict:
    env = RimalCleaningEnv(EnvConfig(years=YEARS, soiling_model=SOILING_MODEL))
    lookup = env._lookup
    ratios = lookup.ratios
    if ratios[-1] != 1.0:
        raise RuntimeError("energy table must end at ratio 1.0 (the clean plant)")

    daily = env._daily
    years: dict[str, dict[str, list[float]]] = {}
    for year in YEARS:
        rows = env._episode_starts[year]
        frame = daily.iloc[rows]
        years[str(year)] = {
            # Built-in round(): half-even on the decimal value, which is what
            # the committed file was produced with (np.round differs on ties).
            "aod": [round(float(v), 3) for v in frame["AOD_55"].to_numpy()],
            "rain": [round(float(v), 2) for v in env._rain[rows]],
            "clean": [round(float(v), 1) for v in lookup.values[rows, -1]],
            "k": [round(fit_k(lookup.values[r], ratios), 4) for r in rows],
        }

    # Fit quality, measured rather than quoted: the 95th percentile of the
    # relative error over every (day, ratio) cell of the table.
    errors = []
    for row in range(len(lookup.values)):
        k = fit_k(lookup.values[row], ratios)
        clean = lookup.values[row, -1]
        approx = clean * ratios * (1.0 + k * (1.0 - ratios))
        errors.extend(np.abs(approx / lookup.values[row] - 1.0))
    p95 = float(np.percentile(errors, 95)) * 100.0

    return {
        "meta": {
            "site": "MBR Solar Park (Seih Al-Dahal), Dubai",
            "aod_reference": AOD_CLIMATOLOGY_550NM,
            "soiling_rate_mid": SOILING.rate_mid_per_day,
            "assumed_rate": SOILING.rate_mid_per_day,
            "note": (
                "held-out years; energy uses a per-day linear correction, "
                f"p95 error {p95:.3f}%"
            ),
        },
        "years": years,
    }


def render(data: dict) -> tuple[str, str]:
    payload = json.dumps(data, separators=(",", ":"))
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise RuntimeError(f"{TEMPLATE.name} must contain exactly one {PLACEHOLDER}")
    return payload, template.replace(PLACEHOLDER, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)

    data = build()
    payload, html = render(data)
    n_days = {y: len(v["aod"]) for y, v in data["years"].items()}
    print(f"sim data: {SOILING_MODEL} soiling, years {n_days}, {len(payload):,} bytes")
    print(f"          {data['meta']['note']}")

    targets = {DATA_JSON: payload, SIMULATOR: html}
    if args.check:
        stale = [
            p.name
            for p, content in targets.items()
            if not p.exists() or p.read_text(encoding="utf-8") != content
        ]
        if stale:
            print(f"STALE: {', '.join(stale)} differ from what the engine produces")
            return 1
        print("OK: web/sim_data.json and web/simulator.html match the engine")
        return 0

    for path, content in targets.items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
