"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { PageNav } from "@/components/Nav";

/*
  One template for every page: header (eyebrow · title · lede), then a column
  of full-width panels and stat rows with one spacing scale. Nothing on a page
  sits outside this shell, which is what keeps the pages uniform.
*/

export function PageShell({
  eyebrow,
  title,
  lede,
  children,
}: {
  eyebrow: string;
  title: string;
  lede: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-6xl px-5 pb-16 pt-28 sm:px-8 sm:pt-32">
      <header className="max-w-3xl">
        <p className="eyebrow mb-4">{eyebrow}</p>
        <h1 className="text-3xl font-medium leading-[1.08] tracking-[-0.02em] text-ink sm:text-4xl md:text-5xl">{title}</h1>
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
  return (
    <Reveal>
      <section className="glass p-5 sm:p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <h2 className="text-base font-medium text-ink">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
          </div>
          {controls && <div className="flex flex-wrap items-center gap-x-4 gap-y-2">{controls}</div>}
        </div>
        {children}
        {footer && <div className="mt-4 border-t border-white/5 pt-4 text-sm leading-relaxed text-ink-2">{footer}</div>}
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
  tone?: "ink" | "belief" | "naive" | "agent" | "truth" | "calendar" | "sand";
}) {
  const color = {
    ink: "text-ink",
    belief: "text-belief",
    naive: "text-naive",
    agent: "text-agent",
    truth: "text-truth",
    calendar: "text-calendar",
    sand: "text-sand",
  }[tone];
  return (
    <div className="glass flex flex-col p-4 sm:p-5">
      <p className="eyebrow mb-2">{label}</p>
      <p className={`hero-figure text-2xl leading-none sm:text-3xl ${color}`}>
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
      <p className="max-w-3xl text-sm leading-relaxed text-ink-3">{children}</p>
    </Reveal>
  );
}

/** Radio-style chip group used by every control on the site. */
export function Chips<T extends string | number>({
  options,
  value,
  onChange,
  label,
  tone = "sand",
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  tone?: "sand" | "agent";
}) {
  const on = tone === "sand" ? "bg-sand text-surface" : "bg-agent text-surface";
  return (
    <div className="flex flex-wrap gap-1" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`mono rounded-full px-2.5 py-1 text-xs transition ${value === o.value ? on : "bg-white/5 text-ink-2 hover:bg-white/10"}`}
        >
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
      <span className="w-10 text-ink">{format(value)}</span>
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
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} aria-hidden />
      )}
      {children}
    </span>
  );
}

export function Legend({ children }: { children: ReactNode }) {
  return <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1">{children}</div>;
}

export const SERIES = {
  belief: "#3987e5",
  naive: "#d95926",
  agent: "#9085e9",
  truth: "#c98500",
  calendar: "#199e70",
  ink: "#f2ebdf",
  ink2: "#b8ad9c",
  ink3: "#8a8072",
  sand: "#e0a458",
} as const;

export const Skeleton = ({ height }: { height: number }) => <div className="animate-pulse rounded-xl bg-white/5" style={{ height }} />;
