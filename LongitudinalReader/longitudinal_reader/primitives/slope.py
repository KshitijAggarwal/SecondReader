"""Primitive 1 — the slope detector. Pure Python, no LLM.

The mechanically undeniable receipt: a numeric lab drifting monotonically through
or toward a reference bound over years, where every single value looked fine at
its own visit. Nobody drew the line, so nobody saw it. This code draws the line.

Flags a lab series when ALL hold:
  - >= 3 datapoints spanning a meaningful window,
  - near-monotone drift (<= 1 reversal) in one direction,
  - the total change is a clinically meaningful fraction of the reference width, and
  - the trajectory is heading toward / crossing a reference bound (or already has).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..events import Event, PatientRecord

MIN_POINTS = 3
MAX_REVERSALS = 1
# total change must exceed this fraction of the reference-range width to matter
MEANINGFUL_FRACTION = 0.5


@dataclass
class SlopeFinding:
    code: str
    system: str
    unit: str | None
    direction: str  # "rising" | "falling"
    first: tuple[str, float]
    last: tuple[str, float]
    slope_per_year: float
    total_change: float
    points: list[tuple[str, float]]
    ref_low: float | None
    ref_high: float | None
    crosses_ref: bool  # ends outside the range it (mostly) started inside
    approaching_ref: bool  # heading toward the nearer bound it will breach
    span_days: int
    reversals: int
    fraction_of_range: float | None = field(default=None)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "system": self.system,
            "unit": self.unit,
            "direction": self.direction,
            "first": {"date": self.first[0], "value": self.first[1]},
            "last": {"date": self.last[0], "value": self.last[1]},
            "slope_per_year": round(self.slope_per_year, 4),
            "total_change": round(self.total_change, 4),
            "ref_low": self.ref_low,
            "ref_high": self.ref_high,
            "crosses_ref": self.crosses_ref,
            "approaching_ref": self.approaching_ref,
            "span_days": self.span_days,
            "reversals": self.reversals,
            "fraction_of_range": (
                round(self.fraction_of_range, 2) if self.fraction_of_range is not None else None
            ),
            "points": [{"date": d, "value": v} for d, v in self.points],
        }


def _series(labs: list[Event], code: str) -> list[Event]:
    pts = [e for e in labs if e.code == code and e.value is not None]
    return sorted(pts, key=lambda e: e.day)


def _least_squares_slope(days: list[float], vals: list[float]) -> float:
    n = len(days)
    mx = sum(days) / n
    my = sum(vals) / n
    num = sum((x - mx) * (y - my) for x, y in zip(days, vals))
    den = sum((x - mx) ** 2 for x in days)
    return num / den if den else 0.0


def _count_reversals(vals: list[float], overall_dir: int) -> int:
    reversals = 0
    for a, b in zip(vals, vals[1:]):
        step = b - a
        if step == 0:
            continue
        if (step > 0) != (overall_dir > 0):
            reversals += 1
    return reversals


def analyze_series(series: list[Event]) -> SlopeFinding | None:
    if len(series) < MIN_POINTS:
        return None

    points = [(e.date, e.value) for e in series]
    vals = [e.value for e in series]
    day0 = series[0].day
    days = [float((e.day - day0).days) for e in series]

    total_change = vals[-1] - vals[0]
    if total_change == 0:
        return None
    overall_dir = 1 if total_change > 0 else -1
    reversals = _count_reversals(vals, overall_dir)
    if reversals > MAX_REVERSALS:
        return None

    span_days = int(days[-1])
    if span_days <= 0:
        return None
    slope_per_year = _least_squares_slope(days, vals) * 365.0

    ref_low = next((e.ref_low for e in series if e.ref_low is not None), None)
    ref_high = next((e.ref_high for e in series if e.ref_high is not None), None)

    # Meaningfulness gate: change must be a real fraction of the reference width.
    fraction = None
    if ref_low is not None and ref_high is not None and ref_high > ref_low:
        fraction = abs(total_change) / (ref_high - ref_low)
        if fraction < MEANINGFUL_FRACTION:
            return None

    direction = "rising" if overall_dir > 0 else "falling"
    first_v, last_v = vals[0], vals[-1]

    def _in_range(v: float) -> bool:
        lo_ok = ref_low is None or v >= ref_low
        hi_ok = ref_high is None or v <= ref_high
        return lo_ok and hi_ok

    crosses_ref = _in_range(first_v) and not _in_range(last_v)

    # Approaching the bound it's driving toward, even if still technically in-range.
    approaching_ref = False
    if not crosses_ref:
        if direction == "rising" and ref_high is not None and last_v < ref_high:
            # within the top 25% of the range and climbing
            approaching_ref = ref_low is not None and last_v >= ref_low + 0.75 * (ref_high - ref_low)
        elif direction == "falling" and ref_low is not None and last_v > ref_low:
            approaching_ref = ref_high is not None and last_v <= ref_high - 0.75 * (ref_high - ref_low)

    if ref_low is None and ref_high is None:
        # no bounds to head toward; require a stronger raw drift to bother flagging
        approaching_ref = abs(total_change) >= abs(first_v) * 0.4

    if not (crosses_ref or approaching_ref):
        return None

    return SlopeFinding(
        code=series[0].code,
        system=series[0].system,
        unit=series[0].unit,
        direction=direction,
        first=(points[0][0], points[0][1]),
        last=(points[-1][0], points[-1][1]),
        slope_per_year=slope_per_year,
        total_change=total_change,
        points=points,
        ref_low=ref_low,
        ref_high=ref_high,
        crosses_ref=crosses_ref,
        approaching_ref=approaching_ref,
        span_days=span_days,
        reversals=reversals,
        fraction_of_range=fraction,
    )


def detect_slopes(record: PatientRecord) -> list[SlopeFinding]:
    """Return every lab series that is drifting through/toward a reference bound."""
    labs = record.labs()
    codes = sorted({e.code for e in labs if e.code})
    findings = []
    for code in codes:
        f = analyze_series(_series(labs, code))
        if f:
            findings.append(f)
    # strongest trajectories first
    findings.sort(key=lambda f: (f.crosses_ref, f.fraction_of_range or 0), reverse=True)
    return findings
