"""Web app tests.

Every test points ``create_app`` at a temp directory, so the suite never reads or writes
``data/plans`` and stays offline. The fixture plan is built with the ``plans`` dataclasses
rather than a JSON blob: if the schema changes, these tests should fail to construct
rather than silently assert against a stale shape.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cycling_coach.plans import (
    STATUS_COMPLETED,
    STATUS_MISSED,
    Constraints,
    Plan,
    Session,
    Week,
    save_plan,
)
from cycling_coach.web.app import create_app

PLAN_ID = "2026-w36-base"


def _monday(offset_weeks: int = 0) -> date:
    """Monday of the current week, so 'this week' is always inside the fixture plan."""
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset_weeks)


def build_plan(plan_id: str = PLAN_ID, language: str = "pt-BR") -> Plan:
    """Two weeks: one already ridden (mixed compliance), one still ahead."""
    w1_start = _monday(-1)
    w2_start = _monday(0)

    week1 = Week(
        index=1,
        start_date=w1_start,
        kind="load",
        target_tss=320,
        target_hours=6.0,
        note="Primeira semana de carga.",
        sessions=[
            Session(
                date=w1_start + timedelta(days=1),
                name="Endurance Z2",
                kind="endurance",
                duration_min=90,
                description="Ritmo constante, sem picos.",
                target_zone="Z2",
                target_watts=[125, 171],
                planned_tss=68,
                fueling={"carb_g_per_h": 30, "fluid_ml_per_h": 500, "sodium_mg_per_h": 400},
                status=STATUS_COMPLETED,
                actual={"name": "Rodagem", "duration_min": 92, "tss": 70.0, "np_w": 160},
            ),
            Session(
                date=w1_start + timedelta(days=3),
                name="Sweet Spot 3x15",
                kind="sweetspot",
                duration_min=75,
                description="3x15 min a 88-93% do FTP.",
                target_zone="Z3",
                target_watts=[200, 212],
                planned_tss=75,
                fueling={"carb_g_per_h": 45, "fluid_ml_per_h": 600, "sodium_mg_per_h": 500},
                status=STATUS_MISSED,
            ),
            Session(
                date=w1_start + timedelta(days=5),
                name="Longão",
                kind="long",
                duration_min=180,
                description="Longo em Z2 com 3x10 min tempo.",
                target_zone="Z2",
                target_watts=[125, 171],
                planned_tss=140,
                fueling={
                    "carb_g_per_h": 60,
                    "carb_total_g": 180,
                    "fluid_ml_per_h": 650,
                    "sodium_mg_per_h": 520,
                    "notes": ["Pré-treino: ~110 g de carboidrato."],
                    "warnings": ["Sem teste de suor — sódio é estimativa."],
                },
            ),
            Session(
                date=w1_start + timedelta(days=6),
                name="Descanso",
                kind="rest",
                duration_min=0,
            ),
        ],
    )
    week2 = Week(
        index=2,
        start_date=w2_start,
        kind="recovery",
        target_tss=180,
        target_hours=4.0,
        sessions=[
            Session(
                date=w2_start + timedelta(days=1),
                name="Recuperação",
                kind="recovery",
                duration_min=60,
                target_zone="Z1",
                target_watts=[90, 125],
                planned_tss=35,
            ),
            Session(
                date=w2_start + timedelta(days=5),
                name="VO2 5x4",
                kind="vo2",
                duration_min=70,
                description="5x4 min a 110-120% do FTP.",
                target_zone="Z5",
                target_watts=[251, 274],
                planned_tss=90,
                fueling={"carb_g_per_h": 30, "fluid_ml_per_h": 550, "sodium_mg_per_h": 420},
            ),
        ],
    )
    return Plan(
        id=plan_id,
        created_at=datetime(2026, 8, 28, 21, 40),
        constraints=Constraints(
            days_per_week=4,
            weekly_hours=6.0,
            days_available=["tue", "thu", "sat", "sun"],
            long_ride_day="sat",
            weeks=2,
        ),
        weeks=[week1, week2],
        language=language,
        athlete="alisson_cs",
        ftp_at_creation=228,
        weight_at_creation=75.0,
        phase="base",
        rationale="Bloco de base piramidal.",
        warnings=["FTP tem 60 dias."],
    )


@pytest.fixture
def plan(tmp_path: Path) -> Plan:
    p = build_plan()
    save_plan(p, tmp_path)
    return p


@pytest.fixture
def client(tmp_path: Path, plan: Plan) -> TestClient:
    return TestClient(create_app(plans_root=tmp_path), raise_server_exceptions=False)


@pytest.fixture
def empty_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(plans_root=tmp_path / "nothing-here"),
                      raise_server_exceptions=False)


# ------------------------------------------------------------------- dashboard
def test_dashboard_renders_the_plan(client: TestClient, plan: Plan) -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert plan.id in body
    assert "VO2 5x4" in body               # a session from the week we are in
    assert "Recuperação" in body
    assert "<svg" in body                  # both charts are inline SVG, no CDN
    assert "cdn" not in body.lower()


def test_dashboard_shows_form_and_compliance(client: TestClient) -> None:
    body = client.get("/").text
    assert "CTL" in body and "ATL" in body and "TSB" in body
    # One session done, one missed in week 1 — compliance must be visible, not implied.
    assert "Concluído" in body and "Perdido" in body


def test_dashboard_uses_ptbr_chrome(client: TestClient, plan: Plan) -> None:
    """Chrome follows plan.language; the plan's own prose is already PT-BR."""
    body = client.get("/").text
    for word in ("Semana", "Concluído", "Perdido", "Painel"):
        assert word in body

    week = client.get(f"/plan/{plan.id}/week/1").text
    assert "Treinos" in week and "Descanso" in week

    long_ride = plan.weeks[0].sessions[2]
    detail = client.get(f"/session/{plan.id}/{long_ride.date.isoformat()}").text
    for word in ("Treino", "Duração", "Carboidrato"):
        assert word in detail


def test_english_plan_falls_back_to_english_chrome(tmp_path: Path) -> None:
    save_plan(build_plan(plan_id="2026-w40-build", language="en"), tmp_path)
    c = TestClient(create_app(plans_root=tmp_path))
    body = c.get("/").text
    assert "Completed" in body and "Missed" in body
    assert "Concluído" not in body


# ------------------------------------------------------------------ plan pages
def test_plan_page_lists_every_week(client: TestClient, plan: Plan) -> None:
    r = client.get(f"/plan/{plan.id}")
    assert r.status_code == 200
    for week in plan.weeks:
        assert f"/plan/{plan.id}/week/{week.index}" in r.text
    assert "Bloco de base piramidal." in r.text   # rationale is shown, not hidden


def test_week_page_shows_its_sessions(client: TestClient, plan: Plan) -> None:
    r = client.get(f"/plan/{plan.id}/week/1")
    assert r.status_code == 200
    for s in plan.weeks[0].sessions:
        assert s.name in r.text
    # and not the other week's
    assert "VO2 5x4" not in r.text


def test_unknown_week_is_404(client: TestClient, plan: Plan) -> None:
    assert client.get(f"/plan/{plan.id}/week/99").status_code == 404


# --------------------------------------------------------------- session page
def test_session_page_shows_watts_and_fueling(client: TestClient, plan: Plan) -> None:
    session = plan.weeks[0].sessions[2]        # the long ride, full fuel block
    r = client.get(f"/session/{plan.id}/{session.date.isoformat()}")
    assert r.status_code == 200
    body = r.text
    assert "125" in body and "171" in body     # target watts, absolute numbers
    assert "W" in body
    assert "Carboidrato" in body               # PT-BR fueling label
    assert "60" in body                        # carb g/h
    assert "Pré-treino: ~110 g de carboidrato." in body
    assert "Sem teste de suor — sódio é estimativa." in body
    assert session.description in body


def test_session_status_is_labelled_not_only_coloured(client: TestClient, plan: Plan) -> None:
    missed = plan.weeks[0].sessions[1]
    r = client.get(f"/session/{plan.id}/{missed.date.isoformat()}")
    assert "Perdido" in r.text
    assert "✕" in r.text


def test_malformed_date_is_400_not_500(client: TestClient, plan: Plan) -> None:
    r = client.get(f"/session/{plan.id}/not-a-date")
    assert r.status_code == 400
    assert "YYYY-MM-DD" in r.text


def test_session_on_a_day_with_no_ride_is_404(client: TestClient, plan: Plan) -> None:
    assert client.get(f"/session/{plan.id}/1999-01-01").status_code == 404


# ------------------------------------------------------------------------ api
def test_api_returns_the_saved_plan(client: TestClient, plan: Plan, tmp_path: Path) -> None:
    r = client.get(f"/api/plan/{plan.id}")
    assert r.status_code == 200
    payload = r.json()
    assert payload == json.loads((tmp_path / f"{plan.id}.json").read_text())
    assert payload["id"] == plan.id
    assert len(payload["weeks"]) == len(plan.weeks)
    assert payload["weeks"][0]["sessions"][0]["target_watts"] == [125, 171]


def test_api_unknown_plan_is_json_404(client: TestClient) -> None:
    r = client.get("/api/plan/does-not-exist")
    assert r.status_code == 404
    assert "error" in r.json()


def test_api_plans_index(client: TestClient, plan: Plan) -> None:
    r = client.get("/api/plans")
    assert r.status_code == 200
    assert [p["id"] for p in r.json()] == [plan.id]


# -------------------------------------------------------------- failure modes
def test_unknown_plan_id_renders_404_page(client: TestClient) -> None:
    r = client.get("/plan/nope")
    assert r.status_code == 404
    assert "404" in r.text
    assert "<html" in r.text                   # a page, not a JSON blob


def test_empty_plans_dir_does_not_500(empty_client: TestClient) -> None:
    r = empty_client.get("/")
    assert r.status_code == 200
    assert "No plans yet" in r.text


def test_malformed_plan_file_does_not_500(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "broken.json").write_text("{not json")
    c = TestClient(create_app(plans_root=tmp_path), raise_server_exceptions=False)
    assert c.get("/").status_code == 200       # empty state, the bad file is skipped
    assert c.get("/plan/broken").status_code == 404


def test_static_css_is_served_locally(client: TestClient) -> None:
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert "prefers-color-scheme: dark" in r.text
