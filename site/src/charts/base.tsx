"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ScaleLinear } from "d3-scale";

/** Width of a container, tracked with ResizeObserver. */
export function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => setWidth(entries[0].contentRect.width));
    ro.observe(el);
    setWidth(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

export interface Margin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export const MARGIN: Margin = { top: 16, right: 20, bottom: 36, left: 56 };

/** Recessive horizontal gridlines + left axis labels. */
export function YAxis({
  scale,
  ticks = 5,
  format,
  x0,
  x1,
}: {
  scale: ScaleLinear<number, number>;
  ticks?: number;
  format: (v: number) => string;
  x0: number;
  x1: number;
}) {
  return (
    <g className="axis">
      {scale.ticks(ticks).map((t) => (
        <g key={t} transform={`translate(0,${scale(t)})`}>
          <line className="gridline" x1={x0} x2={x1} />
          <text x={x0 - 8} dy="0.32em" textAnchor="end">
            {format(t)}
          </text>
        </g>
      ))}
    </g>
  );
}

/** Bottom axis: a single baseline rule and labels. */
export function XAxis({
  scale,
  ticks = 6,
  format,
  y,
  values,
}: {
  scale: ScaleLinear<number, number>;
  ticks?: number;
  format: (v: number) => string;
  y: number;
  values?: number[];
}) {
  const tickValues = values ?? scale.ticks(ticks);
  const [d0, d1] = scale.range();
  return (
    <g className="axis" transform={`translate(0,${y})`}>
      <line x1={d0} x2={d1} />
      {tickValues.map((t) => (
        <text key={t} x={scale(t)} y={20} textAnchor="middle">
          {format(t)}
        </text>
      ))}
    </g>
  );
}

/** Chart frame: a responsive SVG with margins. */
export function Frame({
  height,
  margin = MARGIN,
  children,
  label,
  className = "",
}: {
  height: number;
  margin?: Margin;
  children: (inner: { width: number; height: number; margin: Margin }) => ReactNode;
  label: string;
  className?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const inner = { width: Math.max(0, width - margin.left - margin.right), height: height - margin.top - margin.bottom, margin };
  return (
    <div ref={ref} className={`w-full ${className}`}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={label} className="block overflow-visible">
          <g transform={`translate(${margin.left},${margin.top})`}>{children(inner)}</g>
        </svg>
      )}
    </div>
  );
}

/** A frosted tooltip positioned in chart space. */
export function Tip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  const flip = x > width * 0.7;
  return (
    <foreignObject x={flip ? x - 190 : x + 12} y={Math.max(0, y - 10)} width={180} height={120} style={{ pointerEvents: "none" }}>
      <div className="glass glass-strong mono rounded-xl px-3 py-2 text-[11px] leading-relaxed text-ink-2">{children}</div>
    </foreignObject>
  );
}
