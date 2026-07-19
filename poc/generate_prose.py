"""
Fill each synthetic cohort record with a realistic ambient transcript + SOAP note
+ after-visit summary, in the style of the Abridge synthetic-ambient-fhir-25 data.

Thesis-critical constraint: the DISQUALIFYING fact (semaglutide / depression /
hypokalemia) must NOT appear in the transcript or note. It lives only in the
structured chart (pulled from outside records / prior labs). That is the whole
point of TrialGuard: it catches what the conversation never surfaced.

Rewrites data/trial_cohort.jsonl in place (structured chart untouched).
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient
import patient_loader

COHORT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "trial_cohort.jsonl")

# What each patient's chart contains that must stay OUT of the conversation/note.
BURIED = {
    "control": None,
    "glp1": "an active semaglutide (GLP-1 agonist) prescription from an outside clinic",
    "depression": "a past diagnosis of major depressive disorder on the problem list",
    "hypokalemia": "a recent serum potassium of 3.0 mmol/L (mild hypokalemia) on outside labs",
}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "transcript": {"type": "string"},
        "note": {"type": "string"},
        "after_visit_summary": {"type": "string"},
    },
    "required": ["transcript", "note", "after_visit_summary"],
}

SYSTEM = (
    "You generate synthetic (fully fictional, no real patient) clinical documentation for a "
    "research dataset. Match this house style: (1) transcript = a warm, natural, speaker-labeled "
    "ambient conversation ('DR:' and 'PT:' turns, ~900-1200 words), realistic and specific; "
    "(2) note = a SOAP-style clinical note in markdown with **Subjective:**, **Objective:**, "
    "**Assessment:**, **Plan:** sections (~350-500 words); (3) after_visit_summary = a short, "
    "plain-language patient-facing summary. Ground everything ONLY in the structured facts given. "
    "Do NOT invent disqualifying medical facts."
)


def build_user(record, chart_text, buried):
    p = record["patient_context"]["patient"]
    name = f"{' '.join(p['name'][0]['given'])} {p['name'][0]['family']}"
    omit = (f"\n\nIMPORTANT: The patient's structured chart also contains {buried}, pulled from "
            f"outside records. This did NOT come up during today's visit. Do NOT mention or allude "
            f"to it anywhere in the transcript, note, or summary — it must remain absent from the "
            f"conversation, exactly as in a real visit where the clinician never surfaced it."
            ) if buried else ("\n\nThis patient's chart is unremarkable for exclusions; write a "
            "routine screening visit.")
    return (
        f"Patient: {name} ({p['gender']}, born {p['birthDate']}).\n"
        f"Visit: research-study screening visit for an anti-obesity medication trial, ~6-7 months "
        f"after metabolic (bariatric) surgery. The clinician reviews how the patient is doing since "
        f"surgery — weight trend, diet, activity, energy, any concerns — and explains the study.\n\n"
        f"Structured chart digest (ground the visible visit in this):\n{chart_text}{omit}"
    )


def main():
    records = [json.loads(l) for l in open(COHORT) if l.strip()]
    llm = LLMClient()
    for r in records:
        did = r["metadata"]["demo_id"]
        chart_text = patient_loader.chart_to_text(patient_loader.extract_chart(r))
        out = llm.structured(SYSTEM, build_user(r, chart_text, BURIED.get(did)), SCHEMA)
        r["transcript"] = out["transcript"]
        r["note"] = out["note"]
        r["after_visit_summary"] = out["after_visit_summary"]
        print(f"  {did}: transcript {len(out['transcript'].split())}w, note {len(out['note'].split())}w")
    with open(COHORT, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"updated {len(records)} records -> {COHORT}")


if __name__ == "__main__":
    main()
