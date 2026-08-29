---
name: plan-block
description: Build a training block or taper toward a goal event and optionally write the sessions onto the Intervals.icu calendar. Use when the user asks for a training plan, what to do for the next few weeks, how to prepare for a race or gran fondo, or how to taper.
---

# Plan a block

Design a mesocycle that fits the athlete's real available hours and the demands of the
actual event — then, if they want, put it on the calendar.

## 1. Establish the target

Read `athlete.yaml` for goals, or ask. You need: **date, duration, terrain, priority**.
`coach taper` will use the next A goal automatically. For a real event, look up the
route profile — elevation, length of the decisive climbs, likely temperature — because a
4-hour rolling gran fondo and a 4-hour mountain gran fondo need different blocks.

Then anchor on where the athlete is now: run `/weekly-review` first if you do not already
know current CTL, distribution and consistency. Never plan from the profile alone.

## 2. Choose the structure

```bash
.venv/bin/coach taper                 # taper to the next A goal
.venv/bin/coach taper --days-out 12   # explicit window
.venv/bin/coach block                 # 4-week block-periodized HIT mesocycle [RON14]
.venv/bin/coach zones                 # the wattages to write into sessions
```

Pick by how far out the event is:

- **> 12 weeks** — base. Volume and low-intensity durability, one quality session weekly.
  Aim for the polarized/pyramidal shape `[SEI10]`, 3 weeks load + 1 recovery `[FRI18]`.
- **6-12 weeks** — build. This is where `coach block` fits: a concentrated HIT week then
  three low-intensity weeks. In `[RON14]` that beat two-HIT-sessions-per-week at matched
  volume — VO2max +4.6%, power at 2 mmol/L +10%, while the traditional group gained
  nothing. Not for beginners, and never inside 2 weeks of an A event.
- **3-6 weeks** — specialty. Sessions that look like the event: sustained climbing efforts
  for a mountain fondo, repeated surges for a road race, steady sub-threshold for a TT.
  Rehearse race fueling here (see `/fuel-plan`) — gut training needs about four weeks.
- **< 3 weeks** — taper. Cut volume 40-60%, hold intensity exactly, drop frequency by no
  more than 20% `[MUJ03]`. Expect ~3% improvement, and warn them they will feel flat
  mid-taper before it arrives.

## 3. Write it to the calendar

Only after the user has seen and approved the plan. Then use `add_or_update_event` per
session, with concrete targets from `coach zones`:

```
name:        "VO2max 5x6min"
start_date:  2026-09-08
type:        Ride
description: 20 min warm-up. 5 x 6 min at 262-300 W (Z5), 6 min easy between.
             15 min cool-down. ~75 min total.
             Fuel: 60 g/h carbohydrate, 500 mL/h.
```

Rules for calendar writes:

- **Confirm before writing, and confirm again before deleting.** `delete_events_by_date_range`
  removes real planned work — show what will be deleted and get an explicit yes.
- Write actual wattages, not zone names. "Z5" makes the rider do arithmetic on the road.
- Include the fueling line on any session over 2 hours.
- Check `get_events` first so you do not double-book existing sessions.

## 4. Sanity checks before you hand it over

- Weekly hours must fit `training.weekly_hours` and `training.days_available`. A plan that
  needs 12 hours from someone with 8 is not a plan.
- Ramp CTL no faster than `training.max_ramp_rate`.
- A recovery week every 3-4 weeks, non-negotiable.
- Hard days adjacent to rest days, not stacked against each other.
- The long ride lands on `training.long_ride_day`.

## Cautions

- FTP drifts during a block. If `physiology.ftp_updated` is more than 6-8 weeks old, build
  a test into the plan rather than prescribing wattages from a stale number.
- Block periodization is deliberately overreaching. Tell the user week 1 will feel bad and
  that this is the design, and tell them the abort condition: if sleep, resting HR or HRV
  degrade sharply, cut the block short.
- Plans are hypotheses. Say what you expect to see after 2 weeks, so it can be checked.
