/**
 * RIMAL physics, ported from `rimal/` for the browser.
 *
 * This is the same port that ships in `web/simulator.html`, lifted into an ES
 * module so the site and the node harness share one implementation. It is
 * verified against the Python engine by `scripts/verify_simulator.py
 * --module site/src/lib/physics/rimal.js`: soiling trajectory, rain-wash days,
 * energy, and the exact cleaning days of every decision rule below — including
 * the trained PPO actor, whose forward pass here is checked against torch.
 *
 * Nothing in this file is tuned for the site. Constants are asserted equal to
 * the engine's by the harness; data comes from `public/data/weather.json`,
 * written by `scripts/export_site_data.py`.
 */

export const PRICE = 0.016953; // USD/kWh, MBR phase-5 PPA tariff
export const CLEAN_COST = 60.0; // USD per MWp per pass (calibrated, see M3)
export const RAIN_THRESHOLD = 6.0; // mm/day that washes the array
export const GRACE = 14; // days the surface stays clean after a wash
export const MAX_SOILING = 0.3; // cap on accumulated loss
export const STORM_EXP = 2.0; // superlinear deposition in dust
export const MAX_RATE = 0.07; // one cleaning cycle of soiling in a day

/** Deterministic PRNG so replays are reproducible. */
export function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function gauss(rng) {
  let u = 0;
  let v = 0;
  while (!u) u = rng();
  while (!v) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** Storm soiling: rate scales with (AOD / climatology)^2, capped at a storm day. */
export const dailyRate = (aod, meta) =>
  Math.min(MAX_RATE, meta.soiling_rate_mid * Math.pow(aod / meta.aod_reference, STORM_EXP));

/**
 * energy(ratio) = clean * ratio * (1 + k * (1 - ratio)). A soiled array clips
 * less against the inverter and runs cooler, so it beats linear scaling; k is
 * fitted per day from the pvlib table (p95 error 0.056%).
 */
export const energyAt = (clean, k, ratio) => clean * ratio * (1 + k * (1 - ratio));

/** Kalman filter over soiling loss — the M5 belief. Matches rimal.env.observation. */
export class Kalman {
  constructor() {
    this.q = 0.0008 * 0.0008;
    this.reset();
  }
  reset() {
    this.loss = 0;
    this.v = 1e-6;
    this.grace = 0;
  }
  resetEvent(grace) {
    this.loss = 0;
    this.v = 1e-8;
    this.grace = grace ? GRACE : 0;
  }
  predict(rate) {
    if (this.grace > 0) {
      this.grace--;
      return;
    }
    this.loss = Math.min(this.loss + rate, MAX_SOILING);
    this.v += this.q;
  }
  update(obs, std) {
    const z = 1 - obs;
    const r = Math.max(std * std, 1e-12);
    const k = this.v / (this.v + r);
    this.loss = Math.max(0, this.loss + k * (z - this.loss));
    this.v = (1 - k) * this.v;
  }
  get ratio() {
    return 1 - this.loss;
  }
}

/**
 * The trained PPO actor: a tanh MLP on the standardised observation, greedy.
 * `actor` is the object exported in ppo.json (layers, normaliser, obs layout).
 */
export function ppoAction(actor, obs) {
  const { mean, var: variance } = actor.normaliser;
  let x = obs.map((v, i) => (v - mean[i]) / Math.sqrt(variance[i] + 1e-8));
  actor.layers.forEach((layer, index) => {
    const out = layer.w.map((row, j) => row.reduce((acc, w, i) => acc + w * x[i], layer.b[j]));
    x = index < actor.layers.length - 1 ? out.map(Math.tanh) : out;
  });
  return x[1] > x[0] ? 1 : 0;
}

/** Policy ids the simulator understands. */
export const POLICIES = ['never', 'fixed', 'naive', 'guarded', 'belief', 'ppo'];

/**
 * Run one calendar year of one policy.
 *
 * @param data      the weather.json object ({meta, years})
 * @param year      calendar year present in data.years
 * @param policy    one of POLICIES
 * @param noiseStd  relative observation noise (0 = exact reading)
 * @param threshold cleaning threshold for naive/guarded/belief
 * @param seed      PRNG seed for the observation noise
 * @param opts      { fixedDays=31, guardDays=7, actor (for 'ppo'), referenceYears }
 */
export function simulate(data, year, policy, noiseStd, threshold, seed = 0, opts = {}) {
  const meta = data.meta;
  const y = data.years[String(year)];
  const n = y.aod.length;
  const rng = mulberry32(seed + year * 7919);
  const fixedDays = opts.fixedDays ?? 31;
  const guardDays = opts.guardDays ?? 7;
  const scales = meta.obs_scales ?? { aod: 3.5, temp: 50.0, wind: 12.0, max_days: 365 };

  // The engine's noise reference is the median clean day over every year the
  // environment holds — the held-out three unless told otherwise.
  const refYears = opts.referenceYears ?? meta.holdout_years ?? [year];
  const refPool = refYears.flatMap((yy) => data.years[String(yy)]?.clean ?? []);
  const sorted = [...refPool].sort((a, b) => a - b);
  const refClean = sorted[Math.floor(sorted.length / 2)];

  let loss = 0;
  let grace = 0;
  let energy = 0;
  let cleanEnergy = 0;
  let cost = 0;
  let cleans = 0;
  let rainWashes = 0;
  const kf = new Kalman();
  let cleanedLast = false;
  let rainLast = 0;
  let sinceFixed = 0;
  let sinceGuard = 10_000;
  let sinceClean = 0; // the environment's days-since-cleaning feature

  const tTrue = [];
  const tObs = [];
  const tBelief = [];
  const tStd = [];
  const tBeliefStd = []; // the filter's own uncertainty (sqrt of its variance)
  const cleanDays = [];
  const rainDays = [];
  const pClean = [];

  for (let i = 0; i < n; i++) {
    const ratio = 1 - loss;
    const scale = Math.min(4, Math.max(1, Math.sqrt(refClean / Math.max(y.clean[i], 1e-9))));
    const std = noiseStd * scale;
    const obs = noiseStd > 0 ? Math.min(1.3, Math.max(0.3, ratio * (1 + gauss(rng) * std))) : ratio;

    // Belief update: the filter reacts to YESTERDAY's rain, matching the env,
    // and propagates the constant assumed rate an operator would use.
    if (rainLast > RAIN_THRESHOLD) kf.resetEvent(true);
    else if (cleanedLast) kf.resetEvent(false);
    else if (i > 0) kf.predict(meta.assumed_rate ?? meta.soiling_rate_mid);
    kf.update(obs, Math.max(std, 1e-3));
    rainLast = y.rain[i];

    let clean = false;
    if (policy === 'never') clean = false;
    else if (policy === 'fixed') {
      if (i > 0 && ++sinceFixed >= fixedDays) {
        sinceFixed = 0;
        clean = true;
      }
    } else if (policy === 'naive') clean = obs < threshold;
    else if (policy === 'guarded') {
      sinceGuard += 1;
      if (obs < threshold && sinceGuard >= guardDays) {
        sinceGuard = 0;
        clean = true;
      }
    } else if (policy === 'belief') clean = kf.ratio < threshold;
    else if (policy === 'ppo') {
      if (!opts.actor) throw new Error("policy 'ppo' needs opts.actor from ppo.json");
      const angle = (2 * Math.PI * (i + 1)) / 365.25;
      const feature = [
        obs,
        sinceClean / scales.max_days,
        y.aod[i] / scales.aod,
        (y.temp?.[i] ?? 0) / scales.temp,
        (y.wind?.[i] ?? 0) / scales.wind,
        Math.sin(angle),
        Math.cos(angle),
      ];
      clean = ppoAction(opts.actor, feature) === 1;
    } else throw new Error(`unknown policy ${policy}`);

    if (clean) {
      loss = 0;
      cleans++;
      cost += CLEAN_COST;
      cleanDays.push(i);
      sinceClean = 0;
    } else {
      sinceClean += 1;
    }
    cleanedLast = clean;

    const nowRatio = 1 - loss;
    energy += energyAt(y.clean[i], y.k[i], nowRatio);
    cleanEnergy += y.clean[i];

    tTrue.push(nowRatio);
    tObs.push(obs);
    tBelief.push(kf.ratio);
    tStd.push(std);
    tBeliefStd.push(Math.sqrt(kf.v));
    pClean.push(clean ? 1 : 0);

    // Tomorrow's soiling: rain washes, grace holds, otherwise dust accumulates.
    if (y.rain[i] > RAIN_THRESHOLD) {
      loss = 0;
      grace = GRACE;
      rainDays.push(i);
      rainWashes++;
    } else if (grace > 0) grace--;
    else loss = Math.min(loss + dailyRate(y.aod[i], meta), MAX_SOILING);
  }

  const revenue = energy * PRICE;
  return {
    year,
    policy,
    n,
    tTrue,
    tObs,
    tBelief,
    tStd,
    tBeliefStd,
    cleanDays,
    rainDays,
    cleans,
    rainWashes,
    energy,
    cleanEnergy,
    cost,
    revenue,
    net: revenue - cost,
    lossPct: (100 * (cleanEnergy - energy)) / cleanEnergy,
  };
}
