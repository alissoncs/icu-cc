import { describe, expect, it } from "vitest";
import { classifyDistribution, collapseToSeiler, powerZones, seilerZone, zoneForPower } from "../src";

describe("Coggan zones [COG19]", () => {
  it("boundaries", () => {
    const zones = powerZones(250);
    expect(zones[0]!.key).toBe("Z1");
    expect(zones[6]!.key).toBe("Z7");
    expect(zoneForPower(250, 250)).toBe("Z4"); // FTP itself is threshold
    expect(zoneForPower(150, 250)).toBe("Z2");
    expect(zoneForPower(400, 250)).toBe("Z7");
  });

  it("computes watt ranges from FTP", () => {
    const z = powerZones(200);
    expect(z.map((x) => [x.lowW, x.highW])).toEqual([
      [0, 110], [110, 150], [150, 180], [180, 210], [210, 240], [240, 300], [300, null],
    ]);
  });
});

describe("Seiler 3-zone [SEI10]", () => {
  it("splits wattage", () => {
    expect(seilerZone(150, 250)).toBe(1);
    expect(seilerZone(220, 250)).toBe(2);
    expect(seilerZone(280, 250)).toBe(3);
  });

  it("collapses Coggan seconds", () => {
    expect(collapseToSeiler({ Z2: 100, Z4: 50, Z5: 25 })).toEqual({ 1: 100, 2: 50, 3: 25 });
    expect(collapseToSeiler({ z1: 10, bogus: 5 })).toEqual({ 1: 10, 2: 0, 3: 0 });
  });
});

describe("classifyDistribution", () => {
  it("recognises a polarized week", () => {
    const d = classifyDistribution({ Z2: 8 * 3600, Z3: 0.3 * 3600, Z5: 1.7 * 3600 });
    expect(d.model).toBe("polarized");
    expect(d.lowPct).toBe(80);
    expect(d.moderatePct).toBe(3);
    expect(d.highPct).toBe(17);
  });

  it("calls out the threshold black hole", () => {
    const d = classifyDistribution({ Z2: 4 * 3600, Z3: 3 * 3600, Z4: 2 * 3600 });
    expect(d.model).toBe("threshold");
    expect(d.assessment).toContain("black hole");
    expect(d.notes.length).toBeGreaterThan(0);
  });

  it("does not flag pyramidal as a mistake", () => {
    const d = classifyDistribution({ Z2: 8 * 3600, Z3: 2 * 3600, Z5: 0.4 * 3600 });
    expect(d.model).toBe("pyramidal");
    expect(d.assessment).toContain("legitimate");
  });

  it("handles no data", () => {
    expect(classifyDistribution({}).model).toBe("unknown");
  });
});
