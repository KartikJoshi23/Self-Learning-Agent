# PROGRESS.md — Single Source of Truth for Project State

> **Read this before doing anything. Update it before you stop.**
> Resume instructions live in [HANDOFF.md](HANDOFF.md).
> The binding methodology lives in [Problem-Solving-Skill.md](Problem-Solving-Skill.md).

**Last updated:** 2026-09-12 · by **Master** (Kartu)
**Repository:** https://github.com/KartikJoshi23/Self-Learning-Agent

---

## Current status

| Field | Value |
|---|---|
| **Current phase** | **Phase 4 — Development, post-completion.** Tiers 1 and 2 (M0–M7) complete; Tier 3 not yet scoped. |
| **Phase state** | **Live site built 2026-09-12** (`site/`, Next.js static export, eight pages) and awaiting the Master's Vercel import. **Master review of the collaborator's M6–M7 / audit / simulator work completed 2026-09-12.** Two data-layer faults found and fixed (an upstream rainfall units change, a corrupted lead-in year), every acceptance script re-run on the corrected environment, and the published numbers re-baselined from those runs — logs in `results/`. Conclusion in [FINDINGS.md](FINDINGS.md). **Awaiting Master's decision on Tier 3** — see below. |
| **Blocked on** | Nothing. |
| **Next action** | **Import the repo in Vercel (root directory `site`) and add the live URL to README.md and PROGRESS.md.** Then: **Master decision on Tier 3 scope.** All eight milestones are done and the conclusion is written. Tier 3 as originally planned (continual learning, offline RL, benchmark release) assumed an agent worth deploying; the finding is that a Kalman filter plus a threshold wins. Recommended Tier 3 is therefore **publication of the benchmark and the negative result**, not more agent machinery — see "Next up". |
| **Code written so far** | `rimal/{config,data,physics,env,baselines,eval,agents}`, **195 passing tests**, `scripts/` verify m0–m7 + simulator export/verify + site export, `results/` acceptance logs, `web/` browser simulator, `site/` live site, `FINDINGS.md`, `README.md`. |

---

## Phase gates

Phases run in order. None may be skipped or combined. Each gate needs the
Master's explicit approval before the next phase begins.

| # | Phase | State | Approved by Master |
|---|---|---|---|
| 1 | Read + confirm methodology (`Problem-Solving-Skill.md`) | ✅ Complete | ✅ Yes — 2026-08-29 |
| 2 | Deep research + agent concept proposal | ✅ Complete (audited, 8 corrections) | ✅ Yes — 2026-08-29 |
| 3 | Full implementation plan | ✅ Delivered (`IMPLEMENTATION-PLAN.md`) | ✅ **Tier 1 approved** — 2026-08-29 |
| 4 | Development — Tier 1 (M0–M4) | ✅ Complete | ✅ Approved 2026-08-29 |
| 5 | Development — Tier 2 (M5–M7) | ✅ Complete: M5 ✅ M6 ✅ M7 ✅ | ✅ Approved 2026-08-29 |
| 6 | Tier 3 — scope needs redefining, see below | ⬜ Not approved | ⏳ Master's call |

---

## Fixed project constraints

These do not change without the Master saying so explicitly.

- **Zero cost.** No paid APIs, no paid compute, no paid datasets, no cloud bills.
- **Repository is public** and stays public (Master decision, 2026-08-29).
- **Laptop-only.** Must train and evaluate on a CPU laptop. No GPU cluster assumed.
- **Employability first, government pitch second.** The primary deliverable is a
  portfolio-grade, interview-defensible build. A government pitch is a follow-on
  only if the build works.
- **Methodology is binding.** `Problem-Solving-Skill.md` applies to every phase.
- **Five concept criteria** (all must hold simultaneously): genuine Dubai/UAE
  government relevance · UAE recruiter-market relevance · genuine originality
  (not what most builders would produce) · real self-learning/RL depth (not an
  LLM wrapper) · grounded in citable research.

---

## Done

### Phase 1 — Methodology (complete, approved)
- Read `Problem-Solving-Skill.md` in full (six phases + checklist).
- Confirmed understanding with the Master and mapped each methodology phase onto
  this project's research-and-selection work.
- Master confirmed and supplied the zero-cost / laptop-only and
  employability-first constraints.

### Phase 2 — Research (complete, audited, approved)
- Surveyed UAE/Dubai government strategy landscape: Dubai Universal Blueprint for
  AI, UAE National AI Strategy 2031, Dubai Clean Energy Strategy 2050, UAE Water
  Security Strategy 2036, D33 economic agenda, Dubai Future Foundation funding tracks.
- Surveyed the UAE AI hiring market for 2026 (demand/supply gap, what employers
  screen for, where candidate saturation is).
- Surveyed the technical literature on PV soiling, cleaning-schedule optimisation,
  and the RL methods relevant to it.
- Confirmed free, laptop-viable data and tooling exists for the recommended concept.
- Evaluated five candidate concepts against the five criteria; recommended **RIMAL**.
- **Audited the whole research pass; found and corrected 8 errors (2 material).**
  Findings and audit log written to `RESEARCH.md`.

---

### Phase 4 / M0 — Data layer (complete, verified 2026-08-29)
- Project scaffold: `pyproject.toml`, `requirements.txt`, `.venv`, pytest config.
- `rimal/config.py` — site constants and DEWA-derived calibration values, each traced to source.
- `rimal/data/power.py` — NASA POWER hourly fetcher, per-year chunking, parquet cache,
  `-999` fill-value handling, local-time and daily-summary helpers.
- 14 tests passing (12 offline + 2 live-API guards).
- **`scripts/m0_verify.py` — 10/10 acceptance checks PASSED.** Figure at `figures/m0_ghi_aod.png`.

**Two findings from M0 worth carrying forward:**
1. **NASA POWER serves `AOD_55` hourly.** One API supplies both irradiance and the dust
   driver, with no registration. **Copernicus CAMS leaves the critical path; risk R6 closed.**
2. **The hourly JSON cap is on payload size, not time span.** Measured: 9 parameters x 3
   years succeeds, 9 x 5 is rejected (HTTP 422), 4 x 5 succeeds — the cap sits between 27
   and 45 parameter-years. An earlier belief that ">1 year is rejected" was wrong and has
   been corrected in code, docstring and test. Per-year chunking retained as it is
   comfortably inside the cap.

---

### Phase 4 / M1 — Physics core (complete, verified 2026-08-29)
- `rimal/physics/plant.py` — pvlib PVWatts ModelChain; Erbs decomposition from GHI;
  soiling applied as a derate on the irradiance components; specific-yield helpers.
- `rimal/physics/soiling.py` — `KimberSoiling` (constant rate) and
  `AodModulatedSoiling` (rate scales with AOD), sharing one accumulation core.
- **`scripts/m1_verify.py` — 10/10 PASSED.** Yield 1703-1802 kWh/kWp (Solargis 1791.5);
  Kimber 0.235 %/day and AOD-modulated 0.224 %/day, both inside DEWA's 0.14-0.33 band;
  never-cleaned loss 17.55% / 17.27%, models agreeing within 0.28%.
- Tests 16 -> 31. Figure at `figures/m1_physics.png`.

**Three defects found while verifying M1 (all fixed):**
1. **Rainfall was 24x too high.** Hourly `PRECTOTCORR` is a **mm/day rate**, not a
   per-hour depth, so summing it overcounted 24x — Dubai showed 4,405 mm/yr against a
   real ~80-110. Rain is the natural-cleaning trigger, so this turned 4 washing days a
   year into 40 and made a never-cleaned plant look like it lost only 2.8% of its
   energy. Now averaged; 2020 totals 171.5 mm against POWER's own daily product at
   171.4. A network test pins this so it cannot regress.
2. **POWER's irradiance components do not close** against its own GHI (95.1%), putting
   yield below the band. DNI/DHI now derived from GHI via Erbs (closure 1.0000); POA
   ~2323 kWh/m2 vs Global Solar Atlas GTI 2336.2, a 0.6% match. **The acceptance band
   was not widened — the model was fixed.**
3. **The phantom-local-day bug survived in the yield path.** Now factored into
   `power.complete_local_days()` and used by every consumer.

**Deviation from the approved plan:** the plan named pvlib's **HSU** model as the
soiling cross-check. HSU needs PM2.5/PM10 and NASA POWER serves neither (verified
against both parameter catalogues); sourcing PM would add a registration-gated dataset
and break the zero-friction data path. `AodModulatedSoiling` replaces it, serving the
same purpose — an independent deposition mechanism for model-robustness — from
available data.

---

### Phase 4 / M2 — Gymnasium environment v0 (complete, verified 2026-08-29)
- Read **arXiv:2603.07518 in full** (the blocking prerequisite). Formulation: state =
  deposition + days-since-cleaning + temperature + wind + PM + irradiance (**soiling
  directly observable**); binary action; Eq. (4) resets soiling to **exactly 0**
  (perfect cleaning); synthetic weather from fitted monthly distributions; **sparse
  reward once per 20-year episode**. **All four RIMAL differentiation axes confirmed
  unclaimed.** The paper independently names our CVaR gap as its own limitation
  ("suboptimal policies when faced with rare or extreme conditions").
- `rimal/env/cleaning_env.py` — `Rimal-Cleaning-v0`, daily step, 7-dim observation,
  binary action, dense daily reward, one-calendar-year episodes over real data.
- `rimal/env/energy_table.py` — precomputed energy vs soiling ratio, interpolated at
  step time. **Linear scaling was measured to be up to 2.0% wrong** (a soiled array
  clips less and runs cooler) — the same order as the margin a policy competes for —
  so the true pvlib chain is tabulated instead. Worst annual error 0.0019%.
- **`scripts/m2_verify.py` — 10/10 PASSED.** Tests 31 → 49.

**One defect found while verifying — in the check, not the environment.** The
soiling-trajectory comparison was misaligned twice: (a) a year's daily frame depends
on the fetch span, since the first local day of a year needs the prior year's final
UTC hours (2020 alone → 365 days from 02 Jan; 2016-2025 → 366 from 01 Jan); and (b)
the reference ran continuously from 2016, carrying December 2019's soiling into an
episode that starts clean. Both fixed; trajectories now agree to **0.00e+00**.

---

### Phase 4 / M3 — Baselines, metrics, falsification gate (complete, verified 2026-08-29)
- `rimal/baselines/policies.py` — never-clean, always-clean, fixed-interval,
  soiling-threshold; `rimal/eval/harness.py` — episode runner, CVaR on the lower
  tail, policy comparison, and an independent closed-form optimal interval.
- **`scripts/m3_verify.py` — 7/7 PASSED.** Tests 49 → 65.

**🎯 THE FALSIFICATION GATE PASSED.** Run as an existence claim with the admissible
cost range fixed *before* the sweep ($25–150/MWp): some plausible cost must put the
optimum in 28–34 days. **$60/MWp → 31 days and $75/MWp → 34 days**, both inside the
published band. The swept optimum also tracks the closed form
`T* = sqrt(730·C/(E·p·r))` to a mean 19% (17.8% on the 2026-09-11 re-run), consistently longer — as expected, since the
closed form ignores rain resets.

**Default cleaning cost changed $300 → $60/MWp. This is a CALIBRATION, not a
measurement**, and is labelled as such in the code. $300 was an unsourced placeholder;
$60 is the midpoint of the range reproducing published behaviour, and is independently
plausible at ~3 US cents per module per clean (1 MWp ≈ 2,105 modules at DEWA's
445–505 W rating) — the right order for the dry robots DEWA is trialling.

**Reported rather than hidden: the optimum is genuinely flat.** At the default cost any
interval from **16 to 57 days** is within 1% of optimal. Quoting the argmax alone would
overstate how well-determined it is.

**Baselines on held-out years 2023–2025 (USD/MWp/yr):**

| policy | mean net | CVaR@5% | cleans | soiling loss |
|---|---|---|---|---|
| **threshold-0.95** | **27,600** | 27,362 | 12.3 | 1.9% |
| threshold-0.92 | 27,570 | 27,263 | 7.7 | 2.9% |
| fixed-34d | 27,487 | 27,309 | 10.0 | 2.7% |
| fixed-28d | 27,449 | 27,315 | 12.7 | 2.3% |
| never-clean | 24,610 | 22,356 | 0.0 | 14.8% |
| always-clean | 6,980 | 6,905 | 365.0 | 0.0% |

Condition-based thresholds beat fixed intervals, so **M4 faces a harder bar than
fixed-interval alone would have set**.

---

### Phase 4 / M4 — PPO agent (complete, verified 2026-08-29)
- `rimal/agents/ppo.py` — CleanRL-style single-file PPO with observation normalisation.
- **Declared criterion PASSED:** PPO $27,627 ± 18 beats every fixed interval (+$127).
- **But the headline is a NULL RESULT:** `tuned-threshold-0.93` scores **$27,651** —
  PPO loses by $24, inside seed noise. In v0 soiling is observed exactly and cleaning is
  a perfect reset, so the optimal policy *is* a threshold on an observed scalar.
- **A near-miss worth recording:** the first run "passed" against `threshold-0.95`
  ($27,600) from a hand-picked M3 grid that never tested 0.93. The true optimum was
  worth ~$50/MWp/yr more — about twice PPO's apparent margin. Baselines are now tuned on
  *training* years via `tune_threshold()`, the same protocol the agent gets.
- Three bugs fixed to get PPO learning: a policy with no state-dependent rule at all
  (constant P(clean)≈0.038, greedy = never-clean); a reward whose action-dependent part
  ($2.50) was drowned by a constant ($80); and **missing observation normalisation** —
  the actual cause, since soiling ratio arrives in [0.70, 1.00].

**Re-run 2026-09-11 on the corrected environment** (`results/m4_verify.log`): **PASSED 5/5.**
PPO **$27,657 ± 32** vs tuned threshold **$27,677 (−$20)**; +$131 over the best fixed
interval; 8.4 cleans/yr, every seed beats never-clean. Same conclusion as both earlier runs.

### Phase 4 / M5 — Partial observability (complete, verified 2026-08-29)
- `rimal/env/observation.py` — heteroscedastic noise model + Kalman filter;
  `BeliefThreshold`, `ScheduleAwareThreshold`, `BeliefStateWrapper`.
- **All three declared criteria PASSED. One self-imposed scrutiny check FAILED.**

**M5 overturns the M4 null result.** The rule that beat PPO collapses once soiling is
latent (held-out, USD/MWp/yr):

| noise | naive thr | guarded | Kalman belief | blind fixed-31d |
|---|---|---|---|---|
| exact | 27,651 (8.3c) | — | — | 27,500 |
| 0.03 | 27,148 (22.3c) | 27,240 | **27,638** (8.3c) | 27,500 |
| 0.10 | 22,232 (109c) | 26,198 | **27,632** (8.3c) | 27,500 |

The naive rule loses **$5,418 (19.6%)** by *chatter*, not neglect. **From 3% noise up, a
blind fixed interval beats the sensor-driven rule.** The belief policy is nearly immune:
$19 spread across 1–10% noise.

**Belief RMSE 0.0262 → 0.00149 (17.6× reduction; 17.7× on the 2026-09-11 re-run)** after fixing two filter bugs: it
ignored the 14-day rain grace period (drift up to 0.033 — the same order as the noise it
was removing), and it had an off-by-one on rain (env applies a day's rain to the
*following* day).

**PPO, 5 seeds:** belief-state $27,565 ± 30 vs memoryless $27,501 ± 43, **+$64, Welch
t=2.71, p=0.030** — criterion (b) genuinely established. *(The first run reported this as
a PASS on +$43 at n=3, p=0.194. The check now requires significance.)*

**⚠️ The scrutiny check that failed:** neither learned agent beats the hand-built rule —
PPO belief-state $27,565 vs `BeliefThreshold` $27,638 (−$74).

**Re-run 2026-09-11 on the corrected environment** (`results/m5_verify.log`, 5 seeds):
**declared 8/9 — criterion (b) FAILED; scrutiny FAILED.** Everything about the rule
reproduced: belief RMSE 0.00149 vs raw 0.02626 (**17.7×**), naive collapse **−$4,771
(17.2%)** at 10% noise with **97.8 cleans/yr**, blind fixed-31d ($27,526) beats the naive rule
from 3% noise, the belief policy within **$23** of exact observability at every level. **But
the PPO comparison did not replicate:** belief-state **$27,546 ± 18** vs memoryless
**$27,517 ± 37**, **+$29, Welch t = 1.59, p = 0.165** — where the published run had +$64 at
p = 0.030. The earlier significance was fragile at n = 5 and is now recorded as **not
established**. Nothing about the cross-milestone conclusion changes; if anything it sharpens
(a Kalman filter helps a rule enormously and a neural policy barely at all). Scrutiny:
PPO belief-state $27,546 vs `BeliefThreshold` $27,656 (−$110).

**Deviation from the approved plan (recorded 2026-09-11 by Master):** the plan's D3 named
*recurrent PPO* for the POMDP. M5 used a **belief-state wrapper** (Kalman estimate fed to a
memoryless PPO) instead of an LSTM policy; the reasoning is in
`rimal/env/belief_wrapper.py`'s docstring (an explicit filter is inspectable and its RMSE is
measurable, which a hidden LSTM state is not). The plan's criterion (b) was tested with the
belief-state agent as the "recurrent/belief agent". No recurrent policy was trained.

---

## Post-completion audit (2026-09-09)

A deep audit of the whole solution after M7. **Five issues, three of them real defects
that had already reached published output.**

| # | Issue | Status |
|---|---|---|
| 1 | **Circular import.** `rimal/env/belief_wrapper.py` imported observation-layout constants from `rimal.baselines`, closing a cycle that broke `scripts/m3_verify.py` **for three milestones**. Only fails when baselines is imported before env — pytest's collection order masked it. | ✅ Layering fixed; `tests/test_imports.py` guards it structurally (AST, fresh interpreter) |
| 2 | **The headline figure came from 3 episodes.** `evaluate()` defaulted to one stochastic realisation per year. Resampled at 120/point: collapse is **−$4,763 (17.2%)**, not −$5,418 (19.6%) — overstated ~13% relative. | ✅ `evaluate()`/`compare()` take `seeds`; M5 uses 40 |
| 3 | **`m5_verify` crashed after every check** — `check()` grew a `declared` flag, the summary still unpacked 3 fields. Latent since the labelling was added, undetected because the script was never re-run. | ✅ Fixed; `tests/test_verify_scripts.py` guards arity for all 8 scripts |
| 4 | M6's conclusions were single-realisation. Re-tested at 120 episodes, paired t-tests: efficacy-aware −104.0 ± 3.8 (**p < 0.0001**), partial-cleaning +27.8 ± 8.3 (**p = 0.0011**). | ✅ Both survive, now properly powered |
| 5 | README was **seven milestones stale** — still said "M0 complete" on a public repo. | ✅ Rewritten |

**The pattern worth recording:** every one of these was invisible to the test suite *by
construction* — masked by collection order, hidden behind a default argument, or in prose
nothing tested. Two of those categories are now permanently guarded. Twice an edit broke
an *earlier* acceptance script and nothing noticed, because the script was never re-run;
that is now a static check on every commit.

Verified unchanged by the audit: **M0 11/11 · M1 10/10 · M2 10/10 · M3 7/7 · M5 8/8
declared**, and the 17.6× belief-RMSE headline reproduces exactly. Tests 133 → **176**.

---

## Master review (2026-09-11)

Phase 5 of the methodology applied to everything committed since `55a5488` (M6, M7, the
audit, the simulator, the handoff rewrite). `pytest` was green and m0–m3 passed on arrival;
the faults below were found by **probing the live data source** and by **reading the cache
the code trusts**, neither of which the suite does.

| # | Finding | Status |
|---|---|---|
| R1 | **NASA POWER changed the units of hourly `PRECTOTCORR`** between 2026-08-29 and 2026-09-11 — from a mm/day *rate* to a per-hour *depth*, every other column byte-identical (`old == 24·new` to within the new product's 0.005 mm rounding; daily product unchanged at 171.4 mm for 2020). The code averaged it, correctly for August's form and **24× too low** for September's: a fresh clone computed **7.1 mm/yr**. Invisible on a warm cache — the physical-floor guard passes and the network test deliberately read the cache. | ✅ Every fetch now classifies its units against POWER's daily product (ratio ≈ 24 → rate, ≈ 1 → depth ×24, else refused) and caches the canonical rate. Network test fetches fresh. 9 new tests. |
| R2 | **The 2015 lead-in year was cached corrupted** (`PRECTOTCORR = −99,000` every hour), written nine minutes before the physical-floor guard was committed and never re-validated on read. Leakage: **1 Jan 2016 rain = −16,498 mm/day** in the training environment. No published result affected (nothing was trained after 09-10), but any re-run on this machine would have been. | ✅ Cached files are cleaned and validated on every read, refused by name if bad. 2015 deleted and refetched (89 mm/yr). `_rain.min() = 0.00` on both train and held-out envs. |
| R3 | **Published dollar figures no longer reproduced.** The collaborator's lead-in fix restored 1 Jan 2023 to the held-out set (364 → 365 days); `threshold-0.93` moved $27,651 → $27,677. The commit asserted "no conclusion changes" but M4–M7 were not re-run. | ✅ **M4–M7 re-run on the corrected environment**; every number in FINDINGS/README/PROGRESS re-baselined from the observed output; logs committed under `results/`. See the M4–M7 sections and FINDINGS.md for the figures. |
| R4 | The simulator's "verified in node" figures were asserted; the harness was not committed, nor the export that produced `sim_data.json`. | ✅ `scripts/export_sim_data.py` rebuilds `sim_data.json` and `simulator.html` **byte-for-byte** (`--check`); `scripts/verify_simulator.py` slices the physics out of the *shipped* HTML, runs it under node and compares with the engine — **8/8**: soiling to 6.8e-5, clean energy to 3e-7, soiled energy to 0.017%, identical rain and cleaning days for naive, belief and fixed rules. Both under test. |
| R5 | M0's declared checks could see neither fault. | ✅ Section [5] added: rainfall never negative in any cached year incl. the lead-in; mean annual rainfall in 30–1000 mm. **13/13.** Injecting the 24× bug turns it red (observed). |
| R6 | Two plan deviations unrecorded (M5 recurrent PPO → belief wrapper; M7 Lagrangian PPO never built). Session log nine sessions short. Test count stated three different ways. | ✅ Recorded under M5/M7; session log reconstructed from git and labelled; counts reconciled. |

**Verified on arrival, before any change:** `pytest` 183 passed · M0 11/11 · M1 10/10 ·
M2 10/10 · M3 7/7. **Verified after:** see the session-log row and FINDINGS.md.

### Audit of the review itself (2026-09-12, before starting the site)

The strongest falsification of R1 is the one it claims to enable: **a fresh clone, fresh
venv, empty cache, today's endpoint**. Done at a short temp path (`rf/`, deleted after).

| # | Finding | Status |
|---|---|---|
| A1 | **`requirements.txt` had no `torch`** (headed "Core (M0–M3)"), so the README's `pip install -r requirements.txt && pytest -q` **failed at collection** on the fresh clone (`test_agents`, `test_risk`). | ✅ `torch>=2.4` added with the CPU-index note; README quick start updated. |
| A2 | **Fresh clone reproduces the record.** From an empty cache against the live endpoint: **M0 13/13** (annual rainfall 89/172/408/… mm vs the Aug-29 cache's 89/173/409/… — the 0.7% rounding loss of the new product), M1 10/10, M2 10/10, and **M3's table byte-identical to `results/m3_verify.log`**. Full suite **194 passed** in the fresh venv. | ✅ Observed. |
| A3 | **`export_sim_data.py --check` could never pass on a fresh clone**: it demanded byte-equality on `rain`, but the new upstream product's 2-dp rounding shifts ~340 of 1,096 daily values by ≤ 0.05 mm/day — with every wash day, cleaning day and energy figure identical (the node harness passed in the same clone). | ✅ Check now exact on `aod`/`clean`/`k`, rain within the documented 0.12 rounding bound **and** identical wash-day sets. Falsified: flags a threshold crossing inside the bound, an out-of-bound shift, a length change, any `aod`/`k` change. Passes in both clones. |
| A4 | Stale figures in FINDINGS: falsification table said $50 → **27** days (log: 25); closed-form gap "19%" (log: 17.8%); "one seed collapsed to never-cleaning" no longer matched the re-run (2.3 cleans/yr). | ✅ Corrected from the logs. |
| A5 | `IMPLEMENTATION-PLAN.md` still read "awaiting Master approval"; `RESEARCH.md` still listed the arXiv read as open. | ✅ Status lines corrected with pointers to the recorded deviations. |

Not found: no drift between the master venv and a fresh install (both pandas 3.0.5 / numpy
2.4.6 / pvlib 0.15.2 / torch 2.14.0+cpu).

---

## Live site (2026-09-12)

Concept and plan approved by the Master on 2026-09-12 (Next.js + three.js + framer-motion, same
repo under `site/`, fresh single-seed agents for the "learnt" exports, errors section kept, Vercel
Hobby). Redirected mid-build from a single scroll to **a nav bar and one page per section**, with one
uniform template (header → stat row → panels → note).

**What it is.** Next.js 16 static export (`output: "export"`, no server), eight routes: overview
(WebGL hero — a dust field driven by real AOD, an array soiling at the storm model's rate, the year
playing through), calibration, detection, learning, simulator, verdict, errors, reproduce.

**What it shows, and where it comes from.** The site has no numbers of its own.
`scripts/export_site_data.py` writes `site/public/data/`: `weather.json` (ten years, from the engine),
`gate.json` (the M3 sweep, **asserted equal to `results/m3_verify.log`**), `ppo.json` (one PPO seed
trained as M4 trained it, with the policy captured **untrained / 10% / 30% / trained** via a new
default-preserving `checkpoint` argument on `rimal.agents.ppo.train`, plus the trained actor's
weights), `fleet.json` (M6's estimator day by day), `qrdqn.json` (one QR-DQN seed's quantile fans),
`results.json` (every headline number **parsed by regex from `results/*.log`** — a number the pattern
cannot find is an error, not a default).

**The physics in the browser is the engine's.** `site/src/lib/physics/rimal.js` is the simulator port
as an ES module; `scripts/verify_simulator.py --module` runs it under node against the engine:
**10/10** — soiling to 6.8e-5, energy to 0.017%, identical rain and cleaning days for naive, belief,
fixed, guarded **and the trained PPO actor (its JS forward pass vs torch, day for day)**. Under test in
`tests/test_simulator.py`. On exact readings the trained actor cleans 16/10/19 times on 2023–25 against
the naive 0.93 rule's 16/11/19 — it rediscovered the threshold.

**Verified.** `tsc --noEmit` and `eslint` clean · `npm run build` 9 static routes · every route
audited in headless Chrome at 1440×900 and 390×844 (`site/scripts/shoot.mjs`): zero console errors,
zero failed requests, no horizontal overflow, served from the `out/` export by a plain file server ·
Lighthouse desktop on the export: home **80 / 100 / 100 / 100** (perf / a11y / best practices / SEO,
LCP 1.7 s on software GL), learning 93, simulator 94, both a11y 100 · chart palette validated for CVD
separation and contrast against the surface (dataviz validator).

**Bugs found and fixed during the build.** An intermittent crash on the mobile home page (day index
racing the data load — clamped); Lenis swallowing `#anchor` navigation (moot after the move to
routes); WebGL context loss leaving a white rectangle (now falls back to the static hero); Next's
link prefetch requesting RSC payload files the static export names differently (prefetch disabled —
click navigation itself works, 62 ms); the hero lede painting only after hydration (LCP 2.5 s → 1.7 s
by animating it in CSS); an `aria-label` on a plain div and a 4.4:1 chip contrast (a11y 90 → 100).

**Not verified:** the Vercel deployment itself — the import is a Master account action. The
stand-alone `web/simulator.html` is unchanged.

**Deviation from the site plan:** GSAP is present (it drives Lenis from its ticker and registers
ScrollTrigger) but no scroll-scrubbed timeline survived the move from one scroll to eight pages.

**Constraints:** no conflicts. ZERO COST (NASA POWER, node, torch-CPU) and LAPTOP-ONLY
hold; `web/sim_data.json` is 26 KB of derived held-out data, not raw data.

---

## Cross-milestone finding: state estimation, not control

**Four** consecutive milestones now show a model-based rule beating model-free deep RL:
M3 (tuned threshold > every fixed interval), M4 (tuned threshold > PPO), M5
(Kalman+threshold > both PPO variants), M6 (fleet heuristic > PPO by $581, with one seed
in five collapsing entirely; −$456 and a near-collapse on the 2026-09-12 re-run).

**M6 was the milestone designed to break the pattern, and it did not.** It asked whether
stochastic efficacy and a degrading actuator create structure filter-plus-threshold
cannot express. The answer is no: the fleet dimension is second-order at this plant's
economics, and the one part that pays is again a *filter* improvement, not a control one.

**The honest reading is that the hard part of this problem is state estimation, not
control.** Once soiling is known, the control law is a threshold. The single largest
effect anything has produced in this project is M5's **17.6× belief-RMSE reduction** —
from a Kalman filter, not a neural network.

**This is not a failed project.** "We built a simulator calibrated to DEWA's own
measurements, tested four hypotheses about where adaptive control adds value, and found
the problem is a filtering problem" is a stronger and more credible result than a
manufactured RL win — and DEWA would recognise an inflated claim about their own asset
immediately.

**Recommendation to the Master:** run **M7 (CVaR under shamals)**, because risk
sensitivity is the one axis a threshold rule genuinely cannot express, and M3 already
hinted at it — `never-clean` had by far the worst CVaR ($22,356) and 10× the variance of
any cleaning policy. **If M7 also returns negative, stop adding machinery and write up
the honest conclusion** rather than continuing until something wins.

---

### Phase 4 / M6 — Stochastic efficacy and actuator wear (complete, verified 2026-09-02)
- `rimal/env/robots.py` — five-robot fleet: stochastic efficacy, latent health, wear,
  battery cooldown. Fleet mode: 11 actions, 24-dim observation.
- `FleetHeuristic` / `RoundRobinFleet` — deliberately strong opponents.
- **Declared criteria 3/4. The failing one is the finding.** Tests 92 → 110.

**Two flaws in this project's own model, both caught by measurement:**
1. The first fleet had **no dispatch decision at all** — robot A had the highest efficacy
   *and* low wear, so it dominated forever and "always use A" beat efficacy-aware
   dispatch. Fixed by modelling DEWA's documented **battery overheating** as a cooldown.
   Added *after* the flaw was found; recorded as such.
2. The sweep **never swept** — cleaning frequency was 10.0/yr at every cost because the
   threshold was held fixed instead of retuned per cost. Redone; frequency now 43→5/yr,
   and the conclusion survived.

**Findings (held-out, USD/MWp/yr):**
1. Stochastic partial cleaning is real: **$190/yr (0.7%)** vs the idealised world.
2. But *assuming* perfect cleaning costs only **$16–69/yr (<0.25%)** — the Kalman filter
   self-corrects within days. **This corrects Phase 2's own reasoning**, which listed
   perfect-cleaning as a major unclaimed axis. It is an axis, but a small one.
3. **Learning which robot is good loses at every cleaning frequency (−$14 to −$117).**
   Sharp version: **Spearman ρ = 1.00** — the estimator ranks the fleet *perfectly* and
   still loses, because the exploration is paid for in cleans at $60 each. A
   short-horizon bandit result.
4. Graceful degradation holds: a 30× faster-wearing fleet loses only 2.91%.

**PPO on the fleet env (5 seeds):** $26,983 ± 1,085 vs best rule $27,564 (**−$581**).
**Seed 4 collapsed to never-clean (0.3 cleans/yr).** Excluding it: $27,468 ± 56, still
−$96. *One seed in five failing to learn at all is a robustness result in its own
right* — a policy that collapses 20% of the time is not deployable.

**Re-run 2026-09-12 on the corrected environment** (`results/m6_verify.log`), with
`m6_verify.py` strengthened to evaluate every held-out cell at **40 seeds/year (120
episodes)** and to print the paired tests the audit had computed ad hoc: **declared 3/4
(dispatch check FAILED, as before); scrutiny FAILED.** Partial cleaning costs **$181/yr**;
modelling it is worth **$28–90/yr across costs, +$28.4 ± 7.9 at $60 (p = 0.0005)**;
efficacy-aware dispatch **loses at every frequency, −$102.8 ± 3.6 at $60 (p < 0.0001)**
with Spearman ρ = 1.00; 30× wear costs **2.94%**. PPO **$27,133 ± 488 vs rule $27,589
(−$456)**: seed 1 near-collapsed (2.3 cleans/yr), seed 2 over-cleaned (23.3/yr) — the same
instability as the first run, in a different seed.

---

### Phase 4 / M7 — Risk sensitivity and the water constraint (complete, verified 2026-09-05)
- `rimal/physics/soiling.storm_soiling` — superlinear, tail-preserving deposition.
- Water CMDP: wet crew (8.5 m³/MWp/pass) + hard annual budget. 13 actions, 27-dim obs.
- `rimal/agents/qrdqn.py` — QR-DQN with CVaR action selection. Tests 110 → 133.

**Two defects in our own earlier work, both found before M7 could be measured:**
1. **M1 clipped the soiling tail away.** DEWA's 0.14–0.33 %/day is an *average*, not a
   per-day ceiling. The clip pinned 18.7% of days at the cap and compressed an 8× AOD
   spread into 1.5× of soiling — **deleting the phenomenon M7 exists to study**, and
   overstating CVaR across M3–M6 by **~$391/MWp/yr**.
2. **A self-inflicted train/eval mismatch.** The model used the passed frame's own mean
   AOD as reference, so identical dust implied a **0.70× different rate** in evaluation
   than in training — structurally disadvantaging trained policies against online
   filters. Now pinned to a fixed climatology, with a regression test.

**Findings:**
1. Storms create the **first genuine risk/return trade-off** in the project: mean-optimal
   threshold 0.94 vs CVaR-optimal 0.96; +$58 CVaR costs −$55 mean. Under clipping both
   optima sat at 0.94.
2. Water constraint is cheap: **100% satisfaction, $43/MWp/yr (0.16%)** at the tightest
   budget — independently confirming audit finding E2.
3. **QR-DQN loses to a CVaR-tuned threshold**, like for like: rule CVaR **$26,890** vs
   agent **$26,727** (−$163) at seed sd $54.
4. **And the declared criterion fails too.** With the post-hoc α selection removed, CVaR
   does **not** rise monotonically with risk aversion: $26,710 → $26,752 → $26,626 →
   $26,641 as α falls 1.00 → 0.10. The ordering is noise. The distributional machinery
   worked; the advantage never materialised. **M7 declared: FAILED. M7 scrutiny: FAILED.**

**A check of ours that passed for the wrong reason.** The declared CVaR criterion picked
the best risk level *after seeing the results*; with four αs, three seeds and sd ≈ $50,
the max of four noisy numbers beats the reference by chance. The better-powered
evaluation then put risk-neutral top. Replaced with a single pre-specified prediction
(CVaR monotone in risk aversion), which the data does not support.

**Deviation from the approved plan (recorded 2026-09-11 by Master):** the plan's D3 and
M7 row named *Lagrangian PPO* for the water CMDP. **No Lagrangian agent was built.** The
water budget was implemented as a hard constraint in the environment and evaluated with
the rule policies (100% satisfaction at every budget, sacrifice reported as the cost of
the tightest budget). Given that the constraint binds at negligible cost, a Lagrangian
agent had nothing to trade off; defensible, but it is a deviation and is recorded as one.

**Re-run 2026-09-12 on the corrected environment** (`results/m7_verify.log`): **declared
FAILED, scrutiny FAILED** — as before. Clipping overstated CVaR by $391 (unchanged);
mean-optimal 0.94 vs CVaR-optimal 0.96, **+$62 CVaR for −$55 mean**; water **100%
satisfied at every budget, tightest costs $37/MWp/yr (0.14%)** — this settles the earlier
$43 (PROGRESS) vs $29 (FINDINGS) discrepancy, which were two different runs. QR-DQN CVaR by
α: $26,759 → $26,798 → $26,780 → $26,728 — **not monotone**. Like for like: rule CVaR
**$26,890** (identical to the first run) vs agent **$26,388 at α = 0.25 (−$501)**, seed sd
$299 at n = 3 — the agent's held-out tail is both worse and far noisier than first reported
(−$163 at sd $54). *(The first attempt at this re-run on 2026-09-11 was killed by the laptop
sleeping during section [5]; the run recorded here is complete.)*

**Two review notes on M6/M7 code (Master, 2026-09-11), neither changing a finding:**
`RobotSpec.cooldown_days` is documented as days unavailable after a pass, but
`Fleet.advance_day()` runs in the same step, so a robot is unavailable for `cooldown_days − 1`
days (values are swept assumptions; left as is). QR-DQN applies CVaR at action selection
only — the Bellman target is risk-neutral — so finding 4 is about eval-time CVaR selection,
not about fully risk-sensitive training; now stated in FINDINGS.md.

---

## FINAL CONCLUSION — see [FINDINGS.md](FINDINGS.md)

Four hypotheses about where adaptive control adds value; **four negative results for deep
RL** (M4, M5, M6, M7). No learned agent beat a well-tuned rule on any axis.

**The hard part of PV cleaning is state estimation, not control.** Once soiling is known
the control law is a threshold. The largest effect anything produced was M5's **17.7×
reduction in soiling-estimate error** — from a Kalman filter.

The operator-facing result is strong: under a realistic noisy performance-ratio signal a
naive threshold collapses **17.2%** and cleans **~98×/yr instead of 8**; beyond 3% noise
a *blind calendar* beats the sensor-driven rule. Filtering removes that trap entirely.
*(Figures from the 2026-09-11 re-run; the 19.6% / 109× first reported came from three
episodes per point — see the audit.)*

---

## Next up

Tier 3 as planned (M8 continual learning, M9 offline RL + OPE, M10 benchmark release)
assumed an agent worth deploying. It is not the right Tier 3 for the result we got.

**Recommended instead:**
- Publish the Gymnasium environment as a benchmark — still the contribution it always
  was, and *more* interesting with a negative result attached: it is a well-calibrated
  problem on which deep RL does not beat a Kalman filter plus a threshold.
- Write the result up for a venue (IEA-PVPS soiling community, or an energy-ML workshop).
- **M9 (offline RL + OPE) remains worth doing on its own merits** — off-policy evaluation
  is the credibility tool for any DEWA conversation, and it applies to the *rule* as much
  as to an agent.
- M8 (continual learning) is hard to justify now: nothing suggests the winning policy is
  a train-once artefact that drifts.

---

## Open questions for Master

| # | Question | Raised by | Status |
|---|---|---|---|
| 1 | ~~Approve the concept?~~ | Master session | ✅ Approved 2026-08-29 |
| 2 | ~~Repo needed.~~ Provided: https://github.com/KartikJoshi23/Self-Learning-Agent | Master session | ✅ Resolved 2026-08-29 |
| 3 | ~~Public release?~~ | Master session | ✅ **Public, and staying public** — 2026-08-29 |
| 4 | ~~Approve implementation plan?~~ | Master session | ✅ **Tier 1 approved** 2026-08-29 |
| 6 | ~~Approve Tiers 2–3?~~ | Master session | ✅ **Tier 2 approved** 2026-08-29; Tier 3 still open |
| 7 | ~~Re-run `scripts/m4_verify.py` for the archival record.~~ | Master session | ✅ Done 2026-09-05: **M4 PASSED 5/5**, PPO $27,635 ± 10 vs tuned threshold $27,651 (−$16). Same conclusion as before, tighter seeds. |
| 5 | ~~Authorise the initial push?~~ | Master session | ✅ Authorised and pushed 2026-08-29 |
| 9 | **Import the repository in Vercel** (framework Next.js, root directory `site`) and paste the resulting `*.vercel.app` URL into README.md's status line and here. Account action; cannot be done from a session. | Master session 2026-09-12 | ⏳ Open |
| 8 | **Are the two claude.ai artifact links public?** README's headline "▶ Run the live simulator" and the FINDINGS link point to claude.ai artifacts, which are private by default. If not explicitly shared, the public repo's front door links to pages a stranger cannot open. Cannot be verified from a session; check in a browser while signed out. `web/simulator.html` is self-contained and could be linked directly instead. | Master session 2026-09-11 | ⏳ Open |

---

## Blockers

| # | Blocker | Impact | Status |
|---|---|---|---|
| 1 | ~~No git repository initialised.~~ | — | ✅ Resolved 2026-08-29: repo initialised, remote wired to https://github.com/KartikJoshi23/Self-Learning-Agent |
| 2 | ~~Initial push not performed.~~ | — | ✅ Resolved 2026-08-29: `origin/main` exists; collaborator handoff is live. |
| 3 | ~~NASA POWER hourly `PRECTOTCORR` served in different units from the cached data.~~ | A fresh clone computed rainfall 24× too low and every soiling result on top of it silently wrong. | ✅ Resolved 2026-09-11: units classified against the daily product on every fetch; canonical form cached. Live endpoint healthy on 2026-09-11 (the −99,000 fault of 09-10 had cleared). |
| 4 | ~~Lead-in year 2015 cached corrupted on the Master laptop.~~ | Poisoned 1 Jan 2016 for any training run on this machine. | ✅ Resolved 2026-09-11: refetched; cache validated on read from now on. |

---

## Known unverified claims

Per `Problem-Solving-Skill.md` Phase 6 — report reality, not intention. These are
believed true but were **not** confirmed against the primary source:

| Claim | Why unverified | How to close |
|---|---|---|
| ~~Exact formulation of arXiv:2603.07518~~ **CLOSED 2026-08-29** — paper read in full; formulation recorded in `rimal/env/cleaning_env.py`. All four differentiation axes confirmed unclaimed. | — | Closed. |
| ~~The browser simulator "matches the Python engine to 0.02% on energy and reproduces cleaning counts exactly".~~ **CLOSED 2026-09-11** — the harness now lives in `scripts/verify_simulator.py` and is under test: soiling 6.8e-5, clean energy 3e-7, soiled energy 1.7e-4 relative, identical cleaning days for three rules. | — | Closed. |
| The lead-in fix "changes no comparison or conclusion" (commit `5c31785`). | Asserted from the size of the change (0.09%), not observed — M4–M7 were not re-run. | **CLOSED 2026-09-11** by re-running M4–M7; conclusions unchanged, figures re-baselined (see FINDINGS.md). |
| `max_soiling = 0.3` (the 30% cap on accumulated loss) is pvlib's Kimber default, not a DEWA-calibrated value. The never-cleaned baseline spends long stretches pinned at this cap, so it carries real weight in that baseline. | Not site-calibrated; no published MBR figure found. | Low risk for M3/M4 because a cleaning agent rarely reaches the cap. Revisit if the never-clean baseline turns out to matter to a conclusion. |
| DEWA Autonomous Soiling Detector specifics. | dewa.gov.ae returns HTTP 403 to automated fetch; details taken from the UAE Media Office mirror. | Read the DEWA press release directly in a browser. Low impact — not load-bearing for the design. |

### Closed by the 2026-08-29 audit

Eight errors were found in the original Phase 2 presentation and corrected. Full log in
[RESEARCH.md](RESEARCH.md) §6. Two were material:

- **E1 (critical)** — the PPO/SAC Abu Dhabi RL result was misattributed to the MDPI *Systems*
  paper. They are two different works; the RL paper is **arXiv:2603.07518** (March 2026), and
  the *Systems* paper is simulation-optimisation, not RL.
- **E2 (material)** — the water–energy nexus framing was overstated by roughly 2–15×, and
  DEWA's 2026 trial uses **dry** robots consuming no water. Water demoted from a reward term to
  a CMDP constraint; novelty re-centred on stochastic action efficacy and actuator degradation.

## Files to read on resume

| File | Why |
|---|---|
| `Problem-Solving-Skill.md` | Binding methodology. Non-negotiable. |
| `PROGRESS.md` | This file — current state. |
| `HANDOFF.md` | Collaboration and sync rules. |
| `RESEARCH.md` | Approved Phase 2 concept + evidence base + audit log. |
| `IMPLEMENTATION-PLAN.md` | Phase 3 plan: design decisions, milestones M0–M10, verification strategy. |
| `FINDINGS.md` | The project conclusion — every headline number, with the run it came from. |
| `README.md` | Public front door; current verified results. |
| `scripts/m0_verify.py` | The M0 acceptance check. Re-run it if the data layer changes. Its section [5] is the rainfall units/sentinel guard. |
| `results/` | The observed output of every acceptance script, as last run. Numbers in the documents must trace to these. |

---

## Session log

Newest first. Every session appends one row before stopping.

> **Gap, closed 2026-09-11.** No session between 2026-09-01 and 2026-09-11 appended a row
> here — nine sessions, Master and collaborator alike — in breach of maintenance rule 3.
> The rows marked *(reconstructed)* were written by the Master on 2026-09-11 from the git
> log and the commit messages, not from memory of the sessions.

| Date | Machine | Who | Phase | What advanced | Commit |
|---|---|---|---|---|---|
| 2026-09-12 | Master laptop | Master | 4 (site) | **Built the live site** under `site/` (Next.js 16 static export, three.js hero, framer-motion, D3 charts; eight routes with a nav bar and one uniform template after a mid-build redirect away from a single scroll). `scripts/export_site_data.py` produces every number the site shows from the engine and `results/` (PPO checkpoints via a new default-preserving `checkpoint` argument on `ppo.train`); the browser physics module passes the node harness **10/10 incl. the trained PPO actor vs torch**. Audited every route at two widths in headless Chrome (zero errors), Lighthouse desktop 80–95 perf / 100 a11y, six bugs fixed. Tests 194 → 195. **Vercel import is the Master's next action.** | *(this commit)* |
| 2026-09-11 → 12 | Master laptop | Master | 4 (review) | **Reviewed all collaborator work since `55a5488` (Phase 5 applied).** Found and fixed two data-layer faults: **NASA POWER changed the units of hourly `PRECTOTCORR`** between 08-29 and 09-11 (mm/day rate → per-hour depth; a fresh clone computed 7.1 mm/yr instead of 171.4), now normalised against the daily product at fetch time; and the **2015 lead-in year was cached corrupted** (−99,000/h) and read back unchecked (1 Jan 2016 rain −16,498 mm/day) — cache files are now validated on read; 2015 refetched. M0 gained rainfall-integrity checks (13/13). **Re-ran M4–M7 on the corrected environment** and re-baselined every published number; logs committed under `results/`. **M5's declared criterion (b) did not replicate** (+$29, p = 0.165 vs the published +$64, p = 0.030) and is recorded as failed; `m6_verify.py` strengthened to 120-episode paired evaluation. **Audited the review from a fresh clone** (A1–A5 above): `requirements.txt` lacked torch, the sim-data check demanded a byte equality the new upstream precision can't give, three stale figures — all fixed; fresh clone reproduces M0–M3 and 194 tests. Committed `scripts/export_sim_data.py` (reproduces the shipped simulator byte-for-byte) and `scripts/verify_simulator.py` (node harness: 8/8 against the engine), both under test. Recorded two unrecorded plan deviations (M5 recurrent PPO, M7 Lagrangian PPO). Tests 183 → 194. | *(this commit)* |
| 2026-09-10 → 11 | Master laptop | Collaborator session *(reconstructed)* | 4 | Browser simulator `web/simulator.html` (JS port of the physics, verified in node but the harness was not committed); fixed three bugs it exposed — an undocumented −99,000 rainfall fill passing the parser, the first configured year losing its first local day (now one year of lead-in), and the energy table not re-trimmed with the daily frame. Tests 176 → 183. Rewrote both HANDOFF.md prompts. **Did not update PROGRESS.md.** | `5c31785`, `32f4b1a` |
| 2026-09-09 | Master laptop | Collaborator session *(reconstructed)* | 4 | Recorded the post-completion audit in PROGRESS.md. | `c24a2a2` |
| 2026-09-05 | Master laptop | Collaborator session *(reconstructed)* | 4 | **M7** (storm soiling, water CMDP, QR-DQN; two defects in M1's model found first — the clipped tail and the frame-relative AOD reference). M4 archival re-run (5/5). M7 declared criterion re-examined and **failed** honestly. **Audit:** circular import that broke m3_verify for three milestones; M5 headline computed from 3 episodes (re-sampled at 120); M6 re-powered; README rewritten. m5_verify crash after every check fixed; static arity guard for all scripts. Tests 110 → 176. FINDINGS.md written. | `951779a` … `6a40797` |
| 2026-09-02 | Master laptop | Collaborator session *(reconstructed)* | 4 | **M6** (five-robot fleet, stochastic efficacy, wear, cooldown; two flaws in the model caught by ablation). PPO on the fleet env: −$581, one seed in five collapsed. Tests 92 → 110. | `5077903`, `3d10c2d` |
| 2026-09-01 | Master laptop | Master *(reconstructed)* | 4 | M0 audit (timezone boundary bug, unjustified tolerance removed). **M1** physics (10/10; three defects fixed incl. 24× rainfall). **M2** environment (10/10; arXiv:2603.07518 read in full). **M3** baselines + **falsification gate PASSED** (7/7). **M4** PPO — null result vs tuned threshold. **M5** partial observability — Kalman belief, 17.6× RMSE reduction. Tests 14 → 92. **Did not append session-log rows.** | `9daafc5` … `55a5488` |
| 2026-08-29 | Master laptop | Master | 3 → 4 | Tier 1 approved; pushed to GitHub (public). **Completed M0:** scaffold, venv, NASA POWER fetcher with per-year chunking + parquet cache, 14 passing tests, `scripts/m0_verify.py` **passing 10/10**. Found NASA POWER serves `AOD_55` hourly (drops CAMS, closes risk R6); corrected a wrong belief about the API span limit (it is a payload-size cap). Wrote `README.md`. | *(this commit)* |
| 2026-08-29 | Master laptop | Master | 2 → 3 | **Audited Phase 2 research: found and corrected 8 errors (2 material).** Rewrote findings into `RESEARCH.md` with full audit log. Delivered `IMPLEMENTATION-PLAN.md` (Phase 3): design decisions, M0–M10, verification strategy, collaborator split. Initialised git; wired GitHub remote. No code written. | *(this commit)* |
| 2026-08-29 | Master laptop | Master | 1 → 2 | Read and confirmed methodology. Ran full Phase 2 research (UAE government strategy, UAE AI hiring market, PV soiling + RL literature, free-data feasibility). Evaluated five candidate concepts; recommended RIMAL. Created `HANDOFF.md` and `PROGRESS.md`. No code written. | *(pre-repo)* |

---

## Maintenance rules for this file

1. Update **Current status** every session — especially "Next action".
2. Move finished work into **Done** under its phase heading.
3. Log every session in **Session log** with a real commit hash once the repo exists.
4. Anything asserted but not verified goes in **Known unverified claims**. Do not
   quietly drop rows from that table — close them with evidence.
5. Never mark a phase gate approved unless the Master actually approved it.
