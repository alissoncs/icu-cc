---
name: planejar-treino
description: Ask the athlete, in Brazilian Portuguese, for the few constraints that cannot be read from data, then generate, save and render a multi-week training plan and optionally push it to the Intervals.icu calendar. Use when the user writes in Portuguese and asks for training — "quero treino", "montar treino", "plano de treino", "treino para as próximas semanas", "próximas semanas".
---

# Planejar treino (PT-BR)

The intake for a persisted plan. `plan-block` reasons about structure; this one runs the
conversation, collects the constraints, writes `data/plans/<id>.json` and hands back a URL.

**Language split.** Everything the athlete reads is PT-BR: the questions, the session names,
the descriptions, the summary. Code, CLI invocations, CLI output, JSON keys and file
contents stay English. `plan.language` is `"pt-BR"`.

## 1. Descubra antes de perguntar

Never ask for something you can already know. Before the first question:

```bash
.venv/bin/coach profile           # weekly_hours, days_available, long_ride_day, FTP, ramp ceiling, goals
```

```
get_wellness_data   last ~7 days — current CTL and ATL, so week 1 is not a cliff
get_activities      last 4-6 weeks — real hours/week and how consistent they actually are
get_events          anything already on the calendar in the horizon, so you do not double-book
```

Two things matter out of this. **Current CTL** anchors week 1 — a plan seeded from zero
ramps into a hole. **Recent actual hours** are the honest number: if the profile says 8 h
and the last month averaged 5 h, offer 5-6 h and say why. The profile is intent; the
activities are evidence.

## 2. Pergunte o resto — em PT-BR, com `AskUserQuestion`

Five things you genuinely cannot know. Batch them (up to 4 questions per call, so one call
plus a short follow-up), and **pre-fill the profile value as the recommended option** rather
than asking from a blank slate:

1. Quantos dias por semana você consegue treinar?
2. Quantas horas no total por semana?
3. Quais dias da semana? Qual é o dia do treino longo?
4. Tem alguma prova ou objetivo com data?
5. Quantas semanas quer planejar?

Shape of one question — the profile value first, marked as such, with the reason in the
description:

```
question: "Quantas horas no total por semana?"
header:   "Horas"
options:
  - label: "8 h (seu perfil)"
    description: "É o que está no athlete.yaml. Nas últimas 4 semanas você fez 6,2 h/sem."
  - label: "6 h"
    description: "Mais próximo do que você vem fazendo de verdade. Mais fácil de cumprir."
  - label: "10 h"
    description: "Aumento real de volume. Só se as últimas semanas foram consistentes."
```

Same pattern for the rest: `days_available: [mon…sun]` and `long_ride_day: sat` become
"Sábado (seu perfil)" and "Ter/Qui/Sáb/Dom", "4 semanas" is the default horizon (3 de carga
+ 1 de recuperação `[FRI18]`), and "Sem prova por enquanto" is a valid first option for the
goal — do not invent an event. The free-text "Other" path is always there; if they answer in
prose ("4 dias, umas 6 horas, ter/qui/sáb/dom, sábado o longo"), just parse it and skip the
questions you already have.

## 3. Gere e salve

Write the collected answers into a spec, then:

```bash
cat > /tmp/.../spec.json <<'JSON'
{
  "days_per_week": 4,
  "weekly_hours": 6.0,
  "days_available": ["tue", "thu", "sat", "sun"],
  "long_ride_day": "sat",
  "weeks": 4,
  "goal": null,
  "start_ctl": 47.7,
  "language": "pt-BR"
}
JSON
.venv/bin/coach plan create --spec /tmp/.../spec.json
```

That writes `data/plans/<id>.json` — e.g. `2026-w36-base.json` — and prints the id. The
local JSON is the source of truth, not the calendar.

## 4. Apresente

```
→ http://localhost:8010/plan/2026-w36-base
```

If the server is not up, tell them to run `.venv/bin/coach serve --port 8010` in another
terminal. Then summarise **in PT-BR**, short, with the tags:

- quantas semanas e qual a fase (base / build / especialidade / taper);
- as horas semanais e os dias;
- **onde cai a semana de recuperação** — nomeie a semana, é a que o atleta pula `[FRI18]`;
- o porquê: distribuição perto de 80/20 `[SEI10]`, rampa dentro de `max_ramp_rate`, dias
  duros nunca colados, longo no sábado;
- quaisquer `warnings` que o plano trouxer — não os engula.

Wattages are absolute numbers from `coach zones`, never bare zone labels: nobody does
arithmetic on the road.

## 5. Ofereça o calendário

Opt-in, per plan. `add_or_update_event` once per session, with the PT-BR name and
description and the fueling line on anything over 90 minutes.

**Confirme antes de escrever.** Standing guardrail in `CLAUDE.md`: show exactly what will be
created — how many events, which dates, the first one in full — and get an explicit yes.
Check `get_events` first so you do not double-book. Store the returned event id back on the
session as `intervals_event_id` and re-save the plan; that is what lets us later clean up
exactly what we wrote and nothing else.

## Cautions

- **Não estoure a rampa porque pediram.** If the requested hours or weeks imply a CTL ramp
  above `training.max_ramp_rate`, say plainly what you will not do and why — sustained ramps
  past ~5-7 CTL/week are where illness and injury cluster — offer the version that fits, and
  let them override explicitly if they still want it. Record the override in `warnings`.
- **A plan that does not fit their real hours is not a plan.** 9 h of work for someone with
  6 h is a plan that fails in week 2 and takes the athlete's confidence with it. Fit the
  constraint, then make the constrained week as good as it can be.
- **Re-check FTP staleness before writing wattages.** If `physiology.ftp_updated` is more
  than 6-8 weeks old, say so and build a test into week 1 instead of prescribing from a
  stale number. Zone edges are estimates either way `[JAM20]`.
- **Never generate a goal weight or a weight-loss target**, even if it comes up as a way to
  raise W/kg. Explain that under-fuelling costs more power than the mass saves, that RED-S is
  a real injury in endurance cycling, and refer them to a sports dietitian.
- **Confirm before any calendar write, and again before any delete.**
  `delete_events_by_date_range` removes real planned work.
- Plans are hypotheses. Say in PT-BR what you expect to see in 2 weeks, so it can be checked
  — then check it with `/weekly-review` and `coach plan reconcile`.
