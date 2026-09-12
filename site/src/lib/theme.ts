"use client";

import { useCallback, type CSSProperties, type MouseEvent } from "react";

/** Per-page / per-tone accents; every glass border, glow and control reads --accent. */
export type Accent = { hex: string; rgb: string };

export const ACCENTS = {
  sand: { hex: "#e8ad5c", rgb: "232 173 92" },
  truth: { hex: "#c98500", rgb: "201 133 0" },
  belief: { hex: "#4a94ec", rgb: "74 148 236" },
  agent: { hex: "#9085e9", rgb: "144 133 233" },
  calendar: { hex: "#22ad7c", rgb: "34 173 124" },
  naive: { hex: "#e2633a", rgb: "226 99 58" },
  ink: { hex: "#bcb3a6", rgb: "188 179 166" },
} as const satisfies Record<string, Accent>;

export function accentStyle(accent: Accent): CSSProperties {
  return { "--accent": accent.hex, "--accent-rgb": accent.rgb } as CSSProperties;
}

/** Writes the cursor position into --mx/--my so the glass glow can follow it. */
export function useGlow() {
  return useCallback((e: MouseEvent<HTMLElement>) => {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${((e.clientX - rect.left) / rect.width) * 100}%`);
    el.style.setProperty("--my", `${((e.clientY - rect.top) / rect.height) * 100}%`);
  }, []);
}
