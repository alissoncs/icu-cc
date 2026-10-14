/**
 * Training zones: Coggan 7-zone power [COG19], Seiler 3-zone [SEI10].
 *
 * Zone edges are estimates derived from a field-test proxy for LT2, not physiological
 * truth — thresholds vary with test method and protocol [JAM20]. Treat boundaries as
 * soft and never present them as measured.
 */
import type { ZoneKey } from "./types";

export interface PowerZoneDef {
  key: ZoneKey;
  name: string;
  /** Fraction of FTP. */
  low: number;
  /** Fraction of FTP; null = open-ended. */
  high: number | null;
}

/** Coggan 7-zone model, as fractions of FTP. Upper bound null = open-ended. [COG19] */
export const POWER_ZONES: readonly PowerZoneDef[] = [
  { key: "Z1", name: "Active Recovery", low: 0.0, high: 0.55 },
  { key: "Z2", name: "Endurance", low: 0.55, high: 0.75 },
  { key: "Z3", name: "Tempo", low: 0.75, high: 0.9 },
  { key: "Z4", name: "Lactate Threshold", low: 0.9, high: 1.05 },
  { key: "Z5", name: "VO2max", low: 1.05, high: 1.2 },
  { key: "Z6", name: "Anaerobic Capacity", low: 1.2, high: 1.5 },
  { key: "Z7", name: "Neuromuscular Power", low: 1.5, high: null },
];

export const ZONE_KEYS: readonly ZoneKey[] = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"];

/**
 * Seiler 3-zone model mapped onto %FTP. The physiological anchors are VT1 and VT2;
 * ~80% FTP and ~100% FTP are the usual practical proxies. [SEI10] [JAM20]
 */
export const SEILER_LOW_UPPER = 0.8;
export const SEILER_MID_UPPER = 1.0;

export interface Zone {
  key: ZoneKey;
  name: string;
  lowW: number;
  highW: number | null;
  lowPct: number;
  highPct: number | null;
}

/** Coggan 7 power zones for the given FTP. */
export function powerZones(ftpW: number): Zone[] {
  return POWER_ZONES.map((z) => ({
    key: z.key,
    name: z.name,
    lowW: Math.round(ftpW * z.low),
    highW: z.high !== null ? Math.round(ftpW * z.high) : null,
    lowPct: z.low,
    highPct: z.high,
  }));
}

/** Which Coggan zone a given wattage falls in. */
export function zoneForPower(watts: number, ftpW: number): ZoneKey {
  const frac = watts / ftpW;
  for (const z of POWER_ZONES) {
    if (frac >= z.low && (z.high === null || frac < z.high)) return z.key;
  }
  return "Z7";
}

/** Seiler 3-zone bucket (1, 2 or 3) for a given wattage. */
export function seilerZone(watts: number, ftpW: number): 1 | 2 | 3 {
  const frac = watts / ftpW;
  if (frac < SEILER_LOW_UPPER) return 1;
  if (frac < SEILER_MID_UPPER) return 2;
  return 3;
}

const COGGAN_TO_SEILER: Record<string, 1 | 2 | 3> = {
  Z1: 1,
  Z2: 1,
  Z3: 2,
  Z4: 2,
  Z5: 3,
  Z6: 3,
  Z7: 3,
};

/**
 * Roll Coggan Z1-Z7 time into the Seiler 3-zone model.
 *
 * Z1-Z2 -> low, Z3-Z4 -> moderate, Z5+ -> high. Coggan Z3 starts at 75% FTP and the
 * Seiler low/moderate boundary sits near 80%, so a little genuine low-intensity time
 * lands in zone 2 here. That bias is conservative: it reports slightly *more* black
 * hole than there is, which is the direction that fails safe.
 */
export function collapseToSeiler(coggan: Record<string, number>): Record<1 | 2 | 3, number> {
  const out: Record<1 | 2 | 3, number> = { 1: 0, 2: 0, 3: 0 };
  for (const [key, seconds] of Object.entries(coggan)) {
    const bucket = COGGAN_TO_SEILER[key.toUpperCase()];
    if (bucket) out[bucket] += Number(seconds) || 0;
  }
  return out;
}
