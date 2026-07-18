"""Generate a benign longitudinal cohort for the SILENCE panel.

Real Synthea bundles (dropped into data/synthea/) are the production substrate; this
generator stands in so the "runs silently across N, surfaces on few" story works even
before the Java toolchain is ready. Every patient here has stable, in-range,
non-monotone labs and at most a single isolated symptom — so the deterministic
primitives find nothing and the restraint gate stays silent. Reproducible (fixed seed).

Usage:  python tools/gen_cohort.py [N]   ->  writes data/cohort/benign_XX.json
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "cohort"

FIRST = ["James", "Mary", "Robert", "Linda", "John", "Patricia", "Michael", "Barbara",
         "William", "Elizabeth", "David", "Susan", "Carlos", "Wei", "Aisha", "Tomas"]
LAST = ["Nguyen", "Garcia", "Smith", "Johnson", "Lee", "Patel", "Brown", "Martinez",
        "Davis", "Khan", "Rossi", "Kim", "Silva", "Adams", "Cohen", "Park"]

# (code, system, unit, low, high, stable_mean) — jitter stays inside the range and
# is deliberately non-monotone, so slope.py never fires.
LABS = [
    ("creatinine", "renal", "mg/dL", 0.6, 1.1, 0.85),
    ("egfr", "renal", "mL/min/1.73m2", 90, 120, 102),
    ("a1c", "endocrine", "%", 4.0, 5.7, 5.2),
    ("hemoglobin", "hematologic", "g/dL", 12.0, 16.0, 14.0),
    ("tsh", "endocrine", "mIU/L", 0.4, 4.0, 1.8),
    ("calcium", "metabolic", "mg/dL", 8.6, 10.2, 9.4),
]

BENIGN_CONDITIONS = [
    ("Seasonal allergic rhinitis", "resolved"),
    ("Acute viral pharyngitis", "resolved"),
    ("Low back pain, mechanical", "resolved"),
    ("Vitamin D deficiency (repleted)", "resolved"),
]


def _jittered_series(mean: float, low: float, high: float, dates: list[date], rng: random.Random):
    """Values wobbling around a stable mean with a guaranteed reversal (no drift)."""
    span = (high - low) * 0.12
    vals = []
    for i, _ in enumerate(dates):
        # alternate sign so the series is non-monotone -> not a slope
        wobble = span * (0.6 if i % 2 == 0 else -0.6) + rng.uniform(-span * 0.2, span * 0.2)
        v = max(low + 0.1, min(high - 0.1, mean + wobble))
        vals.append(round(v, 1))
    return vals


def make_patient(idx: int, rng: random.Random) -> dict:
    age = rng.randint(35, 78)
    sex = rng.choice(["male", "female"])
    n_visits = rng.randint(3, 5)
    start = date(2021, 1, 1) + timedelta(days=rng.randint(0, 200))
    visit_dates = [start + timedelta(days=365 * i + rng.randint(-20, 20)) for i in range(n_visits)]

    events = []
    # each visit carries a couple of stable labs
    for lab in rng.sample(LABS, k=rng.randint(3, len(LABS))):
        code, system, unit, low, high, mean = lab
        vals = _jittered_series(mean, low, high, visit_dates, rng)
        for d, v in zip(visit_dates, vals):
            events.append({
                "date": d.isoformat(), "type": "lab", "system": system, "code": code,
                "value": v, "unit": unit, "ref_low": low, "ref_high": high,
                "encounter_id": f"v{d.year}",
            })

    # sometimes a single, isolated, benign symptom (NOT recurrent -> no recurrence flag)
    if rng.random() < 0.5:
        d = rng.choice(visit_dates)
        sym, attr = rng.choice([
            ("headache", "tension-type, resolved"),
            ("fatigue", "acute viral illness, resolved"),
            ("dizziness", "orthostatic, hydration advised"),
        ])
        events.append({
            "date": d.isoformat(), "type": "symptom", "system": "constitutional",
            "text": sym, "attribution": attr, "clinician": "PCP", "encounter_id": f"v{d.year}",
        })

    active = []
    if rng.random() < 0.4:
        cond, status = rng.choice(BENIGN_CONDITIONS)
        events.append({
            "date": rng.choice(visit_dates).isoformat(), "type": "condition",
            "system": "unspecified", "code": cond, "onset": visit_dates[0].isoformat(),
            "status": status,
        })

    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    return {
        "patient": {"id": f"benign-{idx:02d}", "name": name, "age": age, "sex": sex,
                    "active_conditions": active, "active_meds": []},
        "source": "cohort",
        "events": events,
    }


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    rng = random.Random(20260718)  # fixed seed -> reproducible cohort
    OUT.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        p = make_patient(i, rng)
        (OUT / f"benign_{i:02d}.json").write_text(json.dumps(p, indent=2))
    print(f"wrote {n} benign patients to {OUT}")


if __name__ == "__main__":
    main()
