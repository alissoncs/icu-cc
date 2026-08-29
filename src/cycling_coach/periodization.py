"""Intensity distribution [SEI10], tapering [MUJ03] and block periodization [RON14]."""

from __future__ import annotations

from dataclasses import dataclass, field

from .profile import AthleteProfile
from .zones import collapse_to_seiler

# Mujika & Padilla taper parameters. [MUJ03]
TAPER_VOLUME_CUT = (0.40, 0.60)   # conservative slice of the reviewed 60-90% range
TAPER_FREQUENCY_CUT_MAX = 0.20    # "no more than 20%"
TAPER_DAYS_OPTIMAL = (8, 14)
TAPER_EXPECTED_GAIN_PCT = (0.5, 6.0)


@dataclass
class IntensityDistribution:
    low_pct: float
    moderate_pct: float
    high_pct: float
    total_hours: float
    model: str
    assessment: str
    notes: list[str] = field(default_factory=list)


def classify_distribution(
    zone_seconds: dict[str, float], by: str = "time"
) -> IntensityDistribution:
    """Classify a week or block as polarized, pyramidal or threshold. [SEI10]

    ``zone_seconds`` is Coggan Z1-Z7 seconds; it is collapsed to the Seiler 3-zone model
    first. Note Seiler's 80/20 finding is usually expressed by *session count*, while
    time-in-zone is what power files give you — time-in-zone always looks more
    low-intensity heavy, so the thresholds below are tuned for time, and the model
    string says which basis was used.
    """
    buckets = collapse_to_seiler(zone_seconds)
    total = sum(buckets.values())
    if total <= 0:
        return IntensityDistribution(0, 0, 0, 0, "unknown", "No zone data.", [])

    low = buckets[1] / total * 100
    mod = buckets[2] / total * 100
    high = buckets[3] / total * 100
    notes: list[str] = []

    if low >= 75 and high >= mod:
        model = "polarized"
        assessment = (
            "Close to the pattern elite endurance athletes converge on: most volume easy, "
            "a real minority genuinely hard, little in between [SEI10]."
        )
    elif low >= 70 and mod > high:
        model = "pyramidal"
        assessment = (
            "Pyramidal — easy base with more tempo/threshold than VO2max work. A "
            "legitimate distribution that matches polarized in several trials, and "
            "common in base and early build phases."
        )
    elif mod >= 25:
        model = "threshold"
        assessment = (
            "Threshold-heavy. This is Seiler's 'black hole': hard enough to accumulate "
            "fatigue, not hard enough to drive the top-end adaptations, and it "
            "compromises the easy days that should be recovering you [SEI10]."
        )
    else:
        model = "mixed"
        assessment = "No clean pattern — likely a transition or an unstructured week."

    if low < 70:
        notes.append(
            f"Only {low:.0f}% of time is genuinely low intensity. Elite practice sits "
            "near 80%. The usual cause is easy rides creeping into tempo."
        )
    if high < 5 and total > 3 * 3600:
        notes.append(
            "Under 5% high intensity. Fine in a base block; a problem if you are "
            "inside 8 weeks of an A event."
        )
    if mod > 30:
        notes.append(
            f"{mod:.0f}% at tempo/threshold is a lot of grey-zone time. Push the easy "
            "days easier and the hard days harder."
        )

    return IntensityDistribution(
        low_pct=round(low, 1),
        moderate_pct=round(mod, 1),
        high_pct=round(high, 1),
        total_hours=round(total / 3600, 1),
        model=f"{model} (by {by}-in-zone)",
        assessment=assessment,
        notes=notes,
    )


@dataclass
class TaperPlan:
    days_out: int
    taper_days: int
    weeks: list[dict[str, object]]
    expected_gain_pct: tuple[float, float]
    principles: list[str]
    warnings: list[str] = field(default_factory=list)


def build_taper(
    profile: AthleteProfile, days_out: int, weekly_hours: float | None = None
) -> TaperPlan:
    """Generate a taper from the current date to an event. [MUJ03]

    The invariant, and the thing athletes most often get wrong: volume falls hard,
    intensity does not fall at all, frequency barely moves.
    """
    base_hours = weekly_hours if weekly_hours is not None else profile.weekly_hours
    warnings: list[str] = []

    taper_days = max(min(days_out, TAPER_DAYS_OPTIMAL[1]), 0)
    if days_out > TAPER_DAYS_OPTIMAL[1]:
        taper_days = TAPER_DAYS_OPTIMAL[1]
    if 0 < days_out < TAPER_DAYS_OPTIMAL[0]:
        warnings.append(
            f"Only {days_out} days out. The optimal taper window is "
            f"{TAPER_DAYS_OPTIMAL[0]}-{TAPER_DAYS_OPTIMAL[1]} days [MUJ03]; you can "
            "still shed fatigue, but expect less of the ~3% gain."
        )
    if days_out <= 0:
        warnings.append("Event date is today or past — nothing to taper.")

    n_weeks = max(1, (taper_days + 6) // 7)
    weeks: list[dict[str, object]] = []
    for i in range(n_weeks):
        # Progressive cut: the final week takes the deeper reduction.
        cut = TAPER_VOLUME_CUT[0] + (TAPER_VOLUME_CUT[1] - TAPER_VOLUME_CUT[0]) * (
            i / max(n_weeks - 1, 1)
        )
        weeks.append(
            {
                "week": f"T-{n_weeks - i}",
                "volume_cut_pct": round(cut * 100),
                "target_hours": round(base_hours * (1 - cut), 1),
                "intensity": "unchanged — keep race-pace and VO2max efforts in",
                "frequency": f"reduce by at most {round(TAPER_FREQUENCY_CUT_MAX * 100)}%",
            }
        )

    principles = [
        "Maintain training intensity. This is the one variable that must not drop — "
        "cutting intensity during a taper loses fitness [MUJ03].",
        f"Reduce volume by {round(TAPER_VOLUME_CUT[0] * 100)}-"
        f"{round(TAPER_VOLUME_CUT[1] * 100)}%. The reviewed studies go as deep as "
        "60-90% for heavily loaded athletes [MUJ03].",
        f"Reduce frequency by no more than {round(TAPER_FREQUENCY_CUT_MAX * 100)}% — "
        "keep riding most days, just shorter [MUJ03].",
        "Keep the intervals, shorten the sets. Two or three race-pace efforts in a "
        "60-75 min ride maintains the stimulus at a fraction of the fatigue cost.",
        "Expect to feel sluggish mid-taper. Form usually arrives in the last 3-5 days.",
    ]

    return TaperPlan(
        days_out=days_out,
        taper_days=taper_days,
        weeks=weeks,
        expected_gain_pct=TAPER_EXPECTED_GAIN_PCT,
        principles=principles,
        warnings=warnings,
    )


@dataclass
class BlockPlan:
    weeks: list[dict[str, object]]
    rationale: str
    warnings: list[str] = field(default_factory=list)


def build_hit_block(profile: AthleteProfile) -> BlockPlan:
    """4-week block-periodized HIT mesocycle. [RON14]

    Week 1 concentrates five HIT sessions; weeks 2-4 drop to one weekly HIT session with
    a low-intensity focus. In Rønnestad & Hansen this beat two-HIT-sessions-per-week at
    matched volume and intensity: VO2max +4.6%, peak power +2.1%, power at 2 mmol/L +10%,
    while the traditional group changed on none of them.
    """
    z5 = round(profile.ftp_w * 1.05), round(profile.ftp_w * 1.20)
    interval = f"5 x 6 min (or 6 x 5 min) at maximal sustainable effort, ~{z5[0]}-{z5[1]} W"

    weeks: list[dict[str, object]] = [
        {
            "week": 1,
            "label": "Concentrated HIT block",
            "hit_sessions": 5,
            "session": interval,
            "note": (
                "Deliberate overreaching. Performance drops inside this week — that is "
                "expected. Everything else in the week is easy or off."
            ),
        }
    ]
    for w in (2, 3, 4):
        weeks.append(
            {
                "week": w,
                "label": "Low-intensity focus + maintenance HIT",
                "hit_sessions": 1,
                "session": interval,
                "note": (
                    "The adaptation happens here. Keep the rest of the volume genuinely "
                    "low intensity — this is where the block week gets absorbed."
                ),
            }
        )

    warnings = [
        "For experienced cyclists with an established aerobic base. The subjects in "
        "[RON14] were trained cyclists at ~62 mL/kg/min VO2max.",
        "Do not run these blocks back to back, and do not schedule one inside 2 weeks "
        "of an A event — week 1 leaves you deeply fatigued.",
        "If sleep, resting HR or HRV degrade sharply during week 1, cut the block short. "
        "Overreaching is the intent; overtraining is not.",
    ]
    if profile.weekly_hours < 6:
        warnings.append(
            f"Your profile lists {profile.weekly_hours} h/week. Five HIT sessions in one "
            "week is a large share of that — consider 3-4 instead."
        )

    return BlockPlan(
        weeks=weeks,
        rationale=(
            "Block periodization of high-intensity aerobic intervals produced superior "
            "adaptations to traditional distribution over 4 weeks at matched total "
            "volume and intensity [RON14]."
        ),
        warnings=warnings,
    )
