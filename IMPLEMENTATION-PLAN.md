# IMPLEMENTATION-PLAN.md — Phase 3 Proposal (RIMAL)

**Status:** ⏳ Proposed — **awaiting Master approval**. No code may be written until this is approved.
**Depends on:** [RESEARCH.md](RESEARCH.md) (approved concept, post-audit).
**Governed by:** [Problem-Solving-Skill.md](Problem-Solving-Skill.md).

---

## 0. Constraints this plan is designed against

| Constraint | Consequence for the design |
|---|---|
| **Zero cost** | Only free data and free libraries. No paid APIs, no cloud. |
| **Laptop-only, CPU** | The environment must run thousands of steps/second. Rules out heavy simulators; rules in a low-dimensional stochastic model. |
| **Employability first** | Every milestone must produce something demonstrable and explainable in an interview. A working beat-the-baseline agent must exist **early**, not at the end. |
| **Collaborator-parallel** | Milestones must be independently ownable, with clean interfaces between them. |
| **Methodology binding** | Every milestone declares its verification *before* it is built. Nothing is "done" until observed working. |

---

## 1. Design decisions (candidates weighed, per methodology Phase 3.1)

### D1 — Soiling model

| Candidate | For | Against | Verdict |
|---|---|---|---|
| **Kimber** (`pvlib.soiling.kimber`) — constant daily accumulation, rain resets above a threshold | Its single parameter **is** a %/day rate, so it maps **directly onto DEWA's published 0.14–0.33 %/day**. Trivially calibratable. Few assumptions. | Empirical; ignores particulate physics. | ✅ **Primary** |
| **HSU** (`pvlib.soiling.hsu`) — physical deposition/removal from PM concentration, rain, wind, tilt | Physically grounded; lets CAMS dust drive deposition directly. | Needs PM2.5/PM10 of uncertain quality for Dubai; more parameters to mis-specify. | ✅ **Secondary — cross-check.** If both models yield the same policy ranking, the result is robust to model choice. That cross-check is itself a portfolio-grade finding. |

### D2 — Action space

| Candidate | Verdict |
|---|---|
| Continuous "fraction of plant cleaned" | ❌ Not how cleaning is actually dispatched. |
| **Discrete, factored: for each block × {no-op, robot A…E, wet crew}** | ✅ **Chosen.** Matches DEWA's real dispatch. Keeps the action space small enough for CPU training. Directly supports per-robot efficacy (69–99%). |

### D3 — Algorithm

| Milestone | Algorithm | Why |
|---|---|---|
| First learning agent | **PPO** (CleanRL single-file) | Parity with the published baseline (arXiv:2603.07518 found PPO > SAC). Stable, CPU-friendly, readable — good portfolio code. |
| POMDP | **Recurrent PPO** + explicit Bayesian belief filter | Two independent routes to the same latent state; comparing them is a result. |
| Risk / distributional | **QR-DQN** on the discrete action space | Gives the full return distribution, so CVaR is read off directly. |
| Constraints | **Lagrangian PPO** (CMDP) | Standard, well-documented, no exotic machinery. |

### D4 — Simulation fidelity vs speed

Chosen: **daily timestep for the decision process, hourly for energy yield.** Cleaning is a daily-scale decision; energy must be integrated hourly for pvlib to be meaningful. A year is 365 decision steps — an episode runs in milliseconds.

---

## 2. Repository structure

```
rimal/
  data/          fetchers + cached parquet (NASA POWER, NSRDB, CAMS); no raw data in git
  physics/       pvlib ModelChain yield; Kimber + HSU soiling; calibration to DEWA rates
  env/           Gymnasium environment (v0 observable → v1 POMDP → v2 full)
  agents/        CleanRL-style single-file PPO / recurrent PPO / QR-DQN / Lagrangian PPO
  baselines/     fixed-28, fixed-34, PR-threshold, reimplemented published PPO
  eval/          metric harness, CVaR, constraint accounting, OPE (SCOPE-RL)
  notebooks/     figures for the write-up
tests/           pytest; env_checker; physics regression tests
docs/            benchmark documentation for public release
```

---

## 3. Milestones

Each milestone: is independently committable, leaves the repo working, and **declares its verification up front**. A milestone is not done until its verification has been *observed passing*.

### 🔹 Tier 1 — Minimum viable portfolio piece (M0–M4)
*Goal: a working agent that beats fixed-interval cleaning on held-out data. If nothing else ever ships, this alone is a defensible interview project.*

| # | Milestone | Verification (declared before build) |
|---|---|---|
| **M0** | Repo scaffold, CI, data fetchers for Seih Al-Dahal (~24.75 °N, 55.35 °E): NASA POWER irradiance/weather + CAMS dust/AOD, cached to parquet. | Plot ≥5 years of GHI and AOD. Confirm the seasonal dust signature matches the literature (spring domestic dust, summer shamal peak). Fetchers are idempotent and offline-replayable. |
| **M1** | Physics core: pvlib `ModelChain` hourly yield; Kimber soiling calibrated to DEWA's 0.14–0.33 %/day; HSU as cross-check. | **(a)** Uncleaned accumulation reproduces DEWA's measured daily rates. **(b)** Annual specific yield lands in the published Dubai range (~1,700–1,900 kWh/kWp). **If either fails, the physics is wrong — stop, do not proceed.** |
| **M2** | Gymnasium env **v0** — fully observable soiling, single deterministic cleaning action. | `gymnasium.utils.env_checker` passes. Sanity ordering holds: always-clean > periodic > never-clean on energy, and the reverse on cost. |
| **M3** | Baselines + metric harness: fixed-28, fixed-34, PR-threshold; net-value metric; CVaR@5%; constraint accounting. | **The falsification test for the whole simulator:** sweep cleaning interval and confirm the optimum lands near **28–34 days**, reproducing the published result. If the simulator disagrees with the literature, the simulator is wrong. |
| **M4** | First learning agent: **PPO** on env v0. | Beats every fixed-interval baseline on **held-out years** (train 2016–2022, test 2023–2025). Seed variance reported over ≥5 seeds. This is the "does it learn at all" gate. |

### 🔹 Tier 2 — The differentiation (M5–M7)
*Goal: the four unclaimed axes from RESEARCH.md §3. This is what separates the project from arXiv:2603.07518.*

| # | Milestone | Verification |
|---|---|---|
| **M5** | **POMDP.** Replace true soiling with a noisy performance-ratio observation confounded by irradiance, temperature and degradation. Add a Bayesian belief filter (Kalman/particle) and a recurrent policy. | **(a)** Belief RMSE against the true latent soiling. **(b)** Recurrent/belief agent beats the memoryless agent under observation noise, and the gap widens as noise rises. **(c)** Memoryless PPO degrades — confirming partial observability is genuinely binding, not decorative. |
| **M6** | **Stochastic heterogeneous actions + actuator health.** Per-robot cleaning efficacy sampled from a Beta fitted to DEWA's **69–99%** range; robot health as a second latent state degrading per DEWA's documented failure modes; maintenance as an action. | Agent learns robot-specific dispatch (verify by inspecting the policy, not just the return). Performance degrades gracefully as robot health falls rather than collapsing. Ablation: fixed-100%-efficacy assumption costs measurable value. |
| **M7** | **CMDP water budget + CVaR risk sensitivity.** Lagrangian PPO for the water constraint; QR-DQN for the return distribution. Inject shamal events at their documented frequency (2–3 storms/month winter; 1–2 multi-day shamals/season). | Constraint satisfaction rate ≥ target with minimal return sacrifice. **CVaR@5% improves versus the risk-neutral agent under injected shamals**, at a quantified cost in mean return. |

### 🔹 Tier 3 — Publication and credibility (M8–M10)
*Goal: turn a good project into a citable public asset and a government-pitchable artefact.*

| # | Milestone | Verification |
|---|---|---|
| **M8** | **Non-stationarity / continual learning.** Seasonal regime drift, multi-year panel degradation, robot wear. | Post-shift recovery time and dynamic regret, per the continual-RL survey's recommended metrics. A continually-adapting agent must beat a train-once agent across a multi-year horizon. |
| **M9** | **Offline RL + off-policy evaluation.** Learn from logged baseline trajectories; evaluate with SCOPE-RL. | OPE estimates track true simulator returns on held-out policies within a stated error band. **This is the honest answer to "how do you know it works without deploying it" — the single most important credibility milestone for a DEWA conversation.** |
| **M10** | Package and publish: documented Gymnasium benchmark, reproducible results, write-up. | A clean clone reproduces every headline number from a single command. Documentation sufficient for a third party to use the environment. |

---

## 4. Verification strategy (methodology Phase 5, applied to the whole project)

1. **The reward cannot be gamed** — energy yield is physically simulated by pvlib from *measured* irradiance, not from a learned model.
2. **Held-out years and held-out sites** — tests generalisation, not memorisation.
3. **Model-choice robustness** — Kimber vs HSU must not change the policy ranking.
4. **Seed variance always reported** — ≥5 seeds; no single-seed claims.
5. **Ablations are mandatory** — each of the four axes must be shown to *earn its place*, or it gets cut.
6. **Off-policy evaluation** — the substitute for deployment we cannot do.
7. **Falsification** — actively look for the failure: a second code path, a leaked future observation, a degenerate policy that exploits a simulator artefact.

---

## 5. Risks and mitigations

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **arXiv:2603.07518 is only ~5 months old** — concurrent work, may already cover an axis. | 🔴 High | **Read the full PDF before M2 freezes the env design.** Positioning is "extends", never "first". |
| R2 | Simulator artefacts — the agent learns to exploit a modelling bug rather than the physics. | 🔴 High | M3's 28–34-day falsification gate; Kimber/HSU cross-check; policy inspection at every milestone. |
| R3 | Scope explosion across four axes. | 🟠 Medium | Tier 1 is a complete standalone project. Tiers 2 and 3 are strictly optional increments. Ship Tier 1 first. |
| R4 | No real DEWA plant data is public — this is a simulation study. | 🟠 Medium | State it plainly, never gloss. Calibrate to DEWA's *published* rates. M9 (OPE) is the credibility answer. |
| R5 | "It's just a simulator" objection in interview. | 🟡 Low | The public benchmark framing inverts this: an open environment where none existed is a contribution, not a limitation. |
| R6 | CAMS/NSRDB registration friction or coverage gaps for Dubai. | 🟡 Low | NASA POWER as fallback (no registration). Verified at M0 before anything depends on it. |

---

## 6. Collaborator split (parallelisable)

| Track | Milestones | Interface |
|---|---|---|
| **A — Physics & data** | M0, M1 | Emits a calibrated soiling+yield model behind a stable function signature |
| **B — Environment & baselines** | M2, M3 | Consumes Track A; emits a Gymnasium env + metric harness |
| **C — Agents** | M4 onward | Consumes Track B's env only; never touches physics |

Tracks B and C can proceed against a stub physics model as soon as M1's interface is fixed.

---

## 7. What is explicitly out of scope

- Any LLM in the decision loop.
- Real-time integration with DEWA systems.
- Computer vision on panel imagery (DEWA's detector already covers sensing).
- Hardware, robotics control, or anything requiring physical access.
- Cloud deployment.

---

## 8. Approval gate

⏸ **This plan requires the Master's explicit approval before any code is written.**

Open decisions for the Master:
1. Approve the plan as scoped, or adjust the tier boundaries?
2. Ship Tier 1 only first, then re-decide on Tiers 2–3? *(Recommended.)*
3. Public repository from the start, or private until Tier 1 is complete?
