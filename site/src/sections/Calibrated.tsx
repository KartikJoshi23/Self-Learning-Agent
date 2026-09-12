"use client";

import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line as d3line, curveMonotoneX } from "d3-shape";
import { motion } from "framer-motion";
import { Frame, Tip, XAxis, YAxis } from "@/charts/base";
import { useData, usd, fmt } from "@/lib/data";
import { ACCENTS, Chips, Key, Legend, Note, PageShell, Panel, SERIES, Skeleton, Stat, StatRow } from "@/components/ui";

export function Calibrated() {
  const { data: gate } = useData("gate");
  const { data: results } = useData("results");
  const [cost, setCost] = useState<number>(60);
  const [hover, setHover] = useState<number | null>(null);

  const curve = gate?.curves[String(cost)];
  const row = gate?.costs.find((c) => c.cost === cost);
  const yRange = useMemo(() => {
    if (!gate) return null;
    const all = Object.values(gate.curves).flat();
    return [Math.min(...all) - 200, Math.max(...all) + 200] as const;
  }, [gate]);

  return (
    <PageShell
      accent={ACCENTS.truth}
      eyebrow="01 · Calibrated to DEWA"
      title="Before any agent was trained, the simulator had to reproduce the literature."
      lede={
        <>
          Energy comes from pvlib on measured irradiance; soiling from DEWA&apos;s own field trial. The falsification gate was declared
          as an existence claim with the admissible cleaning cost fixed in advance ($25–150 per MWp per pass): some plausible cost
          must put the optimal fixed interval where the published work does — <span className="text-ink">28 days</span> (UAE practice)
          and <span className="text-ink">34 days</span> (Abu Dhabi optimum).
        </>
      }
    >
      <StatRow>
        <Stat label="specific yield" value={results ? `${fmt(results.m1.yield_min)}–${fmt(results.m1.yield_max)}` : "—"} unit="kWh/kWp" note="Solargis reference 1,791.5" tone="truth" />
        <Stat label="soiling rate" value={results ? `${results.m1.kimber_rate}` : "—"} unit="%/day" note="DEWA band 0.14–0.33" tone="truth" />
        <Stat label="never cleaned" value={results ? `−${results.m1.never_clean_loss_pct}%` : "—"} note="lifetime energy lost to soiling" />
        <Stat label="closed-form gap" value={results ? `${results.m3.closed_form_gap_pct}%` : "—"} note="swept optimum vs T* = √(730·C / E·p·r)" />
      </StatRow>

      <Panel
        title="Net value against fixed cleaning interval"
        subtitle="USD per MWp per year · training years 2016–2022 · pick the cost of one cleaning pass"
        controls={gate && <Chips label="cleaning cost per pass" value={cost} onChange={setCost} options={gate.costs.map((c) => ({ value: c.cost, label: `$${c.cost}` }))} />}
        footer={
          row && gate ? (
            <>
              At ${cost} per pass the swept optimum is <span className="text-ink">{row.optimum} days</span>, the closed form{" "}
              <span className="text-ink">{row.analytic}</span>.
              {cost === gate.default_cost &&
                ` At the default cost any interval from ${gate.plateau_days[0]} to ${gate.plateau_days[1]} days is within 1% of optimal — the optimum is genuinely flat, and a learned agent's edge was never going to come from picking a better interval.`}
            </>
          ) : undefined
        }
      >
        {gate && curve && yRange && row ? (
          <Frame height={320} label={`Net value versus fixed cleaning interval at $${cost} per pass`}>
            {({ width, height }) => {
              const x = scaleLinear().domain([gate.intervals[0], gate.intervals[gate.intervals.length - 1]]).range([0, width]);
              const y = scaleLinear().domain(yRange).range([height, 0]).nice();
              const path = d3line<number>()
                .x((_, i) => x(gate.intervals[i]))
                .y((v) => y(v))
                .curve(curveMonotoneX)(curve);
              const [p0, p1] = gate.published_optimum_days;
              const plateau = gate.plateau_days;
              const hi = hover === null ? null : Math.round(Math.min(gate.intervals.length - 1, Math.max(0, hover)));
              return (
                <>
                  <YAxis scale={y} x0={0} x1={width} format={(v) => usd(v)} ticks={4} />
                  <rect x={x(p0)} width={x(p1) - x(p0)} y={0} height={height} fill={SERIES.truth} opacity={0.12} />
                  <text x={x((p0 + p1) / 2)} y={12} textAnchor="middle" className="mono" fontSize={10} fill={SERIES.truth}>
                    published 28–34 d
                  </text>
                  {cost === gate.default_cost && (
                    <rect x={x(plateau[0])} width={x(plateau[1]) - x(plateau[0])} y={height - 6} height={6} fill={SERIES.ink3} opacity={0.6} rx={2}>
                      <title>within 1% of optimal: {plateau[0]}–{plateau[1]} days</title>
                    </rect>
                  )}
                  <motion.path key={cost} d={path ?? ""} fill="none" stroke={SERIES.truth} strokeWidth={2} initial={{ pathLength: 0, opacity: 0.4 }} animate={{ pathLength: 1, opacity: 1 }} transition={{ duration: 0.9, ease: "easeOut" }} />
                  <circle cx={x(row.optimum)} cy={y(row.net)} r={5} fill={SERIES.truth} stroke="#0a0910" strokeWidth={2} />
                  <text x={x(row.optimum)} y={y(row.net) - 12} textAnchor="middle" className="mono" fontSize={11} fill="#f4eee4">
                    optimum {row.optimum} d
                  </text>
                  <line x1={x(row.analytic)} x2={x(row.analytic)} y1={0} y2={height} stroke={SERIES.ink3} strokeWidth={1} opacity={0.7} />
                  <text x={x(row.analytic) + 4} y={height - 10} className="mono" fontSize={10} fill={SERIES.ink3}>
                    closed form {row.analytic} d
                  </text>
                  <XAxis scale={x} y={height} format={(v) => `${v} d`} values={[10, 20, 30, 40, 50, 60, 70, 80, 90, 100]} />
                  <rect
                    x={0}
                    y={0}
                    width={width}
                    height={height}
                    fill="transparent"
                    onMouseMove={(e) => {
                      const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
                      setHover(x.invert(e.clientX - rect.left) - gate.intervals[0]);
                    }}
                    onMouseLeave={() => setHover(null)}
                  />
                  {hi !== null && (
                    <>
                      <line x1={x(gate.intervals[hi])} x2={x(gate.intervals[hi])} y1={0} y2={height} stroke="#f4eee4" opacity={0.25} />
                      <circle cx={x(gate.intervals[hi])} cy={y(curve[hi])} r={4} fill="#0a0910" stroke={SERIES.truth} strokeWidth={2} />
                      <Tip x={x(gate.intervals[hi])} y={y(curve[hi])} width={width}>
                        <div className="text-ink">every {gate.intervals[hi]} days</div>
                        <div>{usd(curve[hi])} / MWp / yr</div>
                      </Tip>
                    </>
                  )}
                </>
              );
            }}
          </Frame>
        ) : (
          <Skeleton height={320} />
        )}
        <Legend>
          <Key color={SERIES.truth}>simulated net value</Key>
          <Key color={SERIES.ink3}>closed-form optimum · 1% plateau (bar)</Key>
        </Legend>
      </Panel>

      <Panel title="The falsification table" subtitle="the published band is reproduced at two plausible costs; the table is asserted equal to results/m3_verify.log when exported">
        {gate ? (
          <div className="overflow-x-auto">
            <table className="mono w-full text-xs">
              <thead className="text-ink-3">
                <tr>
                  <th className="py-2 text-left font-normal">cost $/MWp/pass</th>
                  <th className="py-2 text-right font-normal">swept optimum</th>
                  <th className="py-2 text-right font-normal">closed form</th>
                  <th className="py-2 text-right font-normal">net $/MWp/yr</th>
                  <th className="py-2 text-right font-normal">in 28–34 d?</th>
                </tr>
              </thead>
              <tbody>
                {gate.costs.map((c) => {
                  const inBand = c.optimum >= gate.published_optimum_days[0] && c.optimum <= gate.published_optimum_days[1];
                  return (
                    <tr key={c.cost} className={`border-t border-white/5 ${inBand ? "text-ink" : "text-ink-2"}`}>
                      <td className="py-2">${c.cost}</td>
                      <td className="py-2 text-right">{c.optimum} d</td>
                      <td className="py-2 text-right">{c.analytic} d</td>
                      <td className="py-2 text-right">{usd(c.net)}</td>
                      <td className="py-2 text-right">{inBand ? <span className="text-truth">yes</span> : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Skeleton height={200} />
        )}
      </Panel>

      <Note>
        The $60 default is a calibration, not a measurement — the midpoint of the range that reproduces published behaviour, and
        independently plausible at about three US cents per module per clean, the right order for the dry robots DEWA is trialling.
        Grounding: DEWA cleaning-robot field trial (164 modules, 445–505 W, Jul 2024 – Aug 2025), IEA-PVPS Task 13, Global Solar Atlas,
        and NASA POWER for irradiance, weather and aerosol optical depth with no registration.
      </Note>
    </PageShell>
  );
}
