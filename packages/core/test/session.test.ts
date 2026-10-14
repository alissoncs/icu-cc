import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { analyzeActivity, normalize, summarizeWeek, weekBounds, type ActivitySummary } from "../src";

const detail = JSON.parse(
  readFileSync(new URL("../../../fixtures/intervals/activity_detail.json", import.meta.url), "utf8"),
) as Record<string, unknown>;

describe("normalize", () => {
  it("accepts dict zone times and alias names", () => {
    const n = normalize({ title: "x", sport: "Ride", moving_time: 3600, np: 200, zone_times: { Z1: 60, Z2: "120" } });
    expect(n.name).toBe("x");
    expect(n.npW).toBe(200);
    expect(n.zoneTimes).toEqual({ Z1: 60, Z2: 120 });
  });

  it("accepts Intervals list-of-dicts and bare lists", () => {
    expect(normalize({ icu_zone_times: [{ id: "Z1", secs: 5 }, { id: "Z2", secs: 7 }] }).zoneTimes).toEqual({ Z1: 5, Z2: 7 });
    expect(normalize({ zone_times: [1, 2, 3] }).zoneTimes).toEqual({ Z1: 1, Z2: 2, Z3: 3 });
  });

  it("converts Intervals percent IF to a fraction", () => {
    expect(normalize({ icu_intensity: 86 }).if).toBe(0.86);
    expect(normalize({ intensity_factor: 0.86 }).if).toBe(0.86);
  });
});

describe("analyzeActivity on fixtures/intervals/activity_detail.json (FTP 228)", () => {
  const a = analyzeActivity(detail, 228);

  it("reads the summary", () => {
    expect(a.summary).toMatchObject({
      id: "i1000",
      date: "2026-08-24",
      durationS: 12600,
      tss: 215,
      npW: 196,
      avgPowerW: 178,
      avgHr: 141,
      intensityFactor: 0.86,
    });
    expect(a.ftpW).toBe(228);
  });

  it("derives VI, EF, kJ by hand-checkable formulas", () => {
    expect(a.variabilityIndex).toBeCloseTo(196 / 178, 3); // 1.101
    expect(a.efficiencyFactor).toBe(1.39); // 196 / 141
    expect(a.kj).toBe(2243); // 178 W * 12600 s / 1000 = 2242.8
    expect(a.distanceKm).toBe(94.5);
    expect(a.elevationM).toBe(1400);
    expect(a.decouplingPct).toBe(6.2);
  });

  it("builds the zone table and Seiler summary", () => {
    expect(a.zones7).toHaveLength(7);
    expect(a.zones7[0]).toMatchObject({ zone: "Z1", lowW: 0, highW: 125, seconds: 900 }); // 228 * 0.55 = 125.4
    expect(a.zones7[6]).toMatchObject({ zone: "Z7", lowW: 342, highW: null, seconds: 0 });
    expect(a.zones7[1]!.pct).toBe(42.9); // 5400 / 12600
    // low 6300, moderate 5700, high 600 of 12600
    expect(a.zones3).toEqual({ lowPct: 50, moderatePct: 45.2, highPct: 4.8 });
  });

  it("tags findings with sources and carries cautions", () => {
    const text = a.findings.join("\n");
    expect(text).toContain("IF 0.86 — threshold-level");
    expect(text).toContain("VI 1.10 — normal road variability");
    expect(text).toContain("Aerobic decoupling 6.2% — moderate drift");
    expect(text).toContain("215 TSS over 3.5 h");
    expect(text).toContain("[SEI10]");
    expect(a.warnings.some((w) => w.includes("[JAM20]"))).toBe(true);
    expect(a.warnings.some((w) => w.includes("recorded against"))).toBe(false); // activity FTP == fallback
  });

  it("derives IF and TSS when absent and warns on FTP mismatch and missing data", () => {
    const d = analyzeActivity({ moving_time: 3600, np: 260, ftp: 250 }, 200);
    expect(d.summary.intensityFactor).toBe(1.04);
    expect(d.summary.tss).toBe(108.2);
    expect(d.zones3).toBeNull();
    const w = d.warnings.join("\n");
    expect(w).toContain("recorded against FTP 250 W");
    expect(w).toContain("retest FTP");
    expect(w).toContain("Missing from the data: heart rate, time-in-zone");
  });
});

describe("week helpers", () => {
  it("weekBounds returns Monday..Sunday", () => {
    expect(weekBounds("2026-08-26")).toEqual({ weekStart: "2026-08-24", weekEnd: "2026-08-30" });
    expect(weekBounds("2026-08-24").weekStart).toBe("2026-08-24");
    expect(weekBounds("2026-08-30").weekStart).toBe("2026-08-24"); // Sunday
    expect(weekBounds("2026-08-24T07:10:00").weekEnd).toBe("2026-08-30");
    expect(weekBounds("2026-01-01")).toEqual({ weekStart: "2025-12-29", weekEnd: "2026-01-04" });
  });

  it("summarizeWeek sums hours/TSS and aggregates zones", () => {
    const mk = (id: string, date: string, durationS: number, tss: number): ActivitySummary => ({
      id, date, name: id, type: "Ride", durationS, tss, npW: null, avgPowerW: null, intensityFactor: null, avgHr: null,
    });
    const acts = [mk("a", "2026-08-24", 3600, 50), mk("b", "2026-08-26", 7200, 100), mk("out", "2026-08-31", 3600, 80)];
    const w = summarizeWeek(
      acts,
      { a: { Z2: 3600 }, b: { Z2: 5400, Z5: 1800 }, out: { Z4: 3600 } },
      "2026-08-27",
    );
    expect(w).toMatchObject({ weekStart: "2026-08-24", weekEnd: "2026-08-30", hours: 3, tss: 150, rideCount: 2 });
    expect(w.distribution).toMatchObject({ lowPct: 83.3, moderatePct: 0, highPct: 16.7, model: "polarized" });
    expect(summarizeWeek([], {}, "2026-08-24").distribution).toBeNull();
  });
});
