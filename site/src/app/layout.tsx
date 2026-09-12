import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { SmoothScroll } from "@/components/SmoothScroll";
import { Nav } from "@/components/Nav";

const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "RIMAL — Risk-aware Intelligent Maintenance under Aeolian Loading",
  description:
    "A reinforcement-learning benchmark for photovoltaic cleaning in desert conditions, calibrated to Dubai's MBR Solar Park. Four hypotheses about where adaptive control beats a rule — and what the agents actually learnt.",
  metadataBase: new URL("https://rimal.vercel.app"),
  openGraph: {
    title: "RIMAL — state estimation, not control",
    description:
      "Deep RL did not beat a well-tuned rule on any of four hypotheses. The finding that transfers: a Kalman filter cut soiling-estimate error 17.7×.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#0f0d0a",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body className="grain">
        <div className="ambient" aria-hidden>
          <span className="orb" />
        </div>
        <SmoothScroll>
          <Nav />
          {children}
          <footer className="page mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-5 pb-10 text-xs text-ink-3 sm:px-8">
            <p>RIMAL · calibrated to DEWA&apos;s published field measurements and ten years of NASA POWER data for Seih Al-Dahal · built and evaluated on one laptop, at zero cost.</p>
            <p>MIT licence.</p>
          </footer>
        </SmoothScroll>
      </body>
    </html>
  );
}
