"use client";

import { useEffect, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line as d3line, curveMonotoneX } from "d3-shape";
import { interpolateLab } from "d3-interpolate";
import { Frame, Tip, XAxis, YAxis } from "@/charts/base";
import { useData, usd, fmt } from "@/lib/data";
import { ACCENTS, Chips, Key, Legend, Note, PageShell, Panel, SERIES, Skeleton, Slider, Stat, StatRow } from "@/components/ui";

/* ---------------------------------------------------------------------- */
/* PPO: the decision surface, from untrained to trained                     */
/* ---------------------------------------------------------------------- */

const ramp = interpolateLab("#1a1626", SERIES.agent);

function PpoPanel() {
  const { data: ppo } = useData("ppo");
  const { data: results } = useData("results");
  const [stage, setStage] = useState(3);
  const [shown, setShown] = useState<number[][] | null>(null);
  const [hover, setHover] = useState<{ r: number; d: number } | null>(null);
  const animRef = useRef<number | null>(null);

  // Morph between stages rather than swap: the reader watches the cliff form.
  useEffect(() => {
    if (!ppo) return;
    const target = ppo.stages[stage].surface.p_clean;
    const from = shown ?? target;
    const start = performance.now();
    if (animRef.current) cancelAnimationFrame(animRef.current);
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 700);
      const e = 1 - Math.pow(1 - t, 3);
      setShown(from.map((row, i) => row.map((v, j) => v + (target[i][j] - v) * e)));
      if (t < 1) animRef.current = requestAnimationFrame(step);
    };
    animRef.current = requestAnimationFrame(step);
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ppo, stage]);

  if (!ppo) return <Skeleton height={480} />;
  const s = ppo.stages[stage];
  const { ratios, days } = s.surface;
  const grid = shown ?? s.surface.p_clean;
  const dr = ratios[1] - ratios[0];
  const dd = days[1] - days[0];

  return (
    <Panel
      title="PPO · probability of cleaning, by state"
      subtitle={`soiling ratio × days since last clean · one seed, ${fmt(ppo.timesteps)} steps · other features at held-out medians, late April`}
      controls={<Chips label="training stage" value={stage} onChange={setStage} options={ppo.stages.map((st, i) => ({ value: i, label: st.label }))} />}
      footer={
        <>
          Untrained, the policy cleans with a flat, state-independent probability. Trained, it has carved a cliff along the soiling axis at
          almost exactly the tuned threshold — it <span className="text-ink">rediscovered the rule</span>. On the archival five-seed run it
          scored <span className="text-ink">{results ? usd(results.m4.ppo_mean) : "—"} ± {results ? results.m4.ppo_sd : "—"}</span> against the
          rule&apos;s <span className="text-truth">{results ? usd(results.m4.threshold_net) : "—"}</span>: it beat every fixed calendar (+
          {results ? usd(results.m4.margin_over_fixed) : "—"}) and lost to the threshold by {results ? usd(results.m4.threshold_net - results.m4.ppo_mean) : "—"}.
          With soiling observed exactly and cleaning a perfect reset, the optimal policy <em>is</em> a threshold on an observed scalar.
        </>
      }
    >
      <Frame height={300} label="Probability of cleaning as a function of soiling ratio and days since the last clean" margin={{ top: 10, right: 20, bottom: 36, left: 56 }}>
        {({ width, height }) => {
          const x = scaleLinear().domain([ratios[0] - dr / 2, ratios[ratios.length - 1] + dr / 2]).range([0, width]);
          const y = scaleLinear().domain([days[0] - dd / 2, days[days.length - 1] + dd / 2]).range([height, 0]);
          const cw = x(dr) - x(0);
          const ch = y(0) - y(dd);
          return (
            <>
              {grid.map((row, i) =>
                row.map((v, j) => (
                  <rect
                    key={`${i}-${j}`}
                    x={x(ratios[j] - dr / 2)}
                    y={y(days[i] + dd / 2)}
                    width={cw + 0.6}
                    height={ch + 0.6}
                    fill={ramp(v)}
                    onMouseEnter={() => setHover({ r: j, d: i })}
                    onMouseLeave={() => setHover(null)}
                  />
                )),
              )}
              <line x1={x(ppo.threshold)} x2={x(ppo.threshold)} y1={0} y2={height} stroke={SERIES.truth} strokeWidth={1.5} />
              <text x={x(ppo.threshold) + 6} y={14} className="mono" fontSize={10} fill={SERIES.truth} style={{ paintOrder: "stroke", stroke: "#0a0910", strokeWidth: 4 }}>
                tuned threshold {ppo.threshold}
              </text>
              <YAxis scale={y} x0={0} x1={0} format={(v) => `${v} d`} ticks={4} />
              <XAxis scale={x} y={height} format={(v) => v.toFixed(2)} ticks={6} />
              {hover && (
                <Tip x={x(ratios[hover.r])} y={y(days[hover.d])} width={width}>
                  <div className="text-ink">
                    ratio {ratios[hover.r].toFixed(3)} · {days[hover.d]} d since clean
                  </div>
                  <div>
                    P(clean) <span style={{ color: SERIES.agent }}>{(grid[hover.d][hover.r] * 100).toFixed(1)}%</span>
                  </div>
                </Tip>
              )}
            </>
          );
        }}
      </Frame>
      <Legend>
        <span className="inline-flex items-center gap-2 text-xs text-ink-2">
          P(clean) 0
          <span className="h-2 w-24 rounded-full" style={{ background: `linear-gradient(90deg, ${ramp(0)}, ${ramp(1)})` }} aria-hidden />1
        </span>
        <Key color={SERIES.truth}>tuned threshold</Key>
        <span className="ml-auto text-xs text-ink-3">
          this stage on held-out years: <span className="text-ink">{usd(s.holdout_net)}</span>/MWp/yr, {s.holdout_cleans} cleans · rule{" "}
          <span className="text-truth">{usd(ppo.threshold_rule_net)}</span>
        </span>
      </Legend>

      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-xs text-ink-3">episode return during training (scaled reward) · selected stage marked</p>
          <Frame height={130} label="PPO learning curve" margin={{ top: 6, right: 8, bottom: 22, left: 44 }}>
            {({ width, height }) => {
              const lc = ppo.learning_curve;
              const x = scaleLinear().domain([0, ppo.timesteps]).range([0, width]);
              const y = scaleLinear().domain([Math.min(...lc.episode_return), Math.max(...lc.episode_return)]).range([height, 0]).nice();
              const path = d3line<number>()
                .x((_, i) => x(lc.timesteps[i]))
                .y((v) => y(v))
                .curve(curveMonotoneX)(lc.episode_return);
              return (
                <>
                  <YAxis scale={y} x0={0} x1={width} format={(v) => fmt(v)} ticks={3} />
                  <path d={path ?? ""} fill="none" stroke={SERIES.agent} strokeWidth={1.8} />
                  <line x1={x(s.step)} x2={x(s.step)} y1={0} y2={height} stroke={SERIES.ink} opacity={0.35} />
                  <XAxis scale={x} y={height} format={(v) => `${Math.round((v / 1e6) * 10) / 10}M`} ticks={4} />
                </>
              );
            }}
          </Frame>
        </div>
        <div>
          <p className="mb-1 text-xs text-ink-3">this stage on held-out {s.rollout.year}: P(clean) each day, cleans marked</p>
          <Frame height={130} label="Held-out year, probability of cleaning each day" margin={{ top: 6, right: 8, bottom: 22, left: 44 }}>
            {({ width, height }) => {
              const r = s.rollout;
              const x = scaleLinear().domain([0, r.ratio.length - 1]).range([0, width]);
              const y = scaleLinear().domain([0, 1]).range([height, 0]);
              const bw = width / r.ratio.length;
              return (
                <>
                  <YAxis scale={y} x0={0} x1={width} format={(v) => v.toFixed(1)} ticks={2} />
                  {r.p_clean.map((p, i) => (
                    <rect key={i} x={x(i)} y={y(p)} width={Math.max(1, bw)} height={height - y(p)} fill={SERIES.agent} opacity={0.75} />
                  ))}
                  {r.cleaned.map((c, i) => (c ? <circle key={`c${i}`} cx={x(i)} cy={4} r={2} fill={SERIES.ink} /> : null))}
                  <XAxis scale={x} y={height} format={(v) => `d${Math.round(v)}`} ticks={4} />
                </>
              );
            }}
          </Frame>
        </div>
      </div>
    </Panel>
  );
}

/* ---------------------------------------------------------------------- */
/* Fleet: learning which robot                                               */
/* ---------------------------------------------------------------------- */

const ROBOT_COLORS = [SERIES.belief, SERIES.naive, SERIES.agent, SERIES.truth, SERIES.calendar];

function FleetPanel() {
  const { data: fleet } = useData("fleet");
  const { data: results } = useData("results");
  const [day, setDay] = useState(364);
  if (!fleet) return <Skeleton height={480} />;
  const n = fleet.days.length;
  const d = Math.min(day, n - 1);
  const today = fleet.days[d];

  return (
    <Panel
      title="Fleet · learned cleaning efficacy of five robots"
      subtitle={`estimate after each clean, held-out ${fleet.year} · true nominal at the right edge · DEWA's measured band 69–99% shaded`}
      controls={<Slider label="day" value={d} min={0} max={n - 1} step={1} onChange={setDay} format={(v) => `${v + 1}`} />}
      footer={
        <>
          The estimator learns the fleet <span className="text-ink">perfectly</span> — it ranks all five robots in the true order — and still
          loses money at every cleaning frequency, because the exploration that buys that ranking is paid for in $60 cleans and there are only
          five to forty of them a year. A short-horizon bandit result: the manufacturer&apos;s spec sheet wins.
        </>
      }
    >
      <Frame height={300} label="Efficacy estimates for each robot through the year" margin={{ top: 10, right: 130, bottom: 36, left: 48 }}>
        {({ width, height }) => {
          const x = scaleLinear().domain([0, n - 1]).range([0, width]);
          const y = scaleLinear().domain([0.5, 1.0]).range([height, 0]);
          return (
            <>
              <rect x={0} y={y(fleet.efficacy_band[1])} width={width} height={y(fleet.efficacy_band[0]) - y(fleet.efficacy_band[1])} fill={SERIES.ink} opacity={0.04} />
              <YAxis scale={y} x0={0} x1={width} format={(v) => `${Math.round(v * 100)}%`} ticks={5} />
              {fleet.robots.map((robot, r) => {
                const series = fleet.days.slice(0, d + 1).map((row) => row.estimates[r]);
                const path = d3line<number>()
                  .x((_, i) => x(i))
                  .y((v) => y(v))
                  .curve(curveMonotoneX)(series);
                return (
                  <g key={robot.name}>
                    <path d={path ?? ""} fill="none" stroke={ROBOT_COLORS[r]} strokeWidth={1.8} />
                    <line x1={width + 4} x2={width + 14} y1={y(robot.nominal)} y2={y(robot.nominal)} stroke={ROBOT_COLORS[r]} strokeWidth={2} />
                    <text x={width + 18} y={y(robot.nominal)} dy="0.32em" className="mono" fontSize={10} fill={SERIES.ink2}>
                      {robot.name.split("-")[0]} · true {Math.round(robot.nominal * 100)}%
                    </text>
                  </g>
                );
              })}
              {fleet.days.slice(0, d + 1).map((row, i) => (row.robot >= 0 ? <circle key={i} cx={x(i)} cy={height - 4} r={2.5} fill={ROBOT_COLORS[row.robot]} /> : null))}
              <line x1={x(d)} x2={x(d)} y1={0} y2={height} stroke={SERIES.ink} opacity={0.3} />
              <XAxis scale={x} y={height} format={(v) => `d${Math.round(v)}`} ticks={6} />
            </>
          );
        }}
      </Frame>
      <Legend>
        {fleet.robots.map((r, i) => (
          <Key key={r.name} color={ROBOT_COLORS[i]}>
            {r.name} · cooldown {r.cooldown_days} d
          </Key>
        ))}
      </Legend>
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="bill so far" value={usd(today.cost)} note="cleans and services, this year" />
        <Stat label="latent health · A" value={`${Math.round(today.health[0] * 100)}%`} note="the operator cannot see this" tone="belief" />
        <Stat label="rank correctness" value={results ? `ρ = ${results.m6.spearman.toFixed(2)}` : "—"} note="Spearman vs true nominal, end of run" />
        <Stat label="dispatch learning" value={results ? `−${usd(results.m6.dispatch_paired_mean)}` : "—"} note={results ? `± ${results.m6.dispatch_paired_sem}, p < 0.0001, vs the spec sheet` : ""} tone="naive" />
      </div>
    </Panel>
  );
}

/* ---------------------------------------------------------------------- */
/* QR-DQN: the return distribution and the dial that does nothing            */
/* ---------------------------------------------------------------------- */

const ALPHAS = ["1.0", "0.5", "0.25", "0.1"] as const;
type Alpha = (typeof ALPHAS)[number];

function QrdqnPanel() {
  const { data: q } = useData("qrdqn");
  const { data: results } = useData("results");
  const [day, setDay] = useState(200);
  const [alpha, setAlpha] = useState<Alpha>("1.0");
  if (!q) return <Skeleton height={480} />;
  const d = Math.min(day, q.days.length - 1);
  const today = q.days[d];
  const toUsd = (v: number) => v / q.reward_scale;
  const k = Math.max(1, Math.round(Number(alpha) * q.quantile_taus.length));
  const choice = today.choice[alpha];

  return (
    <Panel
      title="QR-DQN · predicted return distribution for each action"
      subtitle={`held-out ${q.year}, storm soiling · quantiles of the discounted return the network predicts on the selected day (the reward is minus soiling loss and cleaning cost, so every value is a cost and less negative is better) · one seed, ${fmt(q.timesteps)} steps`}
      controls={
        <>
          <Slider label="day" value={d} min={0} max={q.days.length - 1} step={1} onChange={setDay} format={(v) => `${v + 1}`} />
          <Chips label="risk level alpha" value={alpha} onChange={setAlpha} options={ALPHAS.map((a) => ({ value: a, label: `α ${a}` }))} />
        </>
      }
      footer={
        <>
          The agent did learn a distribution — watch the two fans separate as the array soils and the storm season arrives. But it applies risk
          only at action selection, re-reading the tail of a distribution learnt under the risk-neutral policy, and that dial changes nothing
          measurable. The structural case for a distributional agent was the strongest in the project; it made no difference.
        </>
      }
    >
      <div className="grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
        <Frame height={280} label="Quantiles of predicted return for no-op and clean" margin={{ top: 10, right: 16, bottom: 36, left: 64 }}>
          {({ width, height }) => {
            const taus = q.quantile_taus;
            const all = today.quantiles.flat().map(toUsd);
            const x = scaleLinear().domain([0, 1]).range([0, width]);
            const y = scaleLinear().domain([Math.min(...all), Math.max(...all)]).range([height, 0]).nice();
            const draw = (vals: number[], color: string, label: string, i: number) => {
              const path = d3line<number>()
                .x((_, j) => x(taus[j]))
                .y((v) => y(toUsd(v)))
                .curve(curveMonotoneX)(vals);
              const tail = vals.slice(0, k).map(toUsd);
              const cvar = tail.reduce((a, b) => a + b, 0) / tail.length;
              return (
                <g key={label}>
                  <path d={path ?? ""} fill="none" stroke={color} strokeWidth={2} opacity={choice === i ? 1 : 0.55} />
                  {vals.map((v, j) => (
                    <circle key={j} cx={x(taus[j])} cy={y(toUsd(v))} r={j < k ? 3.5 : 2} fill={color} opacity={j < k ? 1 : 0.4} />
                  ))}
                  <line x1={0} x2={x(taus[k - 1])} y1={y(cvar)} y2={y(cvar)} stroke={color} strokeWidth={1} opacity={0.8} />
                  <text x={x(taus[Math.min(k - 1, taus.length - 1)]) + 6} y={y(cvar)} dy="0.32em" className="mono" fontSize={10} fill={color} style={{ paintOrder: "stroke", stroke: "#0a0910", strokeWidth: 4 }}>
                    {label} score {usd(cvar)}
                  </text>
                </g>
              );
            };
            return (
              <>
                <YAxis scale={y} x0={0} x1={width} format={(v) => usd(v)} ticks={4} />
                <rect x={0} y={0} width={x(taus[k - 1])} height={height} fill={SERIES.ink} opacity={0.04} />
                {draw(today.quantiles[0], SERIES.calendar, "wait", 0)}
                {draw(today.quantiles[1], SERIES.agent, "clean", 1)}
                <XAxis scale={x} y={height} format={(v) => `τ ${v.toFixed(2)}`} ticks={5} />
              </>
            );
          }}
        </Frame>
        <div>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="state today" value={`${today.ratio.toFixed(3)}`} note={`true soiling ratio · AOD ${today.aod}`} tone="truth" />
            <Stat label={`action at α ${alpha}`} value={choice === 1 ? "clean" : "wait"} note="argmax of the shaded tail's mean" tone="agent" />
          </div>
          <table className="mono mt-4 w-full text-xs">
            <caption className="mb-1 text-left text-xs text-ink-3">CVaR@5% by risk level, held-out (archival run)</caption>
            <thead className="text-ink-3">
              <tr>
                <th className="py-1 text-left font-normal">α</th>
                <th className="py-1 text-right font-normal">mean</th>
                <th className="py-1 text-right font-normal">CVaR@5%</th>
              </tr>
            </thead>
            <tbody>
              {(results?.m7.alpha_table ?? []).map((row) => (
                <tr key={row.alpha} className="border-t border-white/5 text-ink-2">
                  <td className="py-1">{row.alpha.toFixed(2)}</td>
                  <td className="py-1 text-right">{usd(row.mean)}</td>
                  <td className="py-1 text-right text-ink">{usd(row.cvar5)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs leading-relaxed text-ink-3">
            The pre-specified prediction was that CVaR rises as α falls. It does not — the ordering is noise. Like for like, the CVaR-tuned
            threshold takes <span className="text-ink-2">{results ? usd(results.m7.rule_cvar) : "—"}</span> against the agent&apos;s{" "}
            <span className="text-ink-2">{results ? usd(results.m7.agent_cvar) : "—"}</span>.
          </p>
        </div>
      </div>
      <Legend>
        <Key color={SERIES.calendar}>wait (no-op)</Key>
        <Key color={SERIES.agent}>clean</Key>
        <span className="text-xs text-ink-3">· larger dots and the shaded band are the lowest-α share of quantiles the risk level averages</span>
      </Legend>
    </Panel>
  );
}

/* ---------------------------------------------------------------------- */

export function Learnt() {
  const { data: results } = useData("results");
  return (
    <PageShell
      accent={ACCENTS.agent}
      eyebrow="03 · What the agents learnt"
      title="Three agents, three learned artefacts. Each one is real, and each one lost."
      lede={
        <>
          These are not illustrations. The surfaces, estimates and distributions below were exported from agents trained on this benchmark —
          PPO for the observable world, an efficacy estimator for the fleet, QR-DQN for the storm tail — and the rule each was compared against
          is drawn beside it.
        </>
      }
    >
      <StatRow>
        <Stat label="PPO vs tuned rule" value={results ? `−${usd(results.m4.threshold_net - results.m4.ppo_mean)}` : "—"} note="five seeds, held-out years" tone="agent" />
        <Stat label="belief-state PPO" value={results ? `+${usd(results.m5.ppo_gap)}` : "—"} note={results ? `over memoryless, p = ${results.m5.ppo_p} — not significant` : ""} tone="agent" />
        <Stat label="fleet estimator" value={results ? `−${usd(results.m6.dispatch_paired_mean)}` : "—"} note="vs the spec sheet, despite ρ = 1.00" tone="agent" />
        <Stat label="QR-DQN CVaR" value={results ? `−${usd(results.m7.agent_margin)}` : "—"} note="vs a CVaR-tuned threshold, like for like" tone="agent" />
      </StatRow>
      <PpoPanel />
      <FleetPanel />
      <QrdqnPanel />
      <Note>
        Two of the five PPO seeds on the fleet environment drifted toward never cleaning across the two archival runs — a policy that fails
        silently one time in five is a robustness result in its own right. The agents on this page are single seeds trained for the site by{" "}
        <span className="text-ink-2">scripts/export_site_data.py</span>; the archival figures are from the five-seed acceptance runs.
      </Note>
    </PageShell>
  );
}
