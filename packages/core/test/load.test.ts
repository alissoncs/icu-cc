import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  addDays,
  formLabel,
  intensityFactor,
  monotonyAndStrain,
  normalizedPower,
  pmc,
  rampRate,
  trainingStressScore,
  variabilityIndex,
} from "../src";

const dailyLoad = JSON.parse(
  readFileSync(new URL("../../../examples/daily_load.json", import.meta.url), "utf8"),
) as Record<string, number>;

describe("normalized power", () => {
  it("equals average for constant power", () => {
    expect(normalizedPower(Array(600).fill(200))).toBe(200);
  });

  it("exceeds average for variable power", () => {
    const surging = Array.from({ length: 20 }, () => [...Array(30).fill(100), ...Array(30).fill(300)]).flat();
    const avg = surging.reduce((s, v) => s + v, 0) / surging.length;
    expect(normalizedPower(surging)).toBeGreaterThan(avg);
  });

  it("falls back to the mean when shorter than the 30 s window", () => {
    expect(normalizedPower([100, 200, 300])).toBe(200);
    expect(normalizedPower([])).toBe(0);
  });
});

describe("TSS / IF / VI", () => {
  it("one hour at FTP is 100 TSS [COG19]", () => {
    expect(Math.round(trainingStressScore(3600, 250, 250))).toBe(100);
  });

  it("scales with IF squared", () => {
    expect(trainingStressScore(3600, 125, 250)).toBe(25);
    expect(intensityFactor(225, 250)).toBe(0.9);
    expect(variabilityIndex(196, 178)).toBeGreaterThan(1);
  });

  it("guards zero denominators", () => {
    expect(trainingStressScore(3600, 200, 0)).toBe(0);
    expect(intensityFactor(200, 0)).toBe(0);
  });
});

describe("pmc", () => {
  it("fills rest days and decays", () => {
    const points = pmc({ "2026-01-01": 100, "2026-01-21": 0 });
    expect(points).toHaveLength(21);
    const first = points[0]!;
    const last = points[20]!;
    expect(last.ctl).toBeLessThan(first.ctl);
    expect(last.atl).toBeLessThan(first.atl);
    expect(last.atl).toBeLessThan(last.ctl);
  });

  it("TSB uses yesterday's values", () => {
    const loads: Record<string, number> = {};
    for (let i = 0; i < 5; i++) loads[addDays("2026-01-01", i)] = 100;
    expect(pmc(loads)[0]!.tsb).toBe(0);
  });

  it("matches hand-computed values for a single 100 TSS day then a second", () => {
    // ctl_k = 1 - e^(-1/42) = 0.023530; atl_k = 1 - e^(-1/7) = 0.133122
    const p = pmc({ "2026-01-01": 100, "2026-01-02": 100 });
    expect(p[0]).toEqual({ date: "2026-01-01", load: 100, ctl: 2.4, atl: 13.3, tsb: 0 });
    // day 2: tsb = 2.353 - 13.312 = -10.959 ; ctl = 2.353 + 97.647*0.02353 = 4.651 ; atl = 13.312 + 86.688*0.133122 = 24.852
    expect(p[1]).toEqual({ date: "2026-01-02", load: 100, ctl: 4.7, atl: 24.9, tsb: -11 });
  });

  it("honours seeds", () => {
    const p = pmc({ "2026-01-01": 55 }, { ctlSeed: 55, atlSeed: 55 });
    expect(p[0]).toEqual({ date: "2026-01-01", load: 55, ctl: 55, atl: 55, tsb: 0 });
  });

  it("iterates days across month and DST boundaries without skipping", () => {
    const p = pmc({ "2026-03-27": 10, "2026-04-02": 10 }); // spans EU/US DST changes
    expect(p.map((x) => x.date)).toEqual([
      "2026-03-27", "2026-03-28", "2026-03-29", "2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02",
    ]);
    expect(pmc({})).toEqual([]);
  });

  it("is deterministic over examples/daily_load.json seeded 0", () => {
    const pts = pmc(dailyLoad);
    // 2026-07-27 .. 2026-08-28 inclusive
    expect(pts).toHaveLength(33);
    expect(pts[0]).toMatchObject({ date: "2026-07-27", ctl: 0, atl: 0, tsb: 0 });
    expect(pts[32]!.date).toBe("2026-08-28");
    expect(pmc(dailyLoad)).toEqual(pts);

    // Independent recomputation of the same recurrence, unrounded.
    let ctl = 0;
    let atl = 0;
    for (let i = 0; i < 33; i++) {
      const load = dailyLoad[addDays("2026-07-27", i)] ?? 0;
      const tsb = ctl - atl;
      ctl += (load - ctl) * (1 - Math.exp(-1 / 42));
      atl += (load - atl) * (1 - Math.exp(-1 / 7));
      expect(pts[i]!.ctl).toBeCloseTo(ctl, 1);
      expect(pts[i]!.atl).toBeCloseTo(atl, 1);
      expect(pts[i]!.tsb).toBeCloseTo(tsb, 1);
    }
    // Sustained building from zero: fatigue outruns fitness.
    expect(pts[32]!.atl).toBeGreaterThan(pts[32]!.ctl);
    expect(pts[32]!.tsb).toBeLessThan(0);
  });
});

describe("rampRate", () => {
  it("is positive when building", () => {
    const loads: Record<string, number> = {};
    for (let i = 0; i < 30; i++) loads[addDays("2026-01-01", i)] = 100;
    expect(rampRate(pmc(loads))).toBeGreaterThan(0);
  });

  it("is 0 with too few points and equals the CTL delta otherwise", () => {
    expect(rampRate(pmc({ "2026-01-01": 100 }))).toBe(0);
    const pts = pmc(dailyLoad);
    expect(rampRate(pts)).toBe(Math.round((pts[32]!.ctl - pts[25]!.ctl) * 10) / 10);
  });
});

describe("monotony and strain", () => {
  it("is high when every day is identical", () => {
    const [flat] = monotonyAndStrain([80, 80, 80, 80.1, 80, 80, 80]);
    const [varied] = monotonyAndStrain([0, 150, 40, 0, 200, 60, 30]);
    expect(flat).toBeGreaterThan(varied);
  });

  it("matches a hand computation", () => {
    // loads 1,2,3: mean 2, sample sd 1 -> monotony 2.0, strain 6*2 = 12
    expect(monotonyAndStrain([1, 2, 3])).toEqual([2, 12]);
    expect(monotonyAndStrain([5, 5, 5])).toEqual([0, 0]);
    expect(monotonyAndStrain([5])).toEqual([0, 0]);
  });
});

describe("formLabel", () => {
  it("bands TSB", () => {
    expect(formLabel(30)).toContain("very fresh");
    expect(formLabel(10)).toBe("fresh / race-ready");
    expect(formLabel(0)).toBe("neutral");
    expect(formLabel(-20)).toBe("productive training load");
    expect(formLabel(-40)).toContain("high fatigue");
  });
});
