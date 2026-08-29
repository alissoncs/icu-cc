# Intervals.icu Cycling Coach

A Python analysis layer plus a set of Claude skills that turn Intervals.icu training data
into coaching insight: session reads, weekly reviews, evidence-based fueling plans,
benchmarking, and periodized training blocks.

Claude is the coach. This repo is the part of the coach that must be **consistent,
reproducible and traceable to a source** — the maths, the guardrails, and the athlete's own
data. Judgement, context and the conversation stay with Claude.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest        # 37 tests, all offline
```

### The MCP server

[mvilanova/intervals-mcp-server](https://github.com/mvilanova/intervals-mcp-server) is a
separate repo, cloned at `~/projects/intervals-mcp-server`. It has **no console script**,
so it is launched by running `server.py` directly — `MCP_TRANSPORT` defaults to stdio, which
is what Claude Code wants.

```bash
cd ~/projects/intervals-mcp-server
python3 -m venv .venv && .venv/bin/pip install -e .
```

Then copy `.mcp.json.example` to `.mcp.json` and fill in the absolute paths, your API key
and athlete ID. Absolute paths matter — relative ones produce the `spawn ... ENOENT` class
of failure the server's README warns about.

Upstream documents a `uv`-based setup instead. That also works, but is not required; the
plain venv above avoids installing extra system tooling. If dependencies ever fail to build
on your Python, fall back to `brew install uv` and `uv venv --python 3.12 && uv sync`.

Verify before trusting it — a stdio handshake, not just an import:

```bash
printf '%s\n%s\n%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 | API_KEY=<key> ATHLETE_ID=<id> .venv/bin/python src/intervals_mcp_server/server.py
```

Expect `serverInfo` and 20 tools. `.mcp.json` is gitignored because it holds credentials —
never commit it, and never echo the API key into the transcript.

Finally, fill in `athlete.yaml`. Every calculation reads it. Fields marked `TODO
placeholder` are guesses and will skew output until you replace them.

## How the pieces fit

```
Intervals.icu ──MCP tools──► Claude ──JSON──► coach CLI ──numbers──► Claude ──► the user
                (text out)            (you write it)   (deterministic)   (judgement)
```

**The MCP tools return formatted text, not JSON.** This is the one piece of friction worth
knowing up front. The workflow is always:

1. Call the MCP tool (`get_activities`, `get_activity_details`, …).
2. Read the numbers out of the text it returns.
3. Write them into a JSON file in your scratchpad.
4. Run the relevant `coach` subcommand against it.
5. Interpret the output in prose.

`src/cycling_coach/session.py::normalize` is deliberately tolerant about field names and
accepts both `{"Z1": 600}` and Intervals.icu's list-of-dicts zone form, so you do not have
to match the schema exactly.

## The CLI

`coach` lives in the project venv, not on your PATH. Either prefix it or activate the venv
once per shell:

```bash
.venv/bin/coach profile          # explicit, always works
source .venv/bin/activate        # then plain `coach ...` for the rest of the session
```

The commands below are written bare for readability; prefix them with `.venv/bin/` unless
the venv is active.

```bash
coach profile                                              # profile + data-quality warnings
coach zones                                                # power [COG19] and HR [FRI18] zones
coach fuel --duration 4.5 --intensity 0.72 --temp 27 --race
coach session activity.json --tsb -18
coach pmc daily_load.json --ctl-seed 55 --atl-seed 55      # CTL/ATL/TSB, ramp, monotony
coach tid zone_seconds.json                                # polarized / pyramidal / threshold
coach benchmark --5s 1050 --1min 610 --5min 330
coach taper                                                # to the next A goal [MUJ03]
coach block                                                # 4-week HIT mesocycle [RON14]

coach plan create --spec spec.json                         # generate + persist a plan
coach plan list
coach plan show <id> [--week N]
coach plan reconcile <id> --activities acts.json           # planned vs. actual
coach serve --port 8010                                    # the web app
```

Plans persist to `data/plans/<id>.json`. **That file is the source of truth, not the
Intervals.icu calendar** — the calendar is an opt-in projection we push to, so a plan
survives a failed write or a manual edit. `examples/plan_spec.json` is a working spec.

Every subcommand takes `--json` for machine-readable output — use it when you need to
reason over the numbers, and the plain output when you are going to quote them.
`examples/` has working input files for `session` and `pmc`.

## Layout

| Path | What it holds |
|---|---|
| `athlete.yaml` | The athlete profile. Single source of truth for every calculation. |
| `docs/evidence-base.md` | **Read this.** Every source, with the numbers extracted. |
| `docs/roadmap.md` | Where the project is going: plan persistence, the web app, the PT-BR intake. |
| `docs/papers/` | Local PDFs of the sources, plus a manifest of what is missing and why. |
| `docs/sweat-test.md` | How to measure sweat rate and sodium, and why it matters. |
| `src/cycling_coach/profile.py` | Loads and validates `athlete.yaml`. The only file that touches it. |
| `src/cycling_coach/zones.py` | Coggan 7-zone power, Friel HR, Seiler 3-zone. |
| `src/cycling_coach/fueling.py` | Carbohydrate, fluid and sodium model. |
| `src/cycling_coach/load.py` | NP, IF, TSS, PMC, ramp rate, monotony. |
| `src/cycling_coach/periodization.py` | Intensity distribution, taper, block periodization. |
| `src/cycling_coach/benchmarks.py` | Power-profile category bands. |
| `src/cycling_coach/session.py` | Single-activity analysis. |
| `src/cycling_coach/plans.py` | Plan persistence and reconcile. Storage only. |
| `src/cycling_coach/planner.py` | Plan generation: the fixed session catalogue and the scheduling rules. |
| `src/cycling_coach/web/` | FastAPI + Jinja2 dashboard. Server-rendered, inline SVG, no CDN. |
| `.claude/skills/` | The five coaching workflows. |

## Skills

| Skill | Use it when |
|---|---|
| `analyze-session` | "How was yesterday's ride?" — one activity, in depth. |
| `fuel-plan` | "What should I eat for Saturday?" — carbs, fluid, sodium, timing. |
| `weekly-review` | "How was my week?" — load, distribution, ramp, consistency. |
| `plan-block` | "What should I do for the next 6 weeks?" — plans and calendar writes. |
| `benchmark-vs-pros` | "How do I stack up?" — power profile and professional context. |
| `planejar-treino` | **PT-BR.** "Quero treino para as próximas semanas" — asks the athlete in Portuguese, then generates, saves and renders a plan. |

## The evidence base

Nine sources, tagged in code comments and in skill output. Full extraction with numbers is
in `docs/evidence-base.md`.

**Fueling** — `[JEU14]` Jeukendrup 2014 (duration-scaled carbs, the 60 g/h single-transporter
ceiling, multiple transportable carbohydrates) · `[BUR11]` Burke et al. 2011 (daily g/kg
targets, carbohydrate availability) · `[VIR20]` Viribay et al. 2020 (120 g/h, reduced muscle
damage, and the gut-training prerequisite).

**Training** — `[COG19]` Allen, Coggan & McGregor 2019 (FTP, 7 zones, NP/IF/TSS) ·
`[SEI10]` Seiler 2010 (polarized 80/20, the threshold black hole) · `[FRI18]` Friel 2018
(periodization, HR zones, event priority) · `[MUJ03]` Mujika & Padilla 2003 (tapering) ·
`[JAM20]` Jamnick et al. 2020 (threshold methodology, why zones are estimates) ·
`[RON14]` Rønnestad & Hansen 2014 (block periodization).

**When you prescribe something, name the tag.** It is what separates coaching from opinion,
and it lets the user check you.

## Conventions

- **Carbohydrate during exercise is prescribed in g/h, never g/kg/h.** `[JEU14]` found no
  correlation between body mass and exogenous carbohydrate oxidation. Body mass is used for
  fluid and for pre/post-ride carbohydrate only.
- **Ranges stay ranges.** Where the literature gives 0.5-6.0%, the code carries 0.5-6.0%
  and picks within it from the profile. Do not invent precision the sources do not have.
- **Zone boundaries are estimates.** FTP is a field proxy for LT2, not LT2 `[JAM20]`. Never
  present a zone edge as physiological truth.
- **Data-quality warnings propagate.** If `sweat.measured` is false or FTP is stale, the
  tools say so. Carry that through to the user rather than quietly dropping it.
- New numbers need a source in `docs/evidence-base.md` and a test in `tests/`.

## Guardrails

These are not optional, and they matter more than any analysis in this repo.

- **Never generate a goal weight or a weight-loss target.** If the user raises weight to
  raise W/kg, explain that under-fuelling costs more power than the mass saves, that RED-S
  is a real and common injury in endurance cycling, and refer them to a sports dietitian.
  Do not do the arithmetic for them.
- **This is sports nutrition and coaching for a healthy athlete, not medicine.** Medical
  conditions, medication, disordered eating, chest pain, or unexplained persistent fatigue
  go to a physician. Say so plainly and once, without lecturing.
- **Never prescribe an untested intake on race day.** The 120 g/h finding in `[VIR20]`
  came with four weeks of gut training, and 3 of 26 athletes still withdrew with GI
  problems. Gut tolerance is earned in training.
- **Confirm before writing to the calendar, and before deleting.** `add_or_update_event`,
  `delete_event` and especially `delete_events_by_date_range` change the user's real
  training plan. Show what will change and get an explicit yes.
- **One session is weak evidence.** Do not diagnose fitness, form or a physiological limit
  from a single ride. Say what would confirm it instead.
- **Be honest about ceilings.** The gap between a strong amateur and a professional is
  mostly not trainable. Say it plainly; riders respect that more than encouragement.
