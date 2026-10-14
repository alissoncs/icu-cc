/**
 * The contract between apps/api and apps/web, and the shapes packages/core produces.
 * Dates are ISO strings: `YYYY-MM-DD` for days, full ISO for timestamps. No Date objects
 * cross a package boundary, so there is no timezone to get wrong.
 */

export type ZoneKey = "Z1" | "Z2" | "Z3" | "Z4" | "Z5" | "Z6" | "Z7";

/** GET /api/athlete */
export interface AthleteInfo {
  name: string;
  ftpW: number | null;
  weightKg: number | null;
  /** Where ftpW came from, so the UI can say "from Intervals.icu". */
  ftpSource: "intervals" | "fallback";
}

/** One row of GET /api/activities */
export interface ActivitySummary {
  id: string;
  /** YYYY-MM-DD, local */
  date: string;
  name: string;
  type: string;
  durationS: number;
  tss: number | null;
  npW: number | null;
  avgPowerW: number | null;
  intensityFactor: number | null;
  avgHr: number | null;
}

export interface ZoneTime {
  zone: ZoneKey;
  name: string;
  /** Wattage range for the zone at the FTP used; highW null = open-ended. */
  lowW: number;
  highW: number | null;
  seconds: number;
  pct: number;
}

export interface Seiler3 {
  lowPct: number;
  moderatePct: number;
  highPct: number;
}

/** GET /api/activities/:id */
export interface ActivityAnalysis {
  summary: ActivitySummary;
  ftpW: number;
  variabilityIndex: number | null;
  efficiencyFactor: number | null;
  decouplingPct: number | null;
  kj: number | null;
  distanceKm: number | null;
  elevationM: number | null;
  zones7: ZoneTime[];
  zones3: Seiler3 | null;
  /** Plain-language reads, each tagged with its source where one applies, e.g. [SEI10]. */
  findings: string[];
  /** Data-quality and caution notes. These must be shown, never dropped. */
  warnings: string[];
}

/** One element of GET /api/fitness */
export interface FitnessPoint {
  date: string;
  ctl: number;
  atl: number;
  tsb: number;
  load: number;
}

/** GET /api/fitness */
export interface FitnessResponse {
  points: FitnessPoint[];
  /** CTL gained over the last 7 days. */
  rampRate: number;
  formLabel: string;
  /** "intervals" = CTL/ATL read from Intervals wellness; "computed" = derived from loads. */
  source: "intervals" | "computed";
}

export type DistributionModel = "polarized" | "pyramidal" | "threshold" | "mixed" | "unknown";

export interface IntensityDistribution {
  lowPct: number;
  moderatePct: number;
  highPct: number;
  model: DistributionModel;
  assessment: string;
  notes: string[];
}

/** GET /api/weeks/:isoDate — isoDate is any day; the week is Monday–Sunday around it. */
export interface WeekSummary {
  weekStart: string;
  weekEnd: string;
  hours: number;
  tss: number;
  rideCount: number;
  distribution: IntensityDistribution | null;
  activities: ActivitySummary[];
}

/** Error body for every non-2xx from the API. */
export interface ApiError {
  error: string;
  /** Machine-readable, e.g. "intervals_unauthorized", "intervals_not_found". */
  code: string;
}
