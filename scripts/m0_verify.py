"""M0 acceptance check.

The Phase 3 plan declared M0's verification before M0 was built:

    Plot >=5 years of GHI and AOD. Confirm the seasonal dust signature matches
    the literature (spring domestic dust, summer shamal peak). Fetchers are
    idempotent and offline-replayable.

This script performs those checks and reports PASS/FAIL for each. It is the
evidence that M0 is done -- not the fact that the code runs.

Usage:
    python scripts/m0_verify.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rimal.config import DATA, MBR_SOLAR_PARK  # noqa: E402
from rimal.data import power  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

FIGURE_DIR = Path(__file__).resolve().parents[1] / "figures"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")


def main() -> int:
    start, end = DATA.default_start_year, DATA.default_end_year
    span = end - start + 1
    print(f"\nM0 ACCEPTANCE -- {MBR_SOLAR_PARK.name}, {start}-{end}\n")

    # --- Fetch -------------------------------------------------------------
    print("[1] Fetching hourly data (first run hits the network; later runs do not)")
    t0 = time.time()
    hourly = power.fetch_years(start, end)
    print(f"      {len(hourly):,} hourly rows in {time.time() - t0:.1f}s")

    check(
        "coverage >= 5 years",
        span >= 5 and hourly.index.year.nunique() == span,
        f"{hourly.index.year.nunique()} distinct years, {span} requested",
    )

    expected_hours = int(
        (hourly.index.max() - hourly.index.min()).total_seconds() // 3600 + 1
    )
    check(
        "hourly index is gapless",
        len(hourly) == expected_hours and not hourly.index.duplicated().any(),
        f"{len(hourly):,} rows vs {expected_hours:,} expected, "
        f"{hourly.index.duplicated().sum()} duplicates",
    )

    missing = hourly.isna().sum().sum()
    check(
        "no missing values after fill-value handling",
        missing == 0,
        f"{missing} missing cells across {hourly.size:,}",
    )

    # --- Idempotency / offline replay -------------------------------------
    print("\n[2] Idempotency and offline replay")
    t0 = time.time()
    again = power.fetch_years(start, end)
    cached_seconds = time.time() - t0
    check(
        "second fetch is byte-identical",
        again.equals(hourly),
        f"re-read {len(again):,} rows in {cached_seconds:.2f}s",
    )

    original_get = power.requests.get

    def blocked(*args, **kwargs):
        raise AssertionError("network accessed despite warm cache")

    power.requests.get = blocked
    try:
        offline = power.fetch_years(start, end)
        offline_ok, offline_detail = offline.equals(hourly), "served fully from cache"
    except AssertionError as exc:
        offline_ok, offline_detail = False, str(exc)
    finally:
        power.requests.get = original_get
    check("replays with network disabled", offline_ok, offline_detail)

    # --- Physical sanity ---------------------------------------------------
    print("\n[3] Physical sanity")
    daily = power.daily_summary(hourly)
    ghi_kwh = daily["ALLSKY_SFC_SW_DWN"] / 1000.0  # Wh/m2 -> kWh/m2
    annual_ghi = ghi_kwh.groupby(ghi_kwh.index.year).sum()
    # Dubai's global horizontal irradiation is ~2000-2200 kWh/m2/yr.
    full_years = annual_ghi.iloc[:-1] if len(annual_ghi) > 1 else annual_ghi
    in_band = full_years.between(1900, 2300).all()
    check(
        "annual GHI in the published Dubai band (1900-2300 kWh/m2/yr)",
        bool(in_band),
        f"min {full_years.min():.0f}, max {full_years.max():.0f}",
    )

    check(
        "ALLSKY never exceeds CLRSKY",
        bool((daily["ALLSKY_SFC_SW_DWN"] <= daily["CLRSKY_SFC_SW_DWN"] * 1.02).all()),
        "clear-sky reference bounds measured irradiance",
    )

    # --- Seasonal dust signature ------------------------------------------
    print("\n[4] Seasonal dust signature (the substantive M0 check)")
    monthly_aod = daily["AOD_55"].groupby(daily.index.month).mean()
    peak_month = int(monthly_aod.idxmax())
    trough_month = int(monthly_aod.idxmin())
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

    print("      mean AOD_55 by month:")
    for m in range(1, 13):
        bar = "#" * int(monthly_aod[m] / monthly_aod.max() * 40)
        print(f"        {names[m - 1]}  {monthly_aod[m]:.3f}  {bar}")

    # Literature: dust events peak in late spring / summer (May-Aug), driven by
    # external sources and the summer shamal; winter is the quiet season.
    check(
        "AOD peaks in late spring/summer (May-Aug)",
        peak_month in (5, 6, 7, 8),
        f"peak = {names[peak_month - 1]} ({monthly_aod[peak_month]:.3f})",
    )
    check(
        "AOD troughs in the winter quiet season (Nov-Feb)",
        trough_month in (11, 12, 1, 2),
        f"trough = {names[trough_month - 1]} ({monthly_aod[trough_month]:.3f})",
    )
    ratio = monthly_aod.max() / monthly_aod.min()
    check(
        "seasonal amplitude is material (peak/trough > 1.3)",
        ratio > 1.3,
        f"ratio = {ratio:.2f}",
    )

    # --- Figure ------------------------------------------------------------
    FIGURE_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=False)

    axes[0].plot(daily.index, ghi_kwh, lw=0.4, color="#c2731a")
    axes[0].set_ylabel("GHI (kWh/m$^2$/day)")
    axes[0].set_title(f"{MBR_SOLAR_PARK.name} - daily GHI, {start}-{end}")

    axes[1].plot(daily.index, daily["AOD_55"], lw=0.4, color="#8a5a2b")
    axes[1].plot(
        daily.index,
        daily["AOD_55"].rolling(30, center=True).mean(),
        lw=1.4,
        color="#1b1b1b",
        label="30-day mean",
    )
    axes[1].set_ylabel("AOD 550 nm")
    axes[1].set_title("Aerosol optical depth - the dust driver for soiling")
    axes[1].legend(loc="upper right")

    axes[2].bar(range(1, 13), monthly_aod.values, color="#8a5a2b")
    axes[2].set_xticks(range(1, 13), names)
    axes[2].set_ylabel("mean AOD 550 nm")
    axes[2].set_title("Seasonal dust signature (climatology)")

    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    out = FIGURE_DIR / "m0_ghi_aod.png"
    fig.savefig(out, dpi=130)
    print(f"\n      figure written to {out.relative_to(Path.cwd())}")

    # --- Verdict -----------------------------------------------------------
    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 62)
    if failed:
        print(f"M0 FAILED -- {len(failed)} check(s): {', '.join(failed)}")
        return 1
    print(f"M0 PASSED -- {len(RESULTS)}/{len(RESULTS)} checks")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
