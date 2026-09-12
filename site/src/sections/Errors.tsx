"use client";

import { useData, usd } from "@/lib/data";
import { ACCENTS, Note, PageShell, Panel, Stat, StatRow } from "@/components/ui";

export function Errors() {
  const { data: r } = useData("results");
  const defects = [
    {
      title: "Rainfall was 24× too high.",
      body: "NASA POWER's hourly PRECTOTCORR was a mm/day rate, not a per-hour depth, so summing it overcounted 24×. Dubai came out at 4,405 mm a year against a real ~80–110. Rain is the natural-cleaning trigger: this turned 4 washing days a year into 40 and would have silently destroyed the falsification gate.",
      changed: "4 → 40 washes/yr",
    },
    {
      title: "The soiling tail was clipped away.",
      body: "The dust-driven model capped its rate at DEWA's 0.14–0.33 %/day band — an average over 13 months, not a per-day ceiling. The clip pinned 18.7% of days at the cap and deleted the very phenomenon the risk milestone exists to study.",
      changed: r ? `CVaR overstated by ${usd(r.m7.clipping_overstated_cvar)}` : "CVaR overstated by $391",
    },
    {
      title: "A train/eval mismatch we invented ourselves.",
      body: "The soiling model used the passed frame's own mean dust as its reference, so identical dust implied a 0.70× different rate in evaluation than in training — structurally disadvantaging trained policies against online filters, biasing the very comparison the project exists to make.",
      changed: "0.70× rate mismatch",
    },
    {
      title: "An under-tuned baseline nearly produced a fake win.",
      body: "M4's first run passed against threshold-0.95, from a hand-picked grid that never tried 0.93 — the true optimum, worth about twice the margin PPO appeared to win by. Baselines are now tuned on training years under the same protocol the agent gets.",
      changed: "~$50 of hidden margin",
    },
    {
      title: "An unfair protocol nearly produced a second one.",
      body: "M7's first result showed QR-DQN beating the rule by $166. The rule had oracle threshold selection on its own test set, the two were scored on different years, and the agent's CVaR came from ~1.5 tail samples. Like for like, the rule wins.",
      changed: r ? `+$166 → −${usd(r.m7.agent_margin)}` : "+$166 → −$501",
    },
    {
      title: "The headline sweep was computed from three episodes.",
      body: "The evaluation harness defaulted to one stochastic realisation per year, so the most-quoted result rested on three episodes per point. Resampled at 120, the collapse is 17.2% rather than 19.6%: the finding holds, the figure was overstated.",
      changed: "19.6% → 17.2%",
    },
    {
      title: "The first held-out year was one day short.",
      body: "UTC-to-local conversion dropped 1 January of the first requested year, so results depended on which years happened to be loaded. Fixed with a year of lead-in; every M4–M7 figure was then re-run rather than assumed unchanged.",
      changed: "364 → 365 days · all figures re-run",
    },
  ];
  const nearMisses = [
    {
      title: "The data source changed units under us.",
      body: "Between two sessions NASA POWER switched hourly rainfall from a mm/day rate to a per-hour depth, every other column byte-identical. A fresh clone would have run 24× too dry. Every fetch now establishes its units against POWER's daily product and refuses to guess.",
    },
    {
      title: "A cached year arrived corrupted.",
      body: "The lead-in year was cached with −99,000 in every hour, minutes before the guard against exactly that was committed, and read back unchecked — 1 January 2016 entered the training environment with −16,498 mm of rain. Cached files are now validated on every read.",
    },
  ];

  return (
    <PageShell
      accent={ACCENTS.naive}
      eyebrow="06 · Errors we found in our own work"
      title="Seven defects that changed a result. Two near-misses. Two checks that passed for the wrong reason."
      lede={
        <>
          For a negative result, this record is the credibility argument. Each defect was caught by measurement rather than review, is fixed at
          the site of the fault, and is written up in the repository&apos;s findings with the number it changed.
        </>
      }
    >
      <StatRow>
        <Stat label="defects" value="7" note="each changed a published number" tone="naive" />
        <Stat label="near misses" value="2" note="caught before they reached a result" tone="sand" />
        <Stat label="checks tightened" value="2" note="both now fail — the honest verdict" />
        <Stat label="re-runs" value="M4–M7" note="after the environment was corrected" />
      </StatRow>

      <Panel title="Defects, in the order they were found" subtitle="what was wrong · what it changed">
        <ol className="grid gap-2">
          {defects.map((d, i) => (
            <li key={d.title} className="glass-inset grid gap-2 p-4 md:grid-cols-[3rem_1fr_13rem] md:items-start">
              <p className="mono text-base text-sand">{String(i + 1).padStart(2, "0")}</p>
              <div>
                <p className="text-sm text-ink">{d.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-ink-3">{d.body}</p>
              </div>
              <p className="mono text-xs text-ink-2 md:text-right">{d.changed}</p>
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Near misses" subtitle="faults in the data source, caught by probing it rather than trusting the cache">
        <div className="grid gap-2 md:grid-cols-2">
          {nearMisses.map((m) => (
            <div key={m.title} className="glass-inset p-4">
              <p className="text-sm text-ink">{m.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink-3">{m.body}</p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Checks that passed for the wrong reason" subtitle="both were tightened; both now fail">
        <div className="grid gap-2 md:grid-cols-2">
          <div className="glass-inset p-4">
            <p className="text-sm text-ink">A mean compared with no significance test.</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-3">
              M5&apos;s belief-state PPO first &quot;beat&quot; memoryless PPO by $43 at p = 0.19, then by $64 at p = 0.03 — and on the corrected
              environment by {r ? usd(r.m5.ppo_gap) : "$29"} at p = {r ? r.m5.ppo_p : "0.165"}. The criterion is recorded as failed.
            </p>
          </div>
          <div className="glass-inset p-4">
            <p className="text-sm text-ink">The best risk level chosen after seeing the results.</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-3">
              With four risk levels, three seeds and a seed deviation around $50, the maximum of four noisy numbers beats the reference by
              chance. Replaced with one pre-specified prediction — CVaR rises with risk aversion — which the data does not support.
            </p>
          </div>
        </div>
      </Panel>

      <Note>Both corrections make the conclusion stronger, not weaker — which is precisely why they were worth making.</Note>
    </PageShell>
  );
}
