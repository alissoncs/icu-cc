import type { ApiError } from "@icu/core";
import athlete from "../../../fixtures/api/athlete.json";
import activities from "../../../fixtures/api/activities.json";
import activityDetail from "../../../fixtures/api/activity_detail.json";
import fitness from "../../../fixtures/api/fitness.json";
import week from "../../../fixtures/api/week.json";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export function isMock(): boolean {
  if (import.meta.env.VITE_MOCK === "1") return true;
  return typeof location !== "undefined" && new URLSearchParams(location.search).get("mock") === "1";
}

/** Dev-only: answer from fixtures/api/*.json. */
function mockGet(path: string): unknown {
  const [pathname = "", query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  if (pathname === "/api/athlete") return athlete;
  if (pathname === "/api/activities") {
    const days = Number(params.get("days") ?? 30);
    const last = activities.reduce((m, a) => (a.date > m ? a.date : m), "");
    const cutoff = new Date(`${last}T00:00:00Z`);
    cutoff.setUTCDate(cutoff.getUTCDate() - days + 1);
    const c = cutoff.toISOString().slice(0, 10);
    return activities.filter((a) => a.date >= c);
  }
  if (pathname.startsWith("/api/activities/")) return activityDetail;
  if (pathname === "/api/fitness") {
    const days = Number(params.get("days") ?? 42);
    return { ...fitness, points: fitness.points.slice(-days) };
  }
  if (pathname.startsWith("/api/weeks/")) return week;
  throw new ApiRequestError("not found", "not_found", 404);
}

export async function get<T>(path: string): Promise<T> {
  if (isMock()) return structuredClone(mockGet(path)) as T;
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiRequestError("network", "network_error", 0);
  }
  if (!res.ok) {
    let body: Partial<ApiError> = {};
    try {
      body = (await res.json()) as Partial<ApiError>;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiRequestError(body.error ?? res.statusText, body.code ?? "http_error", res.status);
  }
  return (await res.json()) as T;
}
