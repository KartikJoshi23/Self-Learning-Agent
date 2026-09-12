# RIMAL — Findings

**Risk-aware Intelligent Maintenance under Aeolian Loading**
Reinforcement learning for photovoltaic cleaning dispatch at Mohammed bin Rashid Al Maktoum Solar Park, Dubai.

*Eight milestones, M0–M7. All results on held-out years the agents never trained on. Figures are from the 2026-09-11/12 re-run on the corrected environment; each traces to a log in `results/`.*

---

## The headline

We built a simulator of desert PV soiling calibrated to DEWA's own published field measurements, reproduced the cleaning-interval optimum reported in the literature as a falsification gate, and then tested four separate hypotheses about where adaptive control adds value over a well-tuned rule.

**Deep reinforcement learning did not beat a well-tuned rule on any of them.**

The value in this system is concentrated somewhere else entirely:

> **The hard part of PV cleaning is state estimation, not control.**
> Once you know how dirty the panels are, the control law is a threshold. The
> single largest effect anything in this project produced was a **17.7×
> reduction in soiling-estimate error** — and that came from a Kalman filter,
> not a neural network.

This is a negative result for the deep-RL framing and a positive, actionable one for the operator.

---

## What was tested, and what happened

| # | Hypothesis: adaptive control should win because… | Result |
|---|---|---|
| **M4** | soiling is dynamic, so a learned policy beats a fixed schedule | PPO beat every fixed interval (+$131) but **lost to a tuned threshold** by $20 |
| **M5** | soiling is *latent*, so a threshold on a noisy reading must fail | Partial observability is **devastating** (−$4,771, 17.2%) — but a **Kalman filter fixes it**, and PPO still lost. Giving PPO the belief state did not significantly help it either (+$29, p = 0.17) |
| **M6** | cleaning is stochastic and machines wear out | Real but small ($181/yr). Learning *which* robot to use **lost at every cleaning frequency** (−$103 ± 4 at the default cost, p < 0.0001) |
| **M7** | storms make returns fat-tailed, which a scalar threshold cannot express | A genuine risk/return frontier exists — but QR-DQN **lost to a CVaR-tuned threshold** on CVaR@5% by $501 (rule $26,890 vs agent $26,388, seed sd $299), **and its own risk dial did nothing** |

M7 deserves the sharpest statement, because it was the milestone with the best structural case for RL: a scalar threshold genuinely cannot represent "today's return distribution is skewed," while a distributional agent can. It didn't matter. QR-DQN's CVaR did **not** rise monotonically as risk aversion increased — $26,759 → $26,798 → $26,780 → $26,728 as α fell from 1.00 to 0.10 (the first run gave $26,710 → $26,752 → $26,626 → $26,641; a different non-ordering). The ordering is noise. The machinery worked; the advantage never materialised.

*A limit on that statement, recorded by the Master review:* the agent applies CVaR only at **action selection**. Its Bellman target is risk-neutral, so the distribution it learns is that of the risk-neutral policy, and the "risk dial" re-reads that one distribution's tail. That is the standard QR-DQN construction and a fair test of it, but a fully risk-sensitive learner — CVaR in the target, or IQN with a distorted expectation — was not trained. The negative result is about the dial, not about every distributional method.

### The one finding that transfers directly to an operator

Under a noisy performance-ratio signal — which is what a real plant actually measures — a naive threshold rule collapses:

| observation noise | naive threshold | **Kalman belief** | blind fixed-31d |
|---|---|---|---|
| exact | 27,677 (8.3 cleans) | — | 27,526 |
| 1% | 27,642 (10.0) | **27,667** (8.4) | 27,526 |
| 3% | 27,207 (21.7) | **27,656** (8.4) | 27,526 |
| 6% | 25,127 (59.5) | **27,654** (8.3) | 27,526 |
| 10% | 22,906 (97.8) | **27,656** (8.3) | 27,526 |

*120 episodes per cell — 3 held-out years × 40 stochastic realisations. USD/MWp/yr; `results/m5_verify.log`, belief cleaning counts in `results/m5_belief_cleans.log`.*

Two things worth an operator's attention:

1. **The failure mode is chatter, not neglect.** Cleaning frequency explodes from 8 to ~98 per year as unlucky readings trigger unnecessary $60 washes.
2. **From 3% noise upward, a blind calendar beats the sensor-driven rule.** If your soiling estimate is noisy enough, *ignoring it entirely is better than trusting it*. Filtering removes that trap completely — the belief policy varies by **$13** across the whole 1–10% noise range.

---

## Credibility: the falsification gate

Before any agent was trained, the simulator had to reproduce the literature. The gate was framed as an existence claim with the admissible cost range **fixed in advance** ($25–150/MWp per pass):

| cleaning cost | simulated optimum | analytic closed form |
|---|---|---|
| $50/MWp | 27 days | 22.8 |
| **$60/MWp** | **31 days** ✅ | 25.0 |
| **$75/MWp** | **34 days** ✅ | 28.0 |
| $150/MWp | 46 days | 39.6 |

Published values: **28 days** (commonly recommended, UAE) and **34 days** (reported optimal, Abu Dhabi). Both reproduced at a plausible cost. The swept optimum also tracks an independent closed form to within a mean 19%, consistently longer — the right direction, since the closed form ignores rain resets.

**Also reported rather than hidden:** the optimum is genuinely *flat*. Any interval from **16 to 57 days** sits within 1% of optimal. Quoting the argmax alone would badly overstate how well-determined it is — and it reframes the problem, because if fixed intervals are that insensitive, a learned agent's edge was never going to come from picking a better interval.

---

## Errors found in our own work

Seven defects were caught by measurement rather than review. Each changed a result; each is recorded in code at the site of the fix.

**1. Rainfall was 24× too high.** NASA POWER's hourly `PRECTOTCORR` is a **mm/day rate**, not a per-hour depth, so summing it overcounted 24×. Dubai came out at 4,405 mm/yr against a real ~80–110. Rain is the natural-cleaning trigger, so this turned 4 washing days a year into 40 — and made a never-cleaned plant appear to lose only 2.8% of its energy instead of 17.6%. *Would have silently destroyed M3's falsification gate.*

**2. The soiling tail was clipped away.** The AOD-driven model capped its rate at DEWA's 0.14–0.33 %/day band — but that band is an **average over 13 months, not a per-day ceiling**, and the literature is explicit that a storm can undo a cleaning cycle overnight. The clip pinned 18.7% of days at the cap, compressing an 8× spread in measured dust into a 1.5× spread in soiling. **It deleted the entire phenomenon M7 exists to study**, and overstated CVaR by $391/MWp/yr across M3–M6.

**3. A train/eval mismatch we invented ourselves.** The soiling model used *the passed frame's own* mean AOD as its reference, so dynamics depended on which years were loaded: the 2016–2022 training mean (0.4158) and 2023–2025 holdout mean (0.4968) differ by 18.4%, scaling the rate by 0.70× between training and evaluation for identical dust. This structurally disadvantaged trained policies against online filters — biasing the very comparison the project exists to make.

**4. An under-tuned baseline nearly produced a fake win.** M4's first run "passed" against `threshold-0.95`, from a hand-picked grid that never tested 0.93 — the true optimum, worth ~$50/MWp/yr more, about **twice the margin PPO appeared to win by**. Baselines are now tuned on training years under the same protocol the agent gets.

**5. An unfair protocol nearly produced a second one.** M7's first result showed QR-DQN beating the rule by $166. The rule had been given **oracle threshold selection on its own test set**, the two were scored on **different year sets**, and the agent's CVaR came from **~1.5 tail samples**. Under a like-for-like protocol the rule wins — by $163 on the first environment, by $501 on the corrected one.

**6. The headline sweep was computed from three episodes.** The evaluation harness defaulted to a single stochastic realisation per year, so the M5 noise sweep — the most-quoted result in this document — rested on three episodes per point. Resampled at 120 episodes per point, the naive rule's collapse is **−$4,771 (17.2%)** rather than −$5,418 (19.6%): the finding holds, the figure was overstated by about 13% relative. `evaluate()` now takes a `seeds` argument and records one row per episode. *Found by audit after publication; the figures above are the corrected ones.*

**7. The first held-out year was one day short.** NASA POWER serves UTC and Dubai is UTC+4, so 1 January of the first *requested* year is an incomplete local day and was correctly dropped — which meant an environment built for 2023–2025 scored 2023 on 364 days while one built for 2016–2025 used 365. Results depended on which years happened to be requested. The environment now fetches one year of lead-in. The effect is ~0.1% and identical across policies, but every dollar figure in M3–M7 moved (the tuned threshold from $27,651 to $27,677), so **M4–M7 were re-run on the corrected environment on 2026-09-11 and every figure in this document comes from those runs** — the logs are in `results/`. *Found while building the browser simulator; the re-run was done by the Master review rather than assumed from the size of the change.*

**Two faults in the data source, caught before they reached a result.** Between 2026-08-29 and 2026-09-11 NASA POWER's hourly endpoint **changed the units of `PRECTOTCORR`** from a mm/day rate to a per-hour depth, every other column byte-identical. The code averaged it — correct for the August form, **24× too low** for the September one: a fresh clone computed 7.1 mm/yr for 2020 against the daily product's 171.4, the mirror image of defect 1. Every fetch now establishes its units against the daily product and refuses to guess. Separately, the lead-in year had been **cached corrupted** (−99,000 in every hour) minutes before the guard against exactly that was committed, and was read back unchecked; cached files are now validated on every read. Neither changed a published number — the first because all published runs used the August cache, the second because nothing was trained after it landed — but both would have, silently, on the next run.

**A methodological note.** Two checks in this project passed for the wrong reasons and had to be tightened. One compared means with no significance test (+$43 at p=0.194; then reported as confirmed at n=5, p=0.030 — **and on the 2026-09-11 re-run on the corrected environment it did not replicate: +$29, Welch p=0.165, so M5's criterion (b) is now recorded as failed**). The other selected the best risk level *after seeing the results* — with four risk levels, three seeds and a seed deviation around $50, the maximum of four noisy numbers beats the reference by chance. Replaced with a single pre-specified prediction, **that check now fails**, which is the honest verdict. Both are documented at the check site.

It is worth being blunt about what that means: **M7's declared criterion was recorded as passing, and on re-examination it does not hold.** The correction makes the project's conclusion stronger, not weaker, which is precisely why it was worth making.

---

## What we would tell DEWA

1. **Invest in soiling estimation, not in a learned controller.** A Kalman filter over the performance ratio reduced soiling-estimate error **17.7×** and made cleaning decisions essentially immune to sensor noise that destroys a naive rule. DEWA's patented Autonomous Soiling Detector is the right layer to build on.
2. **A tuned condition-based threshold is close to optimal, and deployable.** It beat every learned agent we trained, has no collapse mode, and is inspectable. One PPO seed in five collapsed to never-cleaning — a policy that fails silently 20% of the time is not deployable at a 5 GW asset.
3. **Do not over-invest in fleet optimisation.** Choosing between cleaning robots is second-order at this plant's economics. A learned efficacy estimator ranked the fleet *perfectly* (Spearman ρ = 1.00) and still lost, because the exploration is paid for in $60 cleans and there are only 5–42 of them a year.
4. **Water is a constraint, not a cost.** Meeting a hard annual water budget cost **$37/MWp/yr (0.14%)** at the tightest budget, with 100% satisfaction at every budget. Its energy content is ~1% of the energy recovered — real for the UAE Water Security Strategy 2036, negligible for economics.
5. **Storms are where the remaining risk lives.** Modelling them properly moves CVaR@5% by ~$391/MWp/yr and creates the only genuine risk/return trade-off we found: buying $62 of tail protection costs $55 of mean.

---

## Reproducing this

```bash
git clone https://github.com/KartikJoshi23/Self-Learning-Agent.git
cd Self-Learning-Agent && python -m venv .venv
pip install -r requirements.txt
pytest -q                       # 194 tests
python scripts/m0_verify.py     # ... through m7_verify.py
```

Each milestone has an acceptance script that declares its criteria *before* the milestone is built and prints PASS/FAIL per check. Checks are labelled `declared` (approved in the plan) versus `scrutiny` (harder bars we set ourselves) — and a failing scrutiny check still turns the run red.

All data is free and redistributable: [NASA POWER](https://power.larc.nasa.gov/) supplies irradiance, weather and aerosol optical depth for Seih Al-Dahal with no registration. The whole project runs on a CPU laptop at zero cost.

## Grounding

DEWA cleaning-robot field trial, 164 modules rated 445–505 W, 22 Jul 2024 – 26 Aug 2025: soiling 0.14–0.33 %/day, cleaning efficiencies 69–99%, documented failure modes battery overheating, corrosion, frame misalignment, UV degradation. DEWA Autonomous Soiling Detector (Dec 2025). IEA-PVPS Task 13 on soiling losses. Global Solar Atlas PVOUT 1791.5 kWh/kWp for Dubai. Nearest prior work: [arXiv:2603.07518](https://arxiv.org/abs/2603.07518), An — PPO/SAC for PV cleaning in Abu Dhabi, which treats soiling as observable and cleaning as a perfect reset.
