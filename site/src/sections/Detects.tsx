"use client";

import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { area as d3area, line as d3line, curveMonotoneX } from "d3-shape";
import { Frame, Tip, XAxis, YAxis } from "@/charts/base";
import { useData } from "@/lib/data";
import { Chips, Key, Legend, Note, PageShell, Panel, SERIES, Skeleton, Slider, Stat, StatRow } from "@/components/ui";
import { simulate } from "@/lib/physics/rimal";

const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

export function Detects() {
  const { data } = useData("weather");
  const { data: results } = useData("results");
  const [noise, setNoise] = useState(3);
  const [year, setYear] = useState(2024);
  const [hover, setHover] = useState<number | null>(null);

  const sim = useMemo(() => {
    if (!data) return null;
    const run = simulate(data, year, "belief", noise / 100, 0.93, 1);
    const rmse = (series: number[]) => Math.sqrt(series.reduce((acc, v, i) => acc + (v - run.tTrue[i]) ** 2, 0) / series.length);
    return { run, rmseRaw: rmse(run.tObs), rmseBelief: rmse(run.tBelief) };
  }, [data, year, noise]);

  const years = data?.meta.holdout_years ?? [2023, 2024, 2025];

  return (
    <PageShell
      eyebrow="02 · What the plant detects"
      title="The plant never sees soiling. It sees a noisy performance ratio."
      lede={
        <>
          Actual against expected output, confounded by irradiance, temperature and the noise of a real meter. The naive rule thresholds
          that reading and chatters. The filter treats it as evidence about a hidden state — a Kalman filter over soiling loss, told only
          what an operator knows: the reading, its noise scale, yesterday&apos;s rain and its own cleaning actions.
        </>
      }
    >
      <StatRow>
        <Stat label="raw reading · RMSE" value={sim ? sim.rmseRaw.toFixed(4) : "—"} tone="naive" note="against the hidden truth, this run" />
        <Stat label="Kalman belief · RMSE" value={sim ? sim.rmseBelief.toFixed(4) : "—"} tone="belief" note="same year, same readings" />
        <Stat label="recorded reduction" value={results ? `${results.m5.rmse_reduction}×` : "—"} tone="belief" note={results ? `${results.m5.rmse_raw} → ${results.m5.rmse_belief} · results/m5_verify.log` : ""} />
        <Stat label="belief rule · cleans" value={sim ? `${sim.run.cleans}` : "—"} unit="/yr" note="the filter's decisions this year" />
      </StatRow>

      <Panel
        title="Hidden truth · noisy reading · belief"
        subtitle="soiling ratio through one held-out year, computed live by the verified physics port"
        controls={
          <>
            <Slider label="noise" value={noise} min={0} max={10} step={1} onChange={setNoise} format={(v) => `${v}%`} />
            <Chips label="year" value={year} onChange={setYear} options={years.map((y) => ({ value: y, label: String(y) }))} />
          </>
        }
        footer={
          <>
            The filter has two things a naive threshold lacks: a model of how soiling grows between readings, and knowledge that a wash
            or a clean is a known event rather than something to infer. Two bugs made it — it first ignored the 14-day damp-surface
            grace after rain (a drift of 0.033, the size of the noise it was removing), and it reacted to today&apos;s rain when the plant
            applies rain to tomorrow. Fixed, its error fell {results ? `${results.m5.rmse_reduction}×` : "17.7×"}: the largest single
            effect anything in this project produced.
          </>
        }
      >
        {sim ? (
          <Frame height={340} label="Soiling ratio: hidden truth, noisy reading and Kalman belief through the year">
            {({ width, height }) => {
              const r = sim.run;
              const x = scaleLinear().domain([0, r.n - 1]).range([0, width]);
              const lo = Math.min(0.86, ...r.tTrue, ...r.tBelief) - 0.01;
              const y = scaleLinear().domain([Math.max(0.6, lo), 1.05]).range([height, 0]);
              const lineOf = (s: number[]) =>
                d3line<number>()
                  .x((_, i) => x(i))
                  .y((v) => y(Math.min(1.05, v)))
                  .curve(curveMonotoneX)(s) ?? "";
              const band =
                d3area<number>()
                  .x((_, i) => x(i))
                  .y0((_, i) => y(Math.min(1.05, r.tBelief[i] - 2 * r.tBeliefStd[i])))
                  .y1((_, i) => y(Math.min(1.05, r.tBelief[i] + 2 * r.tBeliefStd[i])))
                  .curve(curveMonotoneX)(r.tBelief) ?? "";
              const hi = hover;
              const monthStarts = Array.from({ length: 12 }, (_, m) => Math.round((m / 12) * r.n));
              return (
                <>
                  <YAxis scale={y} x0={0} x1={width} format={(v) => v.toFixed(2)} ticks={4} />
                  {r.rainDays.map((d) => (
                    <line key={`r${d}`} x1={x(d)} x2={x(d)} y1={0} y2={height} stroke={SERIES.belief} opacity={0.18} />
                  ))}
                  {r.cleanDays.map((d) => (
                    <line key={`c${d}`} x1={x(d)} x2={x(d)} y1={height - 10} y2={height} stroke={SERIES.belief} strokeWidth={2} />
                  ))}
                  {noise > 0 && r.tObs.map((v, i) => <circle key={i} cx={x(i)} cy={y(Math.min(1.05, v))} r={1.6} fill={SERIES.naive} opacity={0.55} />)}
                  <path d={band} fill={SERIES.belief} opacity={0.18} />
                  <path d={lineOf(r.tTrue)} fill="none" stroke={SERIES.ink} strokeWidth={1.2} opacity={0.75} />
                  <path d={lineOf(r.tBelief)} fill="none" stroke={SERIES.belief} strokeWidth={2} />
                  <XAxis scale={x} y={height} values={monthStarts} format={(v) => MONTHS[Math.round((v / r.n) * 12) % 12]} />
                  <rect
                    x={0}
                    y={0}
                    width={width}
                    height={height}
                    fill="transparent"
                    onMouseMove={(e) => {
                      const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
                      setHover(Math.round(Math.min(r.n - 1, Math.max(0, x.invert(e.clientX - rect.left)))));
                    }}
                    onMouseLeave={() => setHover(null)}
                  />
                  {hi !== null && (
                    <>
                      <line x1={x(hi)} x2={x(hi)} y1={0} y2={height} stroke="#f2ebdf" opacity={0.25} />
                      <Tip x={x(hi)} y={y(r.tBelief[hi])} width={width}>
                        <div className="text-ink">day {hi + 1}</div>
                        <div>
                          truth <span className="text-ink">{r.tTrue[hi].toFixed(3)}</span>
                        </div>
                        <div>
                          reading <span style={{ color: SERIES.naive }}>{r.tObs[hi].toFixed(3)}</span>
                        </div>
                        <div>
                          belief <span style={{ color: SERIES.belief }}>{r.tBelief[hi].toFixed(3)}</span> ± {(2 * r.tBeliefStd[hi]).toFixed(3)}
                        </div>
                      </Tip>
                    </>
                  )}
                </>
              );
            }}
          </Frame>
        ) : (
          <Skeleton height={340} />
        )}
        <Legend>
          <Key color={SERIES.ink}>hidden truth</Key>
          <Key color={SERIES.naive}>noisy reading</Key>
          <Key color={SERIES.belief}>Kalman belief ± 2σ · rain washes (faint) · cleans (ticks)</Key>
        </Legend>
      </Panel>

      <Note>
        The belief rule applies the same 0.93 threshold as the naive rule, to the filtered estimate instead of the raw reading. On the
        archival run its net value varies by about $13 across the whole 1–10% noise range, while the naive rule loses{" "}
        {results ? `$${Math.round(results.m5.collapse_usd).toLocaleString()}` : "$4,771"} at 10% — the comparison the Verdict page makes in
        full.
      </Note>
    </PageShell>
  );
}
