"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { PageNav } from "@/components/Nav";
import { ACCENTS, accentStyle, useGlow, type Accent } from "@/lib/theme";

export { ACCENTS, accentStyle, useGlow, type Accent };

/*
  One template for every page: header (eyebrow · title · lede), then a column
  of full-width panels and stat rows with one spacing scale. Each page sets an
  accent that every glass border, eyebrow dot, control and glow on that page
  picks up through CSS variables.
*/

export function PageShell({
  eyebrow,
  title,
  lede,
  accent,
  children,
}: {
  eyebrow: string;
  title: string;
  lede: ReactNode;
  accent: Accent;
  children: ReactNode;
}) {
  return (
    <main className="page mx-auto w-full max-w-6xl px-5 pb-16 pt-28 sm:px-8 sm:pt-32" style={accentStyle(accent)}>
      <header className="max-w-3xl">
        <p className="eyebrow mb-5">{eyebrow}</p>
        <h1 className="gradient-text text-3xl font-medium leading-[1.08] tracking-[-0.02em] sm:text-4xl md:text-5xl">{title}</h1>
        <p className="mt-5 text-base leading-relaxed text-ink-2 sm:text-lg">{lede}</p>
      </header>
      <div className="mt-10 space-y-6 sm:mt-12 sm:space-y-8">{children}</div>
      <PageNav />
    </main>
  );
}

/** Reveal on scroll: a small rise and fade, once. Reduced motion renders static. */
export function Reveal({
  children,
  delay = 0,
  className = "",
  as = "div",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  as?: "div" | "p" | "li";
}) {
  const reduce = useReducedMotion();
  const Tag = motion[as];
  return (
    <Tag
      className={className}
      initial={reduce ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -8% 0px" }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay }}
    >
      {children}
    </Tag>
  );
}

/** A frosted panel with a uniform header: title, subtitle, and controls on the right. */
export function Panel({
  title,
  subtitle,
  controls,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  controls?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const glow = useGlow();
  return (
    <Reveal>
      <section className="glass glass-hover p-5 sm:p-6" onMouseMove={glow}>
        <div className="mb-5 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <h2 className="text-base font-medium text-ink sm:text-lg">{title}</h2>
            {subtitle && <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-ink-3">{subtitle}</p>}
          </div>
          {controls && <div className="flex flex-wrap items-center gap-x-4 gap-y-2">{controls}</div>}
        </div>
        {children}
        {footer && <div className="mt-5 border-t border-white/10 pt-4 text-sm leading-relaxed text-ink-2">{footer}</div>}
      </section>
    </Reveal>
  );
}

/** A row of stat tiles: always four columns on desktop, two on phones. */
export function StatRow({ children }: { children: ReactNode }) {
  return (
    <Reveal>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{children}</div>
    </Reveal>
  );
}

export function Stat({
  label,
  value,
  unit,
  note,
  tone = "ink",
}: {
  label: string;
  value: string;
  unit?: string;
  note?: string;
  tone?: keyof typeof ACCENTS;
}) {
  const glow = useGlow();
  const accent = ACCENTS[tone];
  return (
    <div className="glass glass-hover flex flex-col p-4 sm:p-5" style={accentStyle(accent)} onMouseMove={glow}>
      <p className="eyebrow mb-3">{label}</p>
      <p className="hero-figure stat-figure text-2xl leading-none sm:text-3xl" style={{ color: tone === "ink" ? "var(--color-ink)" : accent.hex }}>
        {value}
        {unit && <span className="ml-1 text-sm text-ink-3">{unit}</span>}
      </p>
      {note && <p className="mt-2 text-xs leading-snug text-ink-3">{note}</p>}
    </div>
  );
}

/** A closing paragraph under a page's panels, same width and voice everywhere. */
export function Note({ children }: { children: ReactNode }) {
  return (
    <Reveal>
      <p className="max-w-3xl border-l-2 pl-5 text-sm leading-relaxed text-ink-3" style={{ borderColor: "rgba(var(--accent-rgb) / 0.5)" }}>
        {children}
      </p>
    </Reveal>
  );
}

/** Radio-style chip group used by every control on the site. */
export function Chips<T extends string | number>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)} className="chip">
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format: (v: number) => string;
}) {
  return (
    <label className="mono flex items-center gap-2 text-xs text-ink-2">
      {label}
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label={label} />
      <span className="w-10 accent-text">{format(value)}</span>
    </label>
  );
}

/** Colour swatch + label, the legend key used by every chart. */
export function Key({ color, children, dash }: { color: string; children: ReactNode; dash?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-ink-2">
      {dash ? (
        <svg width="14" height="6" aria-hidden>
          <line x1="0" y1="3" x2="14" y2="3" stroke={color} strokeWidth="2" strokeDasharray="4 3" />
        </svg>
      ) : (
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color, boxShadow: `0 0 10px ${color}66` }} aria-hidden />
      )}
      {children}
    </span>
  );
}

export function Legend({ children }: { children: ReactNode }) {
  return <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1">{children}</div>;
}

/** An inner tile inside a panel (rows, recommendations, near misses). */
export function Tile({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`glass-inset p-4 ${className}`}>{children}</div>;
}

export const SERIES = {
  belief: "#4a94ec",
  naive: "#e2633a",
  agent: "#9085e9",
  truth: "#c98500",
  calendar: "#22ad7c",
  ink: "#f4eee4",
  ink2: "#bcb3a6",
  ink3: "#8d8578",
  sand: "#e8ad5c",
} as const;

export const Skeleton = ({ height }: { height: number }) => <div className="animate-pulse rounded-xl bg-white/5" style={{ height }} />;
