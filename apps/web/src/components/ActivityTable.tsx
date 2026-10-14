import { Link } from "react-router-dom";
import type { ActivitySummary } from "@icu/core";
import { fmt0, fmt2, fmtDate, fmtDuration, t } from "../i18n";

export default function ActivityTable({ rows }: { rows: ActivitySummary[] }) {
  if (rows.length === 0) return <p className="muted">{t.activities.empty}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">{t.activities.date}</th>
            <th scope="col">{t.activities.name}</th>
            <th scope="col" className="num">
              {t.activities.duration}
            </th>
            <th scope="col" className="num">
              {t.activities.tss}
            </th>
            <th scope="col" className="num">
              {t.activities.np}
            </th>
            <th scope="col" className="num">
              {t.activities.if}
            </th>
            <th scope="col" className="num">
              {t.activities.hr}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id} data-testid="activity-row">
              <td>{fmtDate(a.date)}</td>
              <td>
                <Link to={`/atividades/${encodeURIComponent(a.id)}`}>{a.name}</Link>
              </td>
              <td className="num">{fmtDuration(a.durationS)}</td>
              <td className="num">{fmt0(a.tss)}</td>
              <td className="num">{fmt0(a.npW)}</td>
              <td className="num">{fmt2(a.intensityFactor)}</td>
              <td className="num">{fmt0(a.avgHr)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
