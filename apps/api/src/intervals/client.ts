export type IntervalsErrorCode =
  | "intervals_unauthorized"
  | "intervals_not_found"
  | "intervals_rate_limited"
  | "intervals_unreachable"
  | "intervals_error";

export class IntervalsError extends Error {
  constructor(
    public code: IntervalsErrorCode,
    message: string,
    public status: number,
    public retryAfter?: string,
  ) {
    super(message);
    this.name = "IntervalsError";
  }
}

export interface IntervalsClientOptions {
  apiKey: string;
  athleteId?: string;
  fetchImpl?: typeof fetch;
  baseUrl?: string;
  timeoutMs?: number;
}

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

export class IntervalsClient {
  private readonly apiKey: string;
  private readonly athleteId: string;
  private readonly fetchImpl: typeof fetch;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(opts: IntervalsClientOptions) {
    this.apiKey = opts.apiKey;
    this.athleteId = opts.athleteId || "0";
    this.fetchImpl = opts.fetchImpl ?? fetch;
    this.baseUrl = opts.baseUrl ?? "https://intervals.icu/api/v1";
    this.timeoutMs = opts.timeoutMs ?? 10_000;
  }

  getAthlete(): Promise<Record<string, unknown>> {
    return this.get(`/athlete/${this.athleteId}`);
  }
  getActivities(oldest: string, newest: string): Promise<Record<string, unknown>[]> {
    return this.get(`/athlete/${this.athleteId}/activities`, { oldest, newest });
  }
  getActivity(id: string): Promise<Record<string, unknown>> {
    return this.get(`/activity/${encodeURIComponent(id)}`);
  }
  getWellness(oldest: string, newest: string): Promise<Record<string, unknown>[]> {
    return this.get(`/athlete/${this.athleteId}/wellness`, { oldest, newest });
  }

  private async get<T>(path: string, query?: Record<string, string>): Promise<T> {
    const qs = query ? "?" + new URLSearchParams(query).toString() : "";
    const url = `${this.baseUrl}${path}${qs}`;
    const auth = "Basic " + Buffer.from(`API_KEY:${this.apiKey}`).toString("base64");
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), this.timeoutMs);
    let res: Response;
    try {
      res = await this.fetchImpl(url, {
        method: "GET",
        signal: ctl.signal,
        headers: { Authorization: auth, Accept: "application/json", "User-Agent": UA },
      });
    } catch {
      // Never forward the underlying error: it could echo request details.
      throw new IntervalsError(
        "intervals_unreachable",
        ctl.signal.aborted ? "Intervals.icu did not respond within 10 s." : "Could not reach Intervals.icu.",
        502,
      );
    } finally {
      clearTimeout(timer);
    }
    if (res.status === 401 || res.status === 403)
      throw new IntervalsError("intervals_unauthorized", "Intervals.icu rejected the API key. Check INTERVALS_API_KEY.", 401);
    if (res.status === 404) throw new IntervalsError("intervals_not_found", "Not found on Intervals.icu.", 404);
    if (res.status === 429) {
      const ra = res.headers.get("retry-after") ?? undefined;
      throw new IntervalsError(
        "intervals_rate_limited",
        ra ? `Intervals.icu rate limit hit. Retry after ${ra} s.` : "Intervals.icu rate limit hit.",
        429,
        ra,
      );
    }
    if (!res.ok) throw new IntervalsError("intervals_error", `Intervals.icu returned HTTP ${res.status}.`, 502);
    try {
      return (await res.json()) as T;
    } catch {
      throw new IntervalsError("intervals_error", "Intervals.icu returned invalid JSON.", 502);
    }
  }
}
