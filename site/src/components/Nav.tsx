"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const PAGES = [
  { href: "/", label: "Overview", short: "Overview" },
  { href: "/calibrated", label: "01 · Calibration", short: "Calibration" },
  { href: "/detects", label: "02 · Detection", short: "Detection" },
  { href: "/learnt", label: "03 · Learning", short: "Learning" },
  { href: "/simulate", label: "04 · Simulator", short: "Simulator" },
  { href: "/verdict", label: "05 · Verdict", short: "Verdict" },
  { href: "/errors", label: "06 · Errors", short: "Errors" },
  { href: "/reproduce", label: "07 · Reproduce", short: "Reproduce" },
] as const;

export function Nav() {
  const pathname = usePathname();
  const current = pathname.replace(/\/$/, "") || "/";
  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <div className="glass mx-auto mt-3 flex max-w-6xl items-center gap-4 rounded-2xl px-4 py-2 sm:px-5">
        <Link href="/" prefetch={false} className="hero-figure shrink-0 text-xl text-ink" aria-label="RIMAL overview">
          RIMAL
        </Link>
        <nav className="-mx-1 flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto px-1 [scrollbar-width:none]" aria-label="Pages">
          {PAGES.map((p) => {
            const active = current === p.href;
            return (
              <Link
                key={p.href}
                href={p.href}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                className={`mono shrink-0 rounded-full px-3 py-1.5 text-[11px] tracking-wide transition sm:text-xs ${
                  active ? "bg-sand text-surface" : "text-ink-2 hover:bg-white/10 hover:text-ink"
                }`}
              >
                {p.short}
              </Link>
            );
          })}
        </nav>
        <a
          href="https://github.com/KartikJoshi23/Self-Learning-Agent"
          target="_blank"
          rel="noreferrer"
          className="mono hidden shrink-0 text-xs text-ink-3 transition hover:text-ink lg:inline"
        >
          GitHub ↗
        </a>
      </div>
    </header>
  );
}

/** Previous / next page links, at the foot of every page. */
export function PageNav() {
  const pathname = usePathname();
  const current = pathname.replace(/\/$/, "") || "/";
  const i = PAGES.findIndex((p) => p.href === current);
  const prev = i > 0 ? PAGES[i - 1] : null;
  const next = i >= 0 && i < PAGES.length - 1 ? PAGES[i + 1] : null;
  return (
    <div className="mt-16 flex items-center justify-between border-t border-white/5 pt-6 text-sm">
      {prev ? (
        <Link href={prev.href} prefetch={false} className="text-ink-2 transition hover:text-ink">
          ← {prev.label}
        </Link>
      ) : (
        <span />
      )}
      {next ? (
        <Link href={next.href} prefetch={false} className="text-ink transition hover:text-sand">
          {next.label} →
        </Link>
      ) : (
        <span />
      )}
    </div>
  );
}
