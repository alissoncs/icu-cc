"""Carbohydrate, fluid and electrolyte prescription.

Implements the duration-scaled carbohydrate framework of Jeukendrup [JEU14], the daily
availability targets of Burke et al. [BUR11], and the high-intake ceiling evidenced by
Viribay et al. [VIR20]. See docs/evidence-base.md.

Two rules govern everything here:

1. Carbohydrate during exercise is prescribed in **grams per hour, not g/kg/h**.
   Jeukendrup found no correlation between body weight and exogenous carbohydrate
   oxidation, so weight-scaling in-ride carbs is unsupported [JEU14]. Body mass is used
   only for pre-ride, post-ride and fluid, where it genuinely applies.

2. The model never prescribes more than the athlete's demonstrated tolerance plus one
   gut-training step. 120 g/h worked in [VIR20] only after four weeks of deliberate gut
   training, and 3 of 26 athletes still dropped out with GI distress.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .profile import AthleteProfile

# Oxidation ceiling for a single transportable carbohydrate (SGLT1-limited). [JEU14]
SINGLE_TRANSPORTER_CEILING_G_H = 60.0
# Absolute ceiling this model will prescribe, from the highest dose with published
# evidence of benefit. [VIR20]
ABSOLUTE_CEILING_G_H = 120.0
# How far above demonstrated tolerance one session may push, as gut training.
GUT_TRAINING_STEP_G_H = 10.0
# Practical gastric emptying limit for fluid.
MAX_FLUID_ML_H = 1000.0
# Dehydration tolerated before performance is meaningfully impaired.
ALLOWED_BODY_MASS_LOSS_PCT = 2.0
# Above this, a drink is usually unpalatable and better split into food/capsules.
PALATABILITY_SODIUM_MG_L = 1500.0


@dataclass
class FuelPlan:
    duration_h: float
    intensity_factor: float
    temp_c: float
    humidity_pct: float

    carb_g_per_h: float
    carb_total_g: float
    carb_type: str
    carb_uncapped_g_per_h: float

    fluid_ml_per_h: float
    fluid_total_ml: float
    sweat_rate_l_per_h: float
    sweat_loss_ml: float

    sodium_mg_per_h: float
    sodium_total_mg: float
    sodium_mg_per_l: float
    sodium_replacement_pct: float

    caffeine_mg: float
    pre_ride_carb_g: float
    post_ride_carb_g: float
    post_ride_protein_g: float

    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def base_carb_target(duration_h: float) -> float:
    """Carbohydrate target from duration alone, before intensity adjustment. [JEU14]

    Jeukendrup's bands: mouth rinse under ~1 h, ~30 g/h for 1-2 h, ~60 g/h for 2-3 h,
    ~90 g/h for ultra-endurance. Interpolated at the edges so a 2h05 ride does not jump
    discontinuously from a 1h55 ride.
    """
    if duration_h < 0.75:
        return 0.0
    if duration_h < 1.25:
        return 20.0
    if duration_h < 2.0:
        return 30.0
    if duration_h < 2.5:
        return 45.0
    if duration_h < 3.0:
        return 60.0
    if duration_h < 4.0:
        return 80.0
    return 90.0


def intensity_carb_adjustment(intensity_factor: float) -> float:
    """Carbohydrate is oxidised faster at higher intensity, so the target rises.

    Jeukendrup's bands are duration-anchored; intensity is the documented second axis
    ("exercise duration and intensity"), applied here as a modest shift rather than a
    separate model.
    """
    if intensity_factor >= 0.85:
        return 15.0
    if intensity_factor >= 0.75:
        return 5.0
    if intensity_factor < 0.60:
        return -15.0
    return 0.0


def estimate_sweat_rate(
    profile: AthleteProfile, temp_c: float, humidity_pct: float, intensity_factor: float
) -> float:
    """Adjust the profile's baseline sweat rate for heat, humidity and intensity.

    Multiplicative factors around the temperature at which the baseline was measured.
    These are shaping heuristics, not literature constants — the honest fix is a real
    sweat test, which is why an unmeasured profile always emits a warning.
    """
    rate = profile.sweat_rate_l_per_h

    delta_t = temp_c - profile.sweat_reference_temp_c
    if delta_t >= 0:
        temp_factor = min(1.0 + 0.045 * delta_t, 2.0)
    else:
        temp_factor = max(1.0 + 0.020 * delta_t, 0.6)

    humidity_factor = 1.0
    if humidity_pct > 60:
        humidity_factor = min(1.0 + 0.006 * (humidity_pct - 60), 1.25)

    # Normalised so a typical endurance IF of 0.70 leaves the baseline unchanged.
    intensity_adj = min(max(1.0 + 0.6 * (intensity_factor - 0.70), 0.80), 1.35)

    return rate * temp_factor * humidity_factor * intensity_adj


def sodium_replacement_fraction(duration_h: float, temp_c: float) -> float:
    """What share of sweat sodium loss to replace.

    Short rides tolerate a large sodium deficit; long hot rides do not. Full replacement
    is neither necessary nor practical below a few hours.
    """
    if duration_h < 1.5:
        frac = 0.40
    elif duration_h < 3.0:
        frac = 0.65
    elif duration_h < 5.0:
        frac = 0.80
    else:
        frac = 0.95
    if temp_c >= 25:
        frac = min(frac + 0.15, 1.0)
    return frac


def daily_carb_target_g_per_kg(training_hours_today: float) -> tuple[float, float, str]:
    """Daily carbohydrate band in g/kg body mass. [BUR11]

    Returns (low, high, load_label).
    """
    if training_hours_today < 0.75:
        return 3.0, 5.0, "light"
    if training_hours_today < 1.5:
        return 5.0, 7.0, "moderate"
    if training_hours_today < 4.0:
        return 6.0, 10.0, "high"
    return 8.0, 12.0, "very high"


def build_fuel_plan(
    profile: AthleteProfile,
    duration_h: float,
    intensity_factor: float = 0.70,
    temp_c: float = 18.0,
    humidity_pct: float = 50.0,
    is_race: bool = False,
) -> FuelPlan:
    """Full carbohydrate, fluid and electrolyte plan for one session."""
    if duration_h <= 0:
        raise ValueError("duration_h must be positive")

    notes: list[str] = []
    warnings: list[str] = []

    # --- Carbohydrate ----------------------------------------------------------
    target = base_carb_target(duration_h) + intensity_carb_adjustment(intensity_factor)
    if is_race and duration_h >= 2.5:
        # Race day is where the high-intake evidence applies. [VIR20]
        target = max(target, 90.0)
    target = max(target, 0.0)
    uncapped = target

    tolerance_cap = profile.gut_trained_carb_g_per_h + GUT_TRAINING_STEP_G_H
    carb = min(target, tolerance_cap, ABSOLUTE_CEILING_G_H)

    if target > tolerance_cap:
        warnings.append(
            f"Duration and intensity justify ~{target:.0f} g/h, but your demonstrated "
            f"tolerance is {profile.gut_trained_carb_g_per_h:.0f} g/h. Capped at "
            f"{carb:.0f} g/h. Raise gut_trained_carb_g_per_h only after you actually "
            "hold the higher rate in training [VIR20]."
        )
    elif carb > profile.gut_trained_carb_g_per_h:
        notes.append(
            f"{carb:.0f} g/h is above your logged tolerance of "
            f"{profile.gut_trained_carb_g_per_h:.0f} g/h — treat this as a gut-training "
            "session and do it in training, never first on race day."
        )

    if carb > SINGLE_TRANSPORTER_CEILING_G_H:
        carb_type = "multiple transportable (glucose:fructose ~2:1)"
        notes.append(
            f"Above {SINGLE_TRANSPORTER_CEILING_G_H:.0f} g/h a single carb source "
            "saturates SGLT1. Use a glucose:fructose blend — 2:1 is the ratio used in "
            "[VIR20]; 1:0.8 is also well supported — or you will not oxidise the extra "
            "and will buy GI distress instead [JEU14]."
        )
    elif carb > 0:
        carb_type = "single or multiple transportable"
    else:
        carb_type = "none required"

    if duration_h < 0.75:
        notes.append(
            "Under ~45 min no carbohydrate is needed. If it is a hard effort, a "
            "carbohydrate mouth rinse alone can improve performance [JEU14]."
        )

    if carb >= 100:
        warnings.append(
            "At >=100 g/h, note that 3 of 26 athletes in [VIR20] withdrew with GI "
            "problems despite four weeks of gut training. Rehearse this exact intake "
            "in training first."
        )

    # --- Fluid -----------------------------------------------------------------
    sweat_rate = estimate_sweat_rate(profile, temp_c, humidity_pct, intensity_factor)
    sweat_loss_ml = sweat_rate * duration_h * 1000
    allowed_deficit_ml = profile.weight_kg * (ALLOWED_BODY_MASS_LOSS_PCT / 100) * 1000

    needed_ml = max(sweat_loss_ml - allowed_deficit_ml, 0.0)
    fluid_ml_h = min(needed_ml / duration_h, MAX_FLUID_ML_H)
    fluid_total_ml = fluid_ml_h * duration_h

    if needed_ml / duration_h > MAX_FLUID_ML_H:
        warnings.append(
            f"Estimated sweat loss needs {needed_ml / duration_h:.0f} mL/h but the gut "
            f"empties ~{MAX_FLUID_ML_H:.0f} mL/h. You will finish dehydrated beyond "
            f"{ALLOWED_BODY_MASS_LOSS_PCT}% — pre-hydrate, start cool, and plan stops."
        )
    if fluid_ml_h == 0:
        notes.append(
            "Estimated losses stay inside the 2% body-mass allowance — drink to thirst."
        )

    # --- Sodium ----------------------------------------------------------------
    sodium_loss_mg = sweat_rate * duration_h * profile.sweat_sodium_mg_per_l
    replace_frac = sodium_replacement_fraction(duration_h, temp_c)
    sodium_total = sodium_loss_mg * replace_frac
    sodium_per_h = sodium_total / duration_h
    sodium_conc = (sodium_total / (fluid_total_ml / 1000)) if fluid_total_ml > 0 else 0.0

    if sodium_conc > PALATABILITY_SODIUM_MG_L:
        warnings.append(
            f"Replacing sodium through fluid alone means {sodium_conc:.0f} mg/L, which "
            "most riders find unpalatable. Move part of it to salt capsules or savoury "
            "food."
        )
    if not profile.sweat_measured:
        warnings.append(
            "Sodium figures assume the default 800 mg/L. Real sweat sodium spans "
            "200-2000 mg/L, so this number could be off by more than 2x. Do a sweat test."
        )

    # --- Around the ride -------------------------------------------------------
    if duration_h >= 3 or intensity_factor >= 0.85:
        pre_g_per_kg = 2.5
    elif duration_h >= 1.5:
        pre_g_per_kg = 1.5
    else:
        pre_g_per_kg = 1.0
    pre_carb = pre_g_per_kg * profile.weight_kg
    notes.append(
        f"Pre-ride: ~{pre_carb:.0f} g carbohydrate ({pre_g_per_kg} g/kg) 1-3 h before "
        "[BUR11]."
    )

    post_carb = 1.0 * profile.weight_kg
    post_protein = 0.3 * profile.weight_kg

    caffeine = 0.0
    if profile.caffeine_mg_per_kg > 0 and (is_race or intensity_factor >= 0.80):
        caffeine = profile.caffeine_mg_per_kg * profile.weight_kg
        notes.append(
            f"Caffeine: ~{caffeine:.0f} mg ({profile.caffeine_mg_per_kg} mg/kg) 45-60 min "
            "before. Skip on easy days so it stays effective when it matters."
        )

    low, high, label = daily_carb_target_g_per_kg(duration_h)
    notes.append(
        f"Daily total for a '{label}' day: {low * profile.weight_kg:.0f}-"
        f"{high * profile.weight_kg:.0f} g ({low}-{high} g/kg) across the whole day, "
        "in-ride carbs included [BUR11]."
    )

    if profile.restrictions:
        warnings.append(
            f"Profile lists restrictions: {', '.join(profile.restrictions)}. "
            "Check product choice against these before following this plan."
        )

    return FuelPlan(
        duration_h=duration_h,
        intensity_factor=intensity_factor,
        temp_c=temp_c,
        humidity_pct=humidity_pct,
        carb_g_per_h=round(carb),
        carb_total_g=round(carb * duration_h),
        carb_type=carb_type,
        carb_uncapped_g_per_h=round(uncapped),
        fluid_ml_per_h=round(fluid_ml_h, -1),
        fluid_total_ml=round(fluid_total_ml, -1),
        sweat_rate_l_per_h=round(sweat_rate, 2),
        sweat_loss_ml=round(sweat_loss_ml, -1),
        sodium_mg_per_h=round(sodium_per_h, -1),
        sodium_total_mg=round(sodium_total, -1),
        sodium_mg_per_l=round(sodium_conc, -1),
        sodium_replacement_pct=round(replace_frac * 100),
        caffeine_mg=round(caffeine),
        pre_ride_carb_g=round(pre_carb),
        post_ride_carb_g=round(post_carb),
        post_ride_protein_g=round(post_protein),
        notes=notes,
        warnings=warnings,
    )
