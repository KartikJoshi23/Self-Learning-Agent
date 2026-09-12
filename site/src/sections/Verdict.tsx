"use client";

import { scaleLinear } from "d3-scale";
import { line as d3line, curveMonotoneX } from "d3-shape";
import { Frame, XAxis, YAxis } from "@/charts/base";
import { useData, usd } from "@/lib/data";
import { Key, Legend, Note, PageShell, Panel, SERIES, Skeleton, Stat, StatRow } from "@/components/ui";

export function Verdict() {
  const { data: r } = useData("results");

  const rows = r
    ? [
        {
          m: "M4",
          hypothesis: "Soiling is dynamic, so a learned policy beats a fixed schedule.",
          result: `PPO beat every fixed interval (+${usd(r.m4.margin_over_fixed)}) but lost to a tuned threshold by ${usd(r.m4.threshold_net - r.m4.ppo_mean)}.`,
          number: `${usd(r.m4.ppo_mean)} vs ${usd(r.m4.threshold_net)}`,
        },
        {
          m: "M5",
          hypothesis: "Soiling is latent, so a threshold on a noisy reading must fail.",
          result: `Devastating for the naive rule (−${usd(r.m5.collapse_usd)}, ${((r.m5.collapse_usd / r.m5.exact_net) * 100).toFixed(1)}%) — a Kalman filter fixes it; PPO still lost, and giving it the belief state did not significantly help (+${usd(r.m5.ppo_gap)}, p = ${r.m5.ppo_p}).`,
          number: `${r.m5.rmse_reduction}× less error`,
        },
        {
          m: "M6",
          hypothesis: "Cleaning is stochastic and machines wear out.",
          result: `Real but small (${usd(r.m6.partial_cleaning_cost)}/yr). Learning which robot to use lost at every cleaning frequency (−${usd(r.m6.dispatch_paired_mean)} ± ${r.m6.dispatch_paired_sem} at the default cost).`,
          number: `ρ = ${r.m6.spearman.toFixed(2)}, still lost`,
        },
        {
          m: "M7",
          hypothesis: "Storms make returns fat-tailed, which a scalar threshold cannot express.",
          result: `A genuine risk/return frontier exists (+${usd(r.m7.cvar_gain)} CVaR for −${usd(r.m7.mean_cost)} mean) — QR-DQN lost on CVaR by ${usd(r.m7.agent_margin)}, and its risk dial did nothing measurable.`,
          number: `${usd(r.m7.agent_cvar)} vs ${usd(r.m7.rule_cvar)}`,
        },
      ]
    : [];

  return (
    <PageShell
      eyebrow="05 · The verdict"
      title="Deep RL did not beat a well-tuned rule on any of the four hypotheses."
      lede={
        <>
          Each milestone declared its acceptance criteria before it was built, and a milestone was not done until an acceptance script had been
          observed passing — or failing. The learned agents lost every comparison, and the finding that transfers is about estimation, not
          control: <span className="text-ink">once you know how dirty the panels are, the control law is a threshold.</span>
        </>
      }
    >
      <StatRow>
        <Stat label="soiling-estimate error" value={r ? `${r.m5.rmse_reduction}×` : "—"} note="lower, from a Kalman filter" tone="belief" />
        <Stat label="naive rule at 10% noise" value={r ? `−${((r.m5.collapse_usd / r.m5.exact_net) * 100).toFixed(1)}%` : "—"} note={r ? `${r.m5.noise[3].naive_cleans} cleans a year instead of ${r.m3.threshold_cleans}` : ""} tone="naive" />
        <Stat label="water constraint" value={r ? usd(r.m7.water_cost) : "—"} unit="/MWp/yr" note={r ? `${r.m7.water_cost_pct}% of value, 100% satisfied` : ""} />
        <Stat label="clipped-tail error" value={r ? usd(r.m7.clipping_overstated_cvar) : "—"} unit="/MWp/yr" note="CVaR overstated by the first model" tone="truth" />
      </StatRow>

      <Panel title="Four hypotheses, four results" subtitle="held-out years the agents never trained on · every figure parsed from the acceptance logs">
        {r ? (
          <div className="grid gap-2">
            {rows.map((row) => (
              <div key={row.m} className="grid gap-2 rounded-xl bg-white/[0.03] p-4 md:grid-cols-[3.5rem_1fr_1.4fr_11rem] md:items-center">
                <p className="mono text-base text-sand">{row.m}</p>
                <p className="text-sm text-ink-2">{row.hypothesis}</p>
                <p className="text-sm text-ink">{row.result}</p>
                <p className="mono text-xs text-ink-3 md:text-right">{row.number}</p>
              </div>
            ))}
          </div>
        ) : (
          <Skeleton height={260} />
        )}
      </Panel>

      <Panel
        title="Net value against observation noise"
        subtitle="held-out years, 120 episodes per point · USD per MWp per year · the operator-facing finding"
        footer={
          r ? (
            <>
              The failure mode is chatter, not neglect: cleans explode from {r.m3.threshold_cleans} to ~{Math.round(r.m5.noise[3].naive_cleans)} a year as unlucky
              readings trigger $60 washes. From 3% noise a blind calendar beats the sensor-driven rule; the belief policy varies by{" "}
              {usd(Math.max(...r.m5.noise.map((p) => p.belief)) - Math.min(...r.m5.noise.map((p) => p.belief)))} across the whole range. Filtering
              removes the trap entirely.
            </>
          ) : undefined
        }
      >
        {r ? (
          <Frame height={300} label="Net value of four rules as observation noise rises" margin={{ top: 12, right: 120, bottom: 36, left: 60 }}>
            {({ width, height }) => {
              const noise = r.m5.noise;
              const x = scaleLinear().domain([0, 0.1]).range([0, width]);
              const all = noise.flatMap((p) => [p.naive, p.guarded, p.belief, p.fixed]);
              const y = scaleLinear().domain([Math.min(...all) - 300, Math.max(...all) + 200]).range([height, 0]).nice();
              const series: { key: "naive" | "guarded" | "belief" | "fixed"; label: string; color: string; dash?: string }[] = [
                { key: "belief", label: "Kalman belief", color: SERIES.belief },
                { key: "fixed", label: "blind fixed 31 d", color: SERIES.calendar },
                { key: "guarded", label: "guarded threshold", color: SERIES.naive, dash: "5 4" },
                { key: "naive", label: "naive threshold", color: SERIES.naive },
              ];
              const pts = (k: (typeof series)[number]["key"]) => [{ noise: 0, v: r.m5.exact_net }, ...noise.map((p) => ({ noise: p.noise, v: p[k] }))];
              return (
                <>
                  <YAxis scale={y} x0={0} x1={width} format={(v) => usd(v)} ticks={4} />
                  {series.map((s) => {
                    const data = s.key === "fixed" ? noise.map((p) => ({ noise: p.noise, v: p.fixed })) : pts(s.key);
                    const path = d3line<{ noise: number; v: number }>()
                      .x((d) => x(d.noise))
                      .y((d) => y(d.v))
                      .curve(curveMonotoneX)(data);
                    const last = data[data.length - 1];
                    return (
                      <g key={s.key}>
                        <path d={path ?? ""} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dash} />
                        {data.map((d) => (
                          <circle key={d.noise} cx={x(d.noise)} cy={y(d.v)} r={3.5} fill={s.color} stroke="#16130e" strokeWidth={2} />
                        ))}
                        <text x={x(last.noise) + 8} y={y(last.v)} dy="0.32em" className="mono" fontSize={10} fill={SERIES.ink2}>
                          {s.label}
                        </text>
                      </g>
                    );
                  })}
                  <XAxis scale={x} y={height} format={(v) => `${Math.round(v * 100)}%`} values={[0, 0.01, 0.03, 0.06, 0.1]} />
                </>
              );
            }}
          </Frame>
        ) : (
          <Skeleton height={300} />
        )}
        <Legend>
          <Key color={SERIES.belief}>Kalman belief</Key>
          <Key color={SERIES.calendar}>blind calendar</Key>
          <Key color={SERIES.naive}>naive threshold</Key>
          <Key color={SERIES.naive} dash>
            guarded threshold
          </Key>
        </Legend>
      </Panel>

      <Panel title="What we would tell DEWA" subtitle="five recommendations, each with the number behind it">
        <ol className="grid gap-3 md:grid-cols-2">
          {[
            ["Invest in soiling estimation, not a learned controller.", `A Kalman filter over the performance ratio cut estimate error ${r ? r.m5.rmse_reduction : "17.7"}× and made cleaning decisions immune to noise that destroys a naive rule. The Autonomous Soiling Detector is the right layer to build on.`],
            ["A tuned condition-based threshold is close to optimal, and deployable.", "It beat every learned agent, has no collapse mode, and is inspectable. In each of two five-seed PPO runs one seed collapsed toward never-cleaning — not deployable at a 5 GW asset."],
            ["Do not over-invest in fleet optimisation.", `Choosing between robots is second-order at this plant's economics: a learned estimator ranked the fleet perfectly and still lost ${r ? usd(r.m6.dispatch_paired_mean) : "$103"} a year.`],
            ["Water is a constraint, not a cost.", `A hard annual budget cost ${r ? usd(r.m7.water_cost) : "$37"} per MWp per year at the tightest allocation, satisfied 100% of the time.`],
            ["Storms are where the remaining risk lives.", `Modelling them properly moves CVaR@5% by ${r ? usd(r.m7.clipping_overstated_cvar) : "$391"} and creates the only genuine risk/return trade-off found: ${r ? usd(r.m7.cvar_gain) : "$62"} of tail protection for ${r ? usd(r.m7.mean_cost) : "$55"} of mean.`],
          ].map(([title, body], i) => (
            <li key={title} className="rounded-xl bg-white/[0.03] p-4">
              <p className="mono mb-2 text-xs text-sand">0{i + 1}</p>
              <p className="text-sm text-ink">{title}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink-3">{body}</p>
            </li>
          ))}
        </ol>
      </Panel>

      <Note>{r ? `Every figure on this page is parsed from ${r.generated_from}. A number the export cannot find in its log is an error, not a default.` : ""}</Note>
    </PageShell>
  );
}
