import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import type { ActivityAnalysis, ZoneTime } from "@icu/core";
import { get } from "../api";
import { fmt0, fmt1, fmt2, fmtDate, fmtDuration, t } from "../i18n";
import { QueryState } from "../components/QueryState";

function wattRange(z: ZoneTime): string {
  return z.highW == null ? `${z.lowW}+ ${t.units.w}` : `${z.lowW}–${z.highW} ${t.units.w}`;
}

function Bar({ pct, label }: { pct: number; label: string }) {
  return (
    <div className="bar" role="img" aria-label={label}>
      <div className="bar-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <h3>{label}</h3>
      <p className="big">{value}</p>
    </div>
  );
}

function View({ a }: { a: ActivityAnalysis }) {
  const s = a.summary;
  const z3 = a.zones3;
  return (
    <>
      <p className="muted">
        {fmtDate(s.date)} · {fmtDuration(s.durationS)} {t.units.h}
      </p>

      {a.warnings.length > 0 && (
        <div role="alert" className="callout callout-warn" data-testid="warnings">
          <p className="callout-title">
            <span aria-hidden="true">⚠ </span>
            {t.status.warning}: {t.activity.warnings}
          </p>
          <ul>
            {a.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <h2>{t.activity.metrics}</h2>
      <div className="cards">
        <Metric label={t.activity.np} value={s.npW == null ? t.none : `${fmt0(s.npW)} ${t.units.w}`} />
        <Metric label={t.activity.if} value={fmt2(s.intensityFactor)} />
        <Metric label={t.activity.tss} value={fmt0(s.tss)} />
        <Metric label={t.activity.vi} value={fmt2(a.variabilityIndex)} />
        <Metric label={t.activity.ef} value={fmt2(a.efficiencyFactor)} />
        <Metric label={t.activity.decoupling} value={a.decouplingPct == null ? t.none : `${fmt1(a.decouplingPct)}%`} />
        <Metric label={t.activity.kj} value={a.kj == null ? t.none : `${fmt0(a.kj)} ${t.units.kj}`} />
        <Metric label={t.activity.distance} value={a.distanceKm == null ? t.none : `${fmt1(a.distanceKm)} ${t.units.km}`} />
        <Metric label={t.activity.elevation} value={a.elevationM == null ? t.none : `${fmt0(a.elevationM)} ${t.units.m}`} />
      </div>

      <h2>{t.activity.zones7}</h2>
      <p className="muted">{t.activity.ftpNote(a.ftpW)}</p>
      <ul className="zones">
        {a.zones7.map((z) => (
          <li key={z.zone} data-testid="zone-row">
            <span className="zone-name">
              <strong>{z.zone}</strong> {z.name}
            </span>
            <span className="zone-watts">{wattRange(z)}</span>
            <Bar pct={z.pct} label={`${z.zone} ${fmt1(z.pct)}%`} />
            <span className="zone-val">
              {fmtDuration(z.seconds)} · {fmt1(z.pct)}%
            </span>
          </li>
        ))}
      </ul>

      {z3 && (
        <>
          <h2>{t.activity.zones3}</h2>
          <ul className="zones">
            {(
              [
                [t.activity.low, z3.lowPct],
                [t.activity.moderate, z3.moderatePct],
                [t.activity.high, z3.highPct],
              ] as const
            ).map(([label, pct]) => (
              <li key={label} data-testid="zone3-row">
                <span className="zone-name">{label}</span>
                <span />
                <Bar pct={pct} label={`${label} ${fmt1(pct)}%`} />
                <span className="zone-val">{fmt1(pct)}%</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h2>{t.activity.findings}</h2>
      {a.findings.length === 0 ? (
        <p className="muted">{t.activity.noFindings}</p>
      ) : (
        <ul>
          {a.findings.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function ActivityScreen() {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["activity", id],
    queryFn: () => get<ActivityAnalysis>(`/api/activities/${encodeURIComponent(id)}`),
  });
  return (
    <section>
      <p>
        <Link to="/atividades">← {t.activity.back}</Link>
      </p>
      <h1>{query.data ? query.data.summary.name : t.activities.title}</h1>
      <QueryState query={query}>{(a) => <View a={a} />}</QueryState>
    </section>
  );
}
