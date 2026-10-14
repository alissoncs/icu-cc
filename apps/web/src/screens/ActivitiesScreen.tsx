import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import type { ActivitySummary } from "@icu/core";
import { get } from "../api";
import { t } from "../i18n";
import { QueryState } from "../components/QueryState";
import ActivityTable from "../components/ActivityTable";

const RANGES = [7, 30, 90] as const;

export default function ActivitiesScreen() {
  const [params, setParams] = useSearchParams();
  const raw = Number(params.get("days"));
  const days = (RANGES as readonly number[]).includes(raw) ? raw : 30;
  const query = useQuery({
    queryKey: ["activities", days],
    queryFn: () => get<ActivitySummary[]>(`/api/activities?days=${days}`),
  });
  return (
    <section>
      <h1>{t.activities.title}</h1>
      <div className="toolbar" role="group" aria-label={t.activities.filter}>
        {RANGES.map((d) => (
          <button key={d} type="button" aria-pressed={days === d} onClick={() => setParams({ days: String(d) })}>
            {t.activities.days(d)}
          </button>
        ))}
      </div>
      <QueryState query={query}>{(rows) => <ActivityTable rows={rows} />}</QueryState>
    </section>
  );
}
