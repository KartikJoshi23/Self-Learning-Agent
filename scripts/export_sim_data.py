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

What "the same" means for rainfall, and why it is not byte equality. The
shipped data was exported from the project's canonical cache (fetched
2026-08-29). NASA POWER has since changed the hourly rainfall product to a
2-decimal per-hour depth, which ``rimal.data.power`` converts back to the
canonical mm/day rate -- but the rounding is upstream and cannot be undone, so
a fresh clone's daily rain differs from the cache by up to 24 x 0.005 mm per
hour, in practice <= 0.05 mm/day (measured 2026-09-12: 340 of 1,096 values, max
0.05). Nothing physical depends on that: rain acts through the 6 mm wash
threshold, and no day moves across it. So ``--check`` requires ``aod``,
``clean`` and ``k`` to match exactly, ``rain`` to match within the rounding
bound, and the set of wash days to be identical. The rendered HTML is checked
the same way, through the data it embeds.
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

#: Rain-wash threshold of the soiling models (mm/day); a rain value may differ
#: from the shipped one only if it leaves this decision unchanged.
RAIN_WASH_MM = 6.0
#: Upstream rounding bound on canonical rainfall: 24 x 0.005 mm per hour.
RAIN_TOLERANCE_MM = 0.12

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


def _embedded_data(text: str) -> dict:
    """The data a shipped file carries: the JSON itself, or the HTML's DATA line."""
    if text.lstrip().startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("const DATA = ") and line.endswith(";"):
            return json.loads(line[len("const DATA = "):-1])
    raise RuntimeError("no embedded DATA line found")


def _differences(fresh: dict, shipped: dict) -> list[str]:
    """Explain every way ``shipped`` fails to be what the engine produces."""
    out = []
    if fresh["meta"] != shipped.get("meta"):
        out.append("meta differs")
    if set(fresh["years"]) != set(shipped.get("years", {})):
        out.append(f"years differ: {sorted(fresh['years'])} vs {sorted(shipped.get('years', {}))}")
        return out
    for year, columns in fresh["years"].items():
        theirs = shipped["years"][year]
        for key in ("aod", "clean", "k"):
            if columns[key] != theirs.get(key):
                out.append(f"{year} {key} differs")
        ours, other = np.asarray(columns["rain"]), np.asarray(theirs.get("rain", []))
        if ours.shape != other.shape:
            out.append(f"{year} rain length differs")
            continue
        worst = float(np.abs(ours - other).max()) if len(ours) else 0.0
        if worst > RAIN_TOLERANCE_MM:
            out.append(f"{year} rain differs by {worst:.3f} mm/day, beyond the {RAIN_TOLERANCE_MM} rounding bound")
        if not np.array_equal(ours > RAIN_WASH_MM, other > RAIN_WASH_MM):
            out.append(f"{year} rain-wash days differ")
    return out


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
        problems = []
        for path in targets:
            if not path.exists():
                problems.append(f"{path.name} is missing")
                continue
            shipped = _embedded_data(path.read_text(encoding="utf-8"))
            problems += [f"{path.name}: {p}" for p in _differences(data, shipped)]
        if problems:
            print("STALE: " + "; ".join(problems))
            return 1
        print(
            "OK: web/sim_data.json and web/simulator.html match the engine "
            "(aod/clean/k exact; rain within the upstream rounding bound with "
            "identical wash days)"
        )
        return 0

    for path, content in targets.items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
