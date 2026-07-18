"""Stage 1 — TIMELINE ASSEMBLY (deterministic).

Turn a patient record into one dated, per-system-tagged `PatientRecord`. Two input
shapes are accepted and normalized to the same contract (events.py):

  1. Simplified event-stream JSON  — the hand-authored heroes and the benign
     cohort (the shape in PLAN_LONGITUDINAL.md 7.2). Fast to author, easy to read.
  2. Real FHIR R4 Bundle           — what Synthea emits. We flatten Observations,
     Conditions, MedicationRequests, and Procedures into the same event list.

Everything downstream reads `PatientRecord`, never raw FHIR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import Event, PatientRecord

# --- FHIR lab code -> (normalized code slug, body system) --------------------
# Keyword match against the Observation's display text / LOINC name. Deliberately
# small: it covers the labs whose *slope* is a diagnosis (the spine of the demo).
LAB_MAP: list[tuple[tuple[str, ...], str, str]] = [
    (("creatinine",), "creatinine", "renal"),
    (("glomerular filtration", "egfr", "gfr"), "egfr", "renal"),
    (("urea nitrogen", "bun"), "bun", "renal"),
    (("hemoglobin a1c", "a1c", "hba1c"), "a1c", "endocrine"),
    (("hemoglobin",), "hemoglobin", "hematologic"),
    (("hematocrit",), "hematocrit", "hematologic"),
    (("platelet",), "platelets", "hematologic"),
    (("thyroid stimulating", "tsh"), "tsh", "endocrine"),
    (("ferritin",), "ferritin", "hematologic"),
    (("prostate specific", "psa"), "psa", "genitourinary"),
    (("calcium",), "calcium", "metabolic"),
    (("alanine aminotransferase", "alt", "sgpt"), "alt", "hepatic"),
    (("aspartate aminotransferase", "ast", "sgot"), "ast", "hepatic"),
    (("body weight", "weight"), "weight", "constitutional"),
    (("transferrin saturation", "iron saturation"), "transferrin_sat", "hematologic"),
    (("antinuclear", "ana"), "ana", "immunologic"),
]

# Fallback reference ranges for slugs FHIR sometimes omits. Adult, coarse — the
# slope primitive cares about *direction through a bound*, not exact cutoffs.
REF_RANGES: dict[str, tuple[float, float]] = {
    "creatinine": (0.6, 1.1),
    "egfr": (90.0, 120.0),
    "bun": (7.0, 20.0),
    "a1c": (4.0, 5.7),
    "hemoglobin": (12.0, 16.0),
    "hematocrit": (36.0, 46.0),
    "platelets": (150.0, 400.0),
    "tsh": (0.4, 4.0),
    "ferritin": (30.0, 300.0),
    "psa": (0.0, 4.0),
    "calcium": (8.6, 10.2),
    "alt": (7.0, 56.0),
    "ast": (10.0, 40.0),
    "transferrin_sat": (20.0, 50.0),
}


def _map_lab(display: str) -> tuple[str, str] | None:
    d = (display or "").lower()
    for keywords, slug, system in LAB_MAP:
        if any(k in d for k in keywords):
            return slug, system
    return None


# --- Simplified event-stream JSON --------------------------------------------

def _load_event_stream(data: dict[str, Any], source: str) -> PatientRecord:
    p = data.get("patient", {})
    events = [Event.from_dict(e) for e in data.get("events", [])]
    return PatientRecord(
        patient_id=str(p.get("id") or data.get("id") or "unknown"),
        display_name=p.get("name") or data.get("name"),
        age=p.get("age"),
        sex=p.get("sex"),
        active_conditions=list(p.get("active_conditions", [])),
        active_meds=list(p.get("active_meds", [])),
        events=events,
        source=data.get("source") or source,
    )


# --- FHIR R4 Bundle (Synthea) ------------------------------------------------

def _entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [e.get("resource", {}) for e in bundle.get("entry", [])]


def _display_of(resource: dict[str, Any], key: str = "code") -> str:
    cc = resource.get(key, {})
    if cc.get("text"):
        return cc["text"]
    for c in cc.get("coding", []):
        if c.get("display"):
            return c["display"]
    return ""


def _obs_date(obs: dict[str, Any]) -> str | None:
    for k in ("effectiveDateTime", "issued", "effectivePeriod"):
        v = obs.get(k)
        if isinstance(v, str):
            return v
        if isinstance(v, dict) and v.get("start"):
            return v["start"]
    return None


def _ref_bounds(obs: dict[str, Any], slug: str) -> tuple[float | None, float | None]:
    for rr in obs.get("referenceRange", []):
        low = rr.get("low", {}).get("value")
        high = rr.get("high", {}).get("value")
        if low is not None or high is not None:
            return low, high
    fallback = REF_RANGES.get(slug)
    return fallback if fallback else (None, None)


def _load_fhir_bundle(bundle: dict[str, Any], source: str) -> PatientRecord:
    resources = _entries(bundle)
    patient_res = next((r for r in resources if r.get("resourceType") == "Patient"), {})
    pid = patient_res.get("id", "unknown")
    name = None
    if patient_res.get("name"):
        n = patient_res["name"][0]
        given = " ".join(n.get("given", []))
        name = f"{given} {n.get('family', '')}".strip() or None

    events: list[Event] = []
    active_conditions: list[str] = []
    active_meds: list[str] = []

    for r in resources:
        rtype = r.get("resourceType")

        if rtype == "Observation":
            display = _display_of(r)
            mapped = _map_lab(display)
            if not mapped:
                continue  # only carry labs whose trajectory we can reason over
            slug, system = mapped
            vq = r.get("valueQuantity")
            if not vq or vq.get("value") is None:
                continue
            when = _obs_date(r)
            if not when:
                continue
            low, high = _ref_bounds(r, slug)
            events.append(
                Event(
                    date=when[:10],
                    type="lab",
                    system=system,
                    code=slug,
                    value=float(vq["value"]),
                    unit=vq.get("unit"),
                    ref_low=low,
                    ref_high=high,
                    encounter_id=(r.get("encounter", {}) or {}).get("reference"),
                )
            )

        elif rtype == "Condition":
            display = _display_of(r)
            onset = r.get("onsetDateTime") or (r.get("recordedDate"))
            if not onset:
                continue
            clinical = (r.get("clinicalStatus", {}).get("coding", [{}])[0]).get("code", "active")
            events.append(
                Event(
                    date=onset[:10],
                    type="condition",
                    system="unspecified",
                    code=display,
                    onset=onset[:10],
                    status=clinical,
                    encounter_id=(r.get("encounter", {}) or {}).get("reference"),
                )
            )
            if clinical == "active":
                active_conditions.append(display)

        elif rtype == "MedicationRequest":
            display = _display_of(r, "medicationCodeableConcept")
            when = r.get("authoredOn")
            if not when:
                continue
            status = r.get("status", "active")
            events.append(
                Event(
                    date=when[:10],
                    type="med",
                    system="unspecified",
                    code=display,
                    status=status,
                    encounter_id=(r.get("encounter", {}) or {}).get("reference"),
                )
            )
            if status == "active":
                active_meds.append(display)

        elif rtype == "Procedure":
            display = _display_of(r)
            when = r.get("performedDateTime") or (r.get("performedPeriod", {}) or {}).get("start")
            if not when:
                continue
            events.append(
                Event(
                    date=when[:10],
                    type="procedure",
                    system="unspecified",
                    code=display,
                    encounter_id=(r.get("encounter", {}) or {}).get("reference"),
                )
            )

    # Rough age from birthDate + latest event.
    age = None
    if patient_res.get("birthDate") and events:
        from .events import parse_date

        latest = max(e.day for e in events)
        birth = parse_date(patient_res["birthDate"])
        age = (latest - birth).days // 365

    return PatientRecord(
        patient_id=pid,
        display_name=name,
        age=age,
        sex=patient_res.get("gender"),
        active_conditions=active_conditions,
        active_meds=active_meds,
        events=events,
        source=source,
    )


# --- public API ---------------------------------------------------------------

def _looks_like_fhir(data: dict[str, Any]) -> bool:
    return data.get("resourceType") == "Bundle" or "entry" in data


def load_record(path: str | Path, source: str | None = None) -> PatientRecord:
    """Load one patient file (event-stream JSON or FHIR bundle) -> PatientRecord."""
    path = Path(path)
    data = json.loads(path.read_text())
    src = source or ("synthea" if _looks_like_fhir(data) else "hero")
    rec = _load_fhir_bundle(data, src) if _looks_like_fhir(data) else _load_event_stream(data, src)
    if not rec.display_name:
        rec.display_name = path.stem
    return rec


def load_dir(path: str | Path, source: str | None = None) -> list[PatientRecord]:
    """Load every *.json under a directory as patient records (sorted by name)."""
    path = Path(path)
    records = []
    for f in sorted(path.glob("*.json")):
        try:
            records.append(load_record(f, source))
        except Exception as exc:  # a thin bundle shouldn't kill a cohort run
            print(f"  ! skipped {f.name}: {exc}")
    return records
