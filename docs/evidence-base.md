# Evidence base

Every number this repo prescribes traces back to one of the sources below. When a skill
gives advice, it should be able to name the source. When a source gives a *range*, the
code carries the range and picks within it from the athlete profile — it must never
invent precision the literature does not have.

Tags in brackets (`[JEU14]`, `[SEI10]`, …) are used in code comments and skill output.

---

## Fueling

### `[JEU14]` Jeukendrup, A. E. (2014). A step towards personalized sports nutrition: carbohydrate intake during exercise. *Sports Medicine*, 44(Suppl 1), S25–S33. DOI 10.1007/s40279-014-0148-z

The duration-scaled carbohydrate framework this repo's fueling model is built on.

| Exercise duration | Carbohydrate target | Type |
|---|---|---|
| ~30 min – 1 h | Mouth rinse or small amounts | Any, incl. rinse only |
| ~1 – 2 h | ~30 g/h | Single or multiple |
| ~2 – 3 h | ~60 g/h | Single transportable OK |
| > ~2.5 – 3 h (ultra) | ~90 g/h | **Multiple transportable required** |

Key mechanistic points:

- **A single carbohydrate source saturates at ~60 g/h.** Intestinal SGLT1 transport is the
  ceiling; ingesting more glucose/maltodextrin alone does not raise oxidation.
- **Multiple transportable carbohydrates** (glucose + fructose, using SGLT1 *and* GLUT5)
  push exogenous oxidation "well above 1 g/min (1.26 g/min)" — up to **75% higher**
  oxidation rates than glucose alone. This is why anything above 60 g/h must be a blend.
- **Do not scale by body weight.** Jeukendrup argues explicitly against g/kg/h dosing
  during exercise: "there appears to be no correlation between BW and exogenous
  carbohydrate oxidation." Hourly grams is the correct unit. *(This repo follows that:
  `fueling.py` prescribes g/h, and only uses body mass for pre/post-ride and fluid.)*
- **The gut is trainable.** Higher exogenous oxidation rates were observed after a
  high-carbohydrate diet (6.5 g/kg BW/day) over 28 days.

### `[BUR11]` Burke, L. M., Hawley, J. A., Wong, S. H. S., & Jeukendrup, A. E. (2011). Carbohydrates for training and competition. *Journal of Sports Sciences*, 29(sup1), S17–S27. DOI 10.1080/02640414.2011.585473

Supplies the *daily* carbohydrate layer that sits underneath per-session fueling, and the
"carbohydrate availability" concept.

**Daily carbohydrate targets (g/kg body mass/day):**

| Training load | Description | Target |
|---|---|---|
| Light | Low intensity or skill-based | 3–5 g/kg/day |
| Moderate | ~1 h/day | 5–7 g/kg/day |
| High | 1–3 h/day moderate-to-high intensity | 6–10 g/kg/day |
| Very high | > 4–5 h/day moderate-to-high intensity | 8–12 g/kg/day |

Core framing: judge intake by whether it sustains **high carbohydrate availability**
(adequate substrate for muscle and CNS) or deliberately creates **low availability**
(carbohydrate limiting, used as a training stimulus). Availability is raised by intake in
the hours/days before, during, and in recovery between sessions. Intake during exercise
should be **scaled to the characteristics of the event**, and targets are **periodized**,
not static — an athlete does not eat the same every day of a training week.

### `[VIR20]` Viribay, A., Arribalzaga, S., Mielgo-Ayuso, J., Castañeda-Babarro, A., Seco-Calvo, J., & Urdampilleta, A. (2020). Effects of 120 g/h of carbohydrates intake during a mountain marathon on exercise-induced muscle damage in elite runners. *Nutrients*, 12(5), 1367.

The evidence for going *above* the classic 90 g/h ceiling — and the tolerance caveat.

- **Design:** 20 elite male runners, mountain marathon with ~4000 m cumulative climbing.
  Randomised to 60 g/h (n=6), 90 g/h (n=7), or 120 g/h (n=7). Blood drawn pre-race and
  24 h post.
- **Composition:** all groups used gels at a **2:1 glucose:fructose ratio** (maltodextrin
  + fructose), chosen to raise exogenous carbohydrate oxidation.
- **Results at 24 h post** (mean ± SD), 120 g/h group vs. the others:

  | Marker | 60 g/h | 90 g/h | 120 g/h | p |
  |---|---|---|---|---|
  | CK (U/L) | 1528.8 ± 1099.7 | 1553.0 ± 867.0 | **499.3 ± 245.8** | 0.032 |
  | LDH (U/L) | 504.0 ± 88.9 | 489.6 ± 78.3 | **412.1 ± 29.6** | <0.001 |
  | GOT (U/L) | 70.8 ± 36.1 | 63.0 ± 20.7 | **36.5 ± 6.5** | 0.003 |
  | Urea | 43.8 ± 10.3 | 44.6 ± 7.2 | 42.9 ± 6.1 | n.s. |
  | Creatinine | 0.83 ± 0.08 | 0.91 ± 0.12 | 0.79 ± 0.09 | n.s. |

- **Conclusion:** 120 g/h "could limit the EIMD observed by CK, LDH and GOT and internal
  exercise load compared to CHO ingestion of 60 and 90 g/h," plausibly improving recovery.
- **Caveats that matter more than the headline:**
  - Every participant had completed **personalised gut training**, using intakes up to
    90 g/h at least 2 days/week for the 4 weeks before the race. 120 g/h is not a dose you
    take cold.
  - **6 of 26 enrolled athletes withdrew, 3 with GI problems** (reflux, flatulence) —
    despite that preparation.
  - Small groups (n=6–7), running not cycling, and muscle glycogen was never measured.

**How this repo uses it:** 120 g/h is available as a ceiling, but only unlocked when
`nutrition.gut_trained_carb_g_per_h` in `athlete.yaml` supports it. The model never
prescribes more than your trained ceiling + 10 g/h in one session, and always flags the
glucose:fructose requirement above 60 g/h.

---

## Training prescription

### `[COG19]` Allen, H., Coggan, A. R., & McGregor, S. (2019). *Training and Racing with a Power Meter* (3rd ed.). VeloPress.

Source for FTP and the classic **7-zone power model** used in `zones.py`.

- **FTP** = the highest power an athlete can sustain in a quasi-steady state for
  approximately one hour.
- **20-minute field test:** FTP ≈ 95% of mean power for an all-out 20 min effort. The 5%
  haircut accounts for the anaerobic contribution over 20 min vs. 60 min.
- **Zones as % of FTP:**

  | Zone | Name | % FTP |
  |---|---|---|
  | Z1 | Active Recovery | ≤ 55% |
  | Z2 | Endurance | 56–75% |
  | Z3 | Tempo | 76–90% |
  | Z4 | Lactate Threshold | 91–105% |
  | Z5 | VO2max | 106–120% |
  | Z6 | Anaerobic Capacity | 121–150% |
  | Z7 | Neuromuscular Power | > 150% |

- Also the source for Normalized Power (30 s rolling average, raised to the 4th power,
  averaged, 4th root), Intensity Factor (NP/FTP), TSS, and the Variability Index (NP/avg).

### `[SEI10]` Seiler, S. (2010). What is best practice for training intensity and duration distribution in endurance athletes? *International Journal of Sports Physiology and Performance*, 5(3), 276–291.

Source for training intensity distribution (TID) analysis.

- Uses a **three-zone model** anchored on ventilatory/lactate thresholds: **Z1** below
  VT1/LT1 (low lactate), **Z2** between VT1 and VT2, **Z3** above VT2.
- Elite endurance athletes across sports converge on roughly **80% of sessions at low
  intensity and ~20% at threshold or high intensity** — the "polarized" pattern.
- The practical implication is a warning: athletes drift into the **Z2 "black hole"**,
  training too hard on easy days and too easy on hard days. Time near threshold feels
  productive and accumulates fatigue without the adaptive return of either extreme.
- This repo classifies a week/block as **polarized**, **pyramidal**, or **threshold** and
  reports the drift. Note that pyramidal distributions perform comparably in several
  trials — polarized is a strong default, not a law.

### `[FRI18]` Friel, J. (2018). *The Cyclist's Training Bible* (5th ed.). VeloPress.

Source for periodization structure and the HR zone model.

- **Hierarchy:** season → mesocycle (block, ~3–4 weeks) → microcycle (week) → session.
- **Loading pattern:** typically 3 weeks of progressive load + 1 recovery week, moving from
  general preparation toward event-specific work as the A-race approaches.
- **Event priority:** A races are peaked for (full taper), B races are trained through with
  a short unload, C races are training sessions with a number pinned on.
- **HR zones as % of LTHR** (the "Friel zones" this repo implements):

  | Zone | % LTHR |
  |---|---|
  | Z1 | < 81% |
  | Z2 | 81–89% |
  | Z3 | 90–93% |
  | Z4 | 94–99% |
  | Z5a | 100–102% |
  | Z5b | 103–106% |
  | Z5c | > 106% |

- LTHR is measured as the average HR of a 20–30 min all-out time trial, not a lab value.

### `[MUJ03]` Mujika, I., & Padilla, S. (2003). Scientific bases for precompetition tapering strategies. *Medicine & Science in Sports & Exercise*, 35(7), 1182–1187.

Source for the taper generator in `periodization.py`.

- **Goal:** minimise accumulated fatigue without losing adaptations.
- **Maintain training intensity.** This is the non-negotiable variable; cutting intensity
  during a taper loses fitness.
- **Reduce training volume substantially** — up to **60–90%** in the reviewed studies.
- **Reduce frequency only slightly — no more than 20%.** Keep touching the bike.
- **Duration:** optimal tapers run roughly **8–14 days**, with the full reviewed range
  spanning **4 to more than 28 days** depending on the preceding load.
- **Expected effect:** performance improves by about **3%** (usual range **0.5–6.0%**),
  via cardiorespiratory, metabolic, haematological, hormonal, neuromuscular and
  psychological changes.

### `[JAM20]` Jamnick, N. A., Botella, J., Pyne, D. B., & Bishop, D. J. (2020). An examination of the methodology used to determine the second lactate threshold: implications for training zone prescription. *Sports Medicine*, 50(7), 1339–1356.

The methodological caution that keeps this repo honest about zones.

- Intensity domains are best divided by **metabolic thresholds** into **moderate, heavy,
  and severe**: the heavy domain sits between LT1 and LT2, the severe domain between LT2
  and VO2max.
- **LT2 is the anchor that matters**, closely linked to maximal lactate steady state
  (MLSS).
- **Fixed lactate values (2 and 4 mmol/L) should not be used** to set thresholds — they
  distort zones for individual athletes.
- Threshold estimates vary widely with the *method* and the *test protocol* (stage length,
  increment size), so zones derived from different tests are not interchangeable.
- **Consequence for this repo:** FTP is a convenient, repeatable field proxy for LT2 — but
  it is a proxy, not LT2 itself, and the two can diverge meaningfully in an individual.
  `athlete.yaml` records `ftp_source` for exactly this reason, and zone output is labelled
  as an estimate. Do not present zone boundaries as physiological truth.

### `[RON14]` Rønnestad, B. R., & Hansen, J. (2014). Block periodization of high-intensity aerobic interval training improves maximal oxygen uptake and work output in trained cyclists. *Scandinavian Journal of Medicine & Science in Sports*, 24(2), 276–285.

Source for the block-periodization template in `periodization.py`.

- **Design:** trained cyclists (VO2max ~62–63 mL/kg/min), 4 weeks.
  - **Block periodization (n=10):** week 1 = **five HIT sessions**, then 3 weeks of **one**
    weekly HIT session with a low-intensity focus.
  - **Traditional (n=9):** 4 weeks of **two** weekly HIT sessions interspersed with LIT.
- **HIT sessions:** maximal sustainable effort over **5 × 6 min** or **6 × 5 min**
  intervals.
- **Results:** the block group improved **VO2max by 4.6 ± 3.7%**, **peak power output by
  2.1 ± 2.8%**, and **power at 2 mmol/L lactate by 10 ± 12%** (all p < 0.05). The
  traditional group showed **no significant change** — despite matched total volume and
  intensity.
- **Caveat:** the concentrated week is deliberately overreaching. It suits experienced
  cyclists with an established aerobic base and requires the low-intensity weeks that
  follow. It is not a beginner protocol and should not be repeated back-to-back.

---

## Benchmarking

### Power profile categories

`benchmarks.py` carries approximate W/kg bands for 5 s, 1 min, 5 min and FTP, in the
tradition of the Coggan power profile chart `[COG19]`. **These bands are coarse
approximations for orientation, not the published chart.** They exist to answer "roughly
where do I sit?", and the code labels them as estimates.

### procyclingstats.com

Used for real-world context — rider weights, race profiles, results and startlists — via
the `benchmark-vs-pros` skill. Publicly reported pro climbing outputs (typically
**6.0–6.4 W/kg for 20–40 min** on decisive climbs, ~**5.8–6.0 W/kg** for a flat hour)
should be treated as third-party estimates, not measured data: PCS does not publish power
files, and public power estimates carry large error bars from mass, gradient and wind
assumptions. Cite them as context, never as a target.
