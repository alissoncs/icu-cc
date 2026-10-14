import type { ActivitySummary, AthleteInfo } from "@icu/core";

type Raw = Record<string, unknown>;

const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

export function mapAthlete(raw: Raw): AthleteInfo {
  const settings = Array.isArray(raw.sportSettings) ? (raw.sportSettings as Raw[]) : [];
  const ride = settings.find((s) => Array.isArray(s.types) && (s.types as unknown[]).includes("Ride"));
  const ftp = num(ride?.ftp);
  const name =
    (typeof raw.name === "string" && raw.name) ||
    [raw.firstname, raw.lastname].filter((x) => typeof x === "string" && x).join(" ") ||
    "Athlete";
  return {
    name,
    ftpW: ftp,
    weightKg: num(raw.icu_weight),
    ftpSource: ftp !== null ? "intervals" : "fallback",
  };
}

export function mapActivity(raw: Raw): ActivitySummary {
  const np = num(raw.icu_weighted_avg_watts);
  const ftp = num(raw.icu_ftp);
  let ifac = num(raw.icu_intensity);
  if (ifac !== null) {
    // Percent (86.0) in some payloads, fraction (0.86) in others.
    if (ifac > 3) ifac /= 100;
  } else if (np !== null && ftp) {
    ifac = np / ftp;
  }
  return {
    id: String(raw.id ?? ""),
    date: String(raw.start_date_local ?? raw.start_date ?? "").slice(0, 10),
    name: typeof raw.name === "string" ? raw.name : "",
    type: typeof raw.type === "string" ? raw.type : "Other",
    durationS: num(raw.moving_time) ?? num(raw.elapsed_time) ?? 0,
    tss: num(raw.icu_training_load),
    npW: np,
    avgPowerW: num(raw.icu_average_watts),
    intensityFactor: ifac === null ? null : round(ifac, 3),
    avgHr: num(raw.average_heartrate),
  };
}

export function mapWellness(rows: Raw[]): { date: string; ctl: number; atl: number; load: number }[] {
  const out: { date: string; ctl: number; atl: number; load: number }[] = [];
  for (const r of rows) {
    const ctl = num(r.ctl);
    const atl = num(r.atl);
    if (ctl === null || atl === null || typeof r.id !== "string") continue;
    out.push({ date: r.id.slice(0, 10), ctl, atl, load: num(r.ctlLoad) ?? num(r.atlLoad) ?? 0 });
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}
