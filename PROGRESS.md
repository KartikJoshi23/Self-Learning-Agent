# PROGRESS.md — Single Source of Truth for Project State

> **Read this before doing anything. Update it before you stop.**
> Resume instructions live in [HANDOFF.md](HANDOFF.md).
> The binding methodology lives in [Problem-Solving-Skill.md](Problem-Solving-Skill.md).

**Last updated:** 2026-08-29 · by **Master** (Kartu)
**Repository:** https://github.com/KartikJoshi23/Self-Learning-Agent

---

## Current status

| Field | Value |
|---|---|
| **Current phase** | **Phase 4 — Development (Tier 1: M0–M4)** |
| **Phase state** | **Tier 1 complete** (M0–M4). **Tier 2: M5 ✅, M6 ✅ complete.** M7 awaiting Master's decision — see the recommendation below. |
| **Blocked on** | Nothing. |
| **Next action** | **Master decision required.** Four milestones now say the same thing (see *Cross-milestone finding*). Recommendation: run **M7 (CVaR under shamals)** — risk-sensitivity is the one axis a threshold rule genuinely cannot express — and if it also returns negative, **stop and write up** rather than continue adding machinery. |
| **Code written so far** | `rimal/{config,data,physics,env,baselines,eval,agents}`, **110 passing tests**, `scripts/` verify m0–m6. |

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
| 5 | Development — Tier 2 (M5–M7) | 🔵 M5 ✅ M6 ✅; **M7 held for a decision** | ✅ Approved 2026-08-29 |

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
`T* = sqrt(730·C/(E·p·r))` to a mean 19%, consistently longer — as expected, since the
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

**Belief RMSE 0.0262 → 0.00149 (17.6× reduction)** after fixing two filter bugs: it
ignored the 14-day rain grace period (drift up to 0.033 — the same order as the noise it
was removing), and it had an off-by-one on rain (env applies a day's rain to the
*following* day).

**PPO, 5 seeds:** belief-state $27,565 ± 30 vs memoryless $27,501 ± 43, **+$64, Welch
t=2.71, p=0.030** — criterion (b) genuinely established. *(The first run reported this as
a PASS on +$43 at n=3, p=0.194. The check now requires significance.)*

**⚠️ The scrutiny check that failed:** neither learned agent beats the hand-built rule —
PPO belief-state $27,565 vs `BeliefThreshold` $27,638 (−$74).

---

## Cross-milestone finding: state estimation, not control

**Four** consecutive milestones now show a model-based rule beating model-free deep RL:
M3 (tuned threshold > every fixed interval), M4 (tuned threshold > PPO), M5
(Kalman+threshold > both PPO variants), M6 (fleet heuristic > PPO by $581, with one seed
in five collapsing entirely).

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

---

## Next up

- **M6** — stochastic, heterogeneous cleaning efficacy (DEWA's measured **69–99%** across
  five robots) and cleaning-robot health as a **second latent state** (battery
  overheating, corrosion, frame misalignment, UV degradation over their 13-month trial).
  **Acceptance (declared before build):** the agent learns robot-specific dispatch
  (verified by inspecting the policy, not just the return); performance degrades
  gracefully as robot health falls; and an ablation shows the fixed-100%-efficacy
  assumption costs measurable value.
- **The sharp question M6 must answer:** does any of this create structure that
  filter-plus-threshold cannot express?

---

## Open questions for Master

| # | Question | Raised by | Status |
|---|---|---|---|
| 1 | ~~Approve the concept?~~ | Master session | ✅ Approved 2026-08-29 |
| 2 | ~~Repo needed.~~ Provided: https://github.com/KartikJoshi23/Self-Learning-Agent | Master session | ✅ Resolved 2026-08-29 |
| 3 | ~~Public release?~~ | Master session | ✅ **Public, and staying public** — 2026-08-29 |
| 4 | ~~Approve implementation plan?~~ | Master session | ✅ **Tier 1 approved** 2026-08-29 |
| 6 | ~~Approve Tiers 2–3?~~ | Master session | ✅ **Tier 2 approved** 2026-08-29; Tier 3 still open |
| 7 | Re-run `scripts/m4_verify.py` unattended for the archival record — the corrected run was stopped mid-seed-0 to free CPU for M5. PPO numbers are known and reproducible; only the recorded output and figure are missing. | Master session | ⏳ Open |
| 5 | ~~Authorise the initial push?~~ | Master session | ✅ Authorised and pushed 2026-08-29 |

---

## Blockers

| # | Blocker | Impact | Status |
|---|---|---|---|
| 1 | ~~No git repository initialised.~~ | — | ✅ Resolved 2026-08-29: repo initialised, remote wired to https://github.com/KartikJoshi23/Self-Learning-Agent |
| 2 | ~~Initial push not performed.~~ | — | ✅ Resolved 2026-08-29: `origin/main` exists; collaborator handoff is live. |

---

## Known unverified claims

Per `Problem-Solving-Skill.md` Phase 6 — report reality, not intention. These are
believed true but were **not** confirmed against the primary source:

| Claim | Why unverified | How to close |
|---|---|---|
| ~~Exact formulation of arXiv:2603.07518~~ **CLOSED 2026-08-29** — paper read in full; formulation recorded in `rimal/env/cleaning_env.py`. All four differentiation axes confirmed unclaimed. | — | Closed. |
| *(superseded)* Exact state / action / reward formulation of arXiv:2603.07518 (Heungjo An, *RL-based dynamic cleaning scheduling framework for solar energy system*), and whether it treats soiling as latent. | Abstract confirmed via arXiv, but the abstract does not state the formulation. Full PDF not yet read. | **Read the PDF before milestone M2 freezes the environment design.** This determines which of the four differentiation axes are genuinely unclaimed. |
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
| `README.md` | Public front door; current verified results. |
| `scripts/m0_verify.py` | The M0 acceptance check. Re-run it if the data layer changes. |

---

## Session log

Newest first. Every session appends one row before stopping.

| Date | Machine | Who | Phase | What advanced | Commit |
|---|---|---|---|---|---|
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
