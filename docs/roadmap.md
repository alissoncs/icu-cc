# Roadmap — from analysis library to coached training

> **Status: phases 1-5 built and verified end to end (2026-08-28).** Plan persistence,
> generation, the PT-BR intake skill, the web app and reconcile all exist and are tested.
> The one known gap is listed under "Still open" at the bottom.

This document is the single place that describes where the project is, where it is going,
and why. `CLAUDE.md` says how to work in the repo today; this says what we are building
next and in what order.

---

## Where we are (built and verified)

**Phase 0 — the analysis core.** Complete.

- `athlete.yaml` holds the athlete profile, now populated with real Intervals.icu values
  (FTP 228 W, 75.0 kg — 3.04 W/kg). Fields the API does not expose are marked
  `TODO placeholder`.
- Nine sources extracted into `docs/evidence-base.md`, tagged `[JEU14]`, `[SEI10]` and so
  on. Every prescribed number in the code traces to one.
- Eight `coach` subcommands: `profile`, `zones`, `fuel`, `session`, `pmc`, `tid`,
  `benchmark`, `taper`, `block`.
- 37 tests, all offline.
- MCP server configured and verified — 20 tools over stdio.
- **The load model is validated against the source of truth.** Seeded from Intervals.icu's
  own CTL/ATL on 2026-08-24 and fed four days of real activity load, `coach pmc` produced
  CTL 47.7 / ATL 53.6 against Intervals.icu's 47.66 / 53.57. The maths is right.

**What is missing is everything between "the agent can analyse" and "I know what to ride
on Tuesday."** Today a training plan exists only as text in a chat transcript. It is not
saved, not visible tomorrow, and not comparable against what was actually ridden.

---

## The target experience

The conversation that has to work, end to end:

> **Você:** quero treino para as próximas semanas
>
> **Agente:** *(em PT-BR)* Antes de montar, preciso de algumas informações:
> 1. Quantos dias por semana você consegue treinar?
> 2. Quantas horas no total, e quanto tempo em cada dia?
> 3. Quais dias da semana? Qual dia serve para o treino longo?
> 4. Tem alguma prova ou objetivo com data?
> 5. Quantas semanas você quer planejar?
>
> **Você:** 4 dias, umas 6 horas, ter/qui/sáb/dom, sábado o longo, sem prova, 4 semanas
>
> **Agente:** Plano de 4 semanas criado e salvo.
> → http://localhost:8010/plan/2026-w36-base

Three things have to become true for that to work: the agent must **ask** rather than
assume, the plan must be **persisted**, and there must be a **web app** that renders it.

---

## Architecture

```
Intervals.icu ──MCP──► Claude ──► planner.py ──► data/plans/*.json ──► FastAPI ──► browser
   (actuals)                       (generates)      (source of truth)     (renders)
                                                            │
                                                            └──MCP──► Intervals.icu calendar
                                                               (add_or_update_event, opt-in)
```

**The local JSON is the source of truth, not the Intervals.icu calendar.** The calendar is
a projection we push to, so the plan survives even if a calendar write fails or the user
edits events in the Intervals.icu UI. `plan_push` reconciles by storing the returned event
id on each session.

---

## Data model

`data/plans/<plan-id>.json`, e.g. `2026-w36-base.json`:

```json
{
  "id": "2026-w36-base",
  "created_at": "2026-08-28T21:40:00",
  "language": "pt-BR",
  "athlete": "alisson_cs",
  "ftp_at_creation": 228,
  "weight_at_creation": 75.0,
  "constraints": {
    "days_per_week": 4,
    "weekly_hours": 6.0,
    "days_available": ["tue", "thu", "sat", "sun"],
    "long_ride_day": "sat",
    "weeks": 4
  },
  "goal": null,
  "phase": "base",
  "rationale": "Pyramidal base block. No dated goal, so building durability [SEI10].",
  "weeks": [
    {
      "index": 1,
      "start_date": "2026-08-31",
      "kind": "load",
      "target_tss": 320,
      "target_hours": 6.0,
      "sessions": [
        {
          "date": "2026-09-01",
          "name": "Endurance Z2",
          "kind": "endurance",
          "duration_min": 90,
          "target_zone": "Z2",
          "target_watts": [125, 171],
          "planned_tss": 68,
          "description": "…",
          "fueling": { "carb_g_per_h": 30, "fluid_ml_per_h": 500, "sodium_mg_per_h": 400 },
          "status": "planned",
          "intervals_event_id": null,
          "actual": null
        }
      ]
    }
  ]
}
```

`status` moves `planned → completed | missed | modified`. `actual` is filled by a reconcile
step that matches activities to planned sessions by date, so the web app can show
**planned vs. done** rather than just intent.

Wattages are written as absolute numbers from `coach zones`, never as bare zone labels —
a rider on the road should not be doing arithmetic.

---

## Components to build

### 1. `src/cycling_coach/plans.py` — persistence

Dataclasses mirroring the schema, plus `save_plan`, `load_plan`, `list_plans`,
`current_week`, and `reconcile(plan, activities)`. No business logic; this is storage.

### 2. `src/cycling_coach/planner.py` — generation

`build_plan(profile, constraints) -> Plan`. This is where the evidence base becomes a
calendar. Rules it must enforce, all already documented in `docs/evidence-base.md`:

- **Intensity distribution** near 80/20 low/high `[SEI10]`; pyramidal in base, more
  polarized in build.
- **3 load weeks + 1 recovery week** `[FRI18]`. Non-negotiable — this is the rule athletes
  skip.
- **Ramp rate** within `training.max_ramp_rate`, seeded from current CTL so week 1 is not a
  cliff.
- **Hard days never adjacent**; long ride on `training.long_ride_day`; nothing scheduled on
  days not in `days_available`.
- **Weekly hours fit the constraint.** A plan needing 9 h from someone with 6 is not a plan.
- **Block option** — `--block` emits the Rønnestad structure (5 HIT sessions week 1, then 1
  per week) `[RON14]`, with its overreaching warning attached.
- **Taper** when a dated A goal falls inside the horizon `[MUJ03]`.
- Every session gets its fueling line from `fueling.py` when over 90 minutes.

Reuses `zones.power_zones`, `load.training_stress_score`, `periodization.*`,
`fueling.build_fuel_plan`. It should not reimplement any of that.

### 3. `src/cycling_coach/web/` — the app

**Stack: FastAPI + Jinja2 + uvicorn, server-rendered, charts as inline SVG.** No CDN, no
build step, no JavaScript framework — it runs offline and stays readable. Adds three
dependencies under an optional `[web]` extra so the core library stays lean.

Routes:

| Route | Shows |
|---|---|
| `GET /` | Dashboard: CTL/ATL/TSB, this week's sessions, compliance, next session |
| `GET /plan/{id}` | Full plan, week by week, planned vs. actual |
| `GET /plan/{id}/week/{n}` | One week in detail |
| `GET /session/{plan_id}/{date}` | Session detail: intervals, wattages, full fuel plan |
| `GET /api/plan/{id}` | The raw JSON, so the agent can read back what it wrote |

Launched with `coach serve --port 8010`.

Design notes: mobile-first (this gets read on a phone before a ride), dark mode, PT-BR
labels when `plan.language == "pt-BR"`. The PMC chart and the weekly TSS bars are the two
visuals that earn their place; resist adding more.

### 4. `.claude/skills/planejar-treino/SKILL.md` — the PT-BR intake

Triggers on Portuguese phrasing: "quero treino", "montar treino", "plano de treino",
"próximas semanas".

**It must ask before generating.** The questions, in PT-BR, via `AskUserQuestion`:

1. Quantos dias por semana você consegue treinar?
2. Quantas horas no total por semana?
3. Quais dias da semana? Qual é o dia do treino longo?
4. Tem alguma prova ou objetivo com data?
5. Quantas semanas quer planejar?

What it should *not* ask: anything already in `athlete.yaml` or fetchable from Intervals.icu.
It should read current CTL/ATL from `get_wellness_data` and recent consistency from
`get_activities` first, then ask only what it genuinely cannot know. Defaults from
`athlete.yaml` (`weekly_hours: 8`, `days_available`, `long_ride_day: sat`) should be offered
as the pre-filled answer, not re-asked from scratch.

Then: generate → save → print the URL → offer to push to the Intervals.icu calendar
(**confirm before writing**, per the existing guardrail).

### 5. CLI additions

```bash
coach plan create --spec spec.json     # from the skill's collected answers
coach plan list
coach plan show <id> [--week N]
coach plan reconcile <id> --activities acts.json
coach serve --port 8010
```

---

## Phasing

| Phase | Deliverable | Why this order |
|---|---|---|
| **1** | `plans.py` + schema + `coach plan create/list/show` | Nothing else can exist without persistence. Testable with a hand-written spec. |
| **2** | `planner.py` + tests | The hard part. Must be right before it is pretty — a plan that violates ramp rate or stacks hard days is worse than no plan. |
| **3** | `planejar-treino` skill (PT-BR) | Now the conversation has something to call. |
| **4** | `web/` app + `coach serve` | Now there is something worth rendering. |
| **5** | `reconcile` + planned-vs-actual in the UI | Closes the loop: the plan becomes a thing you are measured against. |

Phases 1–3 already give the full requested workflow minus the browser; phase 4 is what
makes it a product rather than a transcript.

---

## Open decisions

- **Session library vs. generated prose.** A fixed catalogue of session templates
  (`endurance_90`, `vo2_5x6`, `sweetspot_3x15`) is reproducible and testable; free-text
  generation is more adaptive but unverifiable. **Recommendation: catalogue**, with the
  agent free to write the coaching notes around it.
- **How far to push into Intervals.icu.** Writing every planned session to the calendar
  makes the phone app useful on the road, but clutters the calendar and makes deletion
  risky. **Recommendation: opt-in per plan, always confirmed, and store event ids so we can
  clean up exactly what we wrote.**
- **Language.** The skill is PT-BR; the code, docs and CLI stay English. Plan content
  (session names, descriptions) follows `plan.language`. Worth confirming that split is
  what you want before phase 3.

---

## What will not be built

- Anything that generates a goal weight or a weight-loss target. Standing guardrail in
  `CLAUDE.md`.
- Automatic calendar writes without confirmation.
- Plans that ignore the profile's ramp-rate ceiling because the athlete asked for more.
  The tool should say what it will not do and why, and let the athlete override explicitly.


---

## Status — what actually got built

All five phases are implemented. **124 tests pass.** Verified against live data rather
than fixtures:

- **Load model matches the source of truth.** Seeded from Intervals.icu's own CTL/ATL,
  `coach pmc` reproduced their 47.66 / 53.57 exactly.
- **Generated plan honours its constraints.** A 4-week, 6 h/week, 4-day base block landed
  on the requested days, put the long ride on Saturday, and came out **82.5% low /
  15.3% moderate / 2.2% high** — pyramidal, matching `[SEI10]` for a base block.
- **Reconcile closes the loop.** Against 7 real activities: 6 completed, 1 missed,
  86% compliance, 503 planned vs 492 actual TSS. A future-dated session was correctly
  left `planned`, and an activity with no reported load became `None` rather than `0`.

### Defects found and fixed during integration

Six, all found by testing rather than by reading:

| Where | Defect |
|---|---|
| `plans.py` | `list_plans` died on a valid-JSON-but-bad-data file, hiding every other plan |
| `plans.py` | `reconcile` marked a **future** session completed if an activity carried that date |
| `plans.py` | `compliance()` counted today's session as due from midnight, so aderência collapsed every morning |
| `plans.py` | `next_session()` kept advertising a session already ridden |
| `plans.py` | `actual["tss"]` conflated "not reported" with a genuine zero |
| `planner.py` | **No maintenance floor** — a plan could quietly detrain the athlete for a month with no warning |

The last one is the substantive one. The planner checked the ramp *ceiling* but never the
*floor*, so a 6 h/week block against a CTL of 47.7 projected CTL down to 44.3 and said
nothing. It now compares average weekly TSS against maintenance load (CTL x 7) and warns
with the actual numbers. Two earlier attempts at that check were wrong and are worth
recording: reading CTL on the **final day** condemns any block that correctly ends on a
recovery week, and reading the **peak** is useless when CTL only ever decays, because the
peak is then just the starting value.

## Still open

- **The dashboard's PMC is plan-derived, not a live feed.** `web/app.py::plan_pmc()` uses
  measured TSS for completed sessions and planned TSS for future ones, so it becomes
  progressively more real as a plan is reconciled — but it is not the same as reading
  wellness data from Intervals.icu. The chart says so. `plan_pmc` is the single function
  to replace when wiring the live feed.
- **`docs/papers/`** is missing `[JEU14]` and `[VIR20]` as PDFs — open access, but the
  publishers block scripted download. See that folder's README.
- **`starlette.testclient` deprecation** — it wants `httpx2` rather than `httpx`. Cosmetic;
  tests pass.
