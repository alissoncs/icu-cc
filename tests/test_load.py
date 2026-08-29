from datetime import date, timedelta

from cycling_coach.load import (
    intensity_factor,
    monotony_and_strain,
    normalized_power,
    pmc,
    ramp_rate,
    training_stress_score,
    variability_index,
)


def test_np_equals_average_for_constant_power():
    assert normalized_power([200.0] * 600) == 200.0


def test_np_exceeds_average_for_variable_power():
    surging = ([100.0] * 30 + [300.0] * 30) * 20
    avg = sum(surging) / len(surging)
    assert normalized_power(surging) > avg


def test_one_hour_at_ftp_is_100_tss():
    """The definition TSS is anchored on. [COG19]"""
    assert round(training_stress_score(3600, 250, 250)) == 100


def test_tss_scales_with_the_fourth_power_relationship():
    assert training_stress_score(3600, 125, 250) == 25.0
    assert intensity_factor(225, 250) == 0.9
    assert variability_index(196, 178) > 1.0


def test_pmc_fills_rest_days_and_decays():
    start = date(2026, 1, 1)
    loads = {start: 100.0}
    points = pmc({**loads, start + timedelta(days=20): 0.0})
    assert len(points) == 21
    assert points[-1].ctl < points[0].ctl  # fitness decays across the gap
    assert points[-1].atl < points[0].atl  # fatigue decays faster
    assert points[-1].atl < points[-1].ctl


def test_tsb_uses_yesterdays_values():
    """Today's ride must not flatter today's form."""
    start = date(2026, 1, 1)
    points = pmc({start + timedelta(days=i): 100.0 for i in range(5)})
    assert points[0].tsb == 0.0


def test_ramp_rate_positive_when_building():
    start = date(2026, 1, 1)
    points = pmc({start + timedelta(days=i): 100.0 for i in range(30)})
    assert ramp_rate(points) > 0


def test_monotony_high_when_every_day_is_identical():
    flat, _ = monotony_and_strain([80.0, 80.0, 80.0, 80.1, 80.0, 80.0, 80.0])
    varied, _ = monotony_and_strain([0.0, 150.0, 40.0, 0.0, 200.0, 60.0, 30.0])
    assert flat > varied
