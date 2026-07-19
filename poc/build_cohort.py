"""
Build a synthetic patient cohort for the NCT07163650 protocol-amendment demo.

Each record matches the shape of the Abridge synthetic-ambient-fhir-25 dataset
(patient_context + encounter_fhir.related_resources + transcript/note/AVS), but the
STRUCTURED chart is hand-controlled so eligibility is deterministic.

Trial NCT07163650 ("Anti-Obesity Medications 6 Months After Metabolic Surgery"):
  aom_v1 (original, 2025-09-01): inclusion ONLY - 6mo post metabolic surgery,
                                 age 18-55, BMI >= 28. No exclusions.
  aom_v2 (amended,  2026-01-25): same inclusion + a large new exclusion list
                                 (GLP-1 agonists, weight-loss meds, depression,
                                 malignancy, cardiac disease, hypokalemia, ...).

Design (each patient meets all three inclusion facts; carries ONE buried fact):

  demo_id     age  buried fact                          v1 (original)   v2 (amended)
  ----------  ---  -----------------------------------  --------------  ----------------
  control      42  (none)                               NEEDS_REVIEW    NEEDS_REVIEW
  glp1         45  on semaglutide (GLP-1R agonist)      NEEDS_REVIEW    EXCLUDE (GLP-1)
  depression   38  history of major depressive disorder NEEDS_REVIEW    EXCLUDE (psych)
  hypokalemia  50  serum potassium 3.0 mmol/L (low)     NEEDS_REVIEW    EXCLUDE (hypoK)

The buried fact is never an inclusion issue and does not exist as an exclusion in
v1, so v1 = NEEDS_REVIEW for everyone; only the v2 amendment forces the flip.

Writes data/trial_cohort.jsonl (transcript/note filled by generate_prose.py after
the flip is verified mechanically).
"""
import json
from pathlib import Path

VISIT_DATE = "2026-02-15T10:00:00-06:00"  # after the 2026-01-25 amendment
OUT = Path(__file__).resolve().parent / "data" / "trial_cohort.jsonl"


def _pid(prefix):
    base = (prefix + "0" * 32)[:32]
    return f"{base[:8]}-{base[8:12]}-{base[12:16]}-{base[16:20]}-{base[20:32]}"


def condition(pid, label, clinical="active"):
    return {
        "resourceType": "Condition", "id": _pid(pid),
        "clinicalStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": clinical}]},
        "verificationStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/condition-category",
            "code": "encounter-diagnosis", "display": "Encounter Diagnosis"}]}],
        "code": {"coding": [{"system": "http://snomed.info/sct", "display": label}], "text": label},
    }


def observation(pid, loinc, text, value, unit):
    return {
        "resourceType": "Observation", "id": _pid(pid), "status": "final",
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "laboratory", "display": "Laboratory"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": text}], "text": text},
        "valueQuantity": {"value": value, "unit": unit,
                          "system": "http://unitsofmeasure.org", "code": unit},
    }


def procedure(pid, label):
    return {"resourceType": "Procedure", "id": _pid(pid), "status": "completed",
            "code": {"coding": [{"system": "http://snomed.info/sct", "display": label}], "text": label}}


def med_request(pid, label):
    return {"resourceType": "MedicationRequest", "id": _pid(pid), "status": "active", "intent": "order",
            "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                                                       "display": label}], "text": label}}


def make_patient(short_id, demo_id, gender, birth_date, given, family, visit_title,
                 conditions, observations, procedures, med_requests, cond_labels, med_labels):
    ppid, epid = _pid(short_id + "p"), _pid(short_id + "e")
    return {
        "id": f"{ppid}::{epid}",
        "metadata": {
            "source": "synthea-fhir-r4", "synthetic": True, "demo_id": demo_id,
            "patient_id": ppid, "encounter_id": epid, "encounter_reference": f"urn:uuid:{epid}",
            "date": VISIT_DATE, "status": "finished",
            "visit_type": "Screening visit for research study (procedure)",
            "document_status": "current",
            "related_resource_counts": {"Condition": len(conditions), "Observation": len(observations),
                                        "Procedure": len(procedures), "MedicationRequest": len(med_requests)},
            "visit_title": visit_title,
        },
        "patient_context": {
            "patient": {
                "resourceType": "Patient", "id": ppid,
                "name": [{"use": "official", "family": family, "given": given, "prefix": []}],
                "gender": gender, "birthDate": birth_date,
                "maritalStatus": {"coding": [], "text": "Unknown"},
                "address": [{"city": "Springfield", "state": "IL", "country": "US"}],
                "communication": [{"language": {"text": "English"}}],
            },
            "longitudinal_summary": {
                "resource_counts": {"Condition": len(cond_labels) + len(conditions), "Observation": 45,
                                    "MedicationRequest": len(med_labels), "Procedure": 25, "Patient": 1},
                "condition_labels": cond_labels, "medication_labels": med_labels,
            },
        },
        "encounter_fhir": {
            "encounter": {"resourceType": "Encounter", "id": epid, "status": "finished",
                          "type": [{"text": "Screening visit for research study (procedure)"}]},
            "related_resources": {"Condition": conditions, "Observation": observations,
                                  "Procedure": procedures, "MedicationRequest": med_requests},
        },
        "transcript": "", "note": "", "after_visit_summary": "",
        "after_visit_summary_provenance": {"method": "deterministic_extractive_v1",
                                           "source": "clinical_note_assessment_and_plan",
                                           "review_status": "not_clinically_reviewed"},
    }


# Shared inclusion facts: post-bariatric-surgery + BMI >= 28 (age via birthDate).
def inclusion(short_id, bmi):
    obs = [observation(short_id + "b", "39156-5", "Body mass index (BMI) [Ratio]", bmi, "kg/m2")]
    procs = [procedure(short_id + "s", "Bariatric surgery (procedure)")]
    return obs, procs


def base_conditions(short_id):
    return [condition(short_id + "h", "History of bariatric surgery (situation)", clinical="resolved"),
            condition(short_id + "o", "Body mass index 30+ - obesity (finding)")]


patients = []

# 1) CONTROL — clean. NEEDS_REVIEW under both.
obs, procs = inclusion("ctrl", 32.0)
patients.append(make_patient(
    "ctrl", "control", "female", "1983-11-04", ["Maria", "Elena"], "Okonkwo",
    "Research screening visit — anti-obesity medication study",
    conditions=base_conditions("ctrl"), observations=obs, procedures=procs, med_requests=[],
    cond_labels=["History of bariatric surgery (situation)", "Received higher education (finding)"],
    med_labels=[]))

# 2) GLP-1 — on semaglutide (GLP-1R agonist), prescribed elsewhere for weight. EXCLUDE v2.
obs, procs = inclusion("glp1", 33.4)
patients.append(make_patient(
    "glp1", "glp1", "male", "1980-08-22", ["David", "Paul"], "Hartmann",
    "Research screening visit — anti-obesity medication study",
    conditions=base_conditions("glp1"), observations=obs, procedures=procs,
    med_requests=[med_request("glp1m", "Semaglutide 1 MG/0.75 ML Injection")],
    cond_labels=["History of bariatric surgery (situation)", "Body mass index 30+ - obesity (finding)"],
    med_labels=["Semaglutide 1 MG/0.75 ML Injection"]))

# 3) DEPRESSION — history of major depressive disorder. EXCLUDE v2.
obs, procs = inclusion("dep", 30.6)
patients.append(make_patient(
    "dep", "depression", "female", "1988-03-17", ["Priya", "Anne"], "Salvatore",
    "Research screening visit — anti-obesity medication study",
    conditions=base_conditions("dep") + [condition("depc", "Major depressive disorder (disorder)")],
    observations=obs, procedures=procs, med_requests=[],
    cond_labels=["History of bariatric surgery (situation)", "Major depressive disorder (disorder)"],
    med_labels=[]))

# 4) HYPOKALEMIA — buried low-potassium lab (torsades risk factor). EXCLUDE v2.
obs, procs = inclusion("hypok", 31.2)
obs = obs + [observation("hypokk", "2823-3", "Potassium [Moles/volume] in Serum or Plasma", 3.0, "mmol/L")]
patients.append(make_patient(
    "hypok", "hypokalemia", "male", "1975-06-30", ["Robert", "James"], "Delacroix",
    "Research screening visit — anti-obesity medication study",
    conditions=base_conditions("hypok"), observations=obs, procedures=procs, med_requests=[],
    cond_labels=["History of bariatric surgery (situation)", "Body mass index 30+ - obesity (finding)"],
    med_labels=[]))


OUT.parent.mkdir(exist_ok=True)
with open(OUT, "w") as f:
    for p in patients:
        f.write(json.dumps(p) + "\n")
print(f"wrote {len(patients)} patients -> {OUT}")
for p in patients:
    import datetime
    dob = datetime.date.fromisoformat(p["patient_context"]["patient"]["birthDate"])
    age = (datetime.date.fromisoformat(VISIT_DATE[:10]) - dob).days // 365
    print(f"  {p['metadata']['demo_id']:12} {p['patient_context']['patient']['gender']:7} age {age}")
