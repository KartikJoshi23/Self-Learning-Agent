"""M1 acceptance check.

The Phase 3 plan declared M1's verification before M1 was built:

    (a) Uncleaned accumulation reproduces DEWA's measured daily rates.
    (b) Annual specific yield lands in the published Dubai range
        (~1,700-1,900 kWh/kWp).
    If either fails, the physics is wrong -- stop, do not proceed.

Usage:
    python scripts/m1_verify.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from rimal.config import DATA, EXPECTED_SPECIFIC_YIELD_KWH_PER_KWP, SOILING  # noqa: E402
from rimal.data import power  # noqa: E402
from rimal.physics import (  # noqa: E402
    AodModulatedSoiling,
    KimberSoiling,
    annual_specific_yield,
    check_irradiance_closure,
    hourly_ac_energy,
    observed_accumulation_rate,
    specific_yield_kwh_per_kwp,
)

FIGURE_DIR = Path(__file__).resolve().parents[1] / "figures"
RESULTS: list[tuple[str, bool, str]] = []

#: Global Solar Atlas (Solargis) reference for Dubai.
SOLARGIS_PVOUT = 1791.5


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")


def main() -> int:
    lo, hi = EXPECTED_SPECIFIC_YIELD_KWH_PER_KWP
    print(f"\nM1 ACCEPTANCE -- physics core, {DATA.default_start_year}-{DATA.default_end_year}\n")

    hourly = power.fetch_years()
    daily = power.daily_summary(hourly)

    # --- (b) Yield ---------------------------------------------------------
    print("[1] Clean-plant energy yield")
    closure = check_irradiance_closure(hourly)
    check(
        "irradiance components close (GHI = DHI + DNI*cos z)",
        bool(closure.abs().median() < 0.01),
        f"median relative error {closure.median():+.5f}",
    )

    clean_ac = hourly_ac_energy(hourly)
    annual = annual_specific_yield(clean_ac)
    check(
        f"annual specific yield in the published band ({lo:.0f}-{hi:.0f} kWh/kWp)",
        bool(annual.between(lo, hi).all()),
        f"min {annual.min():.0f}, max {annual.max():.0f}, mean {annual.mean():.0f} "
        f"over {len(annual)} years",
    )
    deviation = abs(annual.mean() - SOLARGIS_PVOUT) / SOLARGIS_PVOUT
    check(
        "mean yield within 10% of Global Solar Atlas PVOUT",
        bool(deviation < 0.10),
        f"{annual.mean():.0f} vs Solargis {SOLARGIS_PVOUT:.0f} ({deviation * 100:.1f}% low)",
    )

    # --- (a) Soiling accumulation -----------------------------------------
    print("\n[2] Soiling accumulation vs DEWA's measured rates")
    models = {"Kimber": KimberSoiling(), "AOD-modulated": AodModulatedSoiling()}
    ratios, soiled_yield = {}, {}

    for name, model in models.items():
        ratio = model.soiling_ratio(daily)
        ratios[name] = ratio
        increments = observed_accumulation_rate(ratio)
        mean_rate = increments.mean()
        check(
            f"{name}: mean accumulation in DEWA band "
            f"({SOILING.rate_min_per_day * 100:.2f}-{SOILING.rate_max_per_day * 100:.2f} %/day)",
            bool(SOILING.rate_min_per_day <= mean_rate <= SOILING.rate_max_per_day),
            f"{mean_rate * 100:.3f} %/day "
            f"(p5 {increments.quantile(0.05) * 100:.3f}, p95 {increments.quantile(0.95) * 100:.3f})",
        )
        check(
            f"{name}: soiling ratio stays physical (0 < ratio <= 1)",
            bool((ratio > 0).all() and (ratio <= 1.0).all()),
            f"min {ratio.min():.4f}, max {ratio.max():.4f}",
        )

    # --- Soiling actually costs energy ------------------------------------
    print("\n[3] Soiling reduces energy, and the two models agree")
    clean_total = specific_yield_kwh_per_kwp(clean_ac)
    for name, ratio in ratios.items():
        ac = hourly_ac_energy(hourly, soiling_ratio=ratio)
        soiled_yield[name] = specific_yield_kwh_per_kwp(ac)
        loss_pct = (clean_total - soiled_yield[name]) / clean_total * 100
        check(
            f"{name}: never-clean plant loses energy vs clean",
            soiled_yield[name] < clean_total,
            f"{loss_pct:.2f}% lifetime energy lost to soiling",
        )

    spread = abs(soiled_yield["Kimber"] - soiled_yield["AOD-modulated"]) / clean_total
    check(
        "the two soiling models agree within 2% of clean yield",
        bool(spread < 0.02),
        f"Kimber {soiled_yield['Kimber']:.0f} vs AOD {soiled_yield['AOD-modulated']:.0f} "
        f"kWh/kWp ({spread * 100:.2f}% apart)",
    )

    # --- Figure ------------------------------------------------------------
    FIGURE_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(13, 6.5))
    window = slice("2021-01-01", "2022-12-31")
    for name, ratio in ratios.items():
        axes[0].plot(ratio[window].index, ratio[window], lw=0.9, label=name)
    axes[0].set_ylabel("soiling ratio (1.0 = clean)")
    axes[0].set_title("Never-cleaned soiling accumulation, 2021-2022 (rain resets visible)")
    axes[0].legend(loc="lower left")

    axes[1].bar(annual.index.astype(str), annual.values, color="#c2731a")
    axes[1].axhline(SOLARGIS_PVOUT, ls="--", color="#1b1b1b", label=f"Solargis {SOLARGIS_PVOUT:.0f}")
    axes[1].axhspan(lo, hi, color="#2e7d32", alpha=0.12, label=f"acceptance band {lo:.0f}-{hi:.0f}")
    axes[1].set_ylabel("kWh/kWp")
    axes[1].set_ylim(0, 2000)
    axes[1].set_title("Clean-plant annual specific yield")
    axes[1].legend(loc="lower right")

    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    out = FIGURE_DIR / "m1_physics.png"
    fig.savefig(out, dpi=130)
    print(f"\n      figure written to {out.relative_to(Path.cwd())}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 62)
    if failed:
        print(f"M1 FAILED -- {len(failed)} check(s): {', '.join(failed)}")
        return 1
    print(f"M1 PASSED -- {len(RESULTS)}/{len(RESULTS)} checks")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
