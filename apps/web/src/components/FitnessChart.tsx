import type { FitnessPoint } from "@icu/core";
import { fmt0, fmtShortDate, t } from "../i18n";

const W = 640;
const H = 240;
const PAD = { l: 36, r: 12, t: 12, b: 26 };

export default function FitnessChart({ points }: { points: FitnessPoint[] }) {
  if (points.length === 0) return <p className="muted">{t.form.empty}</p>;
  // One shared y-scale for all series, always including 0 so negative TSB is visible.
  const vals = points.flatMap((p) => [p.ctl, p.atl, p.tsb, 0]);
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.08;
  lo -= pad;
  hi += pad;
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * ih;
  const line = (f: (p: FitnessPoint) => number) =>
    points.map((p, i) => `${x(i).toFixed(1)},${y(f(p)).toFixed(1)}`).join(" ");

  const step = Math.max(10, Math.ceil((hi - lo) / 5 / 10) * 10);
  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v);

  const last = points.length - 1;
  const first = points[0]!;
  const end = points[last]!;
  const series = [
    { key: "ctl", label: t.form.ctl, cls: "s-ctl", dash: undefined, f: (p: FitnessPoint) => p.ctl },
    { key: "atl", label: t.form.atl, cls: "s-atl", dash: "6 3", f: (p: FitnessPoint) => p.atl },
    { key: "tsb", label: t.form.tsb, cls: "s-tsb", dash: "2 3", f: (p: FitnessPoint) => p.tsb },
  ];

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t.form.chartTitle} data-testid="fitness-chart">
        <title>{t.form.chartTitle}</title>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="grid" />
            <text x={PAD.l - 6} y={y(v) + 4} textAnchor="end" className="axis">
              {fmt0(v)}
            </text>
          </g>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} className="zero" data-testid="zero-line" />
        {series.map((s) => (
          <polyline
            key={s.key}
            points={line(s.f)}
            className={`series ${s.cls}`}
            strokeDasharray={s.dash}
            data-testid={`line-${s.key}`}
          />
        ))}
        <line x1={x(last)} x2={x(last)} y1={PAD.t} y2={H - PAD.b} className="today" />
        {series.map((s) => (
          <circle
            key={s.key}
            cx={x(last)}
            cy={y(s.f(end))}
            r={3.5}
            className={`dot ${s.cls}`}
            data-testid="today-marker"
          />
        ))}
        <text x={PAD.l} y={H - 8} className="axis">
          {fmtShortDate(first.date)}
        </text>
        <text x={W - PAD.r} y={H - 8} textAnchor="end" className="axis">
          {fmtShortDate(end.date)} ({t.form.today})
        </text>
      </svg>
      <figcaption className="legend">
        {series.map((s) => (
          <span key={s.key}>
            <svg width="26" height="8" aria-hidden="true">
              <line x1="0" x2="26" y1="4" y2="4" className={`series ${s.cls}`} strokeDasharray={s.dash} />
            </svg>{" "}
            {s.label}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
