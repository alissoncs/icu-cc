"""Training load maths: NP, IF, TSS and the Performance Management Chart. [COG19]"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

ROLLING_WINDOW_S = 30
CTL_TAU_DAYS = 42
ATL_TAU_DAYS = 7


def normalized_power(watts: list[float], sample_rate_hz: float = 1.0) -> float:
    """Normalized Power: 30 s rolling mean, 4th power, average, 4th root. [COG19]"""
    if not watts:
        return 0.0
    window = max(int(ROLLING_WINDOW_S * sample_rate_hz), 1)
    if len(watts) < window:
        return sum(watts) / len(watts)

    rolling: list[float] = []
    running = sum(watts[:window])
    rolling.append(running / window)
    for i in range(window, len(watts)):
        running += watts[i] - watts[i - window]
        rolling.append(running / window)

    fourth = sum(v**4 for v in rolling) / len(rolling)
    return fourth**0.25


def intensity_factor(np_w: float, ftp_w: float) -> float:
    return np_w / ftp_w if ftp_w else 0.0


def training_stress_score(duration_s: float, np_w: float, ftp_w: float) -> float:
    """TSS = (s x NP x IF) / (FTP x 3600) x 100. [COG19]"""
    if ftp_w <= 0:
        return 0.0
    intensity = np_w / ftp_w
    return (duration_s * np_w * intensity) / (ftp_w * 3600) * 100


def variability_index(np_w: float, avg_w: float) -> float:
    """NP/average power. Near 1.0 is steady; >1.15 is a stochastic or badly paced ride."""
    return np_w / avg_w if avg_w else 0.0


def efficiency_factor(np_w: float, avg_hr: float) -> float:
    """Normalized Power per heartbeat. Rising over weeks at matched intensity = aerobic
    fitness improving; it is only comparable within similar session types."""
    return np_w / avg_hr if avg_hr else 0.0


@dataclass(frozen=True)
class PmcPoint:
    day: date
    load: float
    ctl: float
    atl: float
    tsb: float


def pmc(
    daily_load: dict[date, float],
    ctl_tau: int = CTL_TAU_DAYS,
    atl_tau: int = ATL_TAU_DAYS,
    ctl_seed: float = 0.0,
    atl_seed: float = 0.0,
) -> list[PmcPoint]:
    """Performance Management Chart over a continuous daily series.

    CTL (fitness) is a 42-day exponentially weighted average of daily load, ATL (fatigue)
    a 7-day one. TSB (form) is the previous day's CTL minus ATL, which is the convention
    Intervals.icu and TrainingPeaks both use — today's ride should not flatter today's
    form.

    Gaps in ``daily_load`` are filled with zero-load rest days, since decay is the whole
    point of the model.
    """
    if not daily_load:
        return []

    start, end = min(daily_load), max(daily_load)
    ctl_k = 1 - math.exp(-1 / ctl_tau)
    atl_k = 1 - math.exp(-1 / atl_tau)

    ctl, atl = ctl_seed, atl_seed
    out: list[PmcPoint] = []
    day = start
    while day <= end:
        load = float(daily_load.get(day, 0.0))
        tsb = ctl - atl  # yesterday's values, before applying today's load
        ctl += (load - ctl) * ctl_k
        atl += (load - atl) * atl_k
        out.append(PmcPoint(day=day, load=load, ctl=round(ctl, 1), atl=round(atl, 1), tsb=round(tsb, 1)))
        day += timedelta(days=1)
    return out


def ramp_rate(points: list[PmcPoint], days: int = 7) -> float:
    """Change in CTL over the last N days — TSS/day gained per week.

    Sustained ramp above ~5-7 is where injury and illness risk climbs for most athletes.
    """
    if len(points) < days + 1:
        return 0.0
    return round(points[-1].ctl - points[-1 - days].ctl, 1)


def monotony_and_strain(loads: list[float]) -> tuple[float, float]:
    """Foster's monotony (mean/SD of daily load) and strain (weekly load x monotony).

    High monotony — every day the same — is associated with worse adaptation and higher
    illness risk than the same total load with real hard/easy separation.
    """
    if len(loads) < 2:
        return 0.0, 0.0
    mean = sum(loads) / len(loads)
    var = sum((x - mean) ** 2 for x in loads) / (len(loads) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0, 0.0
    monotony = mean / sd
    return round(monotony, 2), round(sum(loads) * monotony, 0)


def form_label(tsb: float) -> str:
    """Plain-language reading of TSB. Bands are conventional, not from a trial."""
    if tsb > 25:
        return "very fresh (detraining risk if held)"
    if tsb > 5:
        return "fresh / race-ready"
    if tsb >= -10:
        return "neutral"
    if tsb >= -30:
        return "productive training load"
    return "high fatigue — recovery needed"
