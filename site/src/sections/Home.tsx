"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useReducedMotion } from "framer-motion";
import { useData, usd } from "@/lib/data";
import { simulate } from "@/lib/physics/rimal";
import type { SceneFrame } from "@/scenes/DustScene";
import { PAGES } from "@/components/Nav";
import { ACCENTS, accentStyle, Reveal, Stat, StatRow, useGlow } from "@/components/ui";

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

const BLURBS: Record<string, string> = {
  "/calibrated": "The simulator had to reproduce the literature before any agent was trained.",
  "/detects": "The plant sees a noisy performance ratio; a Kalman filter recovers the hidden soiling.",
  "/learnt": "PPO's decision surface, the fleet estimator and QR-DQN's return distribution — real, and each lost.",
  "/simulate": "Run the physics, the rules and the trained policy live.",
  "/verdict": "Four hypotheses, four results, and what we would tell DEWA.",
  "/errors": "Seven defects that changed a result, and two near-misses.",
  "/reproduce": "A clean clone reproduces the record from an empty cache.",
};

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
  const glow = useGlow();
  const webglAvailable = useSyncExternalStore(noop, readWebgl, () => false);
  const [webglLost, setWebglLost] = useState(false);
  const [sceneReady, setSceneReady] = useState(false);
  const frame = useRef<SceneFrame>({ density: 0.25, soiling: 0, wind: 2, wash: 0 });
  const [day, setDay] = useState(0);
  const [playing, setPlaying] = useState(true);
  const holder = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);

  // Mount the WebGL scene only after the first paint: the headline and the
  // static fallback render immediately, three.js arrives a moment later.
  useEffect(() => {
    const ric = typeof window.requestIdleCallback === "function" ? window.requestIdleCallback.bind(window) : null;
    if (ric) {
      const handle = ric(() => setSceneReady(true), { timeout: 600 });
      return () => window.cancelIdleCallback(handle);
    }
    const handle = setTimeout(() => setSceneReady(true), 250);
    return () => clearTimeout(handle);
  }, []);

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
    <main className="page" style={accentStyle(ACCENTS.sand)}>
      <div ref={holder} className="relative min-h-[92svh] overflow-hidden">
        {showScene ? (
          <DustScene frame={frame} particles={particles} onContextLost={() => setWebglLost(true)} />
        ) : (
          <div className="absolute inset-0" style={{ background: "radial-gradient(55% 40% at 8% 0%, rgba(232,173,92,0.22), transparent 60%), radial-gradient(50% 40% at 100% 40%, rgba(74,148,236,0.18), transparent 60%), radial-gradient(120% 70% at 50% 100%, rgba(154,100,51,0.4) 0%, rgba(10,9,16,0) 60%), #0a0910" }} />
        )}
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(10,9,16,0.55)_0%,rgba(10,9,16,0)_35%,rgba(10,9,16,0)_72%,#0b0a13_100%)]" />

        <div className="relative mx-auto flex min-h-[92svh] w-full max-w-6xl flex-col justify-between px-5 pb-6 pt-28 sm:px-8 sm:pt-32">
          <div className="max-w-2xl">
            <p className="eyebrow rise mb-5">Reinforcement learning · photovoltaic cleaning · Dubai</p>
            <h1 className="hero-figure rise gradient-text text-6xl font-medium sm:text-8xl">RIMAL</h1>
            <p className="rise rise-2 mt-4 max-w-xl text-base leading-relaxed text-ink-2 sm:text-lg">
              <span className="text-ink">R</span>isk-aware <span className="text-ink">I</span>ntelligent <span className="text-ink">M</span>aintenance under{" "}
              <span className="text-ink">A</span>eolian <span className="text-ink">L</span>oading — <span className="text-sand">رمال</span>, sands. A
              reinforcement-learning benchmark for cleaning a desert solar plant, calibrated to Dubai&apos;s MBR Solar Park — and what four
              learning agents actually learnt.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-[1.15fr_0.85fr] md:items-end">
            <div className="glass glass-hover p-5 sm:p-6" onMouseMove={glow}>
              <div className="mb-4 flex flex-wrap gap-1.5" role="tablist" aria-label="chapters of the year">
                {CAPTIONS.map((c, i) => (
                  <button
                    key={c.eyebrow}
                    role="tab"
                    aria-selected={caption === i}
                    onClick={() => {
                      setDay(Math.round(c.at * (n - 1)));
                      setPlaying(false);
                    }}
                    className={`h-1.5 flex-1 rounded-full transition ${caption === i ? "bg-sand shadow-[0_0_14px_rgba(232,173,92,0.8)]" : "bg-white/10 hover:bg-white/25"}`}
                    aria-label={c.eyebrow}
                  />
                ))}
              </div>
              <p className="eyebrow mb-2">{CAPTIONS[caption].eyebrow}</p>
              <p className={`min-h-[4.5rem] text-base leading-relaxed sm:text-lg ${caption === CAPTIONS.length - 1 ? "text-ink" : "text-ink-2"}`}>{CAPTIONS[caption].text}</p>
            </div>
            <div className="glass glass-hover mono p-4 text-xs text-ink-2" onMouseMove={glow}>
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
                <span className={`rounded-full px-2 py-0.5 ${washing ? "bg-belief/20 text-belief shadow-[0_0_14px_rgba(74,148,236,0.5)]" : "text-ink-3"}`}>{washing ? "rain wash" : "uncleaned"}</span>
              </div>
              <div className="mt-3 flex items-center gap-3">
                <button onClick={() => setPlaying((p) => !p)} className="btn" aria-label={playing ? "pause the year" : "play the year"}>
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
          <p className="eyebrow mb-5">The result</p>
          <p className="max-w-4xl text-2xl leading-snug text-ink sm:text-4xl">
            We built a simulator calibrated to DEWA&apos;s own field measurements, reproduced the published cleaning-interval optimum as a
            falsification gate, then tested four hypotheses about where adaptive control beats a well-tuned rule.{" "}
            <span className="gradient-text">Deep RL did not beat the rule on any of them.</span> The value was somewhere else: a Kalman filter cut
            soiling-estimate error <span className="text-belief">{r ? `${r.m5.rmse_reduction}×` : "17.7×"}</span>.
          </p>
        </Reveal>
        <div className="mt-10">
          <StatRow>
            <Stat label="milestones" value="8" note="M0–M7, each with declared acceptance criteria" tone="sand" />
            <Stat label="hypotheses tested" value="4" note="all negative for deep RL" tone="naive" />
            <Stat label="estimate error" value={r ? `${r.m5.rmse_reduction}×` : "—"} note="lower with a Kalman filter" tone="belief" />
            <Stat label="tuned rule" value={r ? usd(r.m4.threshold_net) : "—"} unit="/MWp/yr" note="beat every learned agent" tone="truth" />
          </StatRow>
        </div>

        <Reveal>
          <p className="eyebrow mb-5 mt-16">Read it in order</p>
          <ol className="grid gap-3 md:grid-cols-2">
            {PAGES.filter((p) => p.href !== "/").map((p, i, all) => (
              <li key={p.href} className={i === all.length - 1 ? "md:col-span-2" : ""}>
                <Link
                  href={p.href}
                  prefetch={false}
                  className="glass glass-hover block h-full p-5 sm:p-6"
                  style={accentStyle(p.accent)}
                  onMouseMove={glow}
                >
                  <p className="eyebrow mb-3">{p.label.split(" · ")[0]}</p>
                  <p className="text-xl text-ink">{p.label.split(" · ")[1]}</p>
                  <p className="mt-1 text-sm leading-relaxed text-ink-3">{BLURBS[p.href]}</p>
                  <p className="accent-text mt-4 text-sm">Open →</p>
                </Link>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </main>
  );
}
