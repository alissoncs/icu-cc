"""FastAPI application: the browser view of a saved plan.

Server-rendered on purpose. A plan is read on a phone in a kit pocket five minutes before
rolling out, so the page has to be complete on first paint with no network round trips
after it — which rules out a client-side framework fetching JSON. The two charts are
inline SVG generated here in Python for the same reason: a charting library would be the
only thing on the page that needs a CDN.

This module reads plans through ``plans.py`` and never recomputes what a dataclass already
derives. ``Week.planned_tss``, ``Plan.compliance()`` and friends are the single definition
of those numbers; duplicating the arithmetic in a template is how a dashboard starts
disagreeing with the CLI.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import plans as plans_mod
from ..load import PmcPoint, form_label, pmc
from ..plans import Plan, PlanError, Week

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# How much of the series the PMC chart shows: 42 days, exactly one CTL time constant.
# Anything older has already decayed out of today's fitness number, so plotting it would
# widen the chart without adding information a phone screen can use.
PMC_WINDOW_DAYS = 42


# --------------------------------------------------------------------------- i18n
# Only the chrome is translated. Session names, descriptions and coaching notes come out
# of the plan already written in ``plan.language`` — the planner owns that voice, not us.
# English is the base layer, so a partially translated locale degrades to English words
# rather than to raw template keys.
LABELS: dict[str, dict[str, Any]] = {
    "en": {
        "app": "Cycling Coach",
        "dashboard": "Dashboard",
        "plan": "Plan",
        "plans": "Plans",
        "week": "Week",
        "weeks": "Weeks",
        "session": "Session",
        "sessions": "Sessions",
        "duration": "Duration",
        "planned": "Planned",
        "completed": "Completed",
        "missed": "Missed",
        "modified": "Modified",
        "rest": "Rest",
        "carbs": "Carbohydrate",
        "fluid": "Fluid",
        "sodium": "Sodium",
        "fueling": "Fueling",
        "fitness": "Fitness (CTL)",
        "fatigue": "Fatigue (ATL)",
        "form": "Form (TSB)",
        "next_session": "Next session",
        "this_week": "This week",
        "compliance": "Compliance",
        "target": "Target",
        "watts": "Watts",
        "zone": "Zone",
        "description": "Description",
        "actual": "Actual",
        "phase": "Phase",
        "goal": "Goal",
        "rationale": "Why this plan",
        "warnings": "Warnings",
        "notes": "Notes",
        "total": "Total",
        "hours": "h",
        "min": "min",
        "back": "Back",
        "all_weeks": "All weeks",
        "weekly_tss": "Planned load per week",
        "pmc_title": "Fitness, fatigue and form",
        "pmc_note": "Projected from this plan, not from ridden data.",
        "no_plans": "No plans yet",
        "no_plans_hint": "Ask the coach to build one, then reload this page.",
        "not_found": "Not found",
        "no_sessions": "Nothing scheduled.",
        "of": "of",
        "per_hour": "/h",
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "kind_load": "Load",
        "kind_recovery": "Recovery",
        "kind_taper": "Taper",
        "kind_block": "Block",
        "help": "Help",
        "help_title": "Skills & commands",
        "help_skills": "Skills",
        "help_skills_hint": "Say these to Claude in conversation.",
        "help_commands": "CLI commands",
        "help_commands_hint": "Run these in a terminal with `coach ...`.",
    },
    "pt-BR": {
        "app": "Treinador de Ciclismo",
        "dashboard": "Painel",
        "plan": "Plano",
        "plans": "Planos",
        "week": "Semana",
        "weeks": "Semanas",
        "session": "Treino",
        "sessions": "Treinos",
        "duration": "Duração",
        "planned": "Planejado",
        "completed": "Concluído",
        "missed": "Perdido",
        "modified": "Modificado",
        "rest": "Descanso",
        "carbs": "Carboidrato",
        "fluid": "Líquido",
        "sodium": "Sódio",
        "fueling": "Nutrição",
        "fitness": "Condição (CTL)",
        "fatigue": "Fadiga (ATL)",
        "form": "Forma (TSB)",
        "next_session": "Próximo treino",
        "this_week": "Esta semana",
        "compliance": "Aderência",
        "target": "Alvo",
        "watts": "Watts",
        "zone": "Zona",
        "description": "Descrição",
        "actual": "Realizado",
        "phase": "Fase",
        "goal": "Objetivo",
        "rationale": "Por que este plano",
        "warnings": "Avisos",
        "notes": "Observações",
        "total": "Total",
        "hours": "h",
        "min": "min",
        "back": "Voltar",
        "all_weeks": "Todas as semanas",
        "weekly_tss": "Carga planejada por semana",
        "pmc_title": "Condição, fadiga e forma",
        "pmc_note": "Projeção deste plano, não de dados pedalados.",
        "no_plans": "Nenhum plano ainda",
        "no_plans_hint": "Peça um plano ao treinador e recarregue esta página.",
        "not_found": "Não encontrado",
        "no_sessions": "Nada programado.",
        "of": "de",
        "per_hour": "/h",
        "weekdays": ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"],
        "kind_load": "Carga",
        "kind_recovery": "Recuperação",
        "kind_taper": "Polimento",
        "kind_block": "Bloco",
        "help": "Ajuda",
        "help_title": "Skills e comandos",
        "help_skills": "Skills",
        "help_skills_hint": "Peça isso ao Claude em conversa.",
        "help_commands": "Comandos CLI",
        "help_commands_hint": "Rode no terminal com `coach ...`.",
    },
}

# Reference card for the help page: the skills and CLI commands this project ships.
# Titles stay in their literal invocation form (skill slug / shell command) in every
# language — only the description is translated — because that is what the user actually
# types, in a terminal or in chat, to invoke them.
HELP_SKILLS: list[dict[str, str]] = [
    {
        "title": "analyze-session",
        "en": '"How was yesterday\'s ride?" — one activity, in depth.',
        "pt-BR": '"Como foi o treino de ontem?" — uma atividade, em profundidade.',
    },
    {
        "title": "fuel-plan",
        "en": '"What should I eat for Saturday?" — carbs, fluid, sodium, timing.',
        "pt-BR": '"O que devo comer no sábado?" — carboidrato, líquido, sódio e timing.',
    },
    {
        "title": "weekly-review",
        "en": '"How was my week?" — load, distribution, ramp, consistency.',
        "pt-BR": '"Como foi minha semana?" — carga, distribuição, rampa, consistência.',
    },
    {
        "title": "plan-block",
        "en": '"What should I do for the next 6 weeks?" — plans and calendar writes.',
        "pt-BR": '"O que fazer nas próximas 6 semanas?" — planos e escrita no calendário.',
    },
    {
        "title": "benchmark-vs-pros",
        "en": '"How do I stack up?" — power profile and professional context.',
        "pt-BR": '"Como eu me comparo?" — perfil de potência e contexto profissional.',
    },
    {
        "title": "planejar-treino",
        "en": "PT-BR. Asks the athlete in Portuguese, then generates, saves and "
        "renders a plan.",
        "pt-BR": '"Quero treino para as próximas semanas" — pergunta em português, '
        "gera, salva e renderiza o plano.",
    },
]

HELP_COMMANDS: list[dict[str, str]] = [
    {
        "title": "coach profile",
        "en": "Athlete profile plus data-quality warnings.",
        "pt-BR": "Perfil do atleta e avisos de qualidade de dados.",
    },
    {
        "title": "coach zones",
        "en": "Power [COG19] and heart-rate [FRI18] training zones.",
        "pt-BR": "Zonas de treino de potência [COG19] e frequência cardíaca [FRI18].",
    },
    {
        "title": "coach fuel",
        "en": "Carbohydrate, fluid and sodium plan for a duration and intensity.",
        "pt-BR": "Plano de carboidrato, líquido e sódio para duração e intensidade.",
    },
    {
        "title": "coach session",
        "en": "Coaching read on one activity, from a saved JSON.",
        "pt-BR": "Leitura de treinador sobre uma atividade, a partir de um JSON salvo.",
    },
    {
        "title": "coach pmc",
        "en": "CTL / ATL / TSB, ramp rate and monotony from a daily load series.",
        "pt-BR": "CTL / ATL / TSB, ramp rate e monotonia a partir da carga diária.",
    },
    {
        "title": "coach tid",
        "en": "Intensity distribution — polarized, pyramidal or threshold.",
        "pt-BR": "Distribuição de intensidade — polarizada, piramidal ou de limiar.",
    },
    {
        "title": "coach benchmark",
        "en": "Power-profile category bands from short best-effort numbers.",
        "pt-BR": "Faixas de categoria a partir dos melhores esforços de potência.",
    },
    {
        "title": "coach taper",
        "en": "Taper to the next A-priority goal [MUJ03].",
        "pt-BR": "Polimento até a próxima prova prioridade A [MUJ03].",
    },
    {
        "title": "coach block",
        "en": "4-week high-intensity mesocycle [RON14].",
        "pt-BR": "Mesociclo de 4 semanas de alta intensidade [RON14].",
    },
    {
        "title": "coach plan create / list / show / reconcile",
        "en": "Generate, list, print and reconcile saved plans against what was ridden.",
        "pt-BR": "Gera, lista, exibe e reconcilia planos salvos com o que foi pedalado.",
    },
    {
        "title": "coach serve",
        "en": "Run this web dashboard.",
        "pt-BR": "Sobe este dashboard web.",
    },
]

# Status must never be signalled by colour alone — a rider in sunglasses on a phone in
# daylight gets the glyph and the word before they get the hue. [accessibility]
STATUS_GLYPH = {
    plans_mod.STATUS_PLANNED: "○",
    plans_mod.STATUS_COMPLETED: "✓",
    plans_mod.STATUS_MISSED: "✕",
    plans_mod.STATUS_MODIFIED: "≈",
}


def labels_for(language: str | None) -> dict[str, Any]:
    """Chrome labels for a plan's language, falling back key-by-key to English."""
    merged = dict(LABELS["en"])
    merged.update(LABELS.get(language or "", {}))
    return merged


def help_rows(items: list[dict[str, str]], language: str | None) -> list[dict[str, str]]:
    """Title + one-line description for the help page, in the dashboard's language."""
    lang = language if language in LABELS else "en"
    return [{"title": it["title"], "desc": it.get(lang, it["en"])} for it in items]


def status_label(status: str, labels: dict[str, Any]) -> str:
    return str(labels.get(status, status))


def week_kind_label(kind: str, labels: dict[str, Any]) -> str:
    return str(labels.get(f"kind_{kind}", kind.title()))


def weekday_short(day: date, labels: dict[str, Any]) -> str:
    return str(labels["weekdays"][day.weekday()])


def fmt_day(day: date, labels: dict[str, Any]) -> str:
    """``sáb 06/09`` — day of week first, because that is how a training week is read."""
    return f"{weekday_short(day, labels)} {day.day:02d}/{day.month:02d}"


# ------------------------------------------------------------------- plan reading
def _daily_load(plan: Plan) -> dict[date, float]:
    """Daily TSS series for the PMC, preferring what was actually ridden.

    A completed session contributes its measured load; a missed one contributes nothing,
    which is the whole point of tracking compliance. Everything still in the future
    contributes its plan.
    """
    out: dict[date, float] = {}
    for s in plan.all_sessions():
        if s.kind == "rest":
            continue
        if s.status == plans_mod.STATUS_MISSED:
            load = 0.0
        elif s.status == plans_mod.STATUS_COMPLETED:
            actual = (s.actual or {}).get("tss")
            load = float(actual) if actual else float(s.planned_tss or 0.0)
        else:
            load = float(s.planned_tss or 0.0)
        out[s.date] = out.get(s.date, 0.0) + load
    return out


def plan_pmc(plan: Plan) -> list[PmcPoint]:
    """PMC over the plan window.

    Seeded rather than started from zero: a plan that begins at CTL 0 draws a six-week
    ramp the athlete never rode and makes week 1 look like a shock it is not. The seed is
    the plan's own first-week daily average, which is the closest thing to "where this
    athlete already is" available without wellness data.
    """
    daily = _daily_load(plan)
    if not daily:
        return []
    first = plan.weeks[0] if plan.weeks else None
    weekly = (first.target_tss if first and first.target_tss else None) or (
        first.planned_tss if first else 0.0
    )
    seed = round(float(weekly or 0.0) / 7, 1)
    return pmc(daily, ctl_seed=seed, atl_seed=seed)


def current_week(plan: Plan, today: date | None = None) -> Week | None:
    """The week we are in, or the next one that starts — never nothing while weeks remain.

    Before a plan starts and after it ends the honest answer differs: ahead of it, show
    what is coming; past the end, show the last week so the page still has content.
    """
    today = today or date.today()
    inside = plan.week_for(today)
    if inside is not None:
        return inside
    upcoming = [w for w in plan.weeks if w.start_date > today]
    if upcoming:
        return min(upcoming, key=lambda w: w.start_date)
    return plan.weeks[-1] if plan.weeks else None


# ------------------------------------------------------------------------- charts
def _points_path(xs: list[float], ys: list[float]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


def pmc_svg(
    points: list[PmcPoint],
    labels: dict[str, Any],
    today: date | None = None,
    width: int = 640,
    height: int = 220,
) -> str:
    """CTL / ATL / TSB as one inline SVG line chart.

    One shared y-scale across all three series, including negative TSB, so the reader can
    see fatigue crossing fitness rather than three charts that have to be mentally
    aligned. Colours come from CSS custom properties so the chart follows dark mode
    without being redrawn.
    """
    if not points:
        return ""
    today = today or date.today()
    window = points[-PMC_WINDOW_DAYS:] if len(points) > PMC_WINDOW_DAYS else points
    if len(window) < 2:
        window = points  # a one-point line is not a chart; show whatever exists

    pad_l, pad_r, pad_t, pad_b = 34, 10, 14, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    values = [v for p in window for v in (p.ctl, p.atl, p.tsb)]
    lo, hi = min(values + [0.0]), max(values + [0.0])
    if hi - lo < 1:
        hi, lo = lo + 1, lo - 1
    span = hi - lo

    n = max(len(window) - 1, 1)
    xs = [pad_l + plot_w * i / n for i in range(len(window))]

    def y_of(value: float) -> float:
        return pad_t + plot_h * (1 - (value - lo) / span)

    zero_y = y_of(0.0)
    series = [
        ("ctl", labels["fitness"], [p.ctl for p in window]),
        ("atl", labels["fatigue"], [p.atl for p in window]),
        ("tsb", labels["form"], [p.tsb for p in window]),
    ]

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{labels["pmc_title"]}">'
    ]
    # Zero reference only matters for TSB, which is the only series that goes negative.
    if lo < 0 < hi:
        parts.append(
            f'<line class="ch-zero" x1="{pad_l}" y1="{zero_y:.1f}" '
            f'x2="{width - pad_r}" y2="{zero_y:.1f}" />'
        )
    parts.append(
        f'<line class="ch-axis" x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" '
        f'y2="{pad_t + plot_h}" />'
    )
    for key, _name, ys in series:
        path = _points_path(xs, [y_of(v) for v in ys])
        parts.append(f'<polyline class="ch-line ch-{key}" points="{path}" />')

    # "You are here" — without it the chart is a plan, not a status.
    marked = [i for i, p in enumerate(window) if p.day == today]
    if marked:
        x = xs[marked[0]]
        parts.append(
            f'<line class="ch-today" x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" '
            f'y2="{pad_t + plot_h}" />'
        )

    parts.append(
        f'<text class="ch-tick" x="{pad_l - 5}" y="{pad_t + 9}" text-anchor="end">'
        f"{hi:.0f}</text>"
    )
    parts.append(
        f'<text class="ch-tick" x="{pad_l - 5}" y="{pad_t + plot_h}" text-anchor="end">'
        f"{lo:.0f}</text>"
    )
    parts.append(
        f'<text class="ch-tick" x="{pad_l}" y="{height - 6}">'
        f"{fmt_day(window[0].day, labels)}</text>"
    )
    parts.append(
        f'<text class="ch-tick" x="{width - pad_r}" y="{height - 6}" text-anchor="end">'
        f"{fmt_day(window[-1].day, labels)}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def weekly_tss_svg(
    plan: Plan,
    labels: dict[str, Any],
    width: int = 640,
    height: int = 180,
) -> str:
    """Planned TSS per week, with the completed share filled in.

    Recovery weeks are marked with a hatch as well as a lighter fill, so the 3-load-plus-1
    structure survives a greyscale print or a colour-blind reader.
    """
    if not plan.weeks:
        return ""
    pad_l, pad_r, pad_t, pad_b = 30, 10, 16, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    planned = [w.planned_tss for w in plan.weeks]
    done = [
        round(
            sum(
                (s.actual or {}).get("tss") or s.planned_tss or 0
                for s in w.sessions
                if s.status == plans_mod.STATUS_COMPLETED
            ),
            1,
        )
        for w in plan.weeks
    ]
    hi = max(planned + [1.0])

    slot = plot_w / len(plan.weeks)
    bar_w = max(slot * 0.62, 6.0)

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{labels["weekly_tss"]}">'
    ]
    parts.append(
        '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<line class="ch-hatch" x1="0" y1="0" x2="0" y2="6" /></pattern></defs>'
    )
    for i, week in enumerate(plan.weeks):
        x = pad_l + slot * i + (slot - bar_w) / 2
        h_plan = plot_h * (planned[i] / hi)
        y_plan = pad_t + plot_h - h_plan
        recovery = week.kind == "recovery"
        cls = "ch-bar ch-bar-recovery" if recovery else "ch-bar"
        parts.append(
            f'<rect class="{cls}" x="{x:.1f}" y="{y_plan:.1f}" width="{bar_w:.1f}" '
            f'height="{h_plan:.1f}" rx="2" />'
        )
        if recovery:
            parts.append(
                f'<rect fill="url(#hatch)" x="{x:.1f}" y="{y_plan:.1f}" '
                f'width="{bar_w:.1f}" height="{h_plan:.1f}" rx="2" />'
            )
        if done[i] > 0:
            h_done = plot_h * (min(done[i], hi) / hi)
            parts.append(
                f'<rect class="ch-bar-done" x="{x:.1f}" '
                f'y="{pad_t + plot_h - h_done:.1f}" width="{bar_w:.1f}" '
                f'height="{h_done:.1f}" rx="2" />'
            )
        parts.append(
            f'<text class="ch-tick" x="{x + bar_w / 2:.1f}" y="{height - 8}" '
            f'text-anchor="middle">{week.index}</text>'
        )
        parts.append(
            f'<text class="ch-val" x="{x + bar_w / 2:.1f}" y="{y_plan - 4:.1f}" '
            f'text-anchor="middle">{planned[i]:.0f}</text>'
        )
    parts.append(
        f'<line class="ch-axis" x1="{pad_l}" y1="{pad_t + plot_h}" '
        f'x2="{width - pad_r}" y2="{pad_t + plot_h}" />'
    )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------- fuel block
# Ordered so the phone screen reads top-down in the order the rider needs it: what to eat,
# what to drink, what to put in the drink.
FUEL_FIELDS: list[tuple[str, str, str]] = [
    ("carb_g_per_h", "carbs", "g/h"),
    ("carb_total_g", "carbs", "g"),
    ("fluid_ml_per_h", "fluid", "mL/h"),
    ("fluid_total_ml", "fluid", "mL"),
    ("sodium_mg_per_h", "sodium", "mg/h"),
    ("sodium_total_mg", "sodium", "mg"),
    ("caffeine_mg", "caffeine", "mg"),
    ("pre_ride_carb_g", "pre_ride", "g"),
    ("post_ride_carb_g", "post_ride", "g"),
]
FUEL_EXTRA_LABELS = {
    "en": {"caffeine": "Caffeine", "pre_ride": "Pre-ride carbs", "post_ride": "Post-ride carbs"},
    "pt-BR": {
        "caffeine": "Cafeína",
        "pre_ride": "Carboidrato pré-treino",
        "post_ride": "Carboidrato pós-treino",
    },
}


def fuel_rows(fueling: dict[str, Any] | None, labels: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a session's fueling dict into displayable rows.

    Tolerant by design: the planner may write a short block (three numbers) or the full
    ``FuelPlan`` dump, and anything it invents that we do not know about is still shown
    rather than silently dropped.
    """
    if not fueling:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, label_key, unit in FUEL_FIELDS:
        value = fueling.get(key)
        seen.add(key)
        if value in (None, "", 0):
            continue
        name = labels.get(label_key) or FUEL_EXTRA_LABELS["en"].get(label_key, label_key)
        rows.append({"label": name, "value": value, "unit": unit})
    for key, value in fueling.items():
        if key in seen or isinstance(value, (list, dict)) or value in (None, "", 0):
            continue
        rows.append({"label": key.replace("_", " "), "value": value, "unit": ""})
    return rows


def fuel_notes(fueling: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if not fueling:
        return [], []
    notes = [str(n) for n in (fueling.get("notes") or [])]
    warnings = [str(w) for w in (fueling.get("warnings") or [])]
    return notes, warnings


# ----------------------------------------------------------------------- the app
def create_app(plans_root: str | Path | None = None) -> FastAPI:
    """Build the app, optionally reading plans from somewhere other than ``data/plans``.

    ``plans_root`` is threaded through every call rather than set globally so tests (and a
    future multi-athlete setup) can point two apps at two directories in one process.
    """
    app = FastAPI(title="Cycling Coach", docs_url=None, redoc_url=None)
    app.state.plans_root = Path(plans_root) if plans_root else None

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals.update(
        fmt_day=fmt_day,
        status_glyph=lambda s: STATUS_GLYPH.get(s, "•"),
        status_label=status_label,
        week_kind_label=week_kind_label,
    )
    app.state.templates = templates

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def root() -> Path | None:
        return app.state.plans_root

    def render(
        request: Request, name: str, ctx: dict[str, Any], status_code: int = 200
    ) -> Response:
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)

    def fail(status: int, message: str) -> StarletteHTTPException:
        return StarletteHTTPException(status_code=status, detail=message)

    def get_plan(plan_id: str) -> Plan:
        try:
            return plans_mod.load_plan(plan_id, root())
        except PlanError as exc:
            raise fail(404, str(exc)) from exc
        except (ValueError, OSError) as exc:  # unreadable or corrupt file on disk
            raise fail(404, f"plan '{plan_id}' could not be read: {exc}") from exc

    def base_ctx(plan: Plan | None) -> dict[str, Any]:
        labels = labels_for(plan.language if plan else None)
        return {"L": labels, "plan": plan, "today": date.today()}

    # ------------------------------------------------------------------ routes
    @app.get("/", response_class=Response)
    def dashboard(request: Request) -> Response:
        all_plans = plans_mod.list_plans(root())
        if not all_plans:
            # An empty install is a normal state, not an error. Say so in English, since
            # with no plan there is no language to follow.
            return render(request, "empty.html", {"L": labels_for(None), "plan": None})

        plan = all_plans[0]
        ctx = base_ctx(plan)
        points = plan_pmc(plan)
        latest = points[-1] if points else None
        ctx.update(
            plans=all_plans,
            week=current_week(plan),
            compliance=plan.compliance(),
            next_session=plan.next_session(),
            pmc_point=latest,
            form=form_label(latest.tsb) if latest else None,
            pmc_chart=pmc_svg(points, ctx["L"]),
            tss_chart=weekly_tss_svg(plan, ctx["L"]),
        )
        return render(request, "dashboard.html", ctx)

    @app.get("/help", response_class=Response)
    def help_page(request: Request) -> Response:
        # Matches whichever plan the dashboard is showing, so the reference card reads in
        # the same language as the rest of the site instead of always defaulting to English.
        all_plans = plans_mod.list_plans(root())
        language = all_plans[0].language if all_plans else None
        ctx = {
            "L": labels_for(language),
            "plan": None,
            "skills": help_rows(HELP_SKILLS, language),
            "commands": help_rows(HELP_COMMANDS, language),
        }
        return render(request, "help.html", ctx)

    @app.get("/plan/{plan_id}", response_class=Response)
    def plan_detail(request: Request, plan_id: str) -> Response:
        plan = get_plan(plan_id)
        ctx = base_ctx(plan)
        ctx.update(
            compliance=plan.compliance(),
            tss_chart=weekly_tss_svg(plan, ctx["L"]),
            current=current_week(plan),
        )
        return render(request, "plan.html", ctx)

    @app.get("/plan/{plan_id}/week/{index}", response_class=Response)
    def week_detail(request: Request, plan_id: str, index: int) -> Response:
        plan = get_plan(plan_id)
        week = next((w for w in plan.weeks if w.index == index), None)
        if week is None:
            raise fail(404, f"plan '{plan_id}' has no week {index}")
        ctx = base_ctx(plan)
        ctx.update(week=week, weeks=plan.weeks)
        return render(request, "week.html", ctx)

    @app.get("/session/{plan_id}/{day}", response_class=Response)
    def session_detail(request: Request, plan_id: str, day: str) -> Response:
        plan = get_plan(plan_id)
        try:
            when = date.fromisoformat(day)
        except ValueError as exc:
            # A typed or truncated URL should explain itself, not 500.
            raise fail(400, f"'{day}' is not a date in YYYY-MM-DD form") from exc
        session = plan.session_on(when)
        if session is None:
            raise fail(404, f"plan '{plan_id}' has no session on {when.isoformat()}")
        ctx = base_ctx(plan)
        rows = fuel_rows(session.fueling, ctx["L"])
        notes, warnings = fuel_notes(session.fueling)
        ctx.update(
            session=session,
            week=plan.week_for(session.date),
            fuel_rows=rows,
            fuel_notes=notes,
            fuel_warnings=warnings,
        )
        return render(request, "session.html", ctx)

    @app.get("/api/plan/{plan_id}")
    def plan_json(plan_id: str) -> JSONResponse:
        """The plan exactly as stored, so the agent can read back what it wrote."""
        return JSONResponse(get_plan(plan_id).to_dict())

    @app.get("/api/plans")
    def plans_json() -> JSONResponse:
        return JSONResponse(
            [
                {
                    "id": p.id,
                    "phase": p.phase,
                    "created_at": p.created_at.isoformat(),
                    "weeks": len(p.weeks),
                    "total_hours": p.total_hours,
                }
                for p in plans_mod.list_plans(root())
            ]
        )

    # ------------------------------------------------------------------ errors
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        return render(
            request,
            "error.html",
            {"L": labels_for(None), "plan": None, "code": exc.status_code,
             "detail": exc.detail},
            status_code=exc.status_code,
        )

    return app


def run(host: str = "127.0.0.1", port: int = 8010, plans_root: str | Path | None = None) -> None:
    """Convenience entry point for ``coach serve``; the CLI owns the argument parsing."""
    import uvicorn

    uvicorn.run(create_app(plans_root), host=host, port=port)
