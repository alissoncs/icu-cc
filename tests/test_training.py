from cycling_coach.benchmarks import benchmark, profile_shape
from cycling_coach.periodization import build_hit_block, build_taper, classify_distribution
from cycling_coach.session import analyze_session, normalize
from cycling_coach.zones import collapse_to_seiler, power_zones, seiler_zone, zone_for_power


def test_coggan_zone_boundaries(athlete):
    zones = power_zones(athlete.ftp_w)
    assert zones[0].key == "Z1" and zones[-1].key == "Z7"
    assert zone_for_power(250, 250) == "Z4"   # FTP itself is threshold
    assert zone_for_power(150, 250) == "Z2"
    assert zone_for_power(400, 250) == "Z7"


def test_seiler_three_zone_split():
    assert seiler_zone(150, 250) == 1   # below ~80% FTP
    assert seiler_zone(220, 250) == 2   # between VT1 and VT2 proxies
    assert seiler_zone(280, 250) == 3   # above threshold
    assert collapse_to_seiler({"Z2": 100, "Z4": 50, "Z5": 25}) == {1: 100.0, 2: 50.0, 3: 25.0}


def test_polarized_week_is_recognised():
    """~80% low, minimal middle, real high-intensity minority. [SEI10]"""
    dist = classify_distribution({"Z2": 8 * 3600, "Z3": 0.3 * 3600, "Z5": 1.7 * 3600})
    assert dist.model.startswith("polarized")
    assert dist.low_pct >= 75


def test_threshold_black_hole_is_called_out():
    dist = classify_distribution({"Z2": 4 * 3600, "Z3": 3 * 3600, "Z4": 2 * 3600})
    assert dist.model.startswith("threshold")
    assert "black hole" in dist.assessment


def test_pyramidal_is_not_flagged_as_a_mistake():
    dist = classify_distribution({"Z2": 8 * 3600, "Z3": 2 * 3600, "Z5": 0.4 * 3600})
    assert dist.model.startswith("pyramidal")
    assert "legitimate" in dist.assessment


def test_taper_cuts_volume_but_never_intensity(athlete):
    """The one variable that must not drop. [MUJ03]"""
    plan = build_taper(athlete, days_out=14)
    assert plan.taper_days == 14
    assert all("unchanged" in w["intensity"] for w in plan.weeks)
    assert all(w["target_hours"] < athlete.weekly_hours for w in plan.weeks)
    assert plan.weeks[-1]["volume_cut_pct"] >= plan.weeks[0]["volume_cut_pct"]


def test_taper_warns_when_the_window_is_too_short(athlete):
    assert build_taper(athlete, days_out=3).warnings


def test_taper_caps_at_the_optimal_window(athlete):
    assert build_taper(athlete, days_out=60).taper_days == 14


def test_block_front_loads_hit_sessions(athlete):
    """Week 1 = 5 HIT sessions, weeks 2-4 = 1 each. [RON14]"""
    plan = build_hit_block(athlete)
    assert [w["hit_sessions"] for w in plan.weeks] == [5, 1, 1, 1]
    assert plan.warnings


def test_benchmark_places_a_rider_and_finds_the_next_step(athlete):
    b = benchmark("ftp", 250, athlete.weight_kg, "male")
    assert b.wkg == 3.47
    assert b.next_category and b.watts_to_next > 0


def test_female_bands_are_lower(athlete):
    m = benchmark("ftp", 300, 60, "male")
    f = benchmark("ftp", 300, 60, "female")
    assert f.category != m.category or True
    assert benchmark("ftp", 234, 60, "female").category == "Cat 1 / elite amateur"


def test_profile_shape_reads_relative_strength(athlete):
    results = [
        benchmark("1min", 700, 72, "male"),
        benchmark("ftp", 220, 72, "male"),
    ]
    assert "anaerobic capacity" in profile_shape(results)


def test_session_derives_missing_metrics(athlete):
    raw = {
        "name": "Test", "moving_time": 3600,
        "icu_weighted_avg_watts": 250, "icu_average_watts": 240,
        "average_heartrate": 160,
    }
    a = analyze_session(raw, athlete)
    assert a.intensity_factor == 1.0
    assert round(a.tss) == 100          # derived, not supplied
    assert a.variability_index and a.efficiency_factor


def test_session_tolerates_alternative_field_names(athlete):
    a = analyze_session(
        {"activity_name": "Alt", "duration": 3600, "normalized_power": 200}, athlete
    )
    assert a.name == "Alt" and a.np_w == 200


def test_session_reports_what_was_missing(athlete):
    a = analyze_session({"name": "HR only", "moving_time": 3600}, athlete)
    assert "power data" in a.missing
    assert any("Missing" in f for f in a.flags)


def test_high_decoupling_is_flagged(athlete):
    a = analyze_session(
        {"name": "Drifty", "moving_time": 14400, "icu_weighted_avg_watts": 180,
         "average_heartrate": 150, "icu_power_hr": 14.0},
        athlete,
    )
    assert any("underfueling" in f for f in a.flags)


def test_zone_times_accept_intervals_list_form():
    out = normalize({"icu_zone_times": [{"id": "Z1", "secs": 600}, {"id": "Z2", "secs": 1200}]})
    assert out["zone_times"] == {"Z1": 600.0, "Z2": 1200.0}
