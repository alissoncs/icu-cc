import { classifyDistribution } from "./distribution";
import { addDays, parseIsoDay, round1 } from "./load";
import type { ActivitySummary, WeekSummary } from "./types";

/** Monday..Sunday ISO dates of the week containing `isoDate` (any day of it). */
export function weekBounds(isoDate: string): { weekStart: string; weekEnd: string } {
  const dow = new Date(parseIsoDay(isoDate)).getUTCDay(); // 0 = Sunday
  const sinceMonday = (dow + 6) % 7;
  const weekStart = addDays(isoDate.slice(0, 10), -sinceMonday);
  return { weekStart, weekEnd: addDays(weekStart, 6) };
}

/**
 * Summarize a week. `zoneSecondsByActivity` maps activity id -> Coggan zone seconds
 * (use `normalize(raw).zoneTimes`). Activities outside the week are ignored.
 */
export function summarizeWeek(
  activities: ActivitySummary[],
  zoneSecondsByActivity: Record<string, Record<string, number>>,
  weekStart: string,
): WeekSummary {
  const { weekStart: start, weekEnd } = weekBounds(weekStart);
  const inWeek = activities
    .filter((a) => a.date >= start && a.date <= weekEnd)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  const agg: Record<string, number> = {};
  for (const a of inWeek) {
    for (const [k, v] of Object.entries(zoneSecondsByActivity[a.id] ?? {})) {
      agg[k] = (agg[k] ?? 0) + v;
    }
  }
  const hasZones = Object.values(agg).some((v) => v > 0);

  return {
    weekStart: start,
    weekEnd,
    hours: round1(inWeek.reduce((s, a) => s + a.durationS, 0) / 3600),
    tss: Math.round(inWeek.reduce((s, a) => s + (a.tss ?? 0), 0)),
    rideCount: inWeek.length,
    distribution: hasZones ? classifyDistribution(agg) : null,
    activities: inWeek,
  };
}
