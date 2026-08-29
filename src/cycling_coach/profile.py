"""Loading and validating athlete.yaml.

This is the only place that reads the profile file. Everything else takes an
``AthleteProfile`` so that calculations are testable without touching disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROFILE_PATH = Path("athlete.yaml")


class ProfileError(ValueError):
    """Raised when athlete.yaml is missing required data or is self-inconsistent."""


@dataclass(frozen=True)
class Goal:
    name: str
    date: date | None
    priority: str = "B"
    type: str = "fitness"
    duration_h: float | None = None
    elevation_m: float | None = None
    notes: str = ""

    @property
    def days_out(self) -> int | None:
        if self.date is None:
            return None
        return (self.date - date.today()).days


@dataclass(frozen=True)
class AthleteProfile:
    name: str
    birth_date: date | None
    sex: str
    height_cm: float
    weight_kg: float

    ftp_w: float
    ftp_source: str
    ftp_updated: date | None
    max_hr: int | None
    lthr: int | None
    resting_hr: int | None
    vo2max: float | None
    w_prime_j: float | None

    sweat_measured: bool
    sweat_rate_l_per_h: float
    sweat_sodium_mg_per_l: float
    sweat_reference_temp_c: float

    gut_trained_carb_g_per_h: float
    caffeine_mg_per_kg: float
    restrictions: list[str]
    preferred_products: list[str]

    weekly_hours: float
    days_available: list[str]
    long_ride_day: str | None
    discipline: str
    max_ramp_rate: float

    goals: list[Goal] = field(default_factory=list)

    @property
    def age(self) -> int | None:
        if self.birth_date is None:
            return None
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )

    @property
    def ftp_wkg(self) -> float:
        return self.ftp_w / self.weight_kg

    @property
    def ftp_age_days(self) -> int | None:
        if self.ftp_updated is None:
            return None
        return (date.today() - self.ftp_updated).days

    def next_goal(self, priority: str | None = "A") -> Goal | None:
        """Soonest future goal, optionally filtered by priority."""
        upcoming = [
            g
            for g in self.goals
            if g.date is not None
            and g.days_out is not None
            and g.days_out >= 0
            and (priority is None or g.priority.upper() == priority.upper())
        ]
        return min(upcoming, key=lambda g: g.date) if upcoming else None  # type: ignore[arg-type,return-value]

    def warnings(self) -> list[str]:
        """Data-quality problems worth surfacing before trusting any output."""
        out: list[str] = []
        age_days = self.ftp_age_days
        if age_days is None:
            out.append("physiology.ftp_updated is not set — FTP staleness unknown.")
        elif age_days > 56:
            out.append(
                f"FTP is {age_days} days old (set {self.ftp_updated}). "
                "Re-test every 6-8 weeks; zones and TSS drift otherwise."
            )
        if not self.sweat_measured:
            out.append(
                "sweat.measured is false — fueling uses population averages. "
                "A sweat test (docs/sweat-test.md) changes sodium targets substantially."
            )
        if self.lthr is None:
            out.append("physiology.lthr is not set — HR zones unavailable.")
        if self.ftp_source in {"intervals_estimate", "8min_test"}:
            out.append(
                f"ftp_source is '{self.ftp_source}' — a weaker LT2 proxy than a ramp or "
                "20 min test. Treat zone edges as soft [JAM20]."
            )
        return out


def _as_date(value: Any, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ProfileError(f"{field_name}: '{value}' is not YYYY-MM-DD") from exc
    raise ProfileError(f"{field_name}: expected a date, got {type(value).__name__}")


def _require(section: dict[str, Any], key: str, path: str) -> Any:
    if key not in section or section[key] is None:
        raise ProfileError(f"athlete.yaml is missing required field: {path}.{key}")
    return section[key]


def load_profile(path: str | Path | None = None) -> AthleteProfile:
    """Read and validate athlete.yaml."""
    p = Path(path) if path else DEFAULT_PROFILE_PATH
    if not p.exists():
        raise ProfileError(
            f"No profile at {p}. Copy athlete.yaml from the repo root and fill it in."
        )

    raw = yaml.safe_load(p.read_text()) or {}
    ath = raw.get("athlete") or {}
    phys = raw.get("physiology") or {}
    sweat = raw.get("sweat") or {}
    nutr = raw.get("nutrition") or {}
    train = raw.get("training") or {}

    weight = float(_require(ath, "weight_kg", "athlete"))
    ftp = float(_require(phys, "ftp_w", "physiology"))
    if weight <= 0:
        raise ProfileError("athlete.weight_kg must be positive.")
    if ftp <= 0:
        raise ProfileError("physiology.ftp_w must be positive.")

    lthr = phys.get("lthr")
    max_hr = phys.get("max_hr")
    if lthr and max_hr and lthr >= max_hr:
        raise ProfileError(
            f"physiology.lthr ({lthr}) must be below max_hr ({max_hr})."
        )

    goals = [
        Goal(
            name=str(g.get("name", "unnamed")),
            date=_as_date(g.get("date"), f"goals[{i}].date"),
            priority=str(g.get("priority", "B")),
            type=str(g.get("type", "fitness")),
            duration_h=float(g["duration_h"]) if g.get("duration_h") else None,
            elevation_m=float(g["elevation_m"]) if g.get("elevation_m") else None,
            notes=str(g.get("notes", "")),
        )
        for i, g in enumerate(raw.get("goals") or [])
    ]

    return AthleteProfile(
        name=str(ath.get("name", "athlete")),
        birth_date=_as_date(ath.get("birth_date"), "athlete.birth_date"),
        sex=str(ath.get("sex", "male")).lower(),
        height_cm=float(ath.get("height_cm") or 0) or 0.0,
        weight_kg=weight,
        ftp_w=ftp,
        ftp_source=str(phys.get("ftp_source", "unknown")),
        ftp_updated=_as_date(phys.get("ftp_updated"), "physiology.ftp_updated"),
        max_hr=int(max_hr) if max_hr else None,
        lthr=int(lthr) if lthr else None,
        resting_hr=int(phys["resting_hr"]) if phys.get("resting_hr") else None,
        vo2max=float(phys["vo2max"]) if phys.get("vo2max") else None,
        w_prime_j=float(phys["w_prime_j"]) if phys.get("w_prime_j") else None,
        sweat_measured=bool(sweat.get("measured", False)),
        sweat_rate_l_per_h=float(sweat.get("rate_l_per_h", 0.9)),
        sweat_sodium_mg_per_l=float(sweat.get("sodium_mg_per_l", 800)),
        sweat_reference_temp_c=float(sweat.get("reference_temp_c", 18)),
        gut_trained_carb_g_per_h=float(nutr.get("gut_trained_carb_g_per_h", 60)),
        caffeine_mg_per_kg=float(nutr.get("caffeine_mg_per_kg", 0)),
        restrictions=list(nutr.get("restrictions") or []),
        preferred_products=list(nutr.get("preferred_products") or []),
        weekly_hours=float(train.get("weekly_hours", 8)),
        days_available=list(train.get("days_available") or []),
        long_ride_day=train.get("long_ride_day"),
        discipline=str(train.get("discipline", "road")),
        max_ramp_rate=float(train.get("max_ramp_rate", 5)),
        goals=goals,
    )
