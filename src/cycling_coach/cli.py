"""Command line entry point: `coach <subcommand>`.

Every subcommand accepts ``--json`` to emit machine-readable output instead of the
human-readable report, which is what the skills use when they need to reason over the
numbers rather than quote them.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .benchmarks import DURATION_LABELS, benchmark, profile_shape
from .fueling import build_fuel_plan
from .load import form_label, monotony_and_strain, pmc, ramp_rate
from .periodization import build_hit_block, build_taper, classify_distribution
from .plans import PlanError
from .profile import AthleteProfile, ProfileError, load_profile
from .session import analyze_session, zone_time_table
from .zones import hr_zones, power_zones


def _dump(obj: Any) -> str:
    def default(o: Any) -> Any:
        if is_dataclass(o) and not isinstance(o, type):
            return asdict(o)
        if isinstance(o, date):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, indent=2, default=default)


def _rule(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}"


def _load(args: argparse.Namespace) -> AthleteProfile:
    return load_profile(args.profile)


# --------------------------------------------------------------------------- profile
def cmd_profile(args: argparse.Namespace) -> int:
    p = _load(args)
    if args.json:
        print(_dump(p))
        return 0

    print(_rule(f"{p.name}"))
    age = f"{p.age} y" if p.age else "age unknown"
    print(f"{age}, {p.height_cm:.0f} cm, {p.weight_kg:.1f} kg, {p.sex}")
    print(f"FTP {p.ftp_w:.0f} W ({p.ftp_wkg:.2f} W/kg) via {p.ftp_source}")
    if p.ftp_age_days is not None:
        print(f"  last updated {p.ftp_updated} ({p.ftp_age_days} days ago)")
    if p.lthr:
        print(f"LTHR {p.lthr} bpm, max HR {p.max_hr}, resting {p.resting_hr}")
    print(f"Training: {p.weekly_hours} h/week, {p.discipline}, max ramp {p.max_ramp_rate} TSS/d")
    print(
        f"Fueling ceiling: {p.gut_trained_carb_g_per_h:.0f} g/h demonstrated; sweat "
        f"{p.sweat_rate_l_per_h} L/h at {p.sweat_sodium_mg_per_l:.0f} mg/L "
        f"({'measured' if p.sweat_measured else 'ESTIMATED'})"
    )

    if p.goals:
        print(_rule("Goals"))
        for g in sorted(p.goals, key=lambda x: (x.date is None, x.date)):
            out = f" ({g.days_out} days out)" if g.days_out is not None and g.days_out >= 0 else ""
            print(f"  [{g.priority}] {g.date} {g.name} — {g.type}{out}")

    warns = p.warnings()
    if warns:
        print(_rule("Data quality"))
        for w in warns:
            print(f"  ! {w}")
    return 0


# ----------------------------------------------------------------------------- zones
def cmd_zones(args: argparse.Namespace) -> int:
    p = _load(args)
    pz = power_zones(p.ftp_w)
    payload: dict[str, Any] = {"ftp_w": p.ftp_w, "power": pz}

    if args.json:
        if p.lthr:
            payload["hr"] = hr_zones(p.lthr)
        print(_dump(payload))
        return 0

    print(_rule(f"Power zones — FTP {p.ftp_w:.0f} W [COG19]"))
    for z in pz:
        pct = (
            f"{z.low_pct * 100:.0f}-{z.high_pct * 100:.0f}%"
            if z.high_pct
            else f">{z.low_pct * 100:.0f}%"
        )
        print(f"  {z.key:<4} {z.name:<22} {z.range_str:<14} {pct}")

    if p.lthr:
        print(_rule(f"HR zones — LTHR {p.lthr} bpm [FRI18]"))
        for z in hr_zones(p.lthr):
            rng = f"{z.low_w}-{z.high_w} bpm" if z.high_w else f"{z.low_w}+ bpm"
            print(f"  {z.key:<4} {rng}")

    print(
        "\nZone edges are estimates from a field-test proxy for LT2, not measured "
        "thresholds. Methods disagree and protocols shift the answer [JAM20]."
    )
    return 0


# ------------------------------------------------------------------------------ fuel
def cmd_fuel(args: argparse.Namespace) -> int:
    p = _load(args)
    plan = build_fuel_plan(
        p,
        duration_h=args.duration,
        intensity_factor=args.intensity,
        temp_c=args.temp,
        humidity_pct=args.humidity,
        is_race=args.race,
    )
    if args.json:
        print(_dump(plan))
        return 0

    print(
        _rule(
            f"Fuel plan — {plan.duration_h:.1f} h at IF {plan.intensity_factor:.2f}, "
            f"{plan.temp_c:.0f} °C / {plan.humidity_pct:.0f}% RH"
            + (" [RACE]" if args.race else "")
        )
    )
    print(f"  Carbohydrate   {plan.carb_g_per_h:.0f} g/h  ({plan.carb_total_g:.0f} g total)")
    print(f"                 type: {plan.carb_type}")
    if plan.carb_uncapped_g_per_h != plan.carb_g_per_h:
        print(f"                 (uncapped target was {plan.carb_uncapped_g_per_h:.0f} g/h)")
    print(f"  Fluid          {plan.fluid_ml_per_h:.0f} mL/h ({plan.fluid_total_ml:.0f} mL total)")
    print(
        f"                 est. sweat {plan.sweat_rate_l_per_h:.2f} L/h "
        f"= {plan.sweat_loss_ml:.0f} mL lost"
    )
    print(
        f"  Sodium         {plan.sodium_mg_per_h:.0f} mg/h ({plan.sodium_total_mg:.0f} mg "
        f"total, {plan.sodium_replacement_pct:.0f}% of loss)"
    )
    if plan.sodium_mg_per_l:
        print(f"                 = {plan.sodium_mg_per_l:.0f} mg/L if taken in the bottles")
    if plan.caffeine_mg:
        print(f"  Caffeine       {plan.caffeine_mg:.0f} mg pre-ride")
    print(f"  Pre-ride       {plan.pre_ride_carb_g:.0f} g carbohydrate")
    print(
        f"  Recovery       {plan.post_ride_carb_g:.0f} g carbohydrate + "
        f"{plan.post_ride_protein_g:.0f} g protein"
    )

    if plan.notes:
        print(_rule("Notes"))
        for n in plan.notes:
            print(f"  - {n}")
    if plan.warnings:
        print(_rule("Warnings"))
        for w in plan.warnings:
            print(f"  ! {w}")
    return 0


# --------------------------------------------------------------------------- session
def cmd_session(args: argparse.Namespace) -> int:
    p = _load(args)
    raw = json.loads(Path(args.activity).read_text())
    if isinstance(raw, list):
        raw = raw[0]
    a = analyze_session(raw, p, tsb=args.tsb)

    if args.json:
        print(_dump(a))
        return 0

    print(_rule(f"{a.name} — {a.date or 'undated'} ({a.type})"))
    bits = [f"{a.duration_h:.2f} h"]
    if a.distance_km:
        bits.append(f"{a.distance_km:.1f} km")
    if a.elevation_m:
        bits.append(f"{a.elevation_m:.0f} m up")
    if a.kj:
        bits.append(f"{a.kj:.0f} kJ")
    print("  " + " | ".join(bits))

    stats = []
    if a.avg_power_w:
        stats.append(f"avg {a.avg_power_w:.0f} W")
    if a.np_w:
        stats.append(f"NP {a.np_w:.0f} W")
    if a.avg_hr:
        stats.append(f"HR {a.avg_hr:.0f} bpm")
    if a.tss:
        stats.append(f"{a.tss:.0f} TSS")
    if stats:
        print("  " + " | ".join(stats))

    if a.zone_times:
        print(_rule("Time in zone"))
        for row in zone_time_table(a.zone_times, p.ftp_w):
            print(
                f"  {row['zone']:<4} {row['name']:<22} {row['range_w']:<12} "
                f"{row['minutes']:>6.1f} min  {row['pct']:>5.1f}%"
            )

    print(_rule("Findings"))
    for f in a.findings:
        print(f"  - {f}")
    if a.flags:
        print(_rule("Flags"))
        for f in a.flags:
            print(f"  ! {f}")
    return 0


# ------------------------------------------------------------------------------- pmc
def cmd_pmc(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.loads).read_text())
    daily = {date.fromisoformat(k): float(v) for k, v in raw.items()}
    points = pmc(daily, ctl_seed=args.ctl_seed, atl_seed=args.atl_seed)
    if not points:
        print("No load data.", file=sys.stderr)
        return 1

    last = points[-1]
    recent = [p.load for p in points[-7:]]
    mono, strain = monotony_and_strain(recent)
    rr = ramp_rate(points)

    payload = {
        "date": last.day,
        "ctl": last.ctl,
        "atl": last.atl,
        "tsb": last.tsb,
        "form": form_label(last.tsb),
        "ramp_rate_7d": rr,
        "week_load": round(sum(recent)),
        "monotony": mono,
        "strain": strain,
        "series": points if args.full else points[-14:],
    }
    if args.json:
        print(_dump(payload))
        return 0

    print(_rule(f"Performance Management Chart — through {last.day}"))
    print(f"  CTL (fitness)  {last.ctl:.1f}")
    print(f"  ATL (fatigue)  {last.atl:.1f}")
    print(f"  TSB (form)     {last.tsb:+.1f} — {form_label(last.tsb)}")
    print(f"  7d ramp rate   {rr:+.1f} CTL/week")
    print(f"  7d load        {sum(recent):.0f} TSS")
    print(f"  Monotony       {mono:.2f} (strain {strain:.0f})")

    notes = []
    p = _load(args)
    if rr > p.max_ramp_rate:
        notes.append(
            f"Ramp rate {rr:+.1f} exceeds your profile limit of {p.max_ramp_rate}. "
            "Sustained ramps this steep are where illness and injury cluster."
        )
    if mono > 2.0:
        notes.append(
            f"Monotony {mono:.2f} is high — the week has no real hard/easy separation. "
            "Same load with sharper contrast adapts better."
        )
    if last.tsb < -30:
        notes.append("TSB below -30. Take the recovery before it takes you.")
    if notes:
        print(_rule("Flags"))
        for n in notes:
            print(f"  ! {n}")
    return 0


# ------------------------------------------------------------------------------- tid
def cmd_tid(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.zones_file).read_text())
    dist = classify_distribution(raw)
    if args.json:
        print(_dump(dist))
        return 0

    print(_rule(f"Intensity distribution — {dist.total_hours:.1f} h"))
    print(f"  Low       {dist.low_pct:>5.1f}%")
    print(f"  Moderate  {dist.moderate_pct:>5.1f}%")
    print(f"  High      {dist.high_pct:>5.1f}%")
    print(f"\n  Model: {dist.model}")
    print(f"  {dist.assessment}")
    if dist.notes:
        print(_rule("Notes"))
        for n in dist.notes:
            print(f"  - {n}")
    return 0


# ------------------------------------------------------------------------- benchmark
def cmd_benchmark(args: argparse.Namespace) -> int:
    p = _load(args)
    inputs = {
        "5s": args.p5s,
        "1min": args.p1min,
        "5min": args.p5min,
        "ftp": args.ftp if args.ftp else p.ftp_w,
    }
    results = [
        benchmark(d, w, p.weight_kg, p.sex) for d, w in inputs.items() if w
    ]
    if args.json:
        print(_dump({"results": results, "shape": profile_shape(results)}))
        return 0

    print(_rule(f"Power profile — {p.weight_kg:.1f} kg, {p.sex}"))
    for r in results:
        line = f"  {DURATION_LABELS[r.duration]:<28} {r.watts:>5.0f} W  {r.wkg:>5.2f} W/kg  {r.category}"
        if r.watts_to_next:
            line += f"  (+{r.watts_to_next:.0f} W -> {r.next_category})"
        print(line)
    print(f"\n  {profile_shape(results)}")
    print(
        "\n  Bands are coarse approximations for orientation, not the published Coggan "
        "chart. Use them to see shape, not to award yourself a category."
    )
    return 0


# ----------------------------------------------------------------------------- taper
def cmd_taper(args: argparse.Namespace) -> int:
    p = _load(args)
    days_out = args.days_out
    if days_out is None:
        goal = p.next_goal("A") or p.next_goal(None)
        if goal is None or goal.days_out is None:
            print("No dated A goal in athlete.yaml; pass --days-out.", file=sys.stderr)
            return 1
        days_out = goal.days_out
        print(f"Tapering to '{goal.name}' on {goal.date} ({days_out} days out).")

    plan = build_taper(p, days_out)
    if args.json:
        print(_dump(plan))
        return 0

    print(_rule(f"Taper — {plan.taper_days} days [MUJ03]"))
    for w in plan.weeks:
        print(
            f"  {w['week']}: {w['target_hours']} h "
            f"(-{w['volume_cut_pct']}% volume), {w['frequency']}"
        )
        print(f"       intensity: {w['intensity']}")
    print(
        f"\n  Expected gain: {plan.expected_gain_pct[0]}-{plan.expected_gain_pct[1]}% "
        "(~3% typical)."
    )
    print(_rule("Principles"))
    for pr in plan.principles:
        print(f"  - {pr}")
    if plan.warnings:
        print(_rule("Warnings"))
        for w in plan.warnings:
            print(f"  ! {w}")
    return 0


# ----------------------------------------------------------------------------- block
def cmd_block(args: argparse.Namespace) -> int:
    p = _load(args)
    plan = build_hit_block(p)
    if args.json:
        print(_dump(plan))
        return 0

    print(_rule("4-week block-periodized HIT mesocycle [RON14]"))
    for w in plan.weeks:
        print(f"  Week {w['week']} — {w['label']}: {w['hit_sessions']} HIT session(s)")
        print(f"       {w['session']}")
        print(f"       {w['note']}")
    print(_rule("Rationale"))
    print(f"  {plan.rationale}")
    print(_rule("Warnings"))
    for w in plan.warnings:
        print(f"  ! {w}")
    return 0


# ------------------------------------------------------------------------------ plan
def cmd_plan_create(args: argparse.Namespace) -> int:
    """Generate and persist a training plan from a spec the intake skill collected."""
    from .planner import build_plan
    from .plans import Constraints, save_plan

    p = _load(args)
    spec = json.loads(Path(args.spec).read_text())

    plan = build_plan(
        p,
        Constraints.from_dict(spec),
        phase=spec.get("phase", "base"),
        goal=spec.get("goal"),
        start_date=date.fromisoformat(spec["start_date"]) if spec.get("start_date") else None,
        current_ctl=float(spec.get("current_ctl", 0.0)),
        use_block=bool(spec.get("use_block", False)),
        language=spec.get("language", "pt-BR"),
    )
    path = save_plan(plan, args.plans_root)

    if args.json:
        print(_dump({"id": plan.id, "path": str(path), "plan": plan.to_dict()}))
        return 0

    print(f"Saved plan '{plan.id}' -> {path}")
    print(f"  {len(plan.weeks)} weeks, {plan.total_hours} h, {plan.total_tss} TSS")
    print(f"  {plan.start_date} to {plan.end_date}, phase '{plan.phase}'")
    if plan.rationale:
        print(f"  {plan.rationale}")
    for w in plan.warnings:
        print(f"  ! {w}")
    print(f"\n  View: http://localhost:8010/plan/{plan.id}  (run: coach serve)")
    return 0


def cmd_plan_list(args: argparse.Namespace) -> int:
    from .plans import list_plans

    plans = list_plans(args.plans_root)
    if args.json:
        print(_dump([{"id": p.id, "phase": p.phase, "weeks": len(p.weeks),
                      "start": p.start_date, "hours": p.total_hours} for p in plans]))
        return 0
    if not plans:
        print("No plans yet. Create one with: coach plan create --spec spec.json")
        return 0
    print(_rule("Plans"))
    for p in plans:
        c = p.compliance()
        done = f"{c['pct']}% done" if c["pct"] is not None else "not started"
        print(f"  {p.id:<24} {p.phase:<10} {len(p.weeks)}w  {p.total_hours:>5.1f} h  "
              f"{p.start_date} -> {p.end_date}  ({done})")
    return 0


def cmd_plan_show(args: argparse.Namespace) -> int:
    from .plans import load_plan

    plan = load_plan(args.id, args.plans_root)
    if args.json:
        print(_dump(plan.to_dict()))
        return 0

    weeks = [w for w in plan.weeks if args.week is None or w.index == args.week]
    if not weeks:
        print(f"Plan '{plan.id}' has no week {args.week}.", file=sys.stderr)
        return 1

    print(_rule(f"{plan.id} — {plan.phase}, {len(plan.weeks)} weeks"))
    if plan.rationale:
        print(f"  {plan.rationale}")
    for w in weeks:
        print(_rule(f"Week {w.index} ({w.kind}) — {w.start_date} to {w.end_date} "
                    f"| {w.planned_hours} h, {w.planned_tss:.0f} TSS"))
        if w.note:
            print(f"  {w.note}")
        for s in sorted(w.sessions, key=lambda x: x.date):
            watts = f"{s.target_watts[0]}-{s.target_watts[1]} W" if s.target_watts else "-"
            mark = {"completed": "[x]", "missed": "[!]", "modified": "[~]"}.get(s.status, "[ ]")
            print(f"  {mark} {s.date} {s.name:<28} {s.duration_min:>4} min  "
                  f"{watts:<14} {(s.planned_tss or 0):>5.0f} TSS")
            if s.description:
                print(f"        {s.description}")
    for w in plan.warnings:
        print(f"\n  ! {w}")
    return 0


def cmd_plan_reconcile(args: argparse.Namespace) -> int:
    """Match completed activities onto planned sessions, so plan vs. actual is real."""
    from .plans import load_plan, reconcile, save_plan

    plan = load_plan(args.id, args.plans_root)
    raw = json.loads(Path(args.activities).read_text())
    activities = raw if isinstance(raw, list) else [raw]
    summary = reconcile(plan, activities)
    save_plan(plan, args.plans_root)

    if args.json:
        print(_dump(summary))
        return 0
    c = summary["compliance"]
    print(_rule(f"Reconciled '{plan.id}' against {len(activities)} activities"))
    print(f"  marked completed: {summary['completed']}")
    print(f"  marked missed:    {summary['missed']}")
    if c["pct"] is not None:
        print(f"  compliance:       {c['completed']}/{c['due']} ({c['pct']}%)")
        print(f"  TSS planned {c['planned_tss']:.0f} vs actual {c['actual_tss']:.0f}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
        from .web.app import create_app
    except ImportError:
        print('Web extra not installed. Run: pip install -e ".[web]"', file=sys.stderr)
        return 2

    print(f"Serving on http://{args.host}:{args.port}  (Ctrl-C to stop)")
    uvicorn.run(create_app(args.plans_root), host=args.host, port=args.port, log_level="warning")
    return 0


# ------------------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="coach", description=__doc__)
    ap.add_argument("--profile", default=None, help="path to athlete.yaml")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--plans-root", default=None, help="plan storage dir (default data/plans)")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("profile", help="show the athlete profile and data-quality warnings").set_defaults(func=cmd_profile)
    sub.add_parser("zones", help="power and HR training zones").set_defaults(func=cmd_zones)

    f = sub.add_parser("fuel", help="carbohydrate, fluid and sodium plan for a session")
    f.add_argument("--duration", type=float, required=True, help="hours")
    f.add_argument("--intensity", type=float, default=0.70, help="intensity factor, 0-1.2")
    f.add_argument("--temp", type=float, default=18.0, help="degrees C")
    f.add_argument("--humidity", type=float, default=50.0, help="percent")
    f.add_argument("--race", action="store_true", help="apply race-day carb targets")
    f.set_defaults(func=cmd_fuel)

    s = sub.add_parser("session", help="analyze one activity from a JSON file")
    s.add_argument("activity", help="path to activity JSON")
    s.add_argument("--tsb", type=float, default=None, help="TSB going into the session")
    s.set_defaults(func=cmd_session)

    m = sub.add_parser("pmc", help="CTL/ATL/TSB from a {date: load} JSON file")
    m.add_argument("loads", help="path to daily load JSON")
    m.add_argument("--ctl-seed", type=float, default=0.0)
    m.add_argument("--atl-seed", type=float, default=0.0)
    m.add_argument("--full", action="store_true", help="emit the whole series, not 14 days")
    m.set_defaults(func=cmd_pmc)

    t = sub.add_parser("tid", help="classify intensity distribution from zone seconds")
    t.add_argument("zones_file", help='path to {"Z1": secs, ...} JSON')
    t.set_defaults(func=cmd_tid)

    b = sub.add_parser("benchmark", help="place power numbers against category bands")
    b.add_argument("--5s", dest="p5s", type=float, default=None)
    b.add_argument("--1min", dest="p1min", type=float, default=None)
    b.add_argument("--5min", dest="p5min", type=float, default=None)
    b.add_argument("--ftp", type=float, default=None, help="defaults to profile FTP")
    b.set_defaults(func=cmd_benchmark)

    tp = sub.add_parser("taper", help="generate a taper into an event")
    tp.add_argument("--days-out", type=int, default=None, help="defaults to next A goal")
    tp.set_defaults(func=cmd_taper)

    sub.add_parser("block", help="4-week block-periodized HIT mesocycle").set_defaults(func=cmd_block)

    # -- plan: generate, inspect and reconcile persisted training plans --------
    pl = sub.add_parser("plan", help="create, list, show and reconcile training plans")
    plsub = pl.add_subparsers(dest="plan_command", required=True)

    pc = plsub.add_parser("create", help="generate a plan from a spec JSON file")
    pc.add_argument("--spec", required=True, help="path to the constraints spec")
    pc.set_defaults(func=cmd_plan_create)

    plsub.add_parser("list", help="list saved plans").set_defaults(func=cmd_plan_list)

    ps = plsub.add_parser("show", help="print a saved plan")
    ps.add_argument("id")
    ps.add_argument("--week", type=int, default=None, help="only this week")
    ps.set_defaults(func=cmd_plan_show)

    pr = plsub.add_parser("reconcile", help="match activities onto planned sessions")
    pr.add_argument("id")
    pr.add_argument("--activities", required=True, help="path to activities JSON")
    pr.set_defaults(func=cmd_plan_reconcile)

    sv = sub.add_parser("serve", help="run the web app")
    sv.add_argument("--port", type=int, default=8010)
    sv.add_argument("--host", default="127.0.0.1")
    sv.set_defaults(func=cmd_serve)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ProfileError as exc:
        print(f"Profile error: {exc}", file=sys.stderr)
        return 2
    except PlanError as exc:
        print(f"Plan error: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
