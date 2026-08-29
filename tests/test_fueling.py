"""The fueling rules that must not silently regress."""

import pytest

from cycling_coach.fueling import (
    ABSOLUTE_CEILING_G_H,
    GUT_TRAINING_STEP_G_H,
    SINGLE_TRANSPORTER_CEILING_G_H,
    base_carb_target,
    build_fuel_plan,
    daily_carb_target_g_per_kg,
    estimate_sweat_rate,
)


def test_carb_target_scales_with_duration():
    """Jeukendrup's bands: rinse under 1h, ~60 g/h at 2-3h, ~90 g/h for ultra. [JEU14]"""
    assert base_carb_target(0.5) == 0
    assert base_carb_target(1.5) == 30
    assert base_carb_target(2.75) == 60
    assert base_carb_target(5.0) == 90
    # Monotonic across the whole range.
    targets = [base_carb_target(h) for h in [0.5, 1.0, 1.5, 2.2, 2.7, 3.5, 6.0]]
    assert targets == sorted(targets)


def test_never_exceeds_demonstrated_tolerance_by_more_than_one_step(athlete):
    """120 g/h in [VIR20] required 4 weeks of gut training; 3 of 26 still dropped out."""
    plan = build_fuel_plan(athlete, duration_h=8.0, intensity_factor=0.75, is_race=True)
    assert plan.carb_g_per_h <= athlete.gut_trained_carb_g_per_h + GUT_TRAINING_STEP_G_H
    assert any("tolerance" in w for w in plan.warnings)


def test_absolute_ceiling_respected_for_a_very_gut_trained_athlete(athlete):
    trained = type(athlete)(**{**athlete.__dict__, "gut_trained_carb_g_per_h": 200})
    plan = build_fuel_plan(trained, duration_h=10.0, intensity_factor=0.80, is_race=True)
    assert plan.carb_g_per_h <= ABSOLUTE_CEILING_G_H


def test_above_60_g_h_demands_a_glucose_fructose_blend(athlete):
    """A single carb source saturates SGLT1 around 60 g/h. [JEU14]"""
    plan = build_fuel_plan(athlete, duration_h=4.0, intensity_factor=0.75, is_race=True)
    assert plan.carb_g_per_h > SINGLE_TRANSPORTER_CEILING_G_H
    assert "multiple transportable" in plan.carb_type
    assert any("fructose" in n for n in plan.notes)


def test_carbs_are_not_scaled_by_body_weight(athlete):
    """[JEU14] found no correlation between body mass and exogenous CHO oxidation."""
    heavy = type(athlete)(**{**athlete.__dict__, "weight_kg": 95.0})
    a = build_fuel_plan(athlete, duration_h=3.0, intensity_factor=0.70)
    b = build_fuel_plan(heavy, duration_h=3.0, intensity_factor=0.70)
    assert a.carb_g_per_h == b.carb_g_per_h


def test_short_easy_ride_needs_no_carbs(athlete):
    plan = build_fuel_plan(athlete, duration_h=0.5, intensity_factor=0.55)
    assert plan.carb_g_per_h == 0
    assert any("mouth rinse" in n for n in plan.notes)


def test_heat_raises_sweat_rate_and_sodium(athlete):
    cool = build_fuel_plan(athlete, duration_h=3.0, temp_c=12)
    hot = build_fuel_plan(athlete, duration_h=3.0, temp_c=33, humidity_pct=80)
    assert hot.sweat_rate_l_per_h > cool.sweat_rate_l_per_h
    assert hot.sodium_mg_per_h > cool.sodium_mg_per_h
    assert hot.fluid_ml_per_h >= cool.fluid_ml_per_h


def test_fluid_never_exceeds_gastric_emptying(athlete):
    plan = build_fuel_plan(athlete, duration_h=6.0, temp_c=38, humidity_pct=90)
    assert plan.fluid_ml_per_h <= 1000
    assert any("dehydrated" in w for w in plan.warnings)


def test_sweat_rate_falls_in_the_cold(athlete):
    assert estimate_sweat_rate(athlete, 5, 50, 0.70) < athlete.sweat_rate_l_per_h


def test_unmeasured_sweat_always_warns(athlete):
    guessing = type(athlete)(**{**athlete.__dict__, "sweat_measured": False})
    plan = build_fuel_plan(guessing, duration_h=3.0)
    assert any("sweat test" in w for w in plan.warnings)


def test_daily_carb_bands_match_burke(athlete):
    """[BUR11] table: light 3-5, moderate 5-7, high 6-10, very high 8-12 g/kg/day."""
    assert daily_carb_target_g_per_kg(0.5)[:2] == (3.0, 5.0)
    assert daily_carb_target_g_per_kg(1.0)[:2] == (5.0, 7.0)
    assert daily_carb_target_g_per_kg(2.5)[:2] == (6.0, 10.0)
    assert daily_carb_target_g_per_kg(5.0)[:2] == (8.0, 12.0)


def test_zero_duration_rejected(athlete):
    with pytest.raises(ValueError):
        build_fuel_plan(athlete, duration_h=0)
