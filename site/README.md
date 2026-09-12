# RIMAL — the site

A static Next.js site for the project: eight pages, one nav bar, and no numbers of its own.

Every figure, curve and animation is driven by `public/data/*.json`, written by
`../scripts/export_site_data.py` from the engine and from the acceptance logs in
`../results/`. The physics that runs live in the browser is `src/lib/physics/rimal.js`,
verified against the Python engine by `../scripts/verify_simulator.py --module`.

## Pages

| Route | What it shows |
|---|---|
| `/` | WebGL hero: a dust field driven by real AOD, an array soiling at the storm model's rate; the result; the index |
| `/calibrated` | The falsification gate: net value vs cleaning interval, the 28–34 day band, the flat optimum |
| `/detects` | Hidden truth, noisy reading and Kalman belief, live, with a noise slider |
| `/learnt` | PPO's P(clean) surface across training, the fleet estimator converging, QR-DQN's quantile fans |
| `/simulate` | Six policies incl. the trained PPO actor, run live on held-out years |
| `/verdict` | Four hypotheses, the noise sweep, the DEWA recommendations |
| `/errors` | Seven defects, two near-misses, two checks that passed for the wrong reason |
| `/reproduce` | Commands, links, layout of the repository |

## Develop

```bash
npm install
npm run dev            # http://localhost:3000
npm run build          # static export to out/
node scripts/shoot.mjs http://localhost:3000 shots   # screenshot + error audit, desktop and mobile (needs Chrome)
```

## Regenerate the data

From the repository root, after any change to results or the engine:

```bash
python scripts/export_site_data.py                  # ~30 min CPU: trains one PPO and one QR-DQN seed
python scripts/verify_simulator.py --module site/src/lib/physics/rimal.js
```

`results.json` is parsed from `results/*.log` by regular expression; a number the
pattern cannot find is an error, not a default.

## Deploy

Vercel, framework Next.js, **root directory `site`**. The build is a pure static export
(`output: "export"`, `trailingSlash: true`): no server, no functions, nothing that costs money.
Any static host serves `out/`.

## Design system

A desert at night, lit from below. `src/app/globals.css` holds the tokens:

- **Colour field** — `.ambient`, a fixed layer of static radial gradients plus three slowly drifting
  orbs (amber, blue, violet); every glass panel frosts it. The home hero paints the same field
  inside the WebGL scene so its canvas can stay opaque.
- **Glass** — `.glass`: gradient background, `backdrop-filter: blur(22px) saturate(1.35)`, a
  gradient border drawn by a masked pseudo-element so it follows the radius, an inner top highlight
  and an accent-tinted shadow. `.glass-hover` adds lift, a brighter border and a cursor-following
  glow (`--mx/--my` written by `useGlow`).
- **Accents** — each page sets `--accent` / `--accent-rgb` (`src/lib/theme.ts`): calibration ochre,
  detection blue, learning violet, simulator aqua, verdict amber, errors orange, reproduce blue.
  Eyebrow dots, borders, chips, sliders, buttons, notes and the nav pill all read it.
- **Type** — Space Grotesk for display, IBM Plex Mono for numbers and controls; page titles are
  gradient text ending in the page accent.

## Stack

Next.js 16 · React 19 · Tailwind 4 · three.js via react-three-fiber (hero scene) · framer-motion
(reveals) · GSAP (registered; drives Lenis) · Lenis (smooth scroll) · D3 scales and shapes (charts as
React SVG). Chart series colours were validated for CVD separation and contrast against the site's
surface (`#0a0910`); colour follows the entity in every chart (belief = blue, naive = orange,
agent = violet, truth = ochre, calendar = aqua).
