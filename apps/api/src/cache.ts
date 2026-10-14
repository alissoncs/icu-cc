export class TtlCache {
  private store = new Map<string, { at: number; value: unknown }>();
  constructor(
    private ttlMs = 5 * 60_000,
    private clock: () => number = Date.now,
  ) {}

  async wrap<T>(key: string, load: () => Promise<T>): Promise<T> {
    const hit = this.store.get(key);
    if (hit && this.clock() - hit.at < this.ttlMs) return hit.value as T;
    const value = await load();
    this.store.set(key, { at: this.clock(), value });
    return value;
  }
}
