"use client";

import { useEffect, useState } from "react";

/*
  Types for public/data/*.json — the contract with scripts/export_site_data.py.
  The site has no numbers of its own; if a field is not here, it is not shown.
*/

export interface WeatherYear {
  aod: number[];
  rain: number[];
  clean: number[];
  k: number[];
  temp: number[];
  wind: number[];
}

export interface Weather {
  meta: {
    site: string;
    latitude: number;
    longitude: number;
    aod_reference: number;
    soiling_rate_mid: number;
    assumed_rate: number;
    obs_scales: { aod: number; temp: number; wind: number; max_days: number };
    rate_band: [number, number];
    storm_exponent: number;
    max_daily_rate: number;
    rain_wash_mm: number;
    grace_days: number;
    max_soiling: number;
    price_usd_per_kwh: number;
    clean_cost_usd_per_mwp: number;
    train_years: number[];
    holdout_years: number[];
  };
  years: Record<string, WeatherYear>;
}

export interface Gate {
  intervals: number[];
  costs: { cost: number; optimum: number; analytic: number; net: number }[];
  curves: Record<string, number[]>;
  published_optimum_days: [number, number];
  plateau_days: [number, number];
  default_cost: number;
}

export interface Actor {
  activation: "tanh";
  layers: { w: number[][]; b: number[] }[];
  normaliser: { mean: number[]; var: number[] };
  obs_layout: string[];
}

export interface PpoStage {
  label: string;
  step: number;
  fraction: number;
  surface: { ratios: number[]; days: number[]; p_clean: number[][] };
  rollout: { year: number; ratio: number[]; p_clean: number[]; cleaned: number[]; net: number; cleans: number };
  holdout_net: number;
  holdout_cleans: number;
  actor?: Actor;
}

export interface Ppo {
  timesteps: number;
  seed: number;
  threshold_rule_net: number;
  threshold: number;
  learning_curve: { timesteps: number[]; episode_return: number[] };
  stages: PpoStage[];
}

export interface FleetDay {
  ratio: number;
  observed: number;
  belief: number;
  robot: number;
  efficacy: number;
  estimates: number[];
  health: number[];
  cost: number;
}

export interface Fleet {
  year: number;
  threshold: number;
  robots: { name: string; nominal: number; cooldown_days: number; wear_per_use: number }[];
  efficacy_band: [number, number];
  days: FleetDay[];
}

export interface QrdqnDay {
  ratio: number;
  observed: number;
  aod: number;
  quantiles: [number[], number[]];
  choice: Record<string, number>;
}

export interface Qrdqn {
  timesteps: number;
  seed: number;
  year: number;
  quantile_taus: number[];
  reward_scale: number;
  days: QrdqnDay[];
  alpha_table: { alpha: number; mean: number; cvar5: number; episodes: number }[];
}

export interface Results {
  generated_from: string;
  m0: { checks: number };
  m1: { checks: number; yield_min: number; yield_max: number; kimber_rate: number; aod_rate: number; never_clean_loss_pct: number };
  m3: {
    checks: number;
    threshold_net: number;
    threshold_cleans: number;
    never_clean_net: number;
    always_clean_net: number;
    closed_form_gap_pct: number;
    plateau: [number, number];
  };
  m4: { checks: number; ppo_mean: number; ppo_sd: number; threshold_net: number; fixed_net: number; margin_over_fixed: number; ppo_cleans: number };
  m5: {
    rmse_belief: number;
    rmse_raw: number;
    rmse_reduction: number;
    exact_net: number;
    collapse_usd: number;
    noise: { noise: number; naive: number; naive_cleans: number; guarded: number; belief: number; belief_cleans: number; fixed: number }[];
    ppo_belief_net: number;
    ppo_belief_sd: number;
    ppo_memoryless_net: number;
    ppo_memoryless_sd: number;
    ppo_gap: number;
    ppo_p: number;
    belief_rule_net: number;
    declared_failed: string;
  };
  m6: {
    partial_cleaning_cost: number;
    perfect_assumption_min: number;
    perfect_assumption_max: number;
    partial_paired_mean: number;
    partial_paired_sem: number;
    partial_p: number;
    dispatch_paired_mean: number;
    dispatch_paired_sem: number;
    dispatch_losses: number[];
    dispatch_cleans: number[];
    spearman: number;
    wear30_pct: number;
    ppo_mean: number;
    ppo_sd: number;
    rule_net: number;
    ppo_seeds: { net: number; cleans: number }[];
  };
  m7: {
    clipping_overstated_cvar: number;
    mean_optimal_threshold: number;
    cvar_optimal_threshold: number;
    cvar_gain: number;
    mean_cost: number;
    water_cost: number;
    water_cost_pct: number;
    alpha_table: { alpha: number; mean: number; cvar5: number }[];
    rule_cvar: number;
    rule_mean: number;
    agent_cvar: number;
    agent_margin: number;
    agent_sd: number;
  };
}

export type DataName = "weather" | "gate" | "ppo" | "fleet" | "qrdqn" | "results";
type DataOf<N extends DataName> = N extends "weather"
  ? Weather
  : N extends "gate"
    ? Gate
    : N extends "ppo"
      ? Ppo
      : N extends "fleet"
        ? Fleet
        : N extends "qrdqn"
          ? Qrdqn
          : Results;

const cache = new Map<DataName, Promise<unknown>>();

export function loadData<N extends DataName>(name: N): Promise<DataOf<N>> {
  if (!cache.has(name)) {
    cache.set(
      name,
      fetch(`/data/${name}.json`).then((response) => {
        if (!response.ok) throw new Error(`could not load ${name}.json (${response.status})`);
        return response.json();
      }),
    );
  }
  return cache.get(name) as Promise<DataOf<N>>;
}

/** Load one data file once; `null` until it arrives, `error` if it never does. */
export function useData<N extends DataName>(name: N): { data: DataOf<N> | null; error: Error | null } {
  const [data, setData] = useState<DataOf<N> | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    let alive = true;
    loadData(name)
      .then((value) => alive && setData(value))
      .catch((err: Error) => alive && setError(err));
    return () => {
      alive = false;
    };
  }, [name]);
  return { data, error };
}

export const usd = (value: number, digits = 0) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits }).format(value);

export const fmt = (value: number, digits = 0) =>
  new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
