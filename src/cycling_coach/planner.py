"""Plan generation — where the evidence base becomes a calendar.

``plans.py`` stores a plan; this module decides what should be in one. Everything here
exists to make a small number of coaching rules impossible to forget, because they are
exactly the rules athletes drop first when they write their own week:

* most of the volume must stay genuinely easy [SEI10];
* the recovery week is not optional [FRI18];
* fitness is built by a ramp the body can absorb, not by the week you wish you could ride
  [COG19];
* hard days need an easy day either side, or neither day is what it says it is.

Two deliberate constraints on how it works. First, sessions come from a **fixed
catalogue** (``SESSION_CATALOGUE``) rather than being written fresh each time: a plan that
cannot be reproduced cannot be tested, and a training plan that cannot be tested is a
guess. Second, every session carries **absolute watts**, never a bare zone label — a rider
on the road should not be doing percentage arithmetic at 30 km/h.

The maths is borrowed, not reinvented: zones from ``zones.py``, TSS and the CTL trajectory
from ``load.py``, taper and block structure from ``periodization.py``, fueling from
``fueling.py``. This module is scheduling and bookkeeping around them.

Session ``name`` and ``description`` follow ``plan.language`` because they are read by the
athlete; code, identifiers and comments stay English.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from itertools import combinations
from typing import Any

from .fueling import build_fuel_plan
from .load import pmc, training_stress_score
from .periodization import (
    TAPER_DAYS_OPTIMAL,
    TAPER_FREQUENCY_CUT_MAX,
    IntensityDistribution,
    TaperPlan,
    build_hit_block,
    build_taper,
    classify_distribution,
)
from .plans import Constraints, Plan, Session, Week, make_plan_id
from .profile import AthleteProfile
from .zones import power_zones, zone_for_power

__all__ = [
    "SESSION_CATALOGUE",
    "SessionTemplate",
    "build_plan",
    "plan_distribution",
]

DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Seiler's 80/20: elite endurance athletes across sports converge near 80% of training at
# low intensity. We aim at it and check the output against it rather than assuming the
# session mix produced it. [SEI10]
LOW_INTENSITY_TARGET_PCT = 80.0
LOW_INTENSITY_FLOOR_PCT = 72.0

# Friel's loading pattern: three progressive weeks, then unload. The recovery week is
# sized in TSS, not hours — an easy week cuts intensity as well as volume, so matching
# hours would leave it too hard. [FRI18]
LOAD_WEEK_PROGRESSION = (0.93, 1.00, 1.07)
RECOVERY_TSS_FRACTION = 0.55
RECOVERY_HOURS_BOUNDS = (0.35, 0.80)

# Weekly hours are allowed to miss the athlete's stated budget by this much before we
# say so. Rounding sessions to sane 5-minute durations costs a few minutes a week.
HOURS_TOLERANCE = 0.10

# Sessions longer than this get a fuel plan attached. Below it, Jeukendrup's bands are
# mouth-rinse-to-30 g/h territory and the line adds noise rather than help. [JEU14]
FUELING_MIN_MINUTES = 90

# A taper week's easy rides get short, not dropped: frequency must fall by no more than
# 20% while volume falls by 40-60%. [MUJ03]
TAPER_ELASTIC_MIN_MIN = 30
TAPER_SET_FACTOR = 0.5

# The non-work portion of an interval session — warm-up, valleys, cool-down — modelled as
# a single easy intensity so a session's NP can be estimated from its structure. [COG19]
EASY_NP_FRACTION = 0.60

# With no CTL supplied we assume the athlete is already riding roughly what they told us
# they can ride, rather than starting from zero. Seeding at zero makes every plan look
# like a cliff and produces a ramp warning on a perfectly sane week.
ASSUMED_CURRENT_FRACTION = 0.85
TSS_PER_HOUR_BASELINE = 55.0

_MAX_CAP_ITERATIONS = 14
# Holding a given CTL takes roughly CTL x 7 TSS per week. A plan may sit this far under
# that line before it counts as detraining rather than as a normal unload: a block that
# ends on its recovery week always averages a little below maintenance.
MAINTENANCE_FLOOR_FRACTION = 0.90
_MIN_VOLUME_SCALE = 0.40


# --------------------------------------------------------------------- catalogue
@dataclass(frozen=True)
class SessionTemplate:
    """One session shape. Durations are minutes; intensities are fractions of FTP.

    ``elastic`` templates stretch to fill whatever volume the week has left. Interval
    templates never do — stretching ``5 x 6 min`` into ``5 x 9 min`` silently turns a
    VO2max session into something else.
    """

    key: str
    kind: str                        # matches plans.Session.kind
    zone_label: str                  # what the athlete sees: "Z2", "sweet spot", ...
    total_min: int
    zone_key: str | None = None      # Coggan zone to read watts from [COG19]
    pct: tuple[float, float] | None = None   # explicit %FTP band, when no zone fits
    reps: int = 0
    rep_min: float = 0.0
    recovery_min: float = 0.0
    elastic: bool = False
    min_min: int = 45
    max_min: int = 150
    name_pt: str = ""
    name_en: str = ""
    cue_pt: str = ""
    cue_en: str = ""

    @property
    def work_min(self) -> float:
        """Minutes actually spent at the target intensity."""
        return self.reps * self.rep_min

    def shortened(self, factor: float) -> SessionTemplate:
        """Fewer sets, same watts — the taper move. [MUJ03]

        Mujika's rule is that volume falls and intensity does not, so a taper shortens the
        session by dropping repetitions rather than by easing the target.
        """
        if not self.reps:
            return self
        reps = max(2, int(round(self.reps * factor)))
        dropped = self.reps - reps
        total = int(round(self.total_min - dropped * (self.rep_min + self.recovery_min)))
        return replace(self, reps=reps, total_min=total)


SESSION_CATALOGUE: dict[str, SessionTemplate] = {
    "recovery_45": SessionTemplate(
        key="recovery_45", kind="recovery", zone_label="Z1", total_min=45,
        pct=(0.45, 0.55),
        name_pt="Recuperação", name_en="Recovery",
        cue_pt="Pedal leve, sem subidas e sem esforço — o objetivo é circulação, não treino.",
        cue_en="Spin easy, no climbs, no efforts — this is circulation, not training.",
    ),
    "endurance_60": SessionTemplate(
        key="endurance_60", kind="endurance", zone_label="Z2", total_min=60,
        zone_key="Z2", elastic=True, min_min=45, max_min=120,
        name_pt="Endurance Z2", name_en="Endurance Z2",
        cue_pt="Mantenha cadência confortável, sem entrar em Z3.",
        cue_en="Hold a comfortable cadence and stay out of Z3.",
    ),
    "endurance_90": SessionTemplate(
        key="endurance_90", kind="endurance", zone_label="Z2", total_min=90,
        zone_key="Z2", elastic=True, min_min=45, max_min=150,
        name_pt="Endurance Z2", name_en="Endurance Z2",
        cue_pt="Mantenha cadência confortável, sem entrar em Z3.",
        cue_en="Hold a comfortable cadence and stay out of Z3.",
    ),
    "long_ride": SessionTemplate(
        key="long_ride", kind="long", zone_label="Z2", total_min=180,
        zone_key="Z2", elastic=True, min_min=75, max_min=330,
        name_pt="Longão Z2", name_en="Long ride Z2",
        cue_pt="Ritmo constante do início ao fim. Coma a cada 30-40 min desde a primeira hora.",
        cue_en="Steady from start to finish. Eat every 30-40 min from the first hour.",
    ),
    "tempo_3x12": SessionTemplate(
        key="tempo_3x12", kind="tempo", zone_label="Z3", total_min=60,
        zone_key="Z3", reps=3, rep_min=12, recovery_min=5,
        name_pt="Tempo", name_en="Tempo",
        cue_pt="Ritmo firme e controlado, respiração ainda regular.",
        cue_en="Firm and controlled, breathing still rhythmic.",
    ),
    # Sweet spot straddles upper Z3 and lower Z4, so it is prescribed as an explicit
    # %FTP band rather than a single Coggan zone. [COG19]
    "sweetspot_3x15": SessionTemplate(
        key="sweetspot_3x15", kind="sweetspot", zone_label="sweet spot", total_min=75,
        pct=(0.88, 0.94), reps=3, rep_min=15, recovery_min=5,
        name_pt="Sweet Spot", name_en="Sweet Spot",
        cue_pt="Esforço forte mas sustentável — a última série deve sair igual à primeira.",
        cue_en="Strong but sustainable — the last set should match the first.",
    ),
    "threshold_2x20": SessionTemplate(
        key="threshold_2x20", kind="threshold", zone_label="Z4", total_min=80,
        zone_key="Z4", reps=2, rep_min=20, recovery_min=8,
        name_pt="Limiar", name_en="Threshold",
        cue_pt="No limiar: duro e controlado, sem estourar nos primeiros minutos.",
        cue_en="At threshold: hard and controlled, do not blow the first minutes.",
    ),
    "vo2_5x6": SessionTemplate(
        key="vo2_5x6", kind="vo2", zone_label="Z5", total_min=75,
        zone_key="Z5", reps=5, rep_min=6, recovery_min=6,
        name_pt="VO2max", name_en="VO2max",
        cue_pt="Esforço máximo sustentável nas séries. Se a potência cair mais de 5%, encerre.",
        cue_en="Maximal sustainable effort per rep. If power drops over 5%, stop the set.",
    ),
    # Rønnestad's HIT session: "5 x 6 min (or 6 x 5 min) at maximal sustainable effort".
    # Kept as its own key with kind "block" so the block structure is countable. [RON14]
    "hit_5x6": SessionTemplate(
        key="hit_5x6", kind="block", zone_label="Z5", total_min=70,
        zone_key="Z5", reps=5, rep_min=6, recovery_min=6,
        name_pt="HIT bloco", name_en="Block HIT",
        cue_pt="Séries no máximo sustentável [RON14]. A semana é sobrecarga proposital.",
        cue_en="Maximal sustainable reps [RON14]. This week is deliberate overreaching.",
    ),
}


# ------------------------------------------------------------------- text helpers
def _fmt_duration(minutes: int, language: str) -> str:
    if minutes >= 120:
        h, m = divmod(int(minutes), 60)
        return f"{h}h{m:02d}"
    return f"{int(minutes)} min"


def _session_name(t: SessionTemplate, language: str) -> str:
    base = t.name_pt if language == "pt-BR" else t.name_en
    if t.reps:
        return f"{base} {t.reps}x{t.rep_min:g}"
    return base


def _session_description(
    t: SessionTemplate, minutes: int, watts: tuple[int, int], language: str
) -> str:
    lo, hi = watts
    pt = language == "pt-BR"
    cue = t.cue_pt if pt else t.cue_en
    if t.reps:
        if pt:
            return (
                f"{t.reps} x {t.rep_min:g} min em {t.zone_label} ({lo}-{hi} W), "
                f"{t.recovery_min:g} min fácil entre as séries. {cue}"
            )
        return (
            f"{t.reps} x {t.rep_min:g} min in {t.zone_label} ({lo}-{hi} W), "
            f"{t.recovery_min:g} min easy between sets. {cue}"
        )
    dur = _fmt_duration(minutes, language)
    if pt:
        return f"{dur} em {t.zone_label} ({lo}-{hi} W). {cue}"
    return f"{dur} in {t.zone_label} ({lo}-{hi} W). {cue}"


# --------------------------------------------------------------- session numbers
def _target_watts(t: SessionTemplate, ftp_w: float) -> tuple[int, int]:
    """Absolute watts for a template. Zone edges come from ``zones.power_zones``. [COG19]"""
    if t.pct is not None:
        return round(ftp_w * t.pct[0]), round(ftp_w * t.pct[1])
    zones = {z.key: z for z in power_zones(ftp_w)}
    z = zones[t.zone_key or "Z2"]
    high = z.high_w if z.high_w is not None else round(ftp_w * 1.6)
    return z.low_w, high


def _estimated_np(t: SessionTemplate, watts: tuple[int, int], minutes: int, ftp_w: float) -> float:
    """Session NP estimate from the midpoint of the target watts. [COG19]

    A steady session simply rides at that midpoint. An interval session spends
    ``work_min`` there and the rest easy, so the two are combined the way NP itself is
    defined — fourth power, averaged over time, fourth root — instead of pretending the
    whole hour was at VO2max power.
    """
    mid = (watts[0] + watts[1]) / 2
    if not t.reps or minutes <= 0:
        return mid
    work = min(t.work_min, minutes)
    easy = ftp_w * EASY_NP_FRACTION
    rest = max(minutes - work, 0.0)
    fourth = (work * mid**4 + rest * easy**4) / minutes
    return fourth**0.25


def _build_session(
    t: SessionTemplate,
    day: date,
    minutes: int,
    profile: AthleteProfile,
    language: str,
) -> Session:
    watts = _target_watts(t, profile.ftp_w)
    np_w = _estimated_np(t, watts, minutes, profile.ftp_w)
    tss = training_stress_score(minutes * 60, np_w, profile.ftp_w)

    fuel: dict[str, Any] | None = None
    if minutes > FUELING_MIN_MINUTES:
        # Anything over ~90 min is where carbohydrate intake starts to decide the back
        # half of the ride. [JEU14]
        fp = build_fuel_plan(profile, minutes / 60, intensity_factor=np_w / profile.ftp_w)
        fuel = {
            "carb_g_per_h": fp.carb_g_per_h,
            "carb_total_g": fp.carb_total_g,
            "carb_type": fp.carb_type,
            "fluid_ml_per_h": fp.fluid_ml_per_h,
            "sodium_mg_per_h": fp.sodium_mg_per_h,
        }

    return Session(
        date=day,
        name=_session_name(t, language),
        kind=t.kind,
        duration_min=int(minutes),
        description=_session_description(t, minutes, watts, language),
        target_zone=t.zone_label,
        target_watts=[int(watts[0]), int(watts[1])],
        planned_tss=round(tss, 1),
        fueling=fuel,
    )


# ------------------------------------------------------------------ day placement
def _available_indices(days_available: list[str] | None) -> list[int]:
    raw = [str(d).strip().lower()[:3] for d in (days_available or [])]
    idx = sorted({DAYS.index(d) for d in raw if d in DAYS})
    return idx or list(range(7))


def _min_cyclic_gap(days: tuple[int, ...] | list[int]) -> int:
    """Smallest gap between days, wrapping across the week boundary.

    The wrap matters: the weekly pattern repeats, so a Monday and a Sunday session are
    back-to-back in real life even though they sit at opposite ends of the row.
    """
    s = sorted(days)
    if len(s) <= 1:
        return 7
    gaps = [b - a for a, b in zip(s, s[1:])]
    gaps.append(7 - s[-1] + s[0])
    return min(gaps)


def _spread(candidates: list[int], n: int, forced: int | None = None) -> list[int]:
    """Pick ``n`` days from ``candidates``, as evenly spaced as the week allows."""
    n = max(0, min(n, len(candidates)))
    if n == 0:
        return []
    best: tuple[int, tuple[int, ...]] | None = None
    for combo in combinations(candidates, n):
        if forced is not None and forced not in combo:
            continue
        score = _min_cyclic_gap(combo)
        if best is None or score > best[0]:
            best = (score, combo)
    if best is None:
        return sorted(candidates)[:n]
    return sorted(best[1])


def _place_hard(candidates: list[int], n: int) -> list[int]:
    """Hard days, never adjacent. Returns fewer than ``n`` if the week cannot hold them."""
    while n > 0:
        best: tuple[int, tuple[int, ...]] | None = None
        for combo in combinations(sorted(candidates), n):
            gap = _min_cyclic_gap(combo)
            if gap < 2:            # adjacent — a hard day next to a hard day is one bad day
                continue
            if best is None or gap > best[0]:
                best = (gap, combo)
        if best is not None:
            return sorted(best[1])
        n -= 1
    return []


# ------------------------------------------------------------------ week contents
def _quality_keys(phase: str, week_kind: str, load_index: int, room: int) -> list[str]:
    """Which quality sessions a week gets.

    Base is pyramidal — more tempo and sweet spot than VO2max — because the point of base
    is durability, and pyramidal distributions match polarized ones in several trials.
    Build shifts the same 20% upward into VO2max work, which is the practical meaning of
    "more polarized". [SEI10]
    """
    if week_kind == "recovery":
        return []                                    # unload means unload [FRI18]
    if phase in {"build", "specialty", "peak"}:
        keys = ["vo2_5x6", "threshold_2x20"]
        if room >= 5:
            keys.append("vo2_5x6")                   # the extra slot goes to the top end
    else:
        keys = ["sweetspot_3x15", "tempo_3x12"]
        # Keep a touch of top-end alive through base rather than losing it entirely.
        if load_index % 3 == 2:
            keys[1] = "vo2_5x6"
    return keys[:room]


def _fit_elastic(slots: list[SessionTemplate], budget: float) -> list[int]:
    """Share the week's remaining minutes across the stretchable rides."""
    if not slots:
        return []
    weights = [2.0 if t.key == "long_ride" else 1.0 for t in slots]
    mins = [t.min_min for t in slots]
    maxs = [t.max_min for t in slots]
    total_w = sum(weights)
    vals = [budget * w / total_w for w in weights]
    for _ in range(6):
        vals = [min(max(v, lo), hi) for v, lo, hi in zip(vals, mins, maxs)]
        diff = budget - sum(vals)
        if abs(diff) < 0.5:
            break
        free = [
            i
            for i, v in enumerate(vals)
            if (diff > 0 and v < maxs[i]) or (diff < 0 and v > mins[i])
        ]
        if not free:
            break
        for i in free:
            vals[i] += diff / len(free)
    # Round to something a rider can read off a stem, downward first so a week never
    # overshoots its budget, then hand the remainder back in 5-minute steps.
    out = [max(int(v // 5) * 5, lo) for v, lo in zip(vals, mins)]
    out = [min(v, hi) for v, hi in zip(out, maxs)]
    while budget - sum(out) >= 5:
        room = [i for i, v in enumerate(out) if v + 5 <= maxs[i]]
        if not room:
            break
        i = min(room, key=lambda j: out[j] - vals[j])
        out[i] += 5
    return out


def _shed(
    assigned: dict[int, SessionTemplate], target_min: float, protect: frozenset[int]
) -> dict[int, SessionTemplate]:
    """Cut structure until the week fits the athlete's budget.

    A plan that needs 9 h from someone with 6 is not a plan. Quality goes first because
    it costs the most fatigue per minute; only when there is no quality left does a day
    come off, and never below two rides.
    """
    while len(assigned) > 2:
        fixed = sum(t.total_min for t in assigned.values() if not t.elastic)
        floor = sum(t.min_min for t in assigned.values() if t.elastic)
        if target_min - fixed >= floor:
            break
        droppable = [d for d, t in assigned.items() if not t.elastic and d not in protect]
        if droppable:
            assigned[max(droppable)] = SESSION_CATALOGUE["endurance_60"]
            continue
        removable = [
            d for d, t in assigned.items()
            if t.elastic and t.key != "long_ride" and d not in protect
        ]
        if not removable:
            break
        del assigned[max(removable)]
    return assigned


def _finalise(
    assigned: dict[int, SessionTemplate], target_min: float
) -> list[tuple[int, SessionTemplate, int]]:
    """Turn a day -> template map into concrete durations."""
    elastic_days = sorted(d for d, t in assigned.items() if t.elastic)
    fixed = sum(t.total_min for d, t in assigned.items() if not t.elastic)
    minutes = _fit_elastic([assigned[d] for d in elastic_days], target_min - fixed)
    per_day = dict(zip(elastic_days, minutes))
    return [
        (d, assigned[d], per_day.get(d, assigned[d].total_min)) for d in sorted(assigned)
    ]


def _taper_easy(t: SessionTemplate) -> SessionTemplate:
    """Shrink an easy ride for a taper week without removing it. [MUJ03]

    Frequency falls by no more than 20%, so the rides stay on the calendar and simply get
    short. The long ride keeps its slot and stays the longest ride of the week — it just
    stops being long.
    """
    if not t.elastic:
        return t
    if t.key == "long_ride":
        return replace(t, min_min=45, max_min=90)
    return replace(t, min_min=TAPER_ELASTIC_MIN_MIN, max_min=60)


def _week_layout(
    constraints: Constraints,
    phase: str,
    week_kind: str,
    load_index: int,
    target_min: float,
    taper_factor: float | None,
) -> list[tuple[int, SessionTemplate, int]]:
    """Decide (weekday, template, minutes) for one ordinary week."""
    available = _available_indices(constraints.days_available)
    n_days = max(1, min(int(constraints.days_per_week or 1), len(available)))
    if week_kind == "recovery" and n_days >= 4:
        n_days -= 1                                  # fewer, easier days [FRI18]

    long_idx: int | None = None
    if constraints.long_ride_day:
        key = str(constraints.long_ride_day).strip().lower()[:3]
        if key in DAYS and DAYS.index(key) in available:
            long_idx = DAYS.index(key)

    days = _spread(available, n_days, forced=long_idx)
    if long_idx is None or long_idx not in days:
        long_idx = days[-1] if days else None

    non_long = [d for d in days if d != long_idx]
    wanted = _quality_keys(phase, week_kind, load_index, len(non_long))
    hard_days = _place_hard(non_long, len(wanted))
    quality = [SESSION_CATALOGUE[k] for k in wanted[: len(hard_days)]]
    if taper_factor is not None:
        # Volume down, intensity untouched: drop sets, keep the watts. [MUJ03]
        quality = [t.shortened(taper_factor) for t in quality]

    assigned: dict[int, SessionTemplate] = dict(zip(hard_days, quality))
    if long_idx is not None:
        assigned[long_idx] = SESSION_CATALOGUE["long_ride"]
    for d in days:
        assigned.setdefault(d, SESSION_CATALOGUE["endurance_90"])

    if taper_factor is not None:
        # A taper week keeps every session and every day — frequency falls by no more
        # than 20% [MUJ03] — and buys its volume cut from the easy rides instead.
        assigned = {d: _taper_easy(t) for d, t in assigned.items()}
        return _finalise(assigned, target_min)

    return _finalise(_shed(assigned, target_min, frozenset()), target_min)


def _block_layout(
    constraints: Constraints,
    week_number: int,
    week_kind: str,
    target_min: float,
    warnings: list[str],
) -> list[tuple[int, SessionTemplate, int]]:
    """Ronnestad block structure: five HIT sessions in week 1, one thereafter. [RON14]

    This is the one place hard days are allowed to sit back-to-back. Concentrating the
    stimulus is the whole mechanism — week 1 is deliberate overreaching, and the
    low-intensity weeks that follow are where it is absorbed.
    """
    available = _available_indices(constraints.days_available)
    hit = SESSION_CATALOGUE["hit_5x6"]

    if week_number == 1:
        n_hit = min(5, len(available))
        if n_hit < 5:
            warnings.append(
                f"Block week 1 wants five HIT sessions [RON14] but only {len(available)} "
                f"days are available — scheduled {n_hit}. The concentrated stimulus is "
                "the mechanism; with fewer days consider a traditional build instead."
            )
        n_days = min(len(available), max(n_hit, int(constraints.days_per_week or n_hit)))
        days = _spread(available, n_days)
        assigned: dict[int, SessionTemplate] = {d: hit for d in days[:n_hit]}
        for d in days[n_hit:]:
            assigned[d] = SESSION_CATALOGUE["endurance_90"]
        if n_hit > int(constraints.days_per_week or 0):
            warnings.append(
                f"Block week 1 uses {n_hit} days against a stated "
                f"{constraints.days_per_week} days/week. Everything outside the HIT "
                "sessions is easy or off [RON14]."
            )
        fixed = sum(t.total_min for t in assigned.values() if not t.elastic)
        if fixed > target_min:
            warnings.append(
                f"Five HIT sessions need ~{fixed / 60:.1f} h; the week's budget is "
                f"{target_min / 60:.1f} h. Week 1 runs over — that is the block, not a bug."
            )
        return _finalise(assigned, target_min)

    # Weeks 2-4: one maintenance HIT session, everything else genuinely low intensity.
    n_days = max(2, min(int(constraints.days_per_week or 1), len(available)))
    if week_kind == "recovery" and n_days >= 4:
        n_days -= 1                                  # the unload week still unloads [FRI18]
    days = _spread(available, n_days)
    long_key = str(constraints.long_ride_day or "").strip().lower()[:3]
    long_idx = (
        DAYS.index(long_key)
        if long_key in DAYS and DAYS.index(long_key) in days
        else days[-1]
    )
    hit_day = _place_hard([d for d in days if d != long_idx], 1)
    assigned = {d: SESSION_CATALOGUE["endurance_90"] for d in days}
    assigned[long_idx] = SESSION_CATALOGUE["long_ride"]
    if hit_day:
        assigned[hit_day[0]] = hit
    protect = frozenset(hit_day)                     # the weekly HIT session is the block
    return _finalise(_shed(assigned, target_min, protect), target_min)


# ------------------------------------------------------------------- verification
def plan_distribution(plan: Plan, ftp_w: float) -> IntensityDistribution:
    """Intensity distribution of a finished plan, by time in zone. [SEI10]

    Each session's NP is recovered from its own TSS and duration, then split between the
    target watts and the easy remainder — the inverse of how ``_estimated_np`` built it.
    This is a check on the output rather than a restatement of the intent: if the session
    mix drifts away from 80/20 the plan says so instead of assuming.
    """
    seconds: dict[str, float] = {}
    easy_w = ftp_w * EASY_NP_FRACTION
    for s in plan.all_sessions():
        if s.kind == "rest" or not s.duration_min:
            continue
        dur_h = s.duration_min / 60
        tss = s.planned_tss or 0.0
        if_ = (tss / (dur_h * 100)) ** 0.5 if dur_h > 0 and tss > 0 else 0.0
        np_w = if_ * ftp_w
        lo, hi = (s.target_watts or [round(easy_w), round(easy_w)])[:2]
        mid = (lo + hi) / 2
        span = mid**4 - easy_w**4
        frac = 1.0 if span <= 0 else min(max((np_w**4 - easy_w**4) / span, 0.0), 1.0)
        work_s = s.duration_min * 60 * frac
        key_work = zone_for_power(mid, ftp_w)
        key_easy = zone_for_power(easy_w, ftp_w)
        seconds[key_work] = seconds.get(key_work, 0.0) + work_s
        seconds[key_easy] = seconds.get(key_easy, 0.0) + (s.duration_min * 60 - work_s)
    return classify_distribution(seconds)


def _peak_ramp(weeks: list[Week], start: date, end: date, ctl_seed: float) -> float:
    """Largest 7-day CTL gain anywhere in the plan, simulated with the real PMC. [COG19]"""
    daily: dict[date, float] = {start: 0.0, end: 0.0}
    for w in weeks:
        for s in w.sessions:
            daily[s.date] = daily.get(s.date, 0.0) + (s.planned_tss or 0.0)
    points = pmc(daily, ctl_seed=ctl_seed, atl_seed=ctl_seed)
    if len(points) <= 7:
        return 0.0
    return round(max(points[i].ctl - points[i - 7].ctl for i in range(7, len(points))), 1)


def _projected_ctl(
    weeks: list[Week], start: date, end: date, ctl_seed: float
) -> tuple[float, float]:
    """(peak, final) CTL across the plan, same simulation as ``_peak_ramp``.

    Both are needed because they answer different questions. **Peak** says whether the
    block built fitness at all; **final** says where the athlete stands on the last day.
    A well-formed block ends on a recovery week, so its final CTL is deliberately below
    its peak — judging the plan on the final value alone condemns correct periodization
    as detraining.
    """
    daily: dict[date, float] = {start: 0.0, end: 0.0}
    for w in weeks:
        for s in w.sessions:
            daily[s.date] = daily.get(s.date, 0.0) + (s.planned_tss or 0.0)
    points = pmc(daily, ctl_seed=ctl_seed, atl_seed=ctl_seed)
    if not points:
        return ctl_seed, ctl_seed
    return round(max(p.ctl for p in points), 1), round(points[-1].ctl, 1)


# ------------------------------------------------------------------ week scaffold
def _week_kinds(n_weeks: int, use_block: bool) -> list[str]:
    """3 load weeks + 1 recovery week, and still a recovery week at 3. [FRI18]"""
    kinds: list[str] = []
    if use_block:
        kinds.append("block")
    while len(kinds) < n_weeks:
        remaining = n_weeks - len(kinds)
        size = min(3 if use_block else 4, remaining)
        if size >= 3:
            kinds.extend(["load"] * (size - 1) + ["recovery"])
        else:
            kinds.extend(["load"] * size)
    return kinds[:n_weeks]


def _goal_date(goal: dict[str, Any] | None) -> date | None:
    if not goal:
        return None
    raw = goal.get("date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


def _first_monday(start_date: date | None) -> date:
    d = start_date or date.today()
    return d + timedelta(days=(7 - d.weekday()) % 7)


def _rationale(phase: str, use_block: bool, has_taper: bool, language: str) -> str:
    pt = language == "pt-BR"
    if use_block:
        return (
            "Bloco de periodização concentrada: 5 sessões HIT na semana 1, depois 1 por "
            "semana com foco em baixa intensidade [RON14]."
            if pt
            else "Block periodization: five HIT sessions in week 1, then one per week "
            "with a low-intensity focus [RON14]."
        )
    head = (
        ("Bloco de base piramidal — volume fácil com tempo e sweet spot [SEI10]."
         if phase == "base"
         else "Bloco de build mais polarizado — o trabalho duro sobe para VO2max [SEI10].")
        if pt
        else ("Pyramidal base block — easy volume with tempo and sweet spot [SEI10]."
              if phase == "base"
              else "More polarized build block — the hard work moves up to VO2max [SEI10].")
    )
    tail = (
        (" Taper montado para a data do objetivo [MUJ03]." if pt
         else " Taper built into the goal date [MUJ03].")
        if has_taper
        else (" Sem data de prova, então o alvo é durabilidade." if pt
              else " No dated goal, so the target is durability.")
    )
    return head + tail


# ------------------------------------------------------------------------- entry
def build_plan(
    profile: AthleteProfile,
    constraints: Constraints,
    *,
    phase: str = "base",
    goal: dict[str, Any] | None = None,
    start_date: date | None = None,
    current_ctl: float = 0.0,
    use_block: bool = False,
    language: str = "pt-BR",
) -> Plan:
    """Generate a full training plan from a profile and what the athlete can actually do.

    The rules enforced here are the ones listed in ``docs/roadmap.md`` and sourced in
    ``docs/evidence-base.md``; each is tagged where it is applied. Where a rule cannot be
    satisfied — a ramp the athlete asked for that the body will not absorb, a block week
    that needs more days than exist — the plan is built to the safe version and says so in
    ``plan.warnings`` rather than quietly doing the unsafe thing.
    """
    warnings: list[str] = []
    language = language or "pt-BR"
    start = _first_monday(start_date)
    n_weeks = max(1, int(constraints.weeks or 4))
    end = start + timedelta(days=7 * n_weeks - 1)

    kinds = _week_kinds(n_weeks, use_block)

    # --- taper --------------------------------------------------------------------
    goal_day = _goal_date(goal)
    taper = None
    taper_weeks: list[int] = []
    if goal_day is not None and start <= goal_day <= end:
        days_out = min((goal_day - start).days, TAPER_DAYS_OPTIMAL[1])
        taper = build_taper(profile, days_out, constraints.weekly_hours)
        # The taper is aligned to whole weeks ending with the one the goal falls in, so a
        # week is either tapered or it is not — a half-tapered week is neither.
        goal_week = (goal_day - start).days // 7
        taper_weeks = [i for i in range(max(0, goal_week - len(taper.weeks) + 1), goal_week + 1)]
        for i in taper_weeks:
            kinds[i] = "taper"
        warnings.extend(taper.warnings)
    elif goal_day is not None:
        warnings.append(
            f"Goal date {goal_day} falls outside the {n_weeks}-week horizon — no taper "
            "was built. Extend the plan or generate a taper closer to the date [MUJ03]."
        )

    if use_block:
        block = build_hit_block(profile)
        warnings.extend(block.warnings)

    # --- volume, then the ramp check ----------------------------------------------
    seed_ctl = current_ctl if current_ctl > 0 else (
        ASSUMED_CURRENT_FRACTION * constraints.weekly_hours * TSS_PER_HOUR_BASELINE / 7
    )
    scale = 1.0
    weeks: list[Week] = []
    ramp = 0.0
    for _ in range(_MAX_CAP_ITERATIONS):
        weeks = _assemble(
            profile, constraints, phase, kinds, start, scale, taper, taper_weeks,
            use_block, language, warnings if scale == 1.0 else [],
        )
        ramp = _peak_ramp(weeks, start, end, seed_ctl)
        if ramp <= profile.max_ramp_rate + 0.05 or scale <= _MIN_VOLUME_SCALE:
            break
        scale = max(scale * 0.9, _MIN_VOLUME_SCALE)

    if scale < 0.995:
        # Never silently exceed the ceiling, and never silently ignore the request. [COG19]
        warnings.append(
            f"Requested {constraints.weekly_hours:.1f} h/week from a starting CTL of "
            f"{seed_ctl:.0f} would push CTL up faster than your ceiling of "
            f"{profile.max_ramp_rate:.1f}/week [COG19]. Volume capped to "
            f"{constraints.weekly_hours * scale:.1f} h/week (peak ramp {ramp:.1f}). "
            "Raise training.max_ramp_rate explicitly if you want to override this."
        )
    if ramp > profile.max_ramp_rate + 0.05:
        warnings.append(
            f"Even at the floor of {_MIN_VOLUME_SCALE:.0%} volume the plan ramps CTL at "
            f"{ramp:.1f}/week, above your ceiling of {profile.max_ramp_rate:.1f}. Your "
            "current CTL is very low relative to the days you want to ride — start with "
            "fewer, shorter sessions."
        )

    # --- hours sanity -------------------------------------------------------------
    for w in weeks:
        if w.kind != "load":
            continue
        want = (w.target_hours or 0.0)
        if want > 0 and abs(w.planned_hours - want) / want > HOURS_TOLERANCE:
            warnings.append(
                f"Week {w.index} plans {w.planned_hours:.1f} h against a target of "
                f"{want:.1f} h — the day count or session lengths could not be made to fit."
            )
        if len(w.sessions) < int(constraints.days_per_week or 0):
            warnings.append(
                f"Week {w.index} uses {len(w.sessions)} of the {constraints.days_per_week} "
                "days you asked for: spreading that many hours over that many days leaves "
                "rides too short to be worth doing. Fewer, longer sessions is the better "
                "trade."
            )

    # Taper frequency: keep touching the bike. [MUJ03]
    if taper_weeks:
        load_days = max(
            (len(w.sessions) for w in weeks if w.kind == "load"),
            default=int(constraints.days_per_week or 0),
        )
        floor = load_days * (1 - TAPER_FREQUENCY_CUT_MAX)
        for i in taper_weeks:
            if i < len(weeks) and len(weeks[i].sessions) < floor:
                warnings.append(
                    f"Taper week {weeks[i].index} drops to {len(weeks[i].sessions)} "
                    f"sessions from {load_days}. Frequency should fall by no more than "
                    f"{TAPER_FREQUENCY_CUT_MAX:.0%} [MUJ03] — shorten the rides instead "
                    "of removing them."
                )

    plan = Plan(
        id=make_plan_id(start, "block" if use_block else phase),
        created_at=datetime.now().replace(microsecond=0),
        constraints=constraints,
        weeks=weeks,
        language=language,
        athlete=profile.name,
        ftp_at_creation=profile.ftp_w,
        weight_at_creation=profile.weight_kg,
        goal=goal,
        phase="block" if use_block else phase,
        rationale=_rationale(phase, use_block, bool(taper_weeks), language),
        warnings=warnings,
    )

    # --- verify the intensity distribution we claimed to build --------------------
    dist = plan_distribution(plan, profile.ftp_w)
    if dist.low_pct < LOW_INTENSITY_FLOOR_PCT:
        warnings.append(
            f"Only {dist.low_pct:.0f}% of planned time is low intensity, against the "
            f"~{LOW_INTENSITY_TARGET_PCT:.0f}% elite endurance athletes converge on "
            "[SEI10]. Shorten the quality sessions or lengthen the easy ones."
        )

    # --- the maintenance floor ----------------------------------------------------
    # The ramp ceiling above stops a plan building fitness faster than it can be
    # absorbed. Nothing yet stopped the opposite: a plan whose weekly load sits below
    # what the athlete is already carrying quietly detrains them for a month. The
    # athlete asked for a base block and would get atrophy, with no warning. Whether
    # that is acceptable depends on intent (coming back from illness, deliberate
    # off-season), so this warns rather than refuses.
    # Measured as sustained weekly load against maintenance load, not as a CTL reading
    # on any single day. Reading the final day punishes a block for ending on its
    # recovery week; reading the peak is useless when CTL only ever decays, because the
    # peak is then just the starting value. Average weekly TSS against CTL x 7 is the
    # question actually being asked, and it is the number the athlete can act on.
    maintenance_tss = seed_ctl * 7
    avg_tss = sum(w.planned_tss for w in weeks) / len(weeks) if weeks else 0.0
    if maintenance_tss > 0 and avg_tss < maintenance_tss * MAINTENANCE_FLOOR_FRACTION:
        peak_ctl, end_ctl = _projected_ctl(weeks, start, end, seed_ctl)
        warnings.append(
            f"This plan loses fitness: it averages {avg_tss:.0f} TSS/week against the "
            f"~{maintenance_tss:.0f} TSS/week needed to hold your current CTL of "
            f"{seed_ctl:.0f}. Projected CTL peaks at {peak_ctl:.0f} and finishes at "
            f"{end_ctl:.0f} over {len(weeks)} weeks. That is the honest consequence of "
            f"{constraints.weekly_hours:.1f} h/week at this intensity — either accept it "
            "as a deliberate easy block, add hours, or add intensity to the hours you "
            "have."
        )

    return plan


def _assemble(
    profile: AthleteProfile,
    constraints: Constraints,
    phase: str,
    kinds: list[str],
    start: date,
    scale: float,
    taper: TaperPlan | None,
    taper_weeks: list[int],
    use_block: bool,
    language: str,
    warnings: list[str],
) -> list[Week]:
    """Materialise every week at a given volume scale."""
    weeks: list[Week] = []
    load_index = 0
    block_week = 0
    last_load_tss = 0.0

    for i, kind in enumerate(kinds):
        w_start = start + timedelta(days=7 * i)
        base_min = constraints.weekly_hours * 60 * scale

        if kind == "recovery":
            target_min = base_min * RECOVERY_TSS_FRACTION
        elif kind == "taper":
            pos = taper_weeks.index(i)
            spec = taper.weeks[min(pos, len(taper.weeks) - 1)] if taper else None
            hours = float(spec["target_hours"]) if spec else constraints.weekly_hours * 0.5
            target_min = hours * 60 * scale
        else:
            target_min = base_min * LOAD_WEEK_PROGRESSION[load_index % len(LOAD_WEEK_PROGRESSION)]

        def make(target: float, k: str = kind) -> list[Session]:
            if use_block:
                layout = _block_layout(constraints, block_week + 1, k, target, warnings)
            elif k == "taper":
                # Same sessions as the last load week, fewer sets, identical watts.
                layout = _week_layout(
                    constraints, phase, "load", max(load_index - 1, 0), target,
                    TAPER_SET_FACTOR,
                )
            else:
                layout = _week_layout(constraints, phase, k, load_index, target, None)
            return [
                _build_session(t, w_start + timedelta(days=d), m, profile, language)
                for d, t, m in layout
            ]

        sessions = make(target_min)

        if kind == "recovery" and last_load_tss > 0:
            # Size the unload in TSS, not hours: an easy week drops intensity too, so
            # matching hours would leave it far too hard. Aim at ~55% of the load week
            # and converge on it. [FRI18]
            want = RECOVERY_TSS_FRACTION * last_load_tss
            lo = base_min * RECOVERY_HOURS_BOUNDS[0]
            hi = base_min * RECOVERY_HOURS_BOUNDS[1]
            for _ in range(4):
                got = sum(s.planned_tss or 0 for s in sessions)
                if got <= 0 or abs(got - want) / want < 0.02:
                    break
                target_min = min(max(target_min * want / got, lo), hi)
                sessions = make(target_min)

        week = Week(
            index=i + 1,
            start_date=w_start,
            kind=kind,
            target_hours=round(target_min / 60, 1),
            target_tss=None,
            note=_week_note(kind, language),
            sessions=sorted(sessions, key=lambda s: s.date),
        )
        week.target_tss = week.planned_tss
        weeks.append(week)

        if use_block:
            block_week += 1
        if kind in {"load", "block"}:
            last_load_tss = week.planned_tss
            load_index += 1

    return weeks


def _week_note(kind: str, language: str) -> str:
    pt = language == "pt-BR"
    notes = {
        "load": ("Semana de carga progressiva.", "Progressive load week."),
        "recovery": (
            "Semana de recuperação — a carga cai para o corpo absorver o bloco [FRI18].",
            "Recovery week — load drops so the block gets absorbed [FRI18].",
        ),
        "taper": (
            "Taper: volume cai, intensidade permanece [MUJ03].",
            "Taper: volume falls, intensity stays [MUJ03].",
        ),
        "block": (
            "Semana de bloco concentrado — sobrecarga proposital [RON14].",
            "Concentrated block week — deliberate overreaching [RON14].",
        ),
    }
    pair = notes.get(kind, ("", ""))
    return pair[0] if pt else pair[1]
