"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useReducedMotion } from "framer-motion";
import { useData, usd } from "@/lib/data";
import { simulate } from "@/lib/physics/rimal";
import type { SceneFrame } from "@/scenes/DustScene";
import { PAGES } from "@/components/Nav";
import { Reveal, Stat, StatRow } from "@/components/ui";

const DustScene = dynamic(() => import("@/scenes/DustScene").then((m) => m.DustScene), { ssr: false });

const HERO_YEAR = 2024; // the stormiest held-out year
const DAYS_PER_SECOND = 9;

const CAPTIONS = [
  { at: 0.0, eyebrow: "Seih Al-Dahal · 24.75°N 55.35°E", text: "Ten years of measured weather from NASA POWER. The dust you see is that day's aerosol optical depth; the array soils at the rate the storm model computes." },
  { at: 0.2, eyebrow: "Deposition", text: "Dust settles on the glass at 0.14–0.33 % of transmission a day — DEWA's own measurement — and faster when the air is thick with it." },
  { at: 0.45, eyebrow: "Shamal", text: "A storm can deposit a whole cleaning cycle's worth of soiling overnight. That tail is where the risk lives, and the first model clipped it away." },
  { at: 0.66, eyebrow: "Rain", text: "Six millimetres in a day washes the array clean. The plant never sees soiling directly — only a noisy performance ratio, confounded by the sky." },
  { at: 0.86, eyebrow: "The finding", text: "Four hypotheses about where a learning agent beats a rule. All four negative. The hard part is state estimation, not control." },
];

let webglSupport: boolean | null = null;
function readWebgl(): boolean {
  if (webglSupport === null) {
    try {
      const canvas = document.createElement("canvas");
      webglSupport = Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
    } catch {
      webglSupport = false;
    }
  }
  return webglSupport;
}
const noop = () => () => {};

export function Home() {
  const { data } = useData("weather");
  const { data: r } = useData("results");
  const reduce = useReducedMotion();
  const webglAvailable = useSyncExternalStore(noop, readWebgl, () => false);
  const [webglLost, setWebglLost] = useState(false);
  // Mount the WebGL scene only after the first paint: the headline and the
  // static fallback render immediately, three.js arrives a moment later.
  const [sceneReady, setSceneReady] = useState(false);
  useEffect(() => {
    const ric = typeof window.requestIdleCallback === "function" ? window.requestIdleCallback.bind(window) : null;
    if (ric) {
      const handle = ric(() => setSceneReady(true), { timeout: 600 });
      return () => window.cancelIdleCallback(handle);
    }
    const handle = setTimeout(() => setSceneReady(true), 250);
    return () => clearTimeout(handle);
  }, []);
  const frame = useRef<SceneFrame>({ density: 0.25, soiling: 0, wind: 2, wash: 0 });
  const [day, setDay] = useState(0);
  const [playing, setPlaying] = useState(true);
  const holder = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);

  const year = useMemo(() => {
    if (!data) return null;
    const sim = simulate(data, HERO_YEAR, "never", 0, 0.93, 0);
    const all = Object.values(data.years).flatMap((y) => y.aod);
    const aodHigh = all.slice().sort((a, b) => a - b)[Math.floor(all.length * 0.995)];
    return { sim, aodHigh, washes: new Set(sim.rainDays), y: data.years[String(HERO_YEAR)] };
  }, [data]);

  // Pause the scene when the hero is off screen.
  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.05 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Advance the year; write the day's physics into the scene's frame.
  useEffect(() => {
    if (!year) return;
    const n = year.sim.n;
    const write = (d: number) => {
      if (year.y.aod[d] === undefined) return;
      frame.current.density = Math.min(1, year.y.aod[d] / year.aodHigh);
      frame.current.soiling = 1 - year.sim.tTrue[d];
      frame.current.wind = year.y.wind[d];
      let wash = 0;
      for (let back = 0; back <= 5; back++) {
        if (year.washes.has(d - back)) {
          wash = 1 - back / 6;
          break;
        }
      }
      frame.current.wash = wash;
    };
    write(day);
    if (!playing || reduce || !visible) return;
    const start = performance.now();
    const from = day;
    let handle = 0;
    const tick = (now: number) => {
      const d = (from + Math.floor(((now - start) / 1000) * DAYS_PER_SECOND)) % n;
      setDay(d);
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, playing, reduce, visible]);

  const n = year?.sim.n ?? 366;
  const at = Math.min(Math.max(0, day), n - 1); // day and data are independent state; never index past the year
  const progress = at / (n - 1);
  const caption = CAPTIONS.reduce((acc, c, i) => (progress >= c.at ? i : acc), 0);
  const date = new Date(Date.UTC(HERO_YEAR, 0, 1 + at)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const aod = year?.y.aod[at] ?? 0;
  const soilingPct = year ? (1 - (year.sim.tTrue[at] ?? 1)) * 100 : 0;
  const washing = year ? [0, 1, 2].some((b) => year.washes.has(at - b)) : false;
  const particles = typeof window !== "undefined" && window.innerWidth < 768 ? 4000 : 12000;
  const showScene = sceneReady && webglAvailable && !webglLost && !reduce;

  return (
    <main>
      <div ref={holder} className="relative min-h-[92svh] overflow-hidden">
        {showScene ? (
          <DustScene frame={frame} particles={particles} active={visible} onContextLost={() => setWebglLost(true)} />
        ) : (
          <div className="absolute inset-0" style={{ background: "radial-gradient(120% 70% at 50% 100%, rgba(138,90,43,0.35) 0%, rgba(15,13,10,0) 60%), #0f0d0a" }} />
        )}
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(15,13,10,0.7)_0%,rgba(15,13,10,0)_40%,rgba(15,13,10,0)_60%,rgba(15,13,10,0.85)_100%)]" />

        <div className="relative mx-auto flex min-h-[92svh] w-full max-w-6xl flex-col justify-between px-5 pb-6 pt-28 sm:px-8 sm:pt-32">
          <div className="max-w-2xl">
            <h1 className="hero-figure rise text-6xl font-medium text-ink sm:text-8xl">RIMAL</h1>
            <p className="rise rise-2 mt-3 max-w-xl text-base leading-relaxed text-ink-2 sm:text-lg">
              <span className="text-ink">R</span>isk-aware <span className="text-ink">I</span>ntelligent <span className="text-ink">M</span>aintenance under{" "}
              <span className="text-ink">A</span>eolian <span className="text-ink">L</span>oading — <span className="text-sand">رمال</span>, sands. A
              reinforcement-learning benchmark for cleaning a desert solar plant, calibrated to Dubai&apos;s MBR Solar Park — and what four
              learning agents actually learnt.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-[1.15fr_0.85fr] md:items-end">
            <div className="glass p-5 sm:p-6">
              <div className="mb-3 flex flex-wrap gap-1" role="tablist" aria-label="chapters of the year">
                {CAPTIONS.map((c, i) => (
                  <button
                    key={c.eyebrow}
                    role="tab"
                    aria-selected={caption === i}
                    onClick={() => {
                      setDay(Math.round(c.at * (n - 1)));
                      setPlaying(false);
                    }}
                    className={`h-1.5 flex-1 rounded-full transition ${caption === i ? "bg-sand" : "bg-white/10 hover:bg-white/20"}`}
                    aria-label={c.eyebrow}
                  />
                ))}
              </div>
              <p className="eyebrow mb-2">{CAPTIONS[caption].eyebrow}</p>
              <p className={`min-h-[4.5rem] text-base leading-relaxed sm:text-lg ${caption === CAPTIONS.length - 1 ? "text-ink" : "text-ink-2"}`}>{CAPTIONS[caption].text}</p>
            </div>
            <div className="glass mono p-4 text-xs text-ink-2">
              <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                <span>
                  <span className="text-ink-3">day </span>
                  <span className="text-ink">{date}</span>
                </span>
                <span>
                  <span className="text-ink-3">AOD₅₅₀ </span>
                  <span className="text-sand">{aod.toFixed(2)}</span>
                </span>
                <span>
                  <span className="text-ink-3">soiling </span>
                  <span className="text-truth">{soilingPct.toFixed(1)}%</span>
                </span>
                <span className={`rounded-full px-2 py-0.5 ${washing ? "bg-belief/20 text-belief" : "text-ink-3"}`}>{washing ? "rain wash" : "uncleaned"}</span>
              </div>
              <div className="mt-3 flex items-center gap-3">
                <button
                  onClick={() => setPlaying((p) => !p)}
                  className="rounded-full bg-sand px-3 py-1 text-surface transition hover:brightness-110"
                  aria-label={playing ? "pause the year" : "play the year"}
                >
                  {playing ? "❚❚" : "▶"}
                </button>
                <input
                  type="range"
                  min={0}
                  max={n - 1}
                  value={at}
                  onChange={(e) => {
                    setPlaying(false);
                    setDay(Number(e.target.value));
                  }}
                  aria-label="day of the year"
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-6xl px-5 py-16 sm:px-8 sm:py-24">
        <Reveal>
          <p className="eyebrow mb-4">The result</p>
          <p className="max-w-4xl text-2xl leading-snug text-ink sm:text-4xl">
            We built a simulator calibrated to DEWA&apos;s own field measurements, reproduced the published cleaning-interval optimum as
            a falsification gate, then tested four hypotheses about where adaptive control beats a well-tuned rule.{" "}
            <span className="text-sand">Deep RL did not beat the rule on any of them.</span> The value was somewhere else: a Kalman filter cut
            soiling-estimate error {r ? `${r.m5.rmse_reduction}×` : "17.7×"}.
          </p>
        </Reveal>
        <div className="mt-10">
          <StatRow>
            <Stat label="milestones" value="8" note="M0–M7, each with declared acceptance criteria" />
            <Stat label="hypotheses tested" value="4" note="all negative for deep RL" tone="naive" />
            <Stat label="estimate error" value={r ? `${r.m5.rmse_reduction}×` : "—"} note="lower with a Kalman filter" tone="belief" />
            <Stat label="tuned rule" value={r ? usd(r.m4.threshold_net) : "—"} unit="/MWp/yr" note="beat every learned agent" tone="truth" />
          </StatRow>
        </div>

        <Reveal>
          <p className="eyebrow mb-4 mt-16">Read it in order</p>
        </Reveal>
        <Reveal>
          <ol className="grid gap-3 md:grid-cols-2">
            {PAGES.filter((p) => p.href !== "/").map((p, i, all) => (
              <li key={p.href} className={i === all.length - 1 ? "md:col-span-2" : ""}>
                <Link href={p.href} prefetch={false} className="glass block h-full p-5 transition hover:bg-white/[0.07]">
                  <p className="mono text-xs text-sand">{p.label.split(" · ")[0]}</p>
                  <p className="mt-1 text-lg text-ink">{p.label.split(" · ")[1]}</p>
                  <p className="mt-1 text-sm text-ink-3">{BLURBS[p.href]}</p>
                </Link>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </main>
  );
}

const BLURBS: Record<string, string> = {
  "/calibrated": "The simulator had to reproduce the literature before any agent was trained.",
  "/detects": "The plant sees a noisy performance ratio; a Kalman filter recovers the hidden soiling.",
  "/learnt": "PPO's decision surface, the fleet estimator and QR-DQN's return distribution — real, and each lost.",
  "/simulate": "Run the physics, the rules and the trained policy live.",
  "/verdict": "Four hypotheses, four results, and what we would tell DEWA.",
  "/errors": "Seven defects that changed a result, and two near-misses.",
  "/reproduce": "A clean clone reproduces the record from an empty cache.",
};
