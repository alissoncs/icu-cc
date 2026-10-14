import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { FitnessResponse } from "@icu/core";
import { get } from "../api";
import { fmt1, t } from "../i18n";
import { QueryState } from "../components/QueryState";
import FitnessChart from "../components/FitnessChart";

function tsbGlyph(tsb: number): { glyph: string; word: string } {
  if (tsb > 5) return { glyph: "▲", word: t.form.fresh };
  if (tsb < -10) return { glyph: "▼", word: t.form.tired };
  return { glyph: "●", word: t.form.neutral };
}

export default function FormScreen() {
  const [days, setDays] = useState<42 | 90>(42);
  const query = useQuery({
    queryKey: ["fitness", days],
    queryFn: () => get<FitnessResponse>(`/api/fitness?days=${days}`),
  });
  return (
    <section>
      <h1>{t.form.title}</h1>
      <QueryState query={query}>
        {(data) => {
          const cur = data.points[data.points.length - 1];
          const g = cur ? tsbGlyph(cur.tsb) : null;
          return (
            <>
              {cur && (
                <div className="cards">
                  <div className="card">
                    <h2>{t.form.ctl}</h2>
                    <p className="big">{fmt1(cur.ctl)}</p>
                  </div>
                  <div className="card">
                    <h2>{t.form.atl}</h2>
                    <p className="big">{fmt1(cur.atl)}</p>
                  </div>
                  <div className="card">
                    <h2>{t.form.tsb}</h2>
                    <p className="big">{fmt1(cur.tsb)}</p>
                    <p>
                      <span aria-hidden="true">{g?.glyph} </span>
                      {data.formLabel} ({g?.word})
                    </p>
                  </div>
                  <div className="card">
                    <h2>{t.form.ramp}</h2>
                    <p className="big">
                      {data.rampRate > 0 ? "+" : ""}
                      {fmt1(data.rampRate)}
                    </p>
                  </div>
                </div>
              )}
              <div className="toolbar" role="group" aria-label={t.form.range}>
                {([42, 90] as const).map((d) => (
                  <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)}>
                    {d === 42 ? t.form.range42 : t.form.range90}
                  </button>
                ))}
              </div>
              <FitnessChart points={data.points} />
              <p className="muted">{data.source === "intervals" ? t.form.sourceIntervals : t.form.sourceComputed}</p>
            </>
          );
        }}
      </QueryState>
    </section>
  );
}
