# RESEARCH.md — Phase 2 Findings (Post-Audit, Corrected)

**Status:** Phase 2 complete. Audited 2026-08-29 and corrected.
**Supersedes:** the original Phase 2 presentation, which contained six errors (logged in §6).

---

## 1. The concept — RIMAL

> **R**isk-aware **I**ntelligent **M**aintenance under **A**eolian **L**oading (رمال — "sands")
>
> A self-learning agent that decides **when, where, and with which machine** to clean a
> desert utility-scale solar plant — when it cannot directly observe how dirty the panels
> are, when the cleaning action's own effectiveness is uncertain, and when the cleaning
> machines themselves are degrading.

### The decision problem

| Element | Reality |
|---|---|
| **Latent state 1** | Soiling ratio — never observed directly, only inferred from a noisy performance ratio confounded by irradiance, temperature, degradation and clipping |
| **Latent state 2** | Cleaning-robot health — DEWA's field study documents battery overheating, corrosion, frame misalignment and UV degradation over 13 months |
| **Action** | Which blocks to clean, with which robot — **effect is stochastic**: DEWA measured cleaning efficiencies of **69–99%** across five robots |
| **Exogenous driver** | Dust deposition; punctuated by shamal events that can undo a cleaning cycle overnight |
| **Constraint** | Water budget (where wet cleaning is used), crew/robot availability |
| **Reward** | Net energy delivered minus cleaning cost — with a fat left tail |

---

## 2. Evidence base (primary sources, verified)

### Site and asset
- **MBR Solar Park**: first five phases commissioned at **3,460 MW**; **4,660 MW** on completion of the 1,800 MW phase 6 (2026); **>5,000 MW by 2030**; ~AED 50 bn invested. World's largest single-site solar park on the IPP model.
- Coordinates for simulation: Seih Al-Dahal, ~24.75 °N, 55.35 °E.

### DEWA's own measurements — the anchor for this project
- **Cleaning robot field study** (*pv magazine*, 14 Aug 2026): DEWA Cleaning Test Facility, **164 crystalline-silicon modules rated 445–505 W** (monofacial PERC glass-backsheet and bifacial PERC glass-glass), monitored **22 Jul 2024 → 26 Aug 2025**. Five **dry-cleaning** robots (bristle and microfibre, fixed-tilt and single-axis tracker).
  - Soiling rates **0.14–0.33 %/day**, reduced to **<0.02 %/day** under daily robotic cleaning.
  - **Cleaning efficiencies 69–99%.** No robot-induced cell damage.
  - Documented failure modes: battery overheating, corrosion, frame misalignment, UV degradation. A 12-point evaluation checklist was recommended.
  - **No water consumption figures reported** — the robots tested are dry.
- **Autonomous Soiling Detector** (DEWA, Dec 2025): compares actual vs expected production to quantify soiling; ~10% reduction in dust-related losses; patented in GCC, Canada, Japan, Australia, India, Jordan, Spain.

> **Why this matters:** DEWA has already built the *sensing* layer and is trialling the
> *actuation* layer. RIMAL is the missing **decision** layer between them.

### Soiling loss context (authoritative)
- **IEA-PVPS Task 13** (*Soiling Losses – Impact on the Performance of PV Power Plants*, 2022): soiling costs **3–5% of annual PV energy production** globally (4–7% energy losses); worst Atacama sites reach 39%.
- Khalifa University, *Effect of Soiling from Dust Particles on Solar Cell Efficiency in the UAE*: efficiency reduction **up to 41.45%** — **laboratory** study, seven sand samples dispersed on a panel, IV measured under one sun. **Not an operational field loss figure.**
- *Characterisation of Dust Particles Deposited on Photovoltaic Panels in the UAE*, Applied Sciences ([10.3390/app132413162](https://doi.org/10.3390/app132413162)) — dust samples from five locations **inside MBR Solar Park**.
- Dust storms: UAE dust events persist 6–14 h; winter dust storms 2–3×/month; multi-day shamals (3–5 days) once or twice per winter season.

### Government strategy alignment
- **Dubai Universal Blueprint for AI** — launched **29 April 2024** by Sheikh Hamdan. Four pillars; pillar 1 is "best application of AI in strategic sectors". Targets AED 100 bn/yr contribution and +50% productivity under **D33**. First phase appointed a Chief AI Officer in every Dubai government entity.
- **UAE National AI Strategy 2031** — **energy/utilities and water are named first-phase priority sectors**.
- **Dubai Clean Energy Strategy 2050** / **Dubai Net Zero 2050** — 100% clean capacity by 2050; 27% by 2030.
- **UAE Water Security Strategy 2036** — 21% demand reduction; 95% treated-water reuse.

### Funding / pitch route — **corrected**
- **Dubai RDI Grant Initiative** (Dubai Research, Development and Innovation Programme, `dubairdi.ae`, with Dubai Future Foundation). 26 projects backed as of Jan 2026. Up to **AED 2,000,000** per project. Tracks: Cognitive Cities; Health & Life Sciences; **Environmental Science (water, energy, ecosystems)**. Requires **TRL 4→7** with a deployment pathway in Dubai.
- ⚠️ **Eligibility constraint:** funds **applied research consortia at Dubai-based universities**, and **≥50% of funding must be spent within Dubai**. **An individual cannot apply directly** — a Dubai-based university partner is required.
- Alternative routes not subject to that constraint: direct DEWA R&D / MBRSIC engagement; the Dubai AI Week open competition run by the Dubai Centre for AI + DFF; Dubai Future Solutions / Prototypes for Humanity (Nov 2026).

### Market relevance (primary source)
- **PwC 2026 AI Jobs Barometer — UAE analysis** (>1 bn job postings, 27 countries): UAE AI-skilled job postings rose from **1.0% (2021) to 3.2% (2025)**; AI-related hiring rose from **32% of roles (2023–24) to 48% (2024–25)**; AI-skill wage premium up to **92%**. UAE is among the fastest-growing AI talent markets globally and ranks 2nd for attracting AI talent relative to population.
- Employer behaviour: hiring prioritises **demonstrable outcomes** — "a project, a dashboard, a case study" — over credentials. Career guidance for the market recommends **three to five UAE-focused projects**.
- ⚠️ Figures circulating as "open AI/ML roles +45% vs candidate pool +12%" and "6,000 → 10,500 unfilled positions" trace to **recruitment-agency marketing blogs**, not audited data. Treated as indicative only.

---

## 3. Prior art and the gap

### Nearest prior work

| Work | What it is | What it does **not** do |
|---|---|---|
| **arXiv:2603.07518** — Heungjo An, *Reinforcement learning-based dynamic cleaning scheduling framework for solar energy system* (**March 2026**) | The closest work. PPO and SAC; Abu Dhabi case study; PPO beats SAC and simulation-optimisation; **up to 13% cost savings**. | Abstract does not specify state/action/reward or whether soiling is latent. **Full PDF must be read before Phase 3 design is frozen.** |
| ***Systems* 2024, [10.3390/systems12100418](https://doi.org/10.3390/systems12100418)** — *Optimal Scheduling of PV Panel Cleaning… in the Middle East* | **Simulation + optimisation, not RL.** Finds optimal interval for Abu Dhabi is **34 days** vs the 28 days commonly recommended. | Not a learning system. Deterministic cleaning effect. |
| Iraqi desert numerical soiling model (Research Square preprint, 2008–2025) | Optimal interval ~30 days. | Preprint, not peer-reviewed. Not a learning system. |

### The four unclaimed axes

1. **Partial observability.** Every prior formulation treats soiling as observable. It is latent. NREL's own SRR method is documented to *"falsely identify soiling in noisy signals, making unsupervised applications challenging."* → **POMDP** with a belief filter.
2. **Stochastic, heterogeneous action efficacy.** DEWA measured **69–99%** cleaning efficiency across robots. All prior work assumes cleaning restores the panel to 100%. → action outcome as a random variable, robot-dependent.
3. **Degrading actuators as a second latent state.** DEWA documented battery, corrosion, alignment and UV degradation over 13 months. No prior work models the cleaner's own health. → **dual-latent-state** problem.
4. **Risk and non-stationarity.** Shamals are fat-tailed; seasons are non-stationary. Expected-value, train-once policies misprice both. → **CVaR / distributional RL** + **continual RL**.

Plus a **hard water budget** as a **constraint** (CMDP), not a reward term — see §6 E2.

### Verified uniqueness
GitHub repository search for a reinforcement-learning environment / gym for photovoltaic soiling or cleaning scheduling returns **0 results**. No public benchmark exists. The environment itself is a contribution.

---

## 4. Method grounding

- *A Survey of Safe RL and Constrained MDPs* — [arXiv:2505.17342](https://arxiv.org/abs/2505.17342)
- *Robust Risk-Sensitive RL with CVaR* — [arXiv:2405.01718](https://arxiv.org/pdf/2405.01718)
- *A Survey of Continual Reinforcement Learning* — [arXiv:2506.21872](https://arxiv.org/pdf/2506.21872)
- *Position: Deployed RL should be Continual* — [arXiv:2606.04029](https://arxiv.org/html/2606.04029v2)
- *SCOPE-RL: offline RL and off-policy evaluation* — [arXiv:2311.18206](https://arxiv.org/pdf/2311.18206)
- *Gymnasium* — [arXiv:2407.17032](https://arxiv.org/pdf/2407.17032)
- Deceglie et al., *Quantifying Soiling Loss Directly from PV Yield* (NREL/OSTI) — the SRR method

---

## 5. Zero-cost toolchain (verified available)

| Need | Source | Cost |
|---|---|---|
| Soiling physics | `pvlib-python` — HSU and Kimber models | Free |
| Soiling extraction from noisy yield | NREL **RdTools** (SRR) | Free |
| Irradiance / weather | **NASA POWER**, **NSRDB** (international coverage) | Free |
| Dust / aerosol driver | **Copernicus CAMS** — *"no restrictions on use, reproduction, or redistribution"* | Free |
| Dubai utility context | **Dubai Pulse** (DEWA annual statistics, CSV + API) | Free |
| RL implementations | **Gymnasium** + **CleanRL** (single-file PPO/SAC/DQN) | Free |
| Safe / risk-sensitive RL | Safety-Gymnasium conventions; CMDP + CVaR literature | Free |

**Compute:** the environment is a low-dimensional stochastic simulator, not a 3D physics engine — thousands of steps/second on CPU. **No GPU required. Total cost AED 0.**

---

## 6. Audit log — errors found and corrected (2026-08-29)

Recorded per `Problem-Solving-Skill.md` Phase 6: report reality, not intention.

| # | Severity | Error in the original Phase 2 presentation | Correction |
|---|---|---|---|
| **E1** | 🔴 Critical | Cited the PPO/SAC Abu Dhabi RL result alongside `10.3390/systems12100418`, implying they were the same work. | They are **two different papers**. The RL work is **arXiv:2603.07518** (Heungjo An, March 2026). The *Systems* paper is **simulation-optimisation, not RL**, and is the source of the 34-day result. Also note the RL paper is only ~5 months old — this is **concurrent work**, not settled prior art. |
| **E2** | 🔴 Material | Claimed cleaning consumes ~24 m³/MW and that desalination energy makes a meaningful closed water–energy loop. | **Overstated by roughly 2–15×.** The 24 m³/MW figure came from a vendor blog assuming ~3,000 panels/MW (~333 W modules); DEWA's own test field uses **445–505 W** modules (~2,000–2,250/MW). Authoritative washing figures are **0.08–0.15 m³/MWh**, or ~**1 L/module**. Recomputed, embedded desalination energy is ≈**1% of the energy recovered** — not a driving term. **Worse: DEWA's 2026 robot trial tested five *dry* robots and reported no water use at all.** → Water is demoted from a reward term to a **CMDP constraint**, and the novelty re-centred on stochastic action efficacy + actuator degradation (§3), which are better evidenced. |
| **E3** | 🟠 Moderate | "Gulf soiling destroys 10–18% of annual yield." | Sourced from a **non-peer-reviewed preprint** and a vendor blog. Replaced with **IEA-PVPS Task 13** (3–5% of annual production globally) and DEWA's own site-specific **0.14–0.33 %/day**. |
| **E4** | 🟠 Moderate | Cited Khalifa University's 41.45% efficiency drop alongside operational figures. | Real study, but a **laboratory** experiment (dispersed sand, IV under one sun). Must be labelled as such, never quoted as field loss. |
| **E5** | 🟡 Minor | "MBR Solar Park is at 2,627 MW today." | Stale (2023/24). **First five phases = 3,460 MW commissioned.** |
| **E6** | 🟠 Moderate | "Dubai Future Foundation grant programme, up to AED 2M" as an accessible pitch route. | Correct name is the **Dubai RDI Grant Initiative**. Amount and tracks were right, but it funds **consortia at Dubai-based universities** with **≥50% spend in Dubai** — **an individual cannot apply directly**. Alternative routes listed in §2. |
| **E7** | 🟡 Minor | Leaned on "+45% roles vs +12% candidates". | Traces to recruitment-agency blogs. Replaced with **PwC 2026 AI Jobs Barometer** as primary. |
| **E8** | 🟡 Minor | Gave the Blueprint launch as "29 April" with no year. | **29 April 2024.** |

### Confirmed correct, no change
- No public Gymnasium/GitHub RL environment for PV soiling cleaning (**0 GitHub results**).
- `pvlib` HSU + Kimber soiling models; NREL RdTools SRR.
- DEWA Autonomous Soiling Detector (Dec 2025) and its patent coverage.
- Free data availability: NASA POWER, NSRDB, Copernicus CAMS, Dubai Pulse.
- All method citations in §4.

### Still open
- **Read arXiv:2603.07518 in full** before Phase 3 design is frozen, to confirm exactly which of the four axes it leaves unaddressed. The abstract does not say.
