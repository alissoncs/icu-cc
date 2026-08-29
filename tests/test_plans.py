"""Persistence tests for ``plans.py``.

The plans root is always a ``tmp_path`` — nothing here may touch the real ``data/plans``.
Anything time-relative is built from ``date.today()``, because ``compliance``,
``next_session`` and ``reconcile`` all read the clock.
"""

import json
import re
from datetime import date, datetime, timedelta

import pytest

from cycling_coach.plans import (
    STATUS_COMPLETED,
    STATUS_MISSED,
    STATUS_PLANNED,
    Constraints,
    Plan,
    PlanError,
    Session,
    Week,
    latest_plan,
    list_plans,
    load_plan,
    make_plan_id,
    reconcile,
    save_plan,
)

TODAY = date.today()


def _constraints(**over) -> Constraints:
    base = dict(
        days_per_week=4,
        weekly_hours=6.0,
        days_available=["tue", "thu", "sat", "sun"],
        long_ride_day="sat",
        weeks=4,
    )
    base.update(over)
    return Constraints(**base)


def _plan(plan_id: str = "2026-w36-base", *, created_at: datetime | None = None,
          weeks: list[Week] | None = None) -> Plan:
    return Plan(
        id=plan_id,
        created_at=created_at or datetime(2026, 8, 28, 21, 40),
        constraints=_constraints(),
        weeks=weeks if weeks is not None else [],
        athlete="test_rider",
        ftp_at_creation=250,
        weight_at_creation=72.0,
        phase="base",
        rationale="Pyramidal base block. No dated goal, so building durability [SEI10].",
    )


def _session(day: date, name: str = "Endurance Z2", kind: str = "endurance",
             minutes: int = 90, tss: float | None = 68.0, **over) -> Session:
    s = Session(
        date=day,
        name=name,
        kind=kind,
        duration_min=minutes,
        description="90 min a 125-171 W.",
        target_zone="Z2",
        target_watts=[125, 171],
        planned_tss=tss,
        fueling={"carb_g_per_h": 30, "fluid_ml_per_h": 500, "sodium_mg_per_h": 400},
    )
    for k, v in over.items():
        setattr(s, k, v)
    return s


def _activity(day: date, tss: float = 71.0, minutes: int = 95, np_w: int = 168,
              name: str = "Morning Ride") -> dict:
    """Intervals.icu-shaped, so ``session.normalize`` has to do its aliasing job."""
    return {
        "name": name,
        "type": "Ride",
        "start_date_local": f"{day.isoformat()}T06:12:00",
        "moving_time": minutes * 60,
        "icu_training_load": tss,
        "icu_weighted_avg_watts": np_w,
        "average_heartrate": 141,
    }


# ------------------------------------------------------------------ round trip
def test_save_then_load_round_trips_the_nested_structure(tmp_path):
    plan = _plan(weeks=[
        Week(
            index=1,
            start_date=date(2026, 8, 31),
            kind="load",
            target_tss=320,
            target_hours=6.0,
            note="Semana de carga.",
            sessions=[
                _session(date(2026, 9, 1)),
                _session(date(2026, 9, 5), "Longo", "long", 180, 140.0),
            ],
        ),
        Week(index=2, start_date=date(2026, 9, 7), kind="recovery", target_tss=180,
             sessions=[_session(date(2026, 9, 8), "Recuperação", "recovery", 60, 35.0)]),
    ])

    path = save_plan(plan, tmp_path)
    assert path == tmp_path / "2026-w36-base.json"

    loaded = load_plan("2026-w36-base", tmp_path)

    assert loaded.to_dict() == plan.to_dict()
    assert loaded.id == plan.id
    assert loaded.created_at == plan.created_at
    assert loaded.constraints == plan.constraints
    assert loaded.phase == "base" and loaded.language == "pt-BR"
    assert loaded.rationale == plan.rationale

    # Dates come back as real date objects, not strings.
    assert isinstance(loaded.weeks[0].start_date, date)
    first = loaded.weeks[0].sessions[0]
    assert isinstance(first.date, date)
    assert first.date == date(2026, 9, 1)
    assert first.target_watts == [125, 171]
    assert first.fueling == {"carb_g_per_h": 30, "fluid_ml_per_h": 500, "sodium_mg_per_h": 400}
    assert first.status == STATUS_PLANNED
    assert [w.kind for w in loaded.weeks] == ["load", "recovery"]
    assert [s.name for s in loaded.weeks[0].sessions] == ["Endurance Z2", "Longo"]


def test_saved_json_keeps_dates_as_iso_strings(tmp_path):
    plan = _plan(weeks=[Week(index=1, start_date=date(2026, 8, 31),
                             sessions=[_session(date(2026, 9, 1))])])
    raw = json.loads(save_plan(plan, tmp_path).read_text())
    assert raw["weeks"][0]["start_date"] == "2026-08-31"
    assert raw["weeks"][0]["sessions"][0]["date"] == "2026-09-01"
    assert raw["created_at"] == "2026-08-28T21:40:00"


# --------------------------------------------------------------------- listing
def test_list_plans_is_newest_first_and_skips_a_malformed_file(tmp_path):
    save_plan(_plan("2026-w34-base", created_at=datetime(2026, 8, 14, 9, 0)), tmp_path)
    save_plan(_plan("2026-w36-build", created_at=datetime(2026, 8, 28, 21, 40)), tmp_path)
    save_plan(_plan("2026-w35-base", created_at=datetime(2026, 8, 21, 12, 0)), tmp_path)
    (tmp_path / "broken.json").write_text("{ this is not json,,,")

    plans = list_plans(tmp_path)

    assert [p.id for p in plans] == ["2026-w36-build", "2026-w35-base", "2026-w34-base"]
    assert latest_plan(tmp_path).id == "2026-w36-build"


def test_list_plans_on_a_missing_directory_is_empty(tmp_path):
    assert list_plans(tmp_path / "nope") == []
    assert latest_plan(tmp_path / "nope") is None


def test_latest_plan_on_an_empty_dir_is_none(tmp_path):
    assert latest_plan(tmp_path) is None


def test_load_plan_on_a_missing_id_raises(tmp_path):
    with pytest.raises(PlanError):
        load_plan("2026-w99-base", tmp_path)


def test_plan_from_dict_rejects_a_missing_required_field():
    with pytest.raises(PlanError):
        Plan.from_dict({"id": "x", "created_at": "2026-08-28T21:40:00"})


# --------------------------------------------------------------------- derived
def test_totals_and_week_geometry():
    plan = _plan(weeks=[
        Week(index=1, start_date=date(2026, 8, 31), sessions=[
            _session(date(2026, 9, 1), minutes=90, tss=68.0),
            _session(date(2026, 9, 5), "Longo", "long", 180, 140.0),
        ]),
        Week(index=2, start_date=date(2026, 9, 7), kind="recovery", sessions=[
            _session(date(2026, 9, 8), "Recuperação", "recovery", 60, 35.0),
        ]),
    ])

    assert plan.weeks[0].end_date == date(2026, 9, 6)
    assert plan.weeks[0].planned_hours == 4.5      # 90 + 180 min
    assert plan.weeks[0].planned_tss == 208.0
    assert plan.weeks[1].planned_hours == 1.0
    assert plan.total_hours == 5.5
    assert plan.total_tss == 243.0
    assert plan.start_date == date(2026, 8, 31)
    assert plan.end_date == date(2026, 9, 13)
    assert len(plan.all_sessions()) == 3


def test_week_for_and_session_on():
    plan = _plan(weeks=[
        Week(index=1, start_date=date(2026, 8, 31), sessions=[_session(date(2026, 9, 1))]),
        Week(index=2, start_date=date(2026, 9, 7), sessions=[_session(date(2026, 9, 8))]),
    ])

    assert plan.week_for(date(2026, 8, 31)).index == 1
    assert plan.week_for(date(2026, 9, 6)).index == 1     # inclusive end
    assert plan.week_for(date(2026, 9, 7)).index == 2
    assert plan.week_for(date(2026, 9, 30)) is None       # outside the plan

    assert plan.session_on(date(2026, 9, 1)).name == "Endurance Z2"
    assert plan.session_on(date(2026, 9, 2)) is None      # a day with nothing on it


def test_next_session_skips_rest_days_and_anything_already_past():
    plan = _plan(weeks=[Week(index=1, start_date=TODAY - timedelta(days=3), sessions=[
        _session(TODAY - timedelta(days=2), "Passado", "endurance"),
        _session(TODAY, "Descanso", "rest", 0, None),
        _session(TODAY + timedelta(days=1), "Amanhã", "threshold"),
        _session(TODAY + timedelta(days=3), "Longo", "long"),
    ])])

    nxt = plan.next_session()
    assert nxt is not None
    assert nxt.name == "Amanhã"

    # Explicit `after` overrides today.
    assert plan.next_session(after=TODAY + timedelta(days=2)).name == "Longo"
    assert plan.next_session(after=TODAY + timedelta(days=10)) is None


def test_next_session_is_none_for_an_all_rest_plan():
    plan = _plan(weeks=[Week(index=1, start_date=TODAY, sessions=[
        _session(TODAY + timedelta(days=1), "Descanso", "rest", 0, None),
    ])])
    assert plan.next_session() is None


def test_is_hard_only_for_the_sessions_that_need_an_easy_day_either_side():
    for kind in ("threshold", "vo2", "block"):
        assert _session(TODAY, kind=kind).is_hard is True
    for kind in ("endurance", "recovery", "tempo", "long", "rest"):
        assert _session(TODAY, kind=kind).is_hard is False


def test_duration_h():
    assert _session(TODAY, minutes=90).duration_h == 1.5


# ------------------------------------------------------------------ compliance
def test_compliance_counts_only_past_sessions_and_ignores_rest():
    plan = _plan(weeks=[Week(index=1, start_date=TODAY - timedelta(days=6), sessions=[
        _session(TODAY - timedelta(days=4), tss=70.0, status=STATUS_COMPLETED,
                 actual={"tss": 74.0, "duration_min": 95}),
        _session(TODAY - timedelta(days=3), tss=60.0, status=STATUS_MISSED),
        _session(TODAY - timedelta(days=2), "Descanso", "rest", 0, None),   # never counted
        _session(TODAY + timedelta(days=2), tss=90.0),                      # still future
    ])])

    c = plan.compliance()

    assert c["due"] == 2                 # the rest day and the future session are excluded
    assert c["completed"] == 1
    assert c["missed"] == 1
    assert c["pct"] == 50
    assert c["planned_tss"] == 130.0     # 70 + 60, not the future 90
    assert c["actual_tss"] == 74.0


def test_compliance_on_a_plan_with_nothing_due_yet():
    plan = _plan(weeks=[Week(index=1, start_date=TODAY + timedelta(days=1), sessions=[
        _session(TODAY + timedelta(days=2)),
    ])])
    c = plan.compliance()
    assert c["due"] == 0 and c["completed"] == 0 and c["pct"] is None


# ---------------------------------------------------------------------- ids
def test_make_plan_id_is_a_sortable_year_week_phase_slug():
    start = date(2026, 8, 31)
    year, week, _ = start.isocalendar()

    plan_id = make_plan_id(start, "base")

    assert plan_id == f"{year}-w{week:02d}-base"
    assert re.fullmatch(r"\d{4}-w\d{2}-[a-z0-9-]+", plan_id)
    assert make_plan_id(start, "Base Build") == f"{year}-w{week:02d}-base-build"

    ascending = [make_plan_id(d, "base") for d in (
        date(2026, 1, 5), date(2026, 3, 2), date(2026, 8, 31), date(2026, 11, 30),
    )]
    assert ascending == sorted(ascending)   # lexicographic order is chronological


# ----------------------------------------------------------------- reconciling
def test_reconcile_completes_matched_sessions_misses_unmatched_and_leaves_the_future():
    done_day = TODAY - timedelta(days=3)
    skipped_day = TODAY - timedelta(days=2)
    future_day = TODAY + timedelta(days=3)

    plan = _plan(weeks=[Week(index=1, start_date=TODAY - timedelta(days=6), sessions=[
        _session(done_day, "Endurance Z2", tss=68.0),
        _session(skipped_day, "Tempo", "tempo", 75, 80.0),
        _session(TODAY - timedelta(days=1), "Descanso", "rest", 0, None),
        _session(future_day, "Longo", "long", 180, 140.0),
    ])])

    summary = reconcile(plan, [_activity(done_day, tss=71.0, minutes=95, np_w=168)])

    done = plan.session_on(done_day)
    assert done.status == STATUS_COMPLETED
    assert done.actual == {
        "name": "Morning Ride",
        "duration_min": 95,
        "tss": 71.0,
        "np_w": 168.0,
        "avg_hr": 141.0,
        "activity_count": 1,
    }

    assert plan.session_on(skipped_day).status == STATUS_MISSED
    assert plan.session_on(skipped_day).actual is None

    # Future work is untouched — a session you have not had the chance to do is not missed.
    assert plan.session_on(future_day).status == STATUS_PLANNED
    assert plan.session_on(future_day).actual is None

    # Rest days are never reconciled either way.
    assert plan.session_on(TODAY - timedelta(days=1)).status == STATUS_PLANNED

    assert summary["completed"] == 1
    assert summary["missed"] == 1
    assert summary["compliance"]["due"] == 2
    assert summary["compliance"]["pct"] == 50


def test_reconcile_sums_tss_across_two_activities_on_the_same_day():
    day = TODAY - timedelta(days=2)
    plan = _plan(weeks=[Week(index=1, start_date=day, sessions=[
        _session(day, "Duplo", "endurance", 150, 120.0),
    ])])

    reconcile(plan, [
        _activity(day, tss=40.0, minutes=45, np_w=150, name="Commute in"),
        _activity(day, tss=85.0, minutes=110, np_w=180, name="Evening Ride"),
    ])

    actual = plan.session_on(day).actual
    assert actual["tss"] == 125.0            # summed across both rides
    assert actual["activity_count"] == 2
    assert actual["name"] == "Evening Ride"  # the longest ride represents the day
    assert actual["duration_min"] == 110
    assert actual["np_w"] == 180.0


def test_reconcile_ignores_activities_on_days_with_no_planned_session():
    day = TODAY - timedelta(days=2)
    plan = _plan(weeks=[Week(index=1, start_date=day, sessions=[_session(day)])])

    summary = reconcile(plan, [
        _activity(day),
        _activity(TODAY - timedelta(days=5), name="Unplanned ride"),
    ])

    assert summary["completed"] == 1
    assert summary["missed"] == 0


def test_reconcile_tolerates_activities_with_no_usable_date():
    day = TODAY - timedelta(days=2)
    plan = _plan(weeks=[Week(index=1, start_date=day, sessions=[_session(day)])])

    summary = reconcile(plan, [{"name": "No date", "moving_time": 3600}, _activity(day)])

    assert summary["completed"] == 1
    assert plan.session_on(day).status == STATUS_COMPLETED


def test_reconcile_survives_a_save_load_round_trip(tmp_path):
    day = TODAY - timedelta(days=2)
    plan = _plan(weeks=[Week(index=1, start_date=day, sessions=[_session(day)])])
    reconcile(plan, [_activity(day, tss=71.0)])

    save_plan(plan, tmp_path)
    loaded = load_plan(plan.id, tmp_path)

    assert loaded.session_on(day).status == STATUS_COMPLETED
    assert loaded.session_on(day).actual["tss"] == 71.0


# --------------------------------------------------------------------------------------
# Regressions. Each of these locks in a fix for a real defect found in review; without
# them the bug is silently reintroducible.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({"created_at": "not-a-timestamp"}, id="bad-created_at"),
        pytest.param({"weeks": [{"index": 1, "start_date": "2026-13-45", "sessions": []}]},
                     id="bad-week-date"),
        pytest.param({"constraints": {"weekly_hours": 6.0}}, id="constraints-missing-key"),
    ],
)
def test_list_plans_survives_a_file_that_is_valid_json_but_bad_data(tmp_path, broken):
    """A corrupt plan must never hide the healthy ones.

    Catching only JSONDecodeError/PlanError/KeyError left bad ISO dates and missing
    constraint keys fatal to the whole listing.
    """
    save_plan(_plan("good-one"), tmp_path)
    payload = _plan("bad-one").to_dict() | broken
    (tmp_path / "bad-one.json").write_text(json.dumps(payload))

    ids = [p.id for p in list_plans(tmp_path)]
    assert ids == ["good-one"]


def test_reconcile_never_completes_a_future_session_even_with_a_matching_activity():
    """An activity dated ahead of today is a timezone or parsing fault, not a ride."""
    future = date.today() + timedelta(days=3)
    plan = _plan(weeks=[Week(index=1, start_date=date.today(),
                             sessions=[_session(future)])])

    summary = reconcile(plan, [_activity(future)])

    assert plan.all_sessions()[0].status == STATUS_PLANNED
    assert plan.all_sessions()[0].actual is None
    assert summary["completed"] == 0


def test_compliance_does_not_count_todays_session_until_it_is_done():
    """Counting today as due from midnight made compliance collapse every morning."""
    today = date.today()
    plan = _plan(weeks=[Week(index=1, start_date=today, sessions=[_session(today)])])

    assert plan.compliance()["due"] == 0

    plan.all_sessions()[0].status = STATUS_COMPLETED
    done = plan.compliance()
    assert done["due"] == 1 and done["completed"] == 1 and done["pct"] == 100


def test_next_session_skips_a_session_already_completed_today():
    today = date.today()
    plan = _plan(weeks=[Week(index=1, start_date=today, sessions=[
        _session(today, name="Ja feito", status=STATUS_COMPLETED),
        _session(today + timedelta(days=1), name="Proximo"),
    ])])
    assert plan.next_session().name == "Proximo"


def test_next_session_skips_a_missed_session():
    today = date.today()
    plan = _plan(weeks=[Week(index=1, start_date=today, sessions=[
        _session(today, name="Perdido", status=STATUS_MISSED),
        _session(today + timedelta(days=2), name="Proximo"),
    ])])
    assert plan.next_session().name == "Proximo"


def test_reconcile_reports_unknown_tss_as_none_not_zero():
    """`round(sum(...)) or None` turned a reported 0.0 and an absent value into None."""
    yesterday = date.today() - timedelta(days=1)
    plan = _plan(weeks=[Week(index=1, start_date=yesterday,
                             sessions=[_session(yesterday)])])

    reconcile(plan, [{"start_date_local": yesterday.isoformat(), "moving_time": 3600,
                      "name": "Sem load"}])

    assert plan.all_sessions()[0].status == STATUS_COMPLETED
    assert plan.all_sessions()[0].actual["tss"] is None
