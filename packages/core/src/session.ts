/**
 * Single-session analysis.
 *
 * `normalize` is deliberately tolerant about field names: Intervals.icu, Strava-style
 * and hand-written shapes all map onto the same canonical keys.
 */
import { classifyDistribution } from "./distribution";
import { efficiencyFactor, intensityFactor, trainingStressScore, variabilityIndex } from "./load";
import type { ActivityAnalysis, Seiler3, ZoneTime } from "./types";
import { POWER_ZONES, collapseToSeiler } from "./zones";

/** Aerobic decoupling (Pw:Hr) bands. Conventional coaching thresholds, not from a trial. */
export const DECOUPLING_GOOD = 5.0;
export const DECOUPLING_MODERATE = 10.0;

const ALIASES = {
  name: ["name", "activity_name", "title"],
  type: ["type", "activity_type", "sport"],
  date: ["start_date_local", "start_date", "date"],
  movingTimeS: ["moving_time", "moving_time_s", "duration", "elapsed_time"],
  avgPowerW: ["icu_average_watts", "average_watts", "avg_power", "average_power"],
  npW: ["icu_weighted_avg_watts", "weighted_average_watts", "normalized_power", "np"],
  avgHr: ["average_heartrate", "avg_hr", "average_hr"],
  maxHr: ["max_heartrate", "max_hr"],
  tss: ["icu_training_load", "training_load", "tss"],
  if: ["icu_intensity", "intensity_factor", "if"],
  ftpW: ["icu_ftp", "ftp"],
  decouplingPct: ["icu_power_hr", "decoupling", "pw_hr"],
  distanceM: ["distance", "distance_m"],
  elevationM: ["total_elevation_gain", "elevation_gain", "elevation_m"],
  calories: ["calories", "icu_calories"],
  zoneTimes: ["icu_zone_times", "zone_times", "power_zone_times"],
  tempC: ["average_temp", "temperature", "temp_c"],
} as const;

type Raw = Record<string, unknown>;

function pick(raw: Raw, key: keyof typeof ALIASES): unknown {
  for (const alias of ALIASES[key]) {
    const v = raw[alias];
    if (v !== undefined && v !== null) return v;
  }
  return null;
}

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Accept either {"Z1": 1200, ...} or Intervals.icu's list-of-dicts form. */
function parseZoneTimes(value: unknown): Record<string, number> {
  if (!value) return {};
  const out: Record<string, number> = {};
  if (Array.isArray(value)) {
    value.forEach((item, i) => {
      if (item && typeof item === "object") {
        const o = item as Raw;
        const key = String(o.id || o.zone || `Z${i + 1}`);
        out[key] = Number(o.secs || o.seconds || 0) || 0;
      } else {
        out[`Z${i + 1}`] = Number(item || 0) || 0;
      }
    });
    return out;
  }
  if (typeof value === "object") {
    for (const [k, v] of Object.entries(value as Raw)) out[String(k)] = Number(v || 0) || 0;
  }
  return out;
}

export interface NormalizedActivity {
  name: string;
  type: string;
  date: string | null;
  movingTimeS: number | null;
  avgPowerW: number | null;
  npW: number | null;
  avgHr: number | null;
  maxHr: number | null;
  tss: number | null;
  /** Intensity factor as a fraction (0.86), whichever unit the source used. */
  if: number | null;
  ftpW: number | null;
  decouplingPct: number | null;
  distanceM: number | null;
  elevationM: number | null;
  calories: number | null;
  zoneTimes: Record<string, number>;
  tempC: number | null;
}

/** Map an activity object from any of the common shapes onto canonical keys. */
export function normalize(raw: Raw): NormalizedActivity {
  let ifv = num(pick(raw, "if"));
  // Intervals.icu reports icu_intensity as a percentage (86), not a fraction (0.86).
  if (ifv !== null && ifv > 3) ifv = ifv / 100;
  const date = pick(raw, "date");
  return {
    name: String(pick(raw, "name") || "unnamed activity"),
    type: String(pick(raw, "type") || "Ride"),
    date: date ? String(date) : null,
    movingTimeS: num(pick(raw, "movingTimeS")),
    avgPowerW: num(pick(raw, "avgPowerW")),
    npW: num(pick(raw, "npW")),
    avgHr: num(pick(raw, "avgHr")),
    maxHr: num(pick(raw, "maxHr")),
    tss: num(pick(raw, "tss")),
    if: ifv,
    ftpW: num(pick(raw, "ftpW")),
    decouplingPct: num(pick(raw, "decouplingPct")),
    distanceM: num(pick(raw, "distanceM")),
    elevationM: num(pick(raw, "elevationM")),
    calories: num(pick(raw, "calories")),
    zoneTimes: parseZoneTimes(pick(raw, "zoneTimes")),
    tempC: num(pick(raw, "tempC")),
  };
}

/** Zone times joined with their wattage ranges, for display. Always all seven zones. */
export function zoneTimeTable(zoneTimes: Record<string, number>, ftpW: number): ZoneTime[] {
  const upper: Record<string, number> = {};
  for (const [k, v] of Object.entries(zoneTimes)) upper[k.toUpperCase()] = (upper[k.toUpperCase()] ?? 0) + v;
  const total = POWER_ZONES.reduce((s, z) => s + (upper[z.key] ?? 0), 0);
  return POWER_ZONES.map((z) => {
    const seconds = upper[z.key] ?? 0;
    return {
      zone: z.key,
      name: z.name,
      lowW: Math.round(ftpW * z.low),
      highW: z.high !== null ? Math.round(ftpW * z.high) : null,
      seconds,
      pct: total > 0 ? Math.round((seconds / total) * 1000) / 10 : 0,
    };
  });
}

/** Seiler 3-zone summary of Coggan zone seconds; null when there is no zone data. */
export function seiler3Summary(zoneTimes: Record<string, number>): Seiler3 | null {
  const b = collapseToSeiler(zoneTimes);
  const total = b[1] + b[2] + b[3];
  if (total <= 0) return null;
  const r1 = (x: number) => Math.round(x * 10) / 10;
  return {
    lowPct: r1((b[1] / total) * 100),
    moderatePct: r1((b[2] / total) * 100),
    highPct: r1((b[3] / total) * 100),
  };
}

/**
 * Turn one activity into structured, quotable findings. Derives anything the source did
 * not provide (IF, TSS, VI, EF) and records what was missing so the narrative can be
 * honest about its gaps. `ftpFallbackW` is used when the activity carries no FTP.
 */
export function analyzeActivity(raw: Raw, ftpFallbackW: number, id?: string): ActivityAnalysis {
  const a = normalize(raw);
  const missing: string[] = [];
  const findings: string[] = [];
  const warnings: string[] = [];

  const durationS = a.movingTimeS ?? 0;
  const durationH = durationS / 3600;
  const ftp = a.ftpW || ftpFallbackW;
  if (a.ftpW && Math.abs(a.ftpW - ftpFallbackW) > 5) {
    warnings.push(
      `The activity was recorded against FTP ${a.ftpW.toFixed(0)} W but the profile FTP ` +
        `is ${ftpFallbackW.toFixed(0)} W. Load numbers below use ${ftp.toFixed(0)} W.`,
    );
  }

  const npW = a.npW;
  const avgW = a.avgPowerW;
  const avgHr = a.avgHr;
  if (npW === null && avgW === null) missing.push("power data");
  if (avgHr === null) missing.push("heart rate");

  let ifv = a.if;
  if (ifv === null && npW) ifv = Math.round(intensityFactor(npW, ftp) * 1000) / 1000;
  let tss = a.tss;
  if (tss === null && npW && durationS) tss = Math.round(trainingStressScore(durationS, npW, ftp) * 10) / 10;

  const vi = npW && avgW ? Math.round(variabilityIndex(npW, avgW) * 1000) / 1000 : null;
  const ef = npW && avgHr ? Math.round(efficiencyFactor(npW, avgHr) * 100) / 100 : null;
  const kj = avgW && durationS ? Math.round((avgW * durationS) / 1000) : null;

  // --- Interpretation --------------------------------------------------------
  if (ifv !== null) {
    const f = ifv.toFixed(2);
    if (ifv < 0.6) {
      findings.push(`IF ${f} — recovery intensity. Its job is blood flow, not stimulus; resist the urge to make it 'count'.`);
    } else if (ifv < 0.75) {
      findings.push(`IF ${f} — true endurance riding, the zone that should make up the bulk of your week [SEI10].`);
    } else if (ifv < 0.85) {
      findings.push(
        `IF ${f} — tempo/sweet spot. Productive in a build block, but this is also the intensity that quietly eats recovery days.`,
      );
    } else if (ifv < 0.95) {
      findings.push(`IF ${f} — threshold-level session. Costly; earn the rest.`);
    } else {
      findings.push(
        `IF ${f} — race or test effort. Anything sustained above 1.0 for this duration means FTP is probably understated.`,
      );
    }
    if (ifv >= 1.02 && durationH >= 0.6) {
      warnings.push(
        `IF ${f} held for ${durationH.toFixed(1)} h is above threshold by definition — retest FTP, it looks stale.`,
      );
    }
  }

  if (vi !== null) {
    const f = vi.toFixed(2);
    if (vi < 1.05) findings.push(`VI ${f} — very steady. Reads as a trainer ride or a flat TT.`);
    else if (vi < 1.15) findings.push(`VI ${f} — normal road variability.`);
    else
      findings.push(
        `VI ${f} — highly stochastic. Either terrain, a group ride, or surging pacing. On a solo effort this is wasted matches.`,
      );
  }

  const dec = a.decouplingPct;
  if (dec !== null) {
    if (dec <= DECOUPLING_GOOD) {
      findings.push(
        `Aerobic decoupling ${dec.toFixed(1)}% — under ${DECOUPLING_GOOD.toFixed(0)}%, so you held output per heartbeat to the end. Good aerobic durability for this duration.`,
      );
    } else if (dec <= DECOUPLING_MODERATE) {
      findings.push(
        `Aerobic decoupling ${dec.toFixed(1)}% — moderate drift. Common when the ride sits at the edge of your current durability, or in heat.`,
      );
    } else {
      findings.push(`Aerobic decoupling ${dec.toFixed(1)}% — significant drift.`);
      warnings.push(
        `Decoupling of ${dec.toFixed(1)}% usually means one of: underfueling, heat, starting too hard, or a duration beyond current aerobic durability.`,
      );
    }
  }

  if (ef !== null) {
    findings.push(
      `Efficiency factor ${ef.toFixed(2)} W/bpm. Only meaningful as a trend against similar sessions — compare it to your last few rides of this type.`,
    );
  }

  if (tss !== null && durationH) {
    findings.push(`${tss.toFixed(0)} TSS over ${durationH.toFixed(1)} h (${(tss / durationH).toFixed(0)} TSS/h).`);
  }

  // --- Intensity distribution within the session -----------------------------
  const zoneTimes = a.zoneTimes;
  const zones3 = seiler3Summary(zoneTimes);
  if (zones3) {
    const dist = classifyDistribution(zoneTimes);
    findings.push(
      `Time in zone: ${dist.lowPct.toFixed(0)}% low / ${dist.moderatePct.toFixed(0)}% moderate / ${dist.highPct.toFixed(0)}% high (Seiler 3-zone) [SEI10].`,
    );
    if (dist.moderatePct > 40 && (ifv ?? 0) < 0.85) {
      warnings.push(
        `${dist.moderatePct.toFixed(0)}% of this ride sat in the tempo/threshold band on what was not a hard session — classic black-hole drift [SEI10].`,
      );
    }
  } else {
    missing.push("time-in-zone");
  }

  warnings.push("Zone boundaries are estimates from FTP, a field proxy for LT2 [JAM20]; treat them as soft.");
  if (missing.length) warnings.push(`Missing from the data: ${missing.join(", ")}. Findings are partial.`);

  const r = (x: number | null, d: number) => (x ? Math.round(x * 10 ** d) / 10 ** d : null);
  return {
    summary: {
      id: id ?? String(raw.id ?? ""),
      date: a.date ? a.date.slice(0, 10) : "",
      name: a.name,
      type: a.type,
      durationS,
      tss: r(tss, 1),
      npW: r(npW, 0),
      avgPowerW: r(avgW, 0),
      intensityFactor: r(ifv, 3),
      avgHr: r(avgHr, 0),
    },
    ftpW: ftp,
    variabilityIndex: vi,
    efficiencyFactor: ef,
    decouplingPct: dec !== null ? Math.round(dec * 10) / 10 : null,
    kj,
    distanceKm: a.distanceM ? Math.round(a.distanceM / 100) / 10 : null,
    elevationM: r(a.elevationM, 0),
    zones7: zoneTimeTable(zoneTimes, ftp),
    zones3,
    findings,
    warnings,
  };
}
