"use client";

import { useEffect, type ReactNode } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

/**
 * Lenis smooth scrolling driven by the GSAP ticker, so ScrollTrigger timelines
 * and the scroll position advance in the same frame. Honours reduced motion by
 * not smoothing at all.
 */
export function SmoothScroll({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // `anchors` routes in-page links through Lenis; the initial hash (a shared
    // #section URL) is honoured explicitly, since the browser's own jump happens
    // before Lenis takes over the scroll position.
    const lenis = new Lenis({ autoRaf: false, lerp: 0.09, wheelMultiplier: 0.9, anchors: true });
    lenis.on("scroll", ScrollTrigger.update);
    if (window.location.hash) {
      const target = document.querySelector(window.location.hash);
      if (target) requestAnimationFrame(() => lenis.scrollTo(target as HTMLElement, { immediate: true }));
    }
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
    };
  }, []);
  return <>{children}</>;
}
