---
name: benchmark-vs-pros
description: Compare the athlete's power profile against category bands and real professional cycling context from procyclingstats.com. Use when the user asks how they stack up, what category they would race, what pros produce on a climb, or what it would take to reach a given level.
---

# Benchmark against categories and pros

Answer "where do I actually sit?" with something more useful than a single W/kg number —
and without either flattering the rider or crushing them.

## 1. Get the power numbers

`get_athlete_power_curves` gives the athlete's best efforts across durations. Pull 5 s,
1 min, 5 min and 20 min / FTP. Note the window the curve covers: a 90-day curve and an
all-time curve say different things, and a curve with no recent maximal efforts
understates the rider rather than measuring them.

```bash
.venv/bin/coach benchmark --5s 1050 --1min 610 --5min 330 --ftp 250
```

Output gives W/kg, a category band, and the watts needed for the next band.

## 2. Read the shape, not just the level

The useful finding is almost never "you are a Cat 3". It is the **shape**: which system is
relatively strongest, and whether that matches the event they care about.

- Strong 5 s / 1 min, weaker FTP → a sprinter's profile. Great for crits, a liability on a
  mountain gran fondo.
- Strong FTP, weak anaerobic → a diesel. Fine for TTs and fondos; will get shed by every
  surge in a road race.
- Weak 5 min relative to FTP → VO2max is the lever with the most headroom, and it responds
  fast to a block `[RON14]`.

Tie this to the athlete's actual goal from `athlete.yaml`. A gran fondo rider does not need
a sprint, and telling them their 5 s power is Cat 4 is noise.

## 3. Add real professional context

Use WebFetch on procyclingstats.com for grounded context:

- `https://www.procyclingstats.com/rider/<rider-name>` — rider weight, age, results,
  specialty ranking.
- `https://www.procyclingstats.com/race/<race>/<year>` — route, profile, results.
- Race pages carry startlists and stage profiles, which are useful for "what does this
  event actually demand?"

**What PCS does and does not give you.** It publishes results, rider weights and race
profiles. It does **not** publish power files. Any pro wattage figure you have seen is a
third-party estimate from climb time, mass and gradient, and carries large error bars.
Present those as estimates and say so.

Reasonable published ranges for orientation: World Tour climbers produce roughly
**6.0-6.4 W/kg for 20-40 minutes** on decisive climbs, and around **5.8-6.0 W/kg** for a
flat hour. Use these as scale, never as targets.

## 4. Frame it usefully

- **Give the gap in watts, not just categories.** "+31 W to Cat 2" is actionable;
  "you are Cat 3" is not.
- **Be honest about the ceiling.** The gap between a strong amateur and a professional is
  mostly not trainable — it is genetics, twenty years of accumulated volume, and a full-time
  job doing it. Say this plainly and without consolation-prize language; riders respect it
  and it stops them chasing a number that will not come.
- **Weight is the other half of W/kg, and the dangerous half.** If the user raises losing
  weight to raise W/kg, do not do the arithmetic and hand them a target. Say that
  performance weight is individual, that under-fuelling costs more power than the mass
  saves, and that RED-S is a real and common injury in this sport. Suggest a sports
  dietitian for a real body-composition goal. Never generate a goal weight.
- **The bands are approximations.** They are in the tradition of the Coggan power profile
  chart `[COG19]` but are not the published chart. Say "roughly", and mean it.

## Cautions

- A power curve is only as good as the efforts in it. If the rider has not done a maximal
  5 s effort in a year, their 5 s number is not a measurement — check before benchmarking.
- Compare like with like: an indoor FTP and an outdoor FTP frequently differ by 5-10%.
