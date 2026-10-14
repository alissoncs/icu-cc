import { buildApp } from "./app.js";
import { IntervalsClient } from "./intervals/client.js";

const key = process.env.INTERVALS_API_KEY?.trim();
const client = key
  ? new IntervalsClient({ apiKey: key, athleteId: process.env.INTERVALS_ATHLETE_ID?.trim() || "0" })
  : null;
const app = buildApp({ client });
const port = Number(process.env.PORT) || 8787;
await app.listen({ host: "127.0.0.1", port });
console.log(`icu api listening on http://127.0.0.1:${port}${client ? "" : " (INTERVALS_API_KEY missing)"}`);
