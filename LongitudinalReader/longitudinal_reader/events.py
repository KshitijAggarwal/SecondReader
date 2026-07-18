"""The normalized event stream — the contract between every stage.

`load.py` produces a `PatientRecord`; primitives and LLM stages consume it and
never touch raw FHIR. Keeping this a plain dataclass (round-trippable to/from the
JSON in PLAN_LONGITUDINAL.md 7.2) means every stage boundary is inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


def parse_date(s: str) -> date:
    """FHIR dates come as YYYY-MM-DD or full datetimes; we only care about the day."""
    return date.fromisoformat(s[:10])


@dataclass
class Event:
    """One dated thing that happened to the patient, tagged by body system.

    Not every field applies to every type — labs carry value/unit/ref bounds,
    symptoms carry text/attribution/clinician, conditions carry onset. `type` is
    one of: lab | symptom | condition | med | procedure.
    """

    date: str  # YYYY-MM-DD (kept as string; use `.day` for the parsed date)
    type: str
    system: str
    encounter_id: str | None = None

    # lab
    code: str | None = None
    value: float | None = None
    unit: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None

    # symptom
    text: str | None = None
    attribution: str | None = None
    clinician: str | None = None

    # condition / med / procedure
    onset: str | None = None
    status: str | None = None  # e.g. active | resolved; med start/stop
    note: str | None = None

    @property
    def day(self) -> date:
        return parse_date(self.date)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class PatientRecord:
    patient_id: str
    age: int | None = None
    sex: str | None = None
    active_conditions: list[str] = field(default_factory=list)
    active_meds: list[str] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    source: str | None = None  # "hero" | "synthea" | "cohort" — for the silence panel
    display_name: str | None = None

    def sorted_events(self) -> list[Event]:
        return sorted(self.events, key=lambda e: e.day)

    def labs(self) -> list[Event]:
        return [e for e in self.events if e.type == "lab"]

    def symptoms(self) -> list[Event]:
        return [e for e in self.events if e.type == "symptom"]

    def span_days(self) -> int:
        if not self.events:
            return 0
        days = [e.day for e in self.events]
        return (max(days) - min(days)).days

    def to_dict(self) -> dict[str, Any]:
        return {
            "patient": {
                "id": self.patient_id,
                "name": self.display_name,
                "age": self.age,
                "sex": self.sex,
                "active_conditions": self.active_conditions,
                "active_meds": self.active_meds,
            },
            "source": self.source,
            "events": [e.to_dict() for e in self.sorted_events()],
        }
