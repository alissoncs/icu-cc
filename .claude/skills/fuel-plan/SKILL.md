---
name: fuel-plan
description: Build a carbohydrate, fluid and electrolyte plan for a specific ride or race, grounded in the sports-nutrition literature and the athlete's own demonstrated gut tolerance and sweat data. Use when the user asks what to eat or drink for a session, how many carbs per hour, how to fuel a race, or why they bonked or had GI trouble.
---

# Fuel plan

Prescribe carbohydrate, fluid and sodium for one session. The model is in
`src/cycling_coach/fueling.py`; the sources are in `docs/evidence-base.md`.

## Run it

```bash
.venv/bin/coach fuel --duration 4.5 --intensity 0.72 --temp 27 --humidity 70 --race
```

- `--duration` hours. The primary driver — Jeukendrup's framework is duration-anchored.
- `--intensity` intensity factor. Use the planned IF, or estimate: 0.55-0.65 easy,
  0.70-0.75 endurance, 0.80-0.85 tempo, 0.90+ race.
- `--temp` / `--humidity` change sweat and sodium substantially. Look up the forecast for a
  real event rather than accepting the defaults.
- `--race` applies race-day carbohydrate targets for sessions over 2.5 h.

For a planned event, get the details first with `get_events` / `get_event_by_id` so the
duration and intensity are the real ones.

## The four rules that must survive into your answer

1. **Grams per hour, never g/kg/h.** Jeukendrup found no correlation between body mass and
   exogenous carbohydrate oxidation `[JEU14]`. A 60 kg and a 90 kg rider on the same ride
   get the same hourly target. Body mass matters for fluid and for pre/post-ride carbs,
   and there only.

2. **Above 60 g/h you must use a glucose:fructose blend.** A single carbohydrate source
   saturates SGLT1 near 60 g/h `[JEU14]`. Prescribing 90 g/h of pure maltodextrin buys GI
   distress and no extra oxidation. 2:1 is the ratio used in `[VIR20]`; 1:0.8 is also well
   supported.

3. **Tolerance is earned, not assigned.** The tool caps intake at
   `nutrition.gut_trained_carb_g_per_h` + 10 g/h. When it caps, say so and say what the
   ride actually wanted. In `[VIR20]`, 120 g/h worked — but every athlete had four weeks of
   gut training first, and 3 of 26 still withdrew with GI problems. Never put a new intake
   rate on race day.

4. **Sodium numbers are guesses until a sweat test exists.** Real sweat sodium spans
   200-2000 mg/L. If `sweat.measured` is false, the output carries a warning; carry it
   through to the user rather than quietly dropping it. Point them at
   `docs/sweat-test.md` — it is an hour of work that makes every future plan real.

## Make it concrete

The tool gives grams and millilitres. Convert that into things the rider can carry, using
`nutrition.preferred_products` when set:

> 80 g/h for 4.5 h = 360 g. Two 750 mL bottles at 80 g each (160 g), plus 5 gels at 25 g
> (125 g), plus two rice cakes (~75 g). Sodium: your bottles at 1000 mg/L cover 1500 mg;
> take 3 salt capsules across the second half for the rest.

Then give the timing: pre-ride meal, the first feed (start early — inside the first
30 minutes), the interval between feeds, and the recovery window.

## Diagnosing what went wrong

When the user reports a bonk, a fade, or gut trouble, work backwards:

- **Bonk / late fade** — compare what they ate to what the ride wanted. Also check for
  high decoupling in the activity, which usually corroborates it.
- **GI distress** — the usual suspects, in order: intake above trained tolerance; a single
  carbohydrate source above 60 g/h; drink concentration too high; too much fluid at once;
  starting the feeding too late and playing catch-up.
- **Cramp** — the evidence for sodium as the sole cause is weaker than the marketing
  suggests. Consider intensity relative to training, novel duration, and pacing before
  blaming electrolytes.

## Cautions

- This is sports nutrition for a healthy athlete, not medical or clinical dietetics. If the
  user raises a medical condition, medication, an eating disorder, or wants to combine
  fueling with significant weight loss, say plainly that this is outside what the tool
  models and belongs with a sports dietitian or physician.
- Check `nutrition.restrictions` before naming products.
