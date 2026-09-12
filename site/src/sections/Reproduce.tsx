"use client";

import { useData } from "@/lib/data";
import { ACCENTS, Note, PageShell, Panel, Stat, StatRow } from "@/components/ui";

const REPO = "https://github.com/KartikJoshi23/Self-Learning-Agent";

export function Reproduce() {
  const { data: r } = useData("results");
  const commands: [string, string][] = [
    [`git clone ${REPO}.git`, ""],
    ["pip install -r requirements.txt", "CPU torch is all it needs"],
    ["pytest -q", "network tests fetch NASA POWER once, then run from cache"],
    ["python scripts/m0_verify.py", r ? `data layer · ${r.m0.checks}/${r.m0.checks}` : "data layer"],
    ["python scripts/m3_verify.py", r ? `falsification gate · ${r.m3.checks}/${r.m3.checks}` : "falsification gate"],
    ["python scripts/m4_verify.py", r ? `PPO · ${r.m4.checks}/${r.m4.checks}, about an hour` : "PPO"],
    ["python scripts/m5_verify.py --seeds 5", "partial observability · ends red, honestly"],
    ["python scripts/verify_simulator.py --module site/src/lib/physics/rimal.js", "this site's physics against the engine"],
    ["python scripts/export_site_data.py", "regenerates every number on this site"],
  ];
  const links: [string, string][] = [
    ["Repository", REPO],
    ["FINDINGS.md", `${REPO}/blob/main/FINDINGS.md`],
    ["Acceptance logs", `${REPO}/tree/main/results`],
    ["Stand-alone simulator", `${REPO}/blob/main/web/simulator.html`],
    ["PROGRESS.md", `${REPO}/blob/main/PROGRESS.md`],
  ];

  return (
    <PageShell
      accent={ACCENTS.belief}
      eyebrow="07 · Reproduce it"
      title="A clean clone reproduces the record from an empty cache."
      lede={
        <>
          Verified on 2026-09-12: fresh clone, fresh virtual environment, no cached data, that day&apos;s NASA POWER endpoint — the
          falsification gate came back byte-identical to the committed log. Everything runs on a CPU laptop at zero cost, and every acceptance
          script prints PASS/FAIL per check against criteria declared before the milestone was built.
        </>
      }
    >
      <StatRow>
        <Stat label="M0 · data layer" value={r ? `${r.m0.checks}/${r.m0.checks}` : "—"} note="incl. rainfall units and sentinel guards" />
        <Stat label="M1 · physics" value={r ? `${r.m1.checks}/${r.m1.checks}` : "—"} note="yield and soiling in the published bands" />
        <Stat label="M3 · falsification" value={r ? `${r.m3.checks}/${r.m3.checks}` : "—"} note="28–34 day optimum reproduced" tone="truth" />
        <Stat label="M5 · M6 · M7" value="red" note="declared or scrutiny checks fail — the honest result" tone="naive" />
      </StatRow>

      <Panel title="Commands" subtitle="from the repository root; the first pytest run fetches the data once">
        <ol className="mono space-y-2 overflow-x-auto text-xs">
          {commands.map(([cmd, note]) => (
            <li key={cmd} className="flex flex-wrap items-baseline gap-x-4">
              <span className="text-ink-3">$</span>
              <span className="whitespace-nowrap text-ink">{cmd}</span>
              {note && <span className="text-ink-3"># {note}</span>}
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Where things live" subtitle="the repository is public and stays public">
        <div className="flex flex-wrap gap-2">
          {links.map(([label, href]) => (
            <a key={href} className="chip !px-4 !py-2 !text-sm !text-ink" href={href} target="_blank" rel="noreferrer">
              {label} ↗
            </a>
          ))}
        </div>
        <dl className="mono mt-5 grid gap-x-8 gap-y-2 text-xs sm:grid-cols-2">
          {[
            ["rimal/data", "NASA POWER fetcher with units and sentinel guards, parquet cache"],
            ["rimal/physics", "pvlib energy yield; Kimber, AOD-modulated and storm soiling"],
            ["rimal/env", "Gymnasium environment, observation noise, Kalman filter, robot fleet"],
            ["rimal/baselines", "fixed-interval, threshold, belief-threshold, fleet heuristics"],
            ["rimal/agents", "PPO (CleanRL style) and QR-DQN with CVaR action selection"],
            ["scripts/", "one acceptance script per milestone, the simulator harness, the site export"],
            ["results/", "the observed output of every acceptance script, as last run"],
            ["site/", "this site — Next.js, static export, no server"],
          ].map(([k, v]) => (
            <div key={k} className="flex gap-3">
              <dt className="w-32 shrink-0 text-sand">{k}</dt>
              <dd className="text-ink-3">{v}</dd>
            </div>
          ))}
        </dl>
      </Panel>

      <Note>
        Grounding: DEWA cleaning-robot field trial (164 modules rated 445–505 W, 22 Jul 2024 – 26 Aug 2025: soiling 0.14–0.33 %/day, cleaning
        efficiencies 69–99%, documented battery overheating, corrosion, frame misalignment and UV degradation); DEWA Autonomous Soiling Detector
        (Dec 2025); IEA-PVPS Task 13; Global Solar Atlas PVOUT 1,791.5 kWh/kWp for Dubai. Nearest prior work: arXiv:2603.07518. MIT licence.
      </Note>
    </PageShell>
  );
}
