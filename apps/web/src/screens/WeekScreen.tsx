import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import type { WeekSummary } from "@icu/core";
import { get } from "../api";
import { fmt0, fmt1, fmtDate, t } from "../i18n";
import { QueryState } from "../components/QueryState";
import ActivityTable from "../components/ActivityTable";

function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function WeekScreen() {
  const { date } = useParams();
  const day = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : todayIso();
  const query = useQuery({
    queryKey: ["week", day],
    queryFn: () => get<WeekSummary>(`/api/weeks/${day}`),
  });
  const ref = query.data?.weekStart ?? day;
  return (
    <section>
      <h1>{t.week.title}</h1>
      <nav className="toolbar" aria-label={t.week.title}>
        <Link className="btn" to={`/semana/${addDays(ref, -7)}`}>
          ← {t.week.prev}
        </Link>
        {query.data && (
          <strong>
            {fmtDate(query.data.weekStart)} – {fmtDate(query.data.weekEnd)}
          </strong>
        )}
        <Link className="btn" to={`/semana/${addDays(ref, 7)}`}>
          {t.week.next} →
        </Link>
      </nav>
      <QueryState query={query}>
        {(w) => (
          <>
            <div className="cards">
              <div className="card">
                <h2>{t.week.hours}</h2>
                <p className="big">{fmt1(w.hours)}</p>
              </div>
              <div className="card">
                <h2>{t.week.tss}</h2>
                <p className="big">{fmt0(w.tss)}</p>
              </div>
              <div className="card">
                <h2>{t.week.rides}</h2>
                <p className="big">{w.rideCount}</p>
              </div>
            </div>

            <h2>{t.week.distribution}</h2>
            {w.distribution ? (
              <div className="card" data-testid="distribution">
                <p>
                  <strong data-testid="model-label">
                    {t.week.models[w.distribution.model] ?? w.distribution.model}
                  </strong>{" "}
                  — {fmt0(w.distribution.lowPct)}% / {fmt0(w.distribution.moderatePct)}% /{" "}
                  {fmt0(w.distribution.highPct)}%
                </p>
                <p>
                  <strong>{t.week.assessment}:</strong> {w.distribution.assessment}
                </p>
                {w.distribution.notes.length > 0 && (
                  <>
                    <h3>{t.week.notes}</h3>
                    <ul>
                      {w.distribution.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ) : (
              <p className="muted">{t.week.noDistribution}</p>
            )}

            <h2>{t.week.activities}</h2>
            <ActivityTable rows={w.activities} />
          </>
        )}
      </QueryState>
    </section>
  );
}
