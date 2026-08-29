"""Power-profile benchmarking against rider categories.

These bands are coarse approximations in the tradition of the Coggan power profile
chart [COG19]. They are NOT the published chart and should always be reported as
orientation, not classification. Real-world pro context comes from the
`benchmark-vs-pros` skill, which reads procyclingstats.com.
"""

from __future__ import annotations

from dataclasses import dataclass

# (category label, minimum W/kg) per duration, descending. Male reference.
_MALE_BANDS: dict[str, list[tuple[str, float]]] = {
    "ftp": [
        ("World Tour", 5.8),
        ("Pro / Continental", 5.0),
        ("Cat 1 / elite amateur", 4.4),
        ("Cat 2", 3.9),
        ("Cat 3", 3.4),
        ("Cat 4", 2.9),
        ("Cat 5 / novice", 0.0),
    ],
    "5min": [
        ("World Tour", 6.8),
        ("Pro / Continental", 6.0),
        ("Cat 1 / elite amateur", 5.3),
        ("Cat 2", 4.7),
        ("Cat 3", 4.1),
        ("Cat 4", 3.5),
        ("Cat 5 / novice", 0.0),
    ],
    "1min": [
        ("World Tour", 10.5),
        ("Pro / Continental", 9.3),
        ("Cat 1 / elite amateur", 8.2),
        ("Cat 2", 7.2),
        ("Cat 3", 6.3),
        ("Cat 4", 5.4),
        ("Cat 5 / novice", 0.0),
    ],
    "5s": [
        ("World Tour", 21.0),
        ("Pro / Continental", 18.5),
        ("Cat 1 / elite amateur", 16.0),
        ("Cat 2", 14.0),
        ("Cat 3", 12.0),
        ("Cat 4", 10.0),
        ("Cat 5 / novice", 0.0),
    ],
}

# Female reference bands sit roughly 0.6-1.5 W/kg lower depending on duration; the gap
# is largest for the short, most anaerobic efforts.
_FEMALE_OFFSET = {"ftp": 0.85, "5min": 0.85, "1min": 0.82, "5s": 0.80}

DURATION_LABELS = {
    "5s": "5 s (neuromuscular)",
    "1min": "1 min (anaerobic capacity)",
    "5min": "5 min (VO2max)",
    "ftp": "FTP (threshold)",
}


@dataclass(frozen=True)
class Benchmark:
    duration: str
    label: str
    watts: float
    wkg: float
    category: str
    next_category: str | None
    watts_to_next: float | None


def _bands(duration: str, sex: str) -> list[tuple[str, float]]:
    bands = _MALE_BANDS[duration]
    if sex.lower().startswith("f"):
        factor = _FEMALE_OFFSET[duration]
        return [(label, round(v * factor, 2)) for label, v in bands]
    return bands


def benchmark(duration: str, watts: float, weight_kg: float, sex: str = "male") -> Benchmark:
    """Place a single power number against the category bands."""
    if duration not in _MALE_BANDS:
        raise ValueError(f"duration must be one of {sorted(_MALE_BANDS)}")
    if weight_kg <= 0:
        raise ValueError("weight_kg must be positive")

    wkg = watts / weight_kg
    bands = _bands(duration, sex)

    category = bands[-1][0]
    next_cat: str | None = None
    next_thresh: float | None = None
    for i, (label, floor) in enumerate(bands):
        if wkg >= floor:
            category = label
            if i > 0:
                next_cat, next_thresh = bands[i - 1][0], bands[i - 1][1]
            break

    to_next = round(next_thresh * weight_kg - watts) if next_thresh else None

    return Benchmark(
        duration=duration,
        label=DURATION_LABELS[duration],
        watts=round(watts),
        wkg=round(wkg, 2),
        category=category,
        next_category=next_cat,
        watts_to_next=to_next,
    )


def profile_shape(results: list[Benchmark]) -> str:
    """Read the shape of a full power profile: which system is relatively strongest.

    Compares category *rank* across durations rather than raw W/kg, since the bands
    already normalise for the physiology of each duration.
    """
    if len(results) < 2:
        return "Not enough durations tested to read a profile shape."

    order = [b[0] for b in _MALE_BANDS["ftp"]][::-1]  # weakest -> strongest
    ranked = {r.duration: order.index(r.category) for r in results if r.category in order}
    if len(ranked) < 2:
        return "Could not rank categories."

    best = max(ranked, key=lambda k: ranked[k])
    worst = min(ranked, key=lambda k: ranked[k])
    if ranked[best] == ranked[worst]:
        return (
            "Evenly balanced profile — no single system stands out. An all-rounder; "
            "training choice should follow your event demands, not your weaknesses."
        )

    reading = {
        "5s": "sprinter's neuromuscular power",
        "1min": "anaerobic capacity",
        "5min": "VO2max",
        "ftp": "threshold/endurance",
    }
    return (
        f"Relative strength: {reading[best]}. Relative weakness: {reading[worst]}. "
        "Whether that is a problem depends entirely on your target event — a gran fondo "
        "rider does not need a sprint, and a crit racer does not need a big FTP."
    )
