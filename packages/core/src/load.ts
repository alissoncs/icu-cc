/** Training load maths: NP, IF, TSS and the Performance Management Chart. [COG19] */
import type { FitnessPoint } from "./types";

export const ROLLING_WINDOW_S = 30;
export const CTL_TAU_DAYS = 42;
export const ATL_TAU_DAYS = 7;

export function round1(x: number): number {
  return Math.round(x * 10) / 10;
}

/** Normalized Power: 30 s rolling mean, 4th power, average, 4th root. [COG19] */
export function normalizedPower(watts: number[], sampleRateHz = 1.0): number {
  if (watts.length === 0) return 0;
  const window = Math.max(Math.trunc(ROLLING_WINDOW_S * sampleRateHz), 1);
  const sum = (a: number[]) => a.reduce((s, v) => s + v, 0);
  if (watts.length < window) return sum(watts) / watts.length;

  const rolling: number[] = [];
  let running = sum(watts.slice(0, window));
  rolling.push(running / window);
  for (let i = window; i < watts.length; i++) {
    running += (watts[i] as number) - (watts[i - window] as number);
    rolling.push(running / window);
  }
  const fourth = rolling.reduce((s, v) => s + v ** 4, 0) / rolling.length;
  return fourth ** 0.25;
}

export function intensityFactor(npW: number, ftpW: number): number {
  return ftpW ? npW / ftpW : 0;
}

/** TSS = (s x NP x IF) / (FTP x 3600) x 100. [COG19] */
export function trainingStressScore(durationS: number, npW: number, ftpW: number): number {
  if (ftpW <= 0) return 0;
  const intensity = npW / ftpW;
  return ((durationS * npW * intensity) / (ftpW * 3600)) * 100;
}

/** NP/average power. Near 1.0 is steady; >1.15 is a stochastic or badly paced ride. */
export function variabilityIndex(npW: number, avgW: number): number {
  return avgW ? npW / avgW : 0;
}

/**
 * Normalized Power per heartbeat. Rising over weeks at matched intensity = aerobic
 * fitness improving; it is only comparable within similar session types.
 */
export function efficiencyFactor(npW: number, avgHr: number): number {
  return avgHr ? npW / avgHr : 0;
}

// --- ISO date helpers (UTC-safe; no local-timezone Date arithmetic) ----------------

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})/;
const DAY_MS = 86_400_000;

export function parseIsoDay(iso: string): number {
  const m = ISO_DAY.exec(iso);
  if (!m) throw new Error(`Not an ISO date: ${iso}`);
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

export function formatIsoDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function addDays(iso: string, days: number): string {
  return formatIsoDay(parseIsoDay(iso) + days * DAY_MS);
}

export interface PmcOptions {
  ctlTau?: number;
  atlTau?: number;
  ctlSeed?: number;
  atlSeed?: number;
}

/**
 * Performance Management Chart over a continuous daily series.
 *
 * CTL (fitness) is a 42-day exponentially weighted average of daily load, ATL (fatigue)
 * a 7-day one. TSB (form) is the previous day's CTL minus ATL, which is the convention
 * Intervals.icu and TrainingPeaks both use — today's ride should not flatter today's
 * form.
 *
 * Gaps in `dailyLoad` (keyed YYYY-MM-DD) are filled with zero-load rest days, since decay
 * is the whole point of the model.
 */
export function pmc(dailyLoad: Record<string, number>, opts: PmcOptions = {}): FitnessPoint[] {
  const days = Object.keys(dailyLoad).sort();
  if (days.length === 0) return [];
  const { ctlTau = CTL_TAU_DAYS, atlTau = ATL_TAU_DAYS, ctlSeed = 0, atlSeed = 0 } = opts;

  const start = parseIsoDay(days[0] as string);
  const end = parseIsoDay(days[days.length - 1] as string);
  const ctlK = 1 - Math.exp(-1 / ctlTau);
  const atlK = 1 - Math.exp(-1 / atlTau);

  let ctl = ctlSeed;
  let atl = atlSeed;
  const out: FitnessPoint[] = [];
  for (let t = start; t <= end; t += DAY_MS) {
    const date = formatIsoDay(t);
    const load = Number(dailyLoad[date] ?? 0);
    const tsb = ctl - atl; // yesterday's values, before applying today's load
    ctl += (load - ctl) * ctlK;
    atl += (load - atl) * atlK;
    out.push({ date, load, ctl: round1(ctl), atl: round1(atl), tsb: round1(tsb) });
  }
  return out;
}

/**
 * Change in CTL over the last N days — TSS/day gained per week.
 * Sustained ramp above ~5-7 is where injury and illness risk climbs for most athletes.
 */
export function rampRate(points: FitnessPoint[], days = 7): number {
  if (points.length < days + 1) return 0;
  const last = points[points.length - 1] as FitnessPoint;
  const prev = points[points.length - 1 - days] as FitnessPoint;
  return round1(last.ctl - prev.ctl);
}

/**
 * Foster's monotony (mean/SD of daily load) and strain (weekly load x monotony).
 * High monotony — every day the same — is associated with worse adaptation and higher
 * illness risk than the same total load with real hard/easy separation.
 */
export function monotonyAndStrain(loads: number[]): [number, number] {
  if (loads.length < 2) return [0, 0];
  const total = loads.reduce((s, v) => s + v, 0);
  const mean = total / loads.length;
  const variance = loads.reduce((s, x) => s + (x - mean) ** 2, 0) / (loads.length - 1);
  const sd = Math.sqrt(variance);
  if (sd === 0) return [0, 0];
  const monotony = mean / sd;
  return [Math.round(monotony * 100) / 100, Math.round(total * monotony)];
}

/** Plain-language reading of TSB. Bands are conventional, not from a trial. */
export function formLabel(tsb: number): string {
  if (tsb > 25) return "very fresh (detraining risk if held)";
  if (tsb > 5) return "fresh / race-ready";
  if (tsb >= -10) return "neutral";
  if (tsb >= -30) return "productive training load";
  return "high fatigue — recovery needed";
}
