import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import { IntervalsClient } from "../src/intervals/client.js";

const KEY = "sekret-key-123";
const fx = (p: string) => JSON.parse(readFileSync(new URL(`../../../fixtures/${p}`, import.meta.url), "utf8"));

function setup(status = 200, athlete: unknown = fx("intervals/athlete.json")) {
  const calls: string[] = [];
  const fetchImpl = (async (url: string | URL, init?: RequestInit) => {
    const u = String(url);
    calls.push(u);
    expect((init?.headers as Record<string, string>)["User-Agent"]).toMatch(/Mozilla/);
    if (status !== 200)
      return new Response("{}", { status, headers: status === 429 ? { "Retry-After": "30" } : {} });
    let body: unknown;
    if (u.includes("/wellness")) body = fx("intervals/wellness.json");
    else if (u.includes("/activities")) body = fx("intervals/activities.json");
    else if (u.includes("/activity/")) body = fx("intervals/activity_detail.json");
    else body = athlete;
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
  const client = new IntervalsClient({ apiKey: KEY, athleteId: "0", fetchImpl });
  const app = buildApp({ client, now: () => new Date("2026-08-30T12:00:00") });
  return { app, calls };
}

describe("routes", () => {
  it("athlete", async () => {
    const r = await setup().app.inject("/api/athlete");
    expect(r.json()).toEqual(fx("api/athlete.json"));
  });
  it("activities match fixture", async () => {
    const r = await setup().app.inject("/api/activities?days=9999");
    expect(r.json()).toEqual(fx("api/activities.json"));
  });
  it("activity detail", async () => {
    const r = await setup().app.inject("/api/activities/i1000");
    const b = r.json();
    expect(r.statusCode).toBe(200);
    expect(b.summary).toEqual(fx("api/activity_detail.json").summary);
    expect(b.ftpW).toBe(228);
  });
  it("fitness", async () => {
    const r = await setup().app.inject("/api/fitness");
    const b = r.json();
    expect(b.source).toBe("intervals");
    // tsb is computed by the (stubbed) science layer; compare the passthrough fields only.
    const strip = (ps: Record<string, unknown>[]) => ps.map(({ tsb: _t, ...p }) => p);
    expect(strip(b.points)).toEqual(strip(fx("api/fitness.json").points));
  });
  it("week", async () => {
    const r = await setup().app.inject("/api/weeks/2026-08-27");
    const b = r.json();
    const exp = fx("api/week.json");
    expect(b.weekStart).toBe(exp.weekStart);
    expect(b.weekEnd).toBe(exp.weekEnd);
    expect(b.activities).toEqual(exp.activities);
  });
  it("missing FTP -> 200 with warning", async () => {
    const r = await setup(200, { name: "x", sportSettings: [] }).app.inject("/api/activities/i1000");
    expect(r.statusCode).toBe(200);
  });
  it("bad date -> 400", async () => {
    expect((await setup().app.inject("/api/weeks/2026-13-99")).statusCode).toBe(400);
    expect((await setup().app.inject("/api/weeks/nope")).statusCode).toBe(400);
  });
  it("cache avoids second upstream call", async () => {
    const { app, calls } = setup();
    await app.inject("/api/activities");
    await app.inject("/api/activities");
    expect(calls.filter((u) => u.includes("/activities"))).toHaveLength(1);
  });
});

describe("errors", () => {
  it("maps upstream statuses", async () => {
    const cases: [number, number, string][] = [
      [401, 401, "intervals_unauthorized"],
      [403, 401, "intervals_unauthorized"],
      [404, 404, "intervals_not_found"],
      [429, 429, "intervals_rate_limited"],
    ];
    for (const [up, down, code] of cases) {
      const r = await setup(up).app.inject("/api/athlete");
      expect(r.statusCode).toBe(down);
      expect(r.json().code).toBe(code);
      if (up === 429) expect(r.headers["retry-after"]).toBe("30");
    }
  });
  it("network failure -> intervals_unreachable, no key leak", async () => {
    const client = new IntervalsClient({
      apiKey: KEY,
      fetchImpl: (async () => {
        throw new Error(`boom ${KEY}`);
      }) as typeof fetch,
    });
    const r = await buildApp({ client }).inject("/api/athlete");
    expect(r.statusCode).toBe(502);
    expect(r.json().code).toBe("intervals_unreachable");
    expect(r.body).not.toContain(KEY);
  });
  it("config_missing except health", async () => {
    const app = buildApp({ client: null });
    const r = await app.inject("/api/athlete");
    expect(r.statusCode).toBe(500);
    expect(r.json().code).toBe("config_missing");
    expect(r.json().error).toContain(".env.example");
    expect((await app.inject("/api/health")).statusCode).toBe(200);
  });
  it("key never appears in any body", async () => {
    const b64 = Buffer.from(`API_KEY:${KEY}`).toString("base64");
    for (const s of [200, 401, 404, 429]) {
      const { app } = setup(s);
      for (const p of ["/api/athlete", "/api/activities", "/api/activities/i1", "/api/fitness", "/api/weeks/2026-08-24"]) {
        const r = await app.inject(p);
        expect(r.body).not.toContain(KEY);
        expect(r.body).not.toContain(b64);
        expect(JSON.stringify(r.headers)).not.toContain(KEY);
      }
    }
  });
});
