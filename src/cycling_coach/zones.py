"""Training zones: Coggan 7-zone power [COG19], Friel HR [FRI18], Seiler 3-zone [SEI10].

Zone edges are estimates derived from a field-test proxy for LT2, not physiological
truth — thresholds vary with test method and protocol [JAM20]. Treat boundaries as
soft and never present them as measured.
"""

from __future__ import annotations

from dataclasses import dataclass

# Coggan 7-zone model, as fractions of FTP. Upper bound None = open-ended. [COG19]
POWER_ZONES: list[tuple[str, str, float, float | None]] = [
    ("Z1", "Active Recovery", 0.00, 0.55),
    ("Z2", "Endurance", 0.55, 0.75),
    ("Z3", "Tempo", 0.75, 0.90),
    ("Z4", "Lactate Threshold", 0.90, 1.05),
    ("Z5", "VO2max", 1.05, 1.20),
    ("Z6", "Anaerobic Capacity", 1.20, 1.50),
    ("Z7", "Neuromuscular Power", 1.50, None),
]

# Friel HR zones, as fractions of LTHR. [FRI18]
HR_ZONES: list[tuple[str, float, float | None]] = [
    ("Z1", 0.00, 0.81),
    ("Z2", 0.81, 0.89),
    ("Z3", 0.89, 0.93),
    ("Z4", 0.93, 0.99),
    ("Z5a", 0.99, 1.02),
    ("Z5b", 1.02, 1.06),
    ("Z5c", 1.06, None),
]

# Seiler 3-zone model mapped onto %FTP. The physiological anchors are VT1 and VT2;
# ~80% FTP and ~100% FTP are the usual practical proxies. [SEI10] [JAM20]
SEILER_LOW_UPPER = 0.80
SEILER_MID_UPPER = 1.00


@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    low_w: int
    high_w: int | None
    low_pct: float
    high_pct: float | None

    @property
    def range_str(self) -> str:
        return f"{self.low_w}-{self.high_w} W" if self.high_w else f"{self.low_w}+ W"


def power_zones(ftp_w: float) -> list[Zone]:
    """Coggan 7 power zones for the given FTP."""
    return [
        Zone(
            key=key,
            name=name,
            low_w=round(ftp_w * lo),
            high_w=round(ftp_w * hi) if hi is not None else None,
            low_pct=lo,
            high_pct=hi,
        )
        for key, name, lo, hi in POWER_ZONES
    ]


def hr_zones(lthr: int) -> list[Zone]:
    """Friel HR zones for the given lactate threshold heart rate."""
    return [
        Zone(
            key=key,
            name=f"HR {key}",
            low_w=round(lthr * lo),
            high_w=round(lthr * hi) if hi is not None else None,
            low_pct=lo,
            high_pct=hi,
        )
        for key, lo, hi in HR_ZONES
    ]


def zone_for_power(watts: float, ftp_w: float) -> str:
    """Which Coggan zone a given wattage falls in."""
    frac = watts / ftp_w
    for key, _name, lo, hi in POWER_ZONES:
        if frac >= lo and (hi is None or frac < hi):
            return key
    return "Z7"


def seiler_zone(watts: float, ftp_w: float) -> int:
    """Seiler 3-zone bucket (1, 2 or 3) for a given wattage."""
    frac = watts / ftp_w
    if frac < SEILER_LOW_UPPER:
        return 1
    if frac < SEILER_MID_UPPER:
        return 2
    return 3


def collapse_to_seiler(coggan_seconds: dict[str, float]) -> dict[int, float]:
    """Roll Coggan Z1-Z7 time into the Seiler 3-zone model.

    Z1-Z2 -> low, Z3-Z4 -> moderate, Z5+ -> high. Coggan Z3 starts at 75% FTP and the
    Seiler low/moderate boundary sits near 80%, so a little genuine low-intensity time
    lands in zone 2 here. That bias is conservative: it reports slightly *more* black
    hole than there is, which is the direction that fails safe.
    """
    mapping = {"Z1": 1, "Z2": 1, "Z3": 2, "Z4": 2, "Z5": 3, "Z6": 3, "Z7": 3}
    out = {1: 0.0, 2: 0.0, 3: 0.0}
    for key, seconds in coggan_seconds.items():
        bucket = mapping.get(key.upper())
        if bucket:
            out[bucket] += float(seconds or 0)
    return out
