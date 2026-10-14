import type { IntensityDistribution } from "./types";
import { collapseToSeiler } from "./zones";

/**
 * Classify a week or block as polarized, pyramidal or threshold. [SEI10]
 *
 * `zoneSeconds` is Coggan Z1-Z7 seconds; it is collapsed to the Seiler 3-zone model
 * first. Note Seiler's 80/20 finding is usually expressed by *session count*, while
 * time-in-zone is what power files give you — time-in-zone always looks more
 * low-intensity heavy, so the thresholds below are tuned for time.
 */
export function classifyDistribution(zoneSeconds: Record<string, number>): IntensityDistribution {
  const buckets = collapseToSeiler(zoneSeconds);
  const total = buckets[1] + buckets[2] + buckets[3];
  if (total <= 0) {
    return { lowPct: 0, moderatePct: 0, highPct: 0, model: "unknown", assessment: "No zone data.", notes: [] };
  }

  const low = (buckets[1] / total) * 100;
  const mod = (buckets[2] / total) * 100;
  const high = (buckets[3] / total) * 100;
  const notes: string[] = [];

  let model: IntensityDistribution["model"];
  let assessment: string;
  if (low >= 75 && high >= mod) {
    model = "polarized";
    assessment =
      "Close to the pattern elite endurance athletes converge on: most volume easy, " +
      "a real minority genuinely hard, little in between [SEI10].";
  } else if (low >= 70 && mod > high) {
    model = "pyramidal";
    assessment =
      "Pyramidal — easy base with more tempo/threshold than VO2max work. A " +
      "legitimate distribution that matches polarized in several trials, and " +
      "common in base and early build phases.";
  } else if (mod >= 25) {
    model = "threshold";
    assessment =
      "Threshold-heavy. This is Seiler's 'black hole': hard enough to accumulate " +
      "fatigue, not hard enough to drive the top-end adaptations, and it " +
      "compromises the easy days that should be recovering you [SEI10].";
  } else {
    model = "mixed";
    assessment = "No clean pattern — likely a transition or an unstructured week.";
  }

  if (low < 70) {
    notes.push(
      `Only ${low.toFixed(0)}% of time is genuinely low intensity. Elite practice sits ` +
        "near 80%. The usual cause is easy rides creeping into tempo.",
    );
  }
  if (high < 5 && total > 3 * 3600) {
    notes.push(
      "Under 5% high intensity. Fine in a base block; a problem if you are " +
        "inside 8 weeks of an A event.",
    );
  }
  if (mod > 30) {
    notes.push(
      `${mod.toFixed(0)}% at tempo/threshold is a lot of grey-zone time. Push the easy ` +
        "days easier and the hard days harder.",
    );
  }

  const r1 = (x: number) => Math.round(x * 10) / 10;
  return { lowPct: r1(low), moderatePct: r1(mod), highPct: r1(high), model, assessment, notes };
}
