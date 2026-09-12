"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { scaleLinear } from "d3-scale";
import { line as d3line, curveMonotoneX } from "d3-shape";
import { Frame, XAxis, YAxis } from "@/charts/base";
import { useData, usd } from "@/lib/data";
import { simulate } from "@/lib/physics/rimal";
import { ACCENTS, Chips, Key, Legend, Note, PageShell, Panel, SERIES, Skeleton, Slider } from "@/components/ui";

type PolicyId = "never" | "fixed" | "naive" | "guarded" | "belief" | "ppo";

const POLICY_META: Record<PolicyId, { label: string; color: string; rgb: string; dash?: string; blurb: string }> = {
  never: { label: "never clean", color: SERIES.ink3, rgb: "141 133 120", blurb: "the do-nothing reference" },
  fixed: { label: "fixed 31 d", color: SERIES.calendar, rgb: "34 173 124", blurb: "a blind calendar — the M3 optimum" },
  naive: { label: "naive threshold", color: SERIES.naive, rgb: "226 99 58", blurb: "clean when the reading drops below the threshold" },
  guarded: { label: "guarded threshold", color: SERIES.naive, rgb: "226 99 58", dash: "5 4", blurb: "the naive rule, never twice in 7 days" },
  belief: { label: "Kalman belief", color: SERIES.belief, rgb: "74 148 236", blurb: "the threshold applied to the filtered belief" },
  ppo: { label: "PPO (trained)", color: SERIES.agent, rgb: "144 133 233", blurb: "the actual trained actor, run in your browser" },
};
const ORDER: PolicyId[] = ["never", "fixed", "naive", "guarded", "belief", "ppo"];
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

export function Simulate() {
  const { data } = useData("weather");
  const { data: ppo } = useData("ppo");
  const actor = ppo?.stages.find((s) => s.actor)?.actor;
  const [year, setYear] = useState(2023);
  const [noise, setNoise] = useState(3);
  const [threshold, setThreshold] = useState(0.93);
  const [selected, setSelected] = useState<PolicyId[]>(["naive", "belief", "ppo"]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const raf = useRef<number | null>(null);

  const runs = useMemo(() => {
    if (!data) return null;
    const out = {} as Record<PolicyId, ReturnType<typeof simulate>>;
    for (const id of ORDER) {
      if (id === "ppo" && !actor) continue;
      out[id] = simulate(data, year, id, noise / 100, threshold, 7, { actor });
    }
    return out;
  }, [data, actor, year, noise, threshold]);

  const n = runs?.never.n ?? 365;

  useEffect(() => {
    if (!playing) return;
    const start = performance.now();
    const from = cursor ?? 0;
    const step = (now: number) => {
      const d = Math.min(n - 1, from + Math.floor((now - start) / 40));
      setCursor(d);
      if (d < n - 1) raf.current = requestAnimationFrame(step);
      else setPlaying(false);
    };
    raf.current = requestAnimationFrame(step);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, n]);

  const toggle = (id: PolicyId) =>
    setSelected((s) => (s.includes(id) ? (s.length > 1 ? s.filter((p) => p !== id) : s) : [...s, id]));

  const focus = selected[selected.length - 1];
  const focusRun = runs?.[focus];
  const day = cursor ?? n - 1;

  return (
    <PageShell
      accent={ACCENTS.calendar}
      eyebrow="04 · How it uses what it learnt"
      title="Run the plant yourself. Same physics, same rules, the same trained policy."
      lede={
        <>
          Choose policies, add sensor noise, move the threshold. Every curve is computed live in your browser by the same port of the engine
          the acceptance harness verifies, and the PPO line is the trained actor&apos;s own forward pass — trained with exact readings, which
          is why noise hurts it too.
        </>
      }
    >
      <Panel
        title="Soiling ratio through a held-out year, by policy"
        subtitle="ticks along the base are cleans · faint vertical lines are rain washes · the horizontal line is the threshold"
        controls={
          <>
            <Slider label="noise" value={noise} min={0} max={10} step={1} onChange={setNoise} format={(v) => `${v}%`} />
            <Slider label="threshold" value={threshold} min={0.88} max={0.98} step={0.01} onChange={setThreshold} format={(v) => v.toFixed(2)} />
            <Chips label="year" value={year} onChange={setYear} options={(data?.meta.holdout_years ?? [2023, 2024, 2025]).map((y) => ({ value: y, label: String(y) }))} />
          </>
        }
        footer={
          <>
            Net = energy × the MBR phase-5 tariff (1.6953 ¢/kWh) − $60 per clean. Held-out years, storm soiling, one noise seed; the archival
            figures on the Verdict page use 120 episodes per cell. The PPO actor was trained on exact readings, so with noise it inherits the
            naive rule&apos;s chatter — set the noise to 0% to see the policy it actually learnt.
          </>
        }
      >
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="policies to compare">
          {ORDER.map((id) => {
            const meta = POLICY_META[id];
            const on = selected.includes(id);
            const disabled = id === "ppo" && !actor;
            return (
              <button
                key={id}
                onClick={() => !disabled && toggle(id)}
                aria-pressed={on}
                disabled={disabled}
                title={meta.blurb}
                className={`chip flex items-center gap-2 ${disabled ? "opacity-40" : ""}`}
                style={{ "--accent": meta.color, "--accent-rgb": meta.rgb } as CSSProperties}
              >
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: meta.color, opacity: on ? 1 : 0.5 }} />
                {meta.label}
              </button>
            );
          })}
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr]">
          <div>
            {runs ? (
              <Frame height={320} label="Soiling ratio through the year under each selected policy" margin={{ top: 10, right: 16, bottom: 36, left: 48 }}>
                {({ width, height }) => {
                  const x = scaleLinear().domain([0, n - 1]).range([0, width]);
                  const lo = Math.min(...selected.flatMap((id) => runs[id]?.tTrue ?? [1]));
                  const y = scaleLinear().domain([Math.max(0.6, lo - 0.02), 1.005]).range([height, 0]);
                  const monthStarts = Array.from({ length: 12 }, (_, m) => Math.round((m / 12) * n));
                  return (
                    <>
                      <YAxis scale={y} x0={0} x1={width} format={(v) => v.toFixed(2)} ticks={4} />
                      <line x1={0} x2={width} y1={y(threshold)} y2={y(threshold)} stroke={SERIES.ink} opacity={0.2} />
                      {runs.never.rainDays.map((d) => (
                        <line key={`r${d}`} x1={x(d)} x2={x(d)} y1={0} y2={height} stroke={SERIES.belief} opacity={0.15} />
                      ))}
                      {selected.map((id) => {
                        const r = runs[id];
                        if (!r) return null;
                        const upto = cursor === null ? r.n : cursor + 1;
                        const path = d3line<number>()
                          .x((_, i) => x(i))
                          .y((v) => y(v))
                          .curve(curveMonotoneX)(r.tTrue.slice(0, upto));
                        const meta = POLICY_META[id];
                        return (
                          <g key={id}>
                            <path d={path ?? ""} fill="none" stroke={meta.color} strokeWidth={id === focus ? 2.2 : 1.4} strokeDasharray={meta.dash} opacity={id === focus ? 1 : 0.7} />
                            {r.cleanDays
                              .filter((d) => d < upto)
                              .map((d) => (
                                <line key={d} x1={x(d)} x2={x(d)} y1={height - 8} y2={height} stroke={meta.color} strokeWidth={1.5} />
                              ))}
                          </g>
                        );
                      })}
                      {cursor !== null && <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={height} stroke={SERIES.ink} opacity={0.5} />}
                      <XAxis scale={x} y={height} values={monthStarts} format={(v) => MONTHS[Math.round((v / n) * 12) % 12]} />
                    </>
                  );
                }}
              </Frame>
            ) : (
              <Skeleton height={320} />
            )}
            <Legend>
              {selected.map((id) => (
                <Key key={id} color={POLICY_META[id].color} dash={Boolean(POLICY_META[id].dash)}>
                  {POLICY_META[id].label}
                </Key>
              ))}
            </Legend>
          </div>

          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs text-ink-3">
                the array under <span className="text-ink-2">{POLICY_META[focus].label}</span>, day {day + 1}
              </p>
              <button
                onClick={() => {
                  if (playing) {
                    setPlaying(false);
                  } else {
                    setCursor(0);
                    setPlaying(true);
                  }
                }}
                className="btn shrink-0 whitespace-nowrap"
              >
                {playing ? "■ stop" : "▶ replay year"}
              </button>
            </div>
            <ArrayStrip soiling={focusRun ? 1 - focusRun.tTrue[day] : 0} washing={focusRun ? focusRun.rainDays.includes(day) || focusRun.cleanDays.includes(day) : false} />
            <table className="mono mt-4 w-full text-xs">
              <thead className="text-ink-3">
                <tr>
                  <th className="py-1 text-left font-normal">policy</th>
                  <th className="py-1 text-right font-normal">net $/MWp</th>
                  <th className="py-1 text-right font-normal">cleans</th>
                  <th className="py-1 text-right font-normal">loss</th>
                </tr>
              </thead>
              <tbody>
                {runs &&
                  ORDER.filter((id) => runs[id])
                    .sort((a, b) => runs[b].net - runs[a].net)
                    .map((id) => (
                      <tr key={id} className={`border-t border-white/5 ${selected.includes(id) ? "text-ink-2" : "text-ink-3"}`}>
                        <td className="py-1.5">
                          <span className="mr-2 inline-block h-2 w-2 rounded-full align-middle" style={{ background: POLICY_META[id].color }} />
                          {POLICY_META[id].label}
                        </td>
                        <td className="py-1.5 text-right text-ink">{usd(runs[id].net)}</td>
                        <td className="py-1.5 text-right">{runs[id].cleans}</td>
                        <td className="py-1.5 text-right">{runs[id].lossPct.toFixed(1)}%</td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </div>
      </Panel>

      <Note>
        Five rules and one learned policy share one simulator. The Kalman belief rule is the one the project recommends; the guarded rule is
        the cheapest alternative an operator would reach for first (never twice in seven days), and on the archival run filtering beats it by
        $25–1,317 depending on the noise. The PPO actor is the trained stage exported for the Learning page, verified against torch
        day-for-day by the acceptance harness.
      </Note>
    </PageShell>
  );
}

/** A strip of modules tinted by the soiling of the focused policy. */
function ArrayStrip({ soiling, washing }: { soiling: number; washing: boolean }) {
  const cells = 24;
  const t = Math.min(1, soiling / 0.3);
  return (
    <div className="glass-inset grid grid-cols-8 gap-1 p-2" role="img" aria-label={`array soiling ${(soiling * 100).toFixed(1)} percent`}>
      {Array.from({ length: cells }, (_, i) => {
        const jitter = ((i * 37) % 11) / 11;
        const film = t * (0.6 + 0.4 * jitter);
        return (
          <div
            key={i}
            className="aspect-[1/1.6] rounded-[3px] transition-colors duration-300"
            style={{
              background: `linear-gradient(180deg, rgba(184,132,71,${film * 0.9}) 0%, rgba(184,132,71,${film}) 100%), linear-gradient(135deg, #0d1424, #16223f)`,
              boxShadow: washing ? "0 0 0 1px rgba(57,135,229,0.8), 0 0 14px rgba(57,135,229,0.35)" : "inset 0 0 0 1px rgba(255,255,255,0.05)",
            }}
          />
        );
      })}
    </div>
  );
}
