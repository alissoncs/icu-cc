import Fastify, { type FastifyInstance } from "fastify";
import type { ApiError } from "@icu/core";
import { TtlCache } from "./cache.js";
import { IntervalsClient, IntervalsError } from "./intervals/client.js";
import { mapActivity, mapAthlete, mapWellness } from "./intervals/map.js";
import { analyzeActivity, buildFitness, summarizeWeek } from "./analysis.js";

export const FTP_FALLBACK_W = 200;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export interface AppOptions {
  client: IntervalsClient | null;
  now?: () => Date;
  cacheTtlMs?: number;
}

const ymd = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function clampDays(q: unknown, def: number): number {
  const n = Number.parseInt(String(q ?? ""), 10);
  if (!Number.isFinite(n)) return def;
  return Math.min(365, Math.max(1, n));
}

const fail = (code: string, error: string): ApiError => ({ code, error });

export function buildApp(opts: AppOptions): FastifyInstance {
  const app = Fastify({ logger: false });
  const now = opts.now ?? (() => new Date());
  const cache = new TtlCache(opts.cacheTtlMs, () => now().getTime());
  const client = opts.client;

  app.setErrorHandler((err, _req, reply) => {
    if (err instanceof IntervalsError) {
      if (err.retryAfter) reply.header("Retry-After", err.retryAfter);
      return reply.status(err.status).send(fail(err.code, err.message));
    }
    return reply.status(500).send(fail("internal_error", "Unexpected server error."));
  });

  app.get("/api/health", async () => ({ ok: true, configured: client !== null }));

  app.register(async (api) => {
    api.addHook("onRequest", async (_req, reply) => {
      if (!client)
        return reply
          .status(500)
          .send(fail("config_missing", "INTERVALS_API_KEY is not set. Copy .env.example to .env and fill in your key."));
    });
    const c = () => client as IntervalsClient;

    const athlete = () => cache.wrap("athlete", () => c().getAthlete());
    const range = (days: number) => {
      const end = now();
      const start = new Date(end);
      start.setDate(start.getDate() - days);
      return { oldest: ymd(start), newest: ymd(end) };
    };

    api.get("/api/athlete", async () => mapAthlete(await athlete()));

    api.get("/api/activities", async (req) => {
      const days = clampDays((req.query as Record<string, unknown>).days, 30);
      const { oldest, newest } = range(days);
      const raw = await cache.wrap(`activities?${oldest}&${newest}`, () => c().getActivities(oldest, newest));
      return raw.map(mapActivity);
    });

    api.get("/api/activities/:id", async (req) => {
      const { id } = req.params as { id: string };
      const raw = await cache.wrap(`activity/${id}`, () => c().getActivity(id));
      const a = mapAthlete(await athlete());
      const result = analyzeActivity(raw, a.ftpW ?? FTP_FALLBACK_W);
      if (a.ftpW === null && typeof raw.icu_ftp !== "number")
        result.warnings.push(
          `No FTP found on Intervals.icu; zones use a ${FTP_FALLBACK_W} W placeholder and are not reliable.`,
        );
      return result;
    });

    api.get("/api/fitness", async (req) => {
      const days = clampDays((req.query as Record<string, unknown>).days, 90);
      const { oldest, newest } = range(days);
      const raw = await cache.wrap(`wellness?${oldest}&${newest}`, () => c().getWellness(oldest, newest));
      return buildFitness(mapWellness(raw));
    });

    api.get("/api/weeks/:isoDate", async (req, reply) => {
      const { isoDate } = req.params as { isoDate: string };
      const valid =
        ISO_DAY.test(isoDate) && !Number.isNaN(Date.parse(isoDate + "T00:00:00Z")) && new Date(isoDate + "T00:00:00Z").toISOString().slice(0, 10) === isoDate;
      if (!valid) return reply.status(400).send(fail("bad_date", "Date must be a valid YYYY-MM-DD."));
      const probe = summarizeWeek([], [], isoDate);
      const raw = await cache.wrap(`activities?${probe.weekStart}&${probe.weekEnd}`, () =>
        c().getActivities(probe.weekStart, probe.weekEnd),
      );
      return summarizeWeek(raw.map(mapActivity), raw, isoDate);
    });
  });

  return app;
}
