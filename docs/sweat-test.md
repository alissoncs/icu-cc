# Measuring your sweat rate and sweat sodium

Until you do this, every sodium number this repo produces is a population average. Real
sweat sodium concentration spans **200-2000 mg/L** between individuals, so the default of
800 mg/L can be wrong by more than a factor of two in either direction. Sweat *rate* varies
almost as widely (0.5-2.0 L/h). This is the single highest-value hour you can spend on your
fueling.

## Sweat rate — do this yourself, today

You need a scale that reads to 0.1 kg.

1. Empty your bladder, strip to shorts, and weigh yourself. Record it in kg.
2. Ride for exactly one hour at a steady, representative intensity. Note the **temperature**
   and **humidity** — the result only applies to conditions near these.
3. Record every millilitre you drink. Weigh bottles before and after if you can (1 mL water
   ≈ 1 g).
4. Towel off, strip, and weigh again. Do not urinate before weighing; if you must, weigh
   what comes out and subtract it.

```
sweat loss (L) = (weight before − weight after) + fluid drunk (L)
```

A rider who started at 72.0 kg, finished at 71.2 kg, and drank 750 mL lost
0.8 + 0.75 = **1.55 L/h**.

Repeat in cool, moderate and hot conditions if you can. Put the moderate-temperature
result in `athlete.yaml`, with the temperature it was measured at:

```yaml
sweat:
  measured: true
  rate_l_per_h: 1.55
  reference_temp_c: 22
```

The model scales this for other temperatures, humidity and intensity — but it scales from
whatever you give it, so an accurate baseline matters more than the scaling.

## Sweat sodium — needs a test

You cannot estimate this reliably. Salt crust on your kit and a taste for salty food are
weak signals at best, and self-assessment correlates poorly with measured values.

Options, roughly in order of accuracy:

- **Lab sweat test** (Precision Fuel & Hydration, Levelen, and similar, or a university
  exercise physiology lab). Absorbent patches on the forearm or back during a controlled
  ride, analysed for sodium concentration. This is the reference standard available to
  amateurs and typically takes an hour.
- **At-home patch kits.** Cheaper, more variable, but far better than guessing.

Record the result and mark the profile as measured:

```yaml
sweat:
  measured: true
  sodium_mg_per_l: 1350
```

Anything above roughly **1200 mg/L** makes you a "salty sweater", and it changes your
plans materially: at 1.5 L/h you would be losing over 2000 mg of sodium per hour, which
cannot be replaced through normal sports drink concentration alone and needs capsules or
savoury food.

## Re-test when

- The season changes substantially, or you relocate to a different climate.
- You gain or lose meaningful fitness — sweat rate rises as you become better trained.
- Your body mass changes by more than a few kilograms.

Roughly once a year, plus before a first event in unfamiliar heat.

## Heat acclimation changes the answer

Ten to fourteen days of deliberate heat exposure raises sweat rate *and* lowers sweat
sodium concentration — you sweat more and conserve salt better. If you acclimate before a
hot event, your pre-acclimation numbers will overstate your sodium needs. Re-measure after
the acclimation block rather than carrying the old figure into race day.
