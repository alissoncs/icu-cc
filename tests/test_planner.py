"""The planner's job is to make coaching rules unbreakable, so the tests assert the rules.

Every test here maps to a line in docs/evidence-base.md. A plan that violates the ramp
ceiling or stacks hard days is worse than no plan, so these are correctness tests, not
smoke tests.
"""

from datetime import date, timedelta

from cycling_coach.load import pmc
from cycling_coach.periodization import TAPER_FREQUENCY_CUT_MAX
from cycling_coach.planner import (
    SESSION_CATALOGUE,
    build_plan,
    plan_distribution,
)
from cycling_coach.plans import Constraints, Plan

MONDAY = date(2026, 8, 31)          # the plans below all start here
FRIDAY_BEFORE = date(2026, 8, 28)


def four_days(weeks: int = 4, hours: float = 6.0) -> Constraints:
    return Constraints(
        days_per_week=4, weekly_hours=hours,
        days_available=["tue", "thu", "sat", "sun"], long_ride_day="sat", weeks=weeks,
    )


def six_days(weeks: int = 4, hours: float = 9.0) -> Constraints:
    return Constraints(
        days_per_week=6, weekly_hours=hours,
        days_available=["mon", "tue", "wed", "thu", "fri", "sat"],
        long_ride_day="sat", weeks=weeks,
    )


def load_weeks(plan):
    return [w for w in plan.weeks if w.kind == "load"]


# ------------------------------------------------------------------ the constraints
def test_weekly_hours_fit_what_the_athlete_actually_has(athlete):
    """A plan needing 9 h from someone with 6 is not a plan."""
    c = four_days()
    plan = build_plan(athlete, c, start_date=FRIDAY_BEFORE)
    for w in load_weeks(plan):
        assert abs(w.planned_hours - c.weekly_hours) / c.weekly_hours <= 0.10


def test_nothing_is_scheduled_on_a_day_off(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    allowed = {1, 3, 5, 6}                      # tue, thu, sat, sun
    assert {s.date.weekday() for s in plan.all_sessions()} <= allowed


def test_days_per_week_is_respected_in_load_weeks(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    assert all(len(w.sessions) == 4 for w in load_weeks(plan))


def test_the_long_ride_lands_on_the_long_ride_day(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    longs = [s for s in plan.all_sessions() if s.kind == "long"]
    assert longs
    assert all(s.date.weekday() == 5 for s in longs)         # saturday
    # and it is genuinely the longest ride of its week
    for w in plan.weeks:
        ride = next((s for s in w.sessions if s.kind == "long"), None)
        if ride:
            assert ride.duration_min == max(s.duration_min for s in w.sessions)


def test_plan_starts_on_a_monday(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    assert plan.weeks[0].start_date == MONDAY
    assert [w.index for w in plan.weeks] == [1, 2, 3, 4]


# --------------------------------------------------------------------- hard/easy
def test_hard_days_are_never_adjacent(athlete):
    """Session.is_hard needs an easy day either side, or neither day is what it says."""
    plan = build_plan(athlete, six_days(), phase="build", start_date=FRIDAY_BEFORE)
    hard = sorted(s.date for s in plan.all_sessions() if s.is_hard)
    assert len(hard) >= 6                       # the test would be vacuous otherwise
    assert all((b - a).days > 1 for a, b in zip(hard, hard[1:]))


def test_hard_days_stay_apart_across_the_week_boundary(athlete):
    """Sunday and the following Monday are back to back in real life."""
    plan = build_plan(athlete, six_days(weeks=6), phase="build", start_date=FRIDAY_BEFORE)
    hard = sorted(s.date for s in plan.all_sessions() if s.is_hard)
    assert all((b - a).days > 1 for a, b in zip(hard, hard[1:]))


# ------------------------------------------------------------------ [FRI18] 3 + 1
def test_fourth_week_is_a_recovery_week(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    assert [w.kind for w in plan.weeks] == ["load", "load", "load", "recovery"]


def test_recovery_week_lands_between_50_and_60_percent_of_load_tss(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    load, recovery = plan.weeks[2], plan.weeks[3]
    ratio = recovery.planned_tss / load.planned_tss
    assert 0.50 <= ratio <= 0.60, ratio
    assert not any(s.is_hard for s in recovery.sessions)


def test_a_three_week_plan_still_unloads(athlete):
    plan = build_plan(athlete, four_days(weeks=3), start_date=FRIDAY_BEFORE)
    assert [w.kind for w in plan.weeks] == ["load", "load", "recovery"]


def test_a_two_week_plan_does_not_waste_a_week_on_recovery(athlete):
    plan = build_plan(athlete, four_days(weeks=2), start_date=FRIDAY_BEFORE)
    assert [w.kind for w in plan.weeks] == ["load", "load"]


def test_load_weeks_progress(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    tss = [w.planned_tss for w in load_weeks(plan)]
    assert tss == sorted(tss)


# --------------------------------------------------------------- [COG19] ramp rate
def _peak_ramp(plan, seed):
    daily = {}
    for s in plan.all_sessions():
        daily[s.date] = daily.get(s.date, 0.0) + (s.planned_tss or 0.0)
    daily.setdefault(plan.start_date, 0.0)
    daily.setdefault(plan.end_date, 0.0)
    points = pmc(daily, ctl_seed=seed, atl_seed=seed)
    return max(points[i].ctl - points[i - 7].ctl for i in range(7, len(points)))


def test_ramp_rate_stays_inside_the_profile_ceiling(athlete):
    plan = build_plan(athlete, four_days(), current_ctl=45, start_date=FRIDAY_BEFORE)
    assert _peak_ramp(plan, 45) <= athlete.max_ramp_rate + 0.05


def test_volume_is_capped_and_said_out_loud_rather_than_exceeded(athlete):
    """The tool says what it will not do and why, instead of silently ramping. [COG19]"""
    asked = Constraints(
        days_per_week=6, weekly_hours=12.0,
        days_available=["mon", "tue", "wed", "thu", "fri", "sat"],
        long_ride_day="sat", weeks=4,
    )
    plan = build_plan(athlete, asked, current_ctl=15, start_date=FRIDAY_BEFORE)
    assert any("capped" in w and "max_ramp_rate" in w for w in plan.warnings)
    assert all(w.planned_hours < asked.weekly_hours for w in load_weeks(plan))
    assert _peak_ramp(plan, 15) <= athlete.max_ramp_rate + 0.05


def test_week_one_is_not_a_cliff_when_ctl_is_supplied(athlete):
    low = build_plan(athlete, four_days(), current_ctl=10, start_date=FRIDAY_BEFORE)
    high = build_plan(athlete, four_days(), current_ctl=60, start_date=FRIDAY_BEFORE)
    assert low.weeks[0].planned_tss <= high.weeks[0].planned_tss


# ------------------------------------------------------------- [SEI10] distribution
def test_most_of_the_time_is_low_intensity(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    dist = plan_distribution(plan, athlete.ftp_w)
    assert dist.low_pct >= 75
    assert dist.high_pct + dist.moderate_pct <= 25


def test_base_is_pyramidal_and_build_is_more_polarized(athlete):
    base = plan_distribution(
        build_plan(athlete, six_days(), phase="base", start_date=FRIDAY_BEFORE),
        athlete.ftp_w,
    )
    build = plan_distribution(
        build_plan(athlete, six_days(), phase="build", start_date=FRIDAY_BEFORE),
        athlete.ftp_w,
    )
    assert base.moderate_pct > base.high_pct          # more tempo than VO2max
    assert build.high_pct > base.high_pct             # the hard work moved up
    assert build.high_pct >= build.moderate_pct       # and the middle emptied out
    assert base.low_pct >= 75 and build.low_pct >= 75


def test_a_plan_that_drifts_off_80_20_says_so(athlete):
    """The check is on the output, not on the intent."""
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    dist = plan_distribution(plan, athlete.ftp_w)
    drifted = any("low intensity" in w for w in plan.warnings)
    assert drifted == (dist.low_pct < 72)


# ------------------------------------------------------------------ [RON14] blocks
def test_block_mode_is_five_then_one(athlete):
    plan = build_plan(athlete, six_days(), use_block=True, start_date=FRIDAY_BEFORE)
    hit = [len([s for s in w.sessions if s.kind == "block"]) for w in plan.weeks]
    assert hit == [5, 1, 1, 1]
    assert plan.phase == "block"


def test_block_carries_its_overreaching_warnings(athlete):
    plan = build_plan(athlete, six_days(), use_block=True, start_date=FRIDAY_BEFORE)
    assert any("Overreaching is the intent" in w for w in plan.warnings)
    assert any("back to back" in w for w in plan.warnings)


def test_block_says_so_when_there_are_not_five_days(athlete):
    plan = build_plan(athlete, four_days(), use_block=True, start_date=FRIDAY_BEFORE)
    assert any("five HIT sessions" in w for w in plan.warnings)


def test_block_week_one_is_the_only_place_hard_days_stack(athlete):
    plan = build_plan(athlete, six_days(), use_block=True, start_date=FRIDAY_BEFORE)
    later = sorted(s.date for w in plan.weeks[1:] for s in w.sessions if s.is_hard)
    assert all((b - a).days > 1 for a, b in zip(later, later[1:]))


# ------------------------------------------------------------------- [MUJ03] taper
def test_taper_cuts_volume_and_leaves_intensity_alone(athlete):
    goal = {"name": "Prova", "date": "2026-09-24", "priority": "A"}
    plan = build_plan(athlete, four_days(), goal=goal, start_date=FRIDAY_BEFORE)
    taper = [w for w in plan.weeks if w.kind == "taper"]
    assert len(taper) == 2

    last_load = load_weeks(plan)[-1]
    for w in taper:
        cut = 1 - w.planned_hours / last_load.planned_hours
        assert 0.40 <= cut <= 0.60, cut                       # volume down 40-60%
        # frequency down by no more than 20%
        assert len(w.sessions) >= len(last_load.sessions) * (1 - TAPER_FREQUENCY_CUT_MAX)

    def peak(week):
        return max(s.target_watts[1] for s in week.sessions)

    def quality(week):
        return {s.kind for s in week.sessions} - {"endurance", "long", "recovery"}

    # Intensity is the one variable that must not drop: same session kinds, same watts.
    for w in taper:
        assert quality(w) == quality(last_load)
        assert peak(w) == peak(last_load)


def test_taper_shortens_the_sets_not_the_watts(athlete):
    goal = {"name": "Prova", "date": "2026-09-24", "priority": "A"}
    plan = build_plan(athlete, four_days(), goal=goal, start_date=FRIDAY_BEFORE)
    load = load_weeks(plan)[-1]
    taper = [w for w in plan.weeks if w.kind == "taper"][-1]
    ss_load = next(s for s in load.sessions if s.kind == "sweetspot")
    ss_taper = next(s for s in taper.sessions if s.kind == "sweetspot")
    assert ss_taper.target_watts == ss_load.target_watts
    assert ss_taper.duration_min < ss_load.duration_min


def test_a_goal_beyond_the_horizon_is_not_silently_ignored(athlete):
    goal = {"name": "Prova", "date": "2027-05-01"}
    plan = build_plan(athlete, four_days(), goal=goal, start_date=FRIDAY_BEFORE)
    assert not any(w.kind == "taper" for w in plan.weeks)
    assert any("outside" in w for w in plan.warnings)


# ------------------------------------------------------------------ [JEU14] fueling
def test_every_ride_over_ninety_minutes_carries_a_fuel_plan(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    long_ones = [s for s in plan.all_sessions() if s.duration_min > 90]
    assert long_ones
    for s in long_ones:
        assert s.fueling
        assert s.fueling["carb_g_per_h"] > 0
        assert s.fueling["fluid_ml_per_h"] >= 0
        assert s.fueling["sodium_mg_per_h"] > 0


def test_short_rides_are_not_cluttered_with_a_fuel_line(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    assert all(s.fueling is None for s in plan.all_sessions() if s.duration_min <= 90)


# ------------------------------------------------------------------- [COG19] watts
def test_targets_are_absolute_watts_never_a_bare_zone(athlete):
    plan = build_plan(athlete, six_days(), phase="build", start_date=FRIDAY_BEFORE)
    for s in plan.all_sessions():
        assert s.target_watts and len(s.target_watts) == 2
        low, high = s.target_watts
        assert isinstance(low, int) and isinstance(high, int)
        assert 0 < low < high
        assert f"{low}-{high} W" in s.description


def test_zone_two_watts_match_the_zone_model(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    endurance = next(s for s in plan.all_sessions() if s.kind == "endurance")
    assert endurance.target_watts == [138, 188]      # 55-75% of a 250 W FTP [COG19]


def test_planned_tss_is_derived_not_invented(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    for s in plan.all_sessions():
        assert s.planned_tss and s.planned_tss > 0
    endurance = next(s for s in plan.all_sessions() if s.kind == "endurance")
    mid = sum(endurance.target_watts) / 2
    expected = (endurance.duration_min / 60) * (mid / athlete.ftp_w) ** 2 * 100
    assert abs(endurance.planned_tss - expected) < 0.5


# ---------------------------------------------------------------------- language
def test_athlete_facing_text_is_brazilian_portuguese_by_default(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    assert plan.language == "pt-BR"
    text = " ".join(f"{s.name} {s.description}" for s in plan.all_sessions())
    assert "Mantenha cadência confortável, sem entrar em Z3." in text
    assert "Longão" in text
    assert "fácil entre as séries" in text
    assert "min em Z2 (138-188 W)" in text
    assert "easy between sets" not in text


def test_english_is_available_for_the_same_plan(athlete):
    plan = build_plan(athlete, four_days(), language="en", start_date=FRIDAY_BEFORE)
    text = " ".join(f"{s.name} {s.description}" for s in plan.all_sessions())
    assert "Hold a comfortable cadence" in text
    assert "cadência" not in text


def test_week_notes_follow_the_plan_language(athlete):
    pt = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    en = build_plan(athlete, four_days(), language="en", start_date=FRIDAY_BEFORE)
    assert "recuperação" in pt.weeks[3].note.lower()
    assert "Recovery week" in en.weeks[3].note


# ---------------------------------------------------------------------- catalogue
def test_the_catalogue_is_fixed_and_reproducible(athlete):
    """Sessions come from a catalogue so a plan can be tested, not just admired."""
    for key in ("endurance_90", "sweetspot_3x15", "vo2_5x6", "recovery_45", "long_ride"):
        assert key in SESSION_CATALOGUE
    first = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    second = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    assert [s.to_dict() for s in first.all_sessions()] == [
        s.to_dict() for s in second.all_sessions()
    ]


def test_the_plan_survives_a_round_trip_through_json(athlete):
    plan = build_plan(athlete, six_days(), phase="build", start_date=FRIDAY_BEFORE)
    again = Plan.from_dict(plan.to_dict())
    assert again.total_tss == plan.total_tss
    assert again.id == plan.id and again.warnings == plan.warnings
    assert len(again.all_sessions()) == len(plan.all_sessions())


def test_the_plan_records_the_athlete_it_was_built_for(athlete):
    plan = build_plan(athlete, four_days(), start_date=FRIDAY_BEFORE)
    assert plan.ftp_at_creation == athlete.ftp_w
    assert plan.weight_at_creation == athlete.weight_kg
    assert plan.id == "2026-w36-base"
    assert "[SEI10]" in plan.rationale


def test_sessions_are_dated_inside_their_own_week(athlete):
    plan = build_plan(athlete, four_days(weeks=6), start_date=FRIDAY_BEFORE)
    for w in plan.weeks:
        assert all(w.contains(s.date) for s in w.sessions)
        assert w.start_date == MONDAY + timedelta(days=7 * (w.index - 1))


# --------------------------------------------------------------------------------------
# The maintenance floor. The ramp ceiling stops a plan building faster than the body can
# absorb; nothing stopped the mirror image, a plan that quietly detrains the athlete for
# a month. Found by generating a real 6 h/week block against a real CTL of 47.7.
# --------------------------------------------------------------------------------------


def _maintenance_warning(plan):
    return next((w for w in plan.warnings if "loses fitness" in w), None)


def test_warns_when_the_plan_sits_below_maintenance(athlete):
    """4 h/week against a CTL of 80 cannot hold that CTL, and must say so."""
    plan = build_plan(
        athlete,
        Constraints(days_per_week=4, weekly_hours=4.0,
                    days_available=["tue", "thu", "sat", "sun"],
                    long_ride_day="sat", weeks=4),
        current_ctl=80.0,
    )
    warning = _maintenance_warning(plan)
    assert warning is not None
    # It must quantify the gap, not just assert it — the athlete needs the number to
    # decide whether to add hours or accept the easy block.
    assert "TSS/week" in warning


def test_no_maintenance_warning_when_the_plan_actually_builds(athlete):
    plan = build_plan(
        athlete,
        Constraints(days_per_week=5, weekly_hours=8.0,
                    days_available=["mon", "tue", "thu", "sat", "sun"],
                    long_ride_day="sat", weeks=4),
        current_ctl=25.0,
    )
    assert _maintenance_warning(plan) is None


def test_a_closing_recovery_week_alone_does_not_trip_the_warning(athlete):
    """CTL dipping a point or two into an unload is the design, not detraining."""
    plan = build_plan(
        athlete,
        Constraints(days_per_week=5, weekly_hours=8.0,
                    days_available=["mon", "tue", "thu", "sat", "sun"],
                    long_ride_day="sat", weeks=4),
        current_ctl=55.0,
    )
    assert plan.weeks[-1].kind == "recovery"
    assert _maintenance_warning(plan) is None
