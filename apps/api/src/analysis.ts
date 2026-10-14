/**
 * Thin adapter between the API and the science in @icu/core. Routes import only from here,
 * so the API never reaches into core's internals directly.
 */
import {
  analyzeActivity as coreAnalyzeActivity,
  formLabel,
  normalize,
  rampRate,
  round1,
  summarizeWeek as coreSummarizeWeek,
} from "@icu/core";
import type { ActivityAnalysis, ActivitySummary, FitnessPoint, FitnessResponse, WeekSummary } from "@icu/core";

export function analyzeActivity(raw: Record<string, unknown>, ftpFallbackW: number): ActivityAnalysis {
  return coreAnalyzeActivity(raw, ftpFallbackW);
}

/**
 * CTL/ATL come from Intervals wellness; TSB is derived with the same convention core's PMC
 * uses and Intervals.icu uses: yesterday's CTL minus yesterday's ATL, so today's ride does
 * not flatter today's form. [COG19]
 */
export function buildFitness(points: { date: string; ctl: number; atl: number; load: number }[]): FitnessResponse {
  const out: FitnessPoint[] = points.map((p, i) => {
    const prev = points[i - 1];
    return { ...p, tsb: prev ? round1(prev.ctl - prev.atl) : 0 };
  });
  const last = out[out.length - 1];
  return {
    points: out,
    rampRate: rampRate(out),
    formLabel: last ? formLabel(last.tsb) : "unknown",
    source: "intervals",
  };
}

export function summarizeWeek(
  activities: ActivitySummary[],
  rawActivities: Record<string, unknown>[],
  anyDay: string,
): WeekSummary {
  const zoneSecondsByActivity: Record<string, Record<string, number>> = {};
  for (const raw of rawActivities) {
    const id = String(raw.id ?? "");
    if (id) zoneSecondsByActivity[id] = normalize(raw).zoneTimes;
  }
  return coreSummarizeWeek(activities, zoneSecondsByActivity, anyDay);
}
