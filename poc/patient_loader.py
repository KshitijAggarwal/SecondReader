"""
STEP: Patient / Chart side.

Loads ONE patient encounter record from the synthetic FHIR dataset and flattens
the full structured chart into a compact, LLM-readable digest.

This is deliberately the *whole* structured record (patient_context +
encounter_fhir.related_resources) — NOT just what came up in the transcript.
The whole point of TrialGuard is to reason over chart facts (meds, conditions,
labs) that never surfaced in the conversation.

POC scope: one hand-picked patient. A subagent can later make this robust across
all 25 records (missing fields, multiple encounters, longitudinal history, etc.).
"""

import json
from pathlib import Path

DATASET = (
    Path(__file__).resolve().parent.parent
    / "synthetic-ambient-fhir-25"
    / "synthetic-ambient-fhir-25.jsonl"
)

# Prediabetes young-adult patient — HbA1c 6.24%, BMI 31.4, carries an
# epinephrine auto-injector. Good demo: prediabetes (not diabetes) + a subtle
# allergy exclusion sitting only in the structured chart.
DEFAULT_PATIENT_PREFIX = "966e9818"


def load_record(patient_prefix: str = DEFAULT_PATIENT_PREFIX) -> dict:
    """Return the raw JSON record whose id starts with `patient_prefix`."""
    with open(DATASET) as f:
        for line in f:
            rec = json.loads(line)
            if rec["id"].startswith(patient_prefix):
                return rec
    raise ValueError(f"No patient record starting with {patient_prefix!r}")


def _coding_text(node: dict) -> str:
    """Pull a human label out of a FHIR CodeableConcept-ish node."""
    if not node:
        return ""
    if node.get("text"):
        return node["text"]
    for c in node.get("coding", []):
        if c.get("display"):
            return c["display"]
    return ""


def extract_chart(record: dict) -> dict:
    """
    Flatten a record into a structured digest of chart facts.

    Returns a dict with: demographics, conditions, medications, observations
    (labs/vitals), procedures. This is the 'patient side' payload handed to the
    reconciler.
    """
    pc = record["patient_context"]
    patient = pc["patient"]
    long_summary = pc.get("longitudinal_summary", {})
    rr = record["encounter_fhir"].get("related_resources", {})

    demographics = {
        "gender": patient.get("gender"),
        "birth_date": patient.get("birthDate"),
        "visit_date": record["metadata"].get("date"),
        "visit_title": record["metadata"].get("visit_title"),
    }

    # Conditions: encounter conditions + longitudinal condition labels.
    conditions = []
    for c in rr.get("Condition", []):
        status = ""
        cs = c.get("clinicalStatus", {}).get("coding", [{}])
        if cs:
            status = cs[0].get("code", "")
        conditions.append({"label": _coding_text(c.get("code", {})), "status": status})
    # Longitudinal condition labels (chart background not tied to this encounter).
    for label in long_summary.get("condition_labels", []):
        conditions.append({"label": label, "status": "longitudinal"})

    # Medications: encounter MedicationRequest + longitudinal medication labels.
    medications = []
    for m in rr.get("MedicationRequest", []):
        medications.append(_coding_text(m.get("medicationCodeableConcept", {})))
    for label in long_summary.get("medication_labels", []):
        medications.append(label)
    medications = [m for m in medications if m]

    # Observations: labs + vitals with values/units.
    observations = []
    for o in rr.get("Observation", []):
        vq = o.get("valueQuantity", {})
        observations.append(
            {
                "label": _coding_text(o.get("code", {})),
                "value": vq.get("value"),
                "unit": vq.get("unit"),
            }
        )

    procedures = [_coding_text(p.get("code", {})) for p in rr.get("Procedure", [])]

    return {
        "patient_id": record["metadata"]["patient_id"],
        "demographics": demographics,
        "conditions": conditions,
        "medications": medications,
        "observations": observations,
        "procedures": [p for p in procedures if p],
    }


def chart_to_text(chart: dict) -> str:
    """Render the digest as a compact text block for the LLM prompt."""
    d = chart["demographics"]
    lines = [
        f"PATIENT (id {chart['patient_id']})",
        f"  gender: {d['gender']}, birth_date: {d['birth_date']}, visit_date: {d['visit_date']}",
        f"  visit: {d['visit_title']}",
        "",
        "CONDITIONS (full chart, not just this visit):",
    ]
    for c in chart["conditions"]:
        lines.append(f"  - {c['label']} [{c['status']}]")
    lines.append("")
    lines.append("MEDICATIONS (full chart):")
    for m in chart["medications"] or ["  (none recorded)"]:
        lines.append(f"  - {m}")
    lines.append("")
    lines.append("OBSERVATIONS / LABS / VITALS:")
    for o in chart["observations"]:
        val = f"{o['value']} {o['unit']}".strip() if o["value"] is not None else "n/a"
        lines.append(f"  - {o['label']}: {val}")
    lines.append("")
    lines.append("PROCEDURES:")
    for p in chart["procedures"] or ["  (none recorded)"]:
        lines.append(f"  - {p}")
    return "\n".join(lines)


if __name__ == "__main__":
    rec = load_record()
    chart = extract_chart(rec)
    print(chart_to_text(chart))
