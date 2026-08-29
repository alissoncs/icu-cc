"""Single-session analysis.

Input is a plain dict of activity fields. The MCP tools return *formatted text*, not
JSON, so the normal flow is: Claude reads the MCP output, writes the numbers it found
into a small JSON file, and this module interprets them. ``normalize`` is therefore
deliberately tolerant about field names and units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .load import (
    efficiency_factor,
    form_label,
    intensity_factor,
    training_stress_score,
    variability_index,
)
from .periodization import classify_distribution
from .profile import AthleteProfile
from .zones import POWER_ZONES

# Aerobic decoupling (Pw:Hr) bands. Conventional coaching thresholds, not from a trial.
DECOUPLING_GOOD = 5.0
DECOUPLING_MODERATE = 10.0

_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "activity_name", "title"),
    "type": ("type", "activity_type", "sport"),
    "date": ("start_date_local", "start_date", "date"),
    "moving_time_s": ("moving_time", "moving_time_s", "duration", "elapsed_time"),
    "avg_power_w": ("icu_average_watts", "average_watts", "avg_power", "average_power"),
    "np_w": ("icu_weighted_avg_watts", "weighted_average_watts", "normalized_power", "np"),
    "avg_hr": ("average_heartrate", "avg_hr", "average_hr"),
    "max_hr": ("max_heartrate", "max_hr"),
    "tss": ("icu_training_load", "training_load", "tss"),
    "if_": ("icu_intensity", "intensity_factor", "if"),
    "ftp_w": ("icu_ftp", "ftp"),
    "decoupling_pct": ("icu_power_hr", "decoupling", "pw_hr"),
    "distance_m": ("distance", "distance_m"),
    "elevation_m": ("total_elevation_gain", "elevation_gain", "elevation_m"),
    "calories": ("calories", "icu_calories"),
    "zone_times": ("icu_zone_times", "zone_times", "power_zone_times"),
    "temp_c": ("average_temp", "temperature", "temp_c"),
}


def _pick(raw: dict[str, Any], key: str) -> Any:
    for alias in _ALIASES[key]:
        if alias in raw and raw[alias] is not None:
            return raw[alias]
    return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zone_times(value: Any) -> dict[str, float]:
    """Accept either {"Z1": 1200, ...} or intervals.icu's list-of-dicts form."""
    if not value:
        return {}
    if isinstance(value, dict):
        return {str(k): float(v or 0) for k, v in value.items()}
    if isinstance(value, list):
        out: dict[str, float] = {}
        for i, item in enumerate(value):
            if isinstance(item, dict):
                key = str(item.get("id") or item.get("zone") or f"Z{i + 1}")
                out[key] = float(item.get("secs") or item.get("seconds") or 0)
            else:
                out[f"Z{i + 1}"] = float(item or 0)
        return out
    return {}


@dataclass
class SessionAnalysis:
    name: str
    type: str
    date: str | None
    duration_h: float
    avg_power_w: float | None
    np_w: float | None
    intensity_factor: float | None
    tss: float | None
    variability_index: float | None
    efficiency_factor: float | None
    decoupling_pct: float | None
    avg_hr: float | None
    distance_km: float | None
    elevation_m: float | None
    kj: float | None
    zone_times: dict[str, float]
    findings: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Map an activity dict from any of the common shapes onto canonical keys."""
    out = {key: _num(_pick(raw, key)) for key in _ALIASES if key not in {"name", "type", "date", "zone_times"}}
    out["name"] = _pick(raw, "name") or "unnamed activity"
    out["type"] = _pick(raw, "type") or "Ride"
    out["date"] = _pick(raw, "date")
    out["zone_times"] = _zone_times(_pick(raw, "zone_times"))
    return out


def analyze_session(
    raw: dict[str, Any], profile: AthleteProfile, tsb: float | None = None
) -> SessionAnalysis:
    """Turn one activity into structured, quotable findings.

    Derives anything the source did not provide (IF, TSS, VI, EF) rather than requiring
    it, and records what was missing so the narrative can be honest about its gaps.
    """
    a = normalize(raw)
    missing: list[str] = []
    findings: list[str] = []
    flags: list[str] = []

    duration_s = a.get("moving_time_s") or 0.0
    duration_h = duration_s / 3600
    ftp = a.get("ftp_w") or profile.ftp_w
    if a.get("ftp_w") and abs(a["ftp_w"] - profile.ftp_w) > 5:
        flags.append(
            f"The activity was recorded against FTP {a['ftp_w']:.0f} W but athlete.yaml "
            f"says {profile.ftp_w:.0f} W. Load numbers below use {ftp:.0f} W."
        )

    np_w = a.get("np_w")
    avg_w = a.get("avg_power_w")
    avg_hr = a.get("avg_hr")

    if np_w is None and avg_w is None:
        missing.append("power data")
    if avg_hr is None:
        missing.append("heart rate")

    if_ = a.get("if_")
    if if_ is None and np_w:
        if_ = round(intensity_factor(np_w, ftp), 3)
    tss = a.get("tss")
    if tss is None and np_w and duration_s:
        tss = round(training_stress_score(duration_s, np_w, ftp), 1)

    vi = a.get("variability_index")
    if vi is None and np_w and avg_w:
        vi = round(variability_index(np_w, avg_w), 3)
    ef = round(efficiency_factor(np_w, avg_hr), 2) if (np_w and avg_hr) else None
    kj = round(avg_w * duration_s / 1000) if (avg_w and duration_s) else None

    # --- Interpretation --------------------------------------------------------
    if if_ is not None:
        if if_ < 0.60:
            findings.append(
                f"IF {if_:.2f} — recovery intensity. Its job is blood flow, not stimulus; "
                "resist the urge to make it 'count'."
            )
        elif if_ < 0.75:
            findings.append(
                f"IF {if_:.2f} — true endurance riding, the zone that should make up the "
                "bulk of your week [SEI10]."
            )
        elif if_ < 0.85:
            findings.append(
                f"IF {if_:.2f} — tempo/sweet spot. Productive in a build block, but this "
                "is also the intensity that quietly eats recovery days."
            )
        elif if_ < 0.95:
            findings.append(f"IF {if_:.2f} — threshold-level session. Costly; earn the rest.")
        else:
            findings.append(
                f"IF {if_:.2f} — race or test effort. Anything sustained above 1.0 for "
                "this duration means FTP is probably understated."
            )
        if if_ >= 1.02 and duration_h >= 0.6:
            flags.append(
                f"IF {if_:.2f} held for {duration_h:.1f} h is above threshold by "
                "definition — retest FTP, it looks stale."
            )

    if vi is not None:
        if vi < 1.05:
            findings.append(f"VI {vi:.2f} — very steady. Reads as a trainer ride or a flat TT.")
        elif vi < 1.15:
            findings.append(f"VI {vi:.2f} — normal road variability.")
        else:
            findings.append(
                f"VI {vi:.2f} — highly stochastic. Either terrain, a group ride, or "
                "surging pacing. On a solo effort this is wasted matches."
            )

    dec = a.get("decoupling_pct")
    if dec is not None:
        if dec <= DECOUPLING_GOOD:
            findings.append(
                f"Aerobic decoupling {dec:.1f}% — under {DECOUPLING_GOOD:.0f}%, so you "
                "held output per heartbeat to the end. Good aerobic durability for this "
                "duration."
            )
        elif dec <= DECOUPLING_MODERATE:
            findings.append(
                f"Aerobic decoupling {dec:.1f}% — moderate drift. Common when the ride "
                "sits at the edge of your current durability, or in heat."
            )
        else:
            findings.append(f"Aerobic decoupling {dec:.1f}% — significant drift.")
            flags.append(
                f"Decoupling of {dec:.1f}% usually means one of: underfueling, heat, "
                "starting too hard, or a duration beyond current aerobic durability. "
                "Check what you actually ate against the fuel plan for this ride."
            )

    if ef is not None:
        findings.append(
            f"Efficiency factor {ef:.2f} W/bpm. Only meaningful as a trend against "
            "similar sessions — compare it to your last few rides of this type."
        )

    if tss is not None and duration_h:
        findings.append(f"{tss:.0f} TSS over {duration_h:.1f} h ({tss / duration_h:.0f} TSS/h).")

    if tsb is not None:
        findings.append(f"Form going in: TSB {tsb:+.0f} — {form_label(tsb)}.")

    # --- Intensity distribution within the session -----------------------------
    zone_times = a.get("zone_times") or {}
    dist = None
    if zone_times:
        dist = classify_distribution(zone_times)
        findings.append(
            f"Time in zone: {dist.low_pct:.0f}% low / {dist.moderate_pct:.0f}% "
            f"moderate / {dist.high_pct:.0f}% high (Seiler 3-zone)."
        )
        if dist.moderate_pct > 40 and (if_ or 0) < 0.85:
            flags.append(
                f"{dist.moderate_pct:.0f}% of this ride sat in the tempo/threshold band "
                "on what was not a hard session — classic black-hole drift [SEI10]."
            )
    else:
        missing.append("time-in-zone")

    # --- Fueling cross-check ---------------------------------------------------
    if duration_h >= 2.0:
        from .fueling import base_carb_target, intensity_carb_adjustment

        needed = base_carb_target(duration_h) + intensity_carb_adjustment(if_ or 0.70)
        findings.append(
            f"A ride of this duration and intensity wanted roughly {needed:.0f} g "
            f"carbohydrate per hour (~{needed * duration_h:.0f} g total) [JEU14]."
        )

    if missing:
        flags.append(f"Missing from the data: {', '.join(missing)}. Findings are partial.")

    return SessionAnalysis(
        name=str(a["name"]),
        type=str(a["type"]),
        date=str(a["date"]) if a.get("date") else None,
        duration_h=round(duration_h, 2),
        avg_power_w=round(avg_w) if avg_w else None,
        np_w=round(np_w) if np_w else None,
        intensity_factor=round(if_, 3) if if_ else None,
        tss=round(tss, 1) if tss else None,
        variability_index=vi,
        efficiency_factor=ef,
        decoupling_pct=round(dec, 1) if dec is not None else None,
        avg_hr=round(avg_hr) if avg_hr else None,
        distance_km=round(a["distance_m"] / 1000, 1) if a.get("distance_m") else None,
        elevation_m=round(a["elevation_m"]) if a.get("elevation_m") else None,
        kj=kj,
        zone_times={k: v for k, v in zone_times.items() if v},
        findings=findings,
        flags=flags,
        missing=missing,
    )


def zone_time_table(zone_times: dict[str, float], ftp_w: float) -> list[dict[str, Any]]:
    """Zone times joined with their wattage ranges, for display."""
    total = sum(zone_times.values()) or 1
    lookup = {key: (name, lo, hi) for key, name, lo, hi in POWER_ZONES}
    rows = []
    for key, secs in sorted(zone_times.items()):
        meta = lookup.get(key.upper())
        rows.append(
            {
                "zone": key,
                "name": meta[0] if meta else "",
                "range_w": (
                    f"{round(ftp_w * meta[1])}-{round(ftp_w * meta[2])}"
                    if meta and meta[2]
                    else (f"{round(ftp_w * meta[1])}+" if meta else "")
                ),
                "minutes": round(secs / 60, 1),
                "pct": round(secs / total * 100, 1),
            }
        )
    return rows
