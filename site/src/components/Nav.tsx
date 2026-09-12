"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ACCENTS, accentStyle, type Accent } from "@/lib/theme";

export const PAGES: readonly { href: string; label: string; short: string; accent: Accent }[] = [
  { href: "/", label: "Overview", short: "Overview", accent: ACCENTS.sand },
  { href: "/calibrated", label: "01 · Calibration", short: "Calibration", accent: ACCENTS.truth },
  { href: "/detects", label: "02 · Detection", short: "Detection", accent: ACCENTS.belief },
  { href: "/learnt", label: "03 · Learning", short: "Learning", accent: ACCENTS.agent },
  { href: "/simulate", label: "04 · Simulator", short: "Simulator", accent: ACCENTS.calendar },
  { href: "/verdict", label: "05 · Verdict", short: "Verdict", accent: ACCENTS.sand },
  { href: "/errors", label: "06 · Errors", short: "Errors", accent: ACCENTS.naive },
  { href: "/reproduce", label: "07 · Reproduce", short: "Reproduce", accent: ACCENTS.belief },
];

export function currentPage(pathname: string) {
  const current = pathname.replace(/\/$/, "") || "/";
  return PAGES.find((p) => p.href === current) ?? PAGES[0];
}

export function Nav() {
  const pathname = usePathname();
  const page = currentPage(pathname);
  return (
    <header className="fixed inset-x-0 top-0 z-50 px-3" style={accentStyle(page.accent)}>
      <div className="glass mx-auto mt-3 flex max-w-6xl items-center gap-4 !rounded-full px-3 py-2 sm:px-4">
        <Link href="/" prefetch={false} className="hero-figure shrink-0 pl-2 text-xl text-ink transition hover:text-sand" aria-label="RIMAL overview">
          RIMAL
        </Link>
        <nav className="-mx-1 flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-1 [scrollbar-width:none]" aria-label="Pages">
          {PAGES.map((p) => {
            const active = page.href === p.href;
            return (
              <Link
                key={p.href}
                href={p.href}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                className="chip shrink-0 !py-1.5 !text-[11px] tracking-wide sm:!text-xs"
                style={accentStyle(p.accent)}
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
          className="mono hidden shrink-0 pr-2 text-xs text-ink-3 transition hover:text-ink lg:inline"
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
  const i = PAGES.findIndex((p) => p.href === currentPage(pathname).href);
  const prev = i > 0 ? PAGES[i - 1] : null;
  const next = i >= 0 && i < PAGES.length - 1 ? PAGES[i + 1] : null;
  return (
    <div className="mt-16 grid gap-3 border-t border-white/10 pt-6 sm:grid-cols-2">
      {prev ? (
        <Link href={prev.href} prefetch={false} className="glass glass-hover block p-4 text-sm" style={accentStyle(prev.accent)}>
          <span className="mono text-[11px] text-ink-3">← previous</span>
          <span className="mt-1 block text-ink">{prev.label}</span>
        </Link>
      ) : (
        <span />
      )}
      {next ? (
        <Link href={next.href} prefetch={false} className="glass glass-hover block p-4 text-right text-sm" style={accentStyle(next.accent)}>
          <span className="mono text-[11px] text-ink-3">next →</span>
          <span className="mt-1 block text-ink">{next.label}</span>
        </Link>
      ) : (
        <span />
      )}
    </div>
  );
}
