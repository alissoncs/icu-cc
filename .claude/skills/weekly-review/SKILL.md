---
name: weekly-review
description: Review a training week or block — volume, load, CTL/ATL/TSB, ramp rate, intensity distribution, consistency and wellness — and say what to change. Use when the user asks how their week or month went, whether they are overreaching, if they are training too hard on easy days, or what to do next week.
---

# Weekly / block review

Zoom out from single rides to the pattern. Most training mistakes are visible only at this
altitude: grey-zone drift, ramp rates that outrun recovery, and weeks that look busy but
carry no real stimulus.

## 1. Gather

```
get_activities    start_date / end_date over the window, limit high enough to catch them all
get_wellness_data same window — resting HR, HRV, sleep, weight, subjective scores
get_events        what was actually planned, so you can compare intent to execution
```

Default window: 7 days for a week review, 28-42 days if the user asks about a block or a
trend. Fetch wellness even if they did not ask — sleep and HRV often explain the training.

## 2. Compute

Write the daily loads and the summed zone times into JSON, then:

```bash
# CTL / ATL / TSB, ramp rate, monotony
cat > /tmp/.../loads.json <<'JSON'
{"2026-08-01": 110, "2026-08-02": 185, "2026-08-03": 55, ...}
JSON
.venv/bin/coach pmc /tmp/.../loads.json --ctl-seed 55 --atl-seed 55

# Intensity distribution across the window
cat > /tmp/.../zones.json <<'JSON'
{"Z1": 5400, "Z2": 28800, "Z3": 7200, "Z4": 2400, "Z5": 900, "Z6": 180}
JSON
.venv/bin/coach tid /tmp/.../zones.json
```

Seed CTL and ATL from the values Intervals.icu already reports at the start of your window
(`icu_ctl` / `icu_atl` on an activity, or the wellness data) — otherwise the model starts
from zero and every number is wrong for the first six weeks.

## 3. Read it

Work through these in order; each is a distinct failure mode:

- **Consistency before everything.** Planned vs. completed sessions. A perfect plan
  executed 60% of the time loses to a modest plan executed fully. If sessions are being
  missed, that is the finding — diagnose why before touching the prescription.
- **Ramp rate against `training.max_ramp_rate`.** Sustained ramps past ~5-7 CTL/week are
  where illness and injury cluster. One steep week after a break is fine; four in a row is
  not.
- **Intensity distribution.** Elite athletes converge near 80% low intensity `[SEI10]`. If
  the tool says `threshold`, that is the black hole: too hard to recover from, too easy to
  drive top-end adaptation. Say which specific rides caused it.
- **Monotony.** Above ~2.0 means the week has no hard/easy contrast. Same total load with
  sharper separation adapts better.
- **TSB in context of the calendar.** −25 in a build block is the job working. −25 eight
  days before an A event is a problem. Always check `get_events` before judging form.
- **Wellness corroboration.** Rising resting HR, falling HRV, poor sleep, or dropping
  subjective scores alongside a high ramp is the signal to unload — earlier than the
  numbers alone would say.

## 4. Prescribe

Give **one** primary change, not a list of seven. Rank by what will actually move the
needle: usually consistency, then distribution, then volume, then intensity. Say what next
week looks like concretely — hours, number of hard sessions, and which day.

If a recovery week is due (typically every 3-4 weeks `[FRI18]`), say so explicitly. Athletes
skip these and then wonder why the block did not stick.

## Cautions

- CTL/ATL/TSB are a model, not physiology. They ignore strength work, life stress, heat and
  illness. Wellness data and how the rider actually feels outrank the chart.
- A single week is noisy. For trend claims, look at 4-6 weeks.
- If wellness is degrading while load climbs, say plainly that this is the pattern that
  precedes non-functional overreaching, and recommend the unload now rather than hedging.
