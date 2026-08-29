"""Training plan persistence.

The local JSON file is the source of truth, not the Intervals.icu calendar. The calendar
is a projection we push to, so a plan survives a failed write or a manual edit in the
Intervals.icu UI. Each session carries the event id it was pushed as, so we can later
reconcile — or clean up exactly what we wrote and nothing else.

This module is storage only. Generation lives in ``planner.py``, rendering in ``web/``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PLANS_DIR = Path("data/plans")

# Session status lifecycle.
STATUS_PLANNED = "planned"
STATUS_COMPLETED = "completed"
STATUS_MISSED = "missed"
STATUS_MODIFIED = "modified"

WEEK_KINDS = {"load", "recovery", "taper", "block"}


class PlanError(ValueError):
    """Raised when a plan is malformed or cannot be found."""


def _as_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise PlanError(f"expected a date, got {type(value).__name__}")


@dataclass
class Session:
    """One planned ride."""

    date: date
    name: str
    kind: str                      # endurance | tempo | sweetspot | threshold | vo2 | block | recovery | long | rest
    duration_min: int
    description: str = ""
    target_zone: str | None = None
    target_watts: list[int] | None = None   # [low, high] absolute watts, never a bare zone label
    planned_tss: float | None = None
    fueling: dict[str, Any] | None = None
    status: str = STATUS_PLANNED
    intervals_event_id: str | None = None
    actual: dict[str, Any] | None = None

    @property
    def duration_h(self) -> float:
        return self.duration_min / 60

    @property
    def is_hard(self) -> bool:
        """Sessions that need a easy day either side."""
        return self.kind in {"threshold", "vo2", "block"}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Session:
        d = dict(d)
        d["date"] = _as_date(d["date"])
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Week:
    index: int
    start_date: date
    kind: str = "load"             # load | recovery | taper | block
    target_tss: float | None = None
    target_hours: float | None = None
    note: str = ""
    sessions: list[Session] = field(default_factory=list)

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=6)

    @property
    def planned_hours(self) -> float:
        return round(sum(s.duration_min for s in self.sessions) / 60, 1)

    @property
    def planned_tss(self) -> float:
        return round(sum(s.planned_tss or 0 for s in self.sessions), 1)

    def contains(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start_date": self.start_date.isoformat(),
            "kind": self.kind,
            "target_tss": self.target_tss,
            "target_hours": self.target_hours,
            "note": self.note,
            "sessions": [s.to_dict() for s in self.sessions],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Week:
        return cls(
            index=int(d["index"]),
            start_date=_as_date(d["start_date"]),
            kind=str(d.get("kind", "load")),
            target_tss=d.get("target_tss"),
            target_hours=d.get("target_hours"),
            note=str(d.get("note", "")),
            sessions=[Session.from_dict(s) for s in d.get("sessions", [])],
        )


@dataclass
class Constraints:
    """What the athlete told us they can actually do."""

    days_per_week: int
    weekly_hours: float
    days_available: list[str]
    long_ride_day: str | None = None
    weeks: int = 4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Constraints:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Plan:
    id: str
    created_at: datetime
    constraints: Constraints
    weeks: list[Week] = field(default_factory=list)
    language: str = "pt-BR"
    athlete: str = ""
    ftp_at_creation: float | None = None
    weight_at_creation: float | None = None
    goal: dict[str, Any] | None = None
    phase: str = "base"            # base | build | specialty | taper | block
    rationale: str = ""
    warnings: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------- derived
    @property
    def start_date(self) -> date | None:
        return min((w.start_date for w in self.weeks), default=None)

    @property
    def end_date(self) -> date | None:
        return max((w.end_date for w in self.weeks), default=None)

    @property
    def total_hours(self) -> float:
        return round(sum(w.planned_hours for w in self.weeks), 1)

    @property
    def total_tss(self) -> float:
        return round(sum(w.planned_tss for w in self.weeks), 1)

    def all_sessions(self) -> list[Session]:
        return [s for w in self.weeks for s in w.sessions]

    def week_for(self, day: date | None = None) -> Week | None:
        """The week containing ``day`` (default today), else None."""
        day = day or date.today()
        return next((w for w in self.weeks if w.contains(day)), None)

    def session_on(self, day: date) -> Session | None:
        return next((s for s in self.all_sessions() if s.date == day), None)

    def next_session(self, after: date | None = None) -> Session | None:
        """The next ride still outstanding.

        Skips anything already ridden or written off, so a session completed this
        morning stops being advertised as "next" for the rest of the day.
        """
        after = after or date.today()
        upcoming = sorted(
            (
                s
                for s in self.all_sessions()
                if s.date >= after
                and s.kind != "rest"
                and s.status not in {STATUS_COMPLETED, STATUS_MISSED}
            ),
            key=lambda s: s.date,
        )
        return upcoming[0] if upcoming else None

    def compliance(self) -> dict[str, Any]:
        """Planned vs. done over sessions that have come due.

        Today's session is only counted once it is actually completed. Counting it as
        due from midnight made compliance collapse every morning and recover only after
        the ride synced, which is alarming for no reason.
        """
        today = date.today()
        due = [
            s
            for s in self.all_sessions()
            if s.kind != "rest"
            and (s.date < today or s.status == STATUS_COMPLETED)
        ]
        done = [s for s in due if s.status == STATUS_COMPLETED]
        return {
            "due": len(due),
            "completed": len(done),
            "missed": len([s for s in due if s.status == STATUS_MISSED]),
            "pct": round(len(done) / len(due) * 100) if due else None,
            "planned_tss": round(sum(s.planned_tss or 0 for s in due), 1),
            "actual_tss": round(
                sum((s.actual or {}).get("tss", 0) or 0 for s in done), 1
            ),
        }

    # ------------------------------------------------------------ (de)serialise
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "language": self.language,
            "athlete": self.athlete,
            "ftp_at_creation": self.ftp_at_creation,
            "weight_at_creation": self.weight_at_creation,
            "constraints": self.constraints.to_dict(),
            "goal": self.goal,
            "phase": self.phase,
            "rationale": self.rationale,
            "warnings": self.warnings,
            "weeks": [w.to_dict() for w in self.weeks],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Plan:
        try:
            return cls(
                id=str(d["id"]),
                created_at=datetime.fromisoformat(d["created_at"]),
                constraints=Constraints.from_dict(d["constraints"]),
                weeks=[Week.from_dict(w) for w in d.get("weeks", [])],
                language=str(d.get("language", "pt-BR")),
                athlete=str(d.get("athlete", "")),
                ftp_at_creation=d.get("ftp_at_creation"),
                weight_at_creation=d.get("weight_at_creation"),
                goal=d.get("goal"),
                phase=str(d.get("phase", "base")),
                rationale=str(d.get("rationale", "")),
                warnings=list(d.get("warnings") or []),
            )
        except KeyError as exc:
            raise PlanError(f"plan is missing required field: {exc}") from exc


# ------------------------------------------------------------------- storage
def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def make_plan_id(start: date, phase: str) -> str:
    """e.g. 2026-w36-base — sortable, readable, and unique per week+phase."""
    year, week, _ = start.isocalendar()
    return f"{year}-w{week:02d}-{slugify(phase)}"


def plans_dir(root: str | Path | None = None) -> Path:
    return Path(root) if root else PLANS_DIR


def plan_path(plan_id: str, root: str | Path | None = None) -> Path:
    return plans_dir(root) / f"{plan_id}.json"


def save_plan(plan: Plan, root: str | Path | None = None) -> Path:
    d = plans_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{plan.id}.json"
    p.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
    return p


def load_plan(plan_id: str, root: str | Path | None = None) -> Plan:
    p = plan_path(plan_id, root)
    if not p.exists():
        raise PlanError(f"no plan '{plan_id}' at {p}")
    return Plan.from_dict(json.loads(p.read_text()))


def list_plans(root: str | Path | None = None) -> list[Plan]:
    d = plans_dir(root)
    if not d.exists():
        return []
    out: list[Plan] = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(Plan.from_dict(json.loads(p.read_text())))
        except Exception:  # noqa: BLE001 - see below
            # Deliberately broad. A single corrupt file must never hide every other
            # plan, and the ways a plan can be malformed are open-ended: unparseable
            # JSON, a bad ISO date deep inside a session, a constraints block missing
            # a key. Catching only the tidy exceptions left most of those fatal.
            continue
    return sorted(out, key=lambda x: x.created_at, reverse=True)


def latest_plan(root: str | Path | None = None) -> Plan | None:
    plans = list_plans(root)
    return plans[0] if plans else None


# --------------------------------------------------------------- reconciling
def reconcile(plan: Plan, activities: list[dict[str, Any]]) -> dict[str, Any]:
    """Match completed activities to planned sessions by date, in place.

    A session with an activity on its date becomes ``completed`` and gains an ``actual``
    block. A past session with nothing against it becomes ``missed``. Future sessions are
    left alone. Returns a summary of what changed.
    """
    from .session import normalize

    by_day: dict[date, list[dict[str, Any]]] = {}
    for raw in activities:
        a = normalize(raw)
        if not a.get("date"):
            continue
        try:
            day = _as_date(str(a["date"])[:10])
        except (PlanError, ValueError):
            continue
        by_day.setdefault(day, []).append(a)

    today = date.today()
    completed = missed = 0

    for s in plan.all_sessions():
        if s.kind == "rest" or s.status == STATUS_MODIFIED:
            continue
        # A session in the future is left alone whatever the activity data says. An
        # activity dated ahead of today means a bad timezone or a mis-parsed
        # start_date_local, not a ride that has happened.
        if s.date > today:
            continue
        matches = by_day.get(s.date, [])
        if matches:
            # Several rides in a day: sum load, take the longest as representative.
            main = max(matches, key=lambda a: a.get("moving_time_s") or 0)
            tss_values = [m.get("tss") for m in matches if m.get("tss") is not None]
            s.status = STATUS_COMPLETED
            s.actual = {
                "name": main.get("name"),
                "duration_min": round((main.get("moving_time_s") or 0) / 60),
                # None means "not reported", which is not the same as a genuine zero.
                "tss": round(sum(tss_values), 1) if tss_values else None,
                "np_w": main.get("np_w"),
                "avg_hr": main.get("avg_hr"),
                "activity_count": len(matches),
            }
            completed += 1
        else:
            s.status = STATUS_MISSED
            missed += 1

    return {
        "completed": completed,
        "missed": missed,
        "compliance": plan.compliance(),
    }
