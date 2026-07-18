"""Primitive 2 — the symptom recurrence counter. Pure Python, no LLM.

The distributed-anchoring receipt: the same symptom said three times, to three
clinicians, over months, each time attributed to something locally reasonable and
benign — a fact that exists in no single chart view. Counted here.

Flags a symptom when: same normalized symptom across >= 3 encounters, with >= 2
distinct benign attributions, and no unifying workup on record.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..events import Event, PatientRecord

MIN_ENCOUNTERS = 3
MIN_DISTINCT_ATTRIBUTIONS = 2

# small synonym map -> canonical symptom
SYNONYMS: dict[str, str] = {
    "fatigue": "fatigue",
    "tired": "fatigue",
    "tiredness": "fatigue",
    "exhaustion": "fatigue",
    "exhausted": "fatigue",
    "low energy": "fatigue",
    "malaise": "fatigue",
    "worn out": "fatigue",
    "dizzy": "dizziness",
    "dizziness": "dizziness",
    "lightheaded": "dizziness",
    "lightheadedness": "dizziness",
    "short of breath": "dyspnea",
    "shortness of breath": "dyspnea",
    "breathless": "dyspnea",
    "dyspnea": "dyspnea",
    "joint pain": "arthralgia",
    "joint pains": "arthralgia",
    "arthralgia": "arthralgia",
    "achy joints": "arthralgia",
    "weight loss": "weight_loss",
    "losing weight": "weight_loss",
    "palpitations": "palpitations",
    "headache": "headache",
    "headaches": "headache",
}

# attributions that signal "explained away as benign / local", not a workup
BENIGN_MARKERS = (
    "stress",
    "anxiety",
    "perimenopause",
    "menopause",
    "viral",
    "deconditioning",
    "sleep",
    "insomnia",
    "aging",
    "overwork",
    "dehydration",
    "diet",
    "normal",
    "reassur",
)

WORKUP_MARKERS = ("workup", "referral", "panel", "ordered", "biopsy", "imaging", "specialist")


def _canonical(text: str) -> str | None:
    t = (text or "").strip().lower()
    if t in SYNONYMS:
        return SYNONYMS[t]
    for phrase, canon in SYNONYMS.items():
        if phrase in t:
            return canon
    return t or None


def _is_benign(attribution: str | None) -> bool:
    a = (attribution or "").lower()
    return any(m in a for m in BENIGN_MARKERS)


@dataclass
class RecurrenceFinding:
    symptom: str
    n_encounters: int
    attributions: list[str]
    clinicians: list[str]
    span_days: int
    workup_seen: bool
    occurrences: list[dict]

    def to_dict(self) -> dict:
        return {
            "symptom": self.symptom,
            "n_encounters": self.n_encounters,
            "attributions": self.attributions,
            "clinicians": self.clinicians,
            "span_days": self.span_days,
            "workup_seen": self.workup_seen,
            "occurrences": self.occurrences,
        }


def find_recurrences(record: PatientRecord) -> list[RecurrenceFinding]:
    groups: dict[str, list[Event]] = {}
    for e in record.symptoms():
        canon = _canonical(e.text or "")
        if not canon:
            continue
        groups.setdefault(canon, []).append(e)

    findings: list[RecurrenceFinding] = []
    for symptom, evs in groups.items():
        evs = sorted(evs, key=lambda e: e.day)
        encounters = {e.encounter_id or e.date for e in evs}
        attributions = [e.attribution for e in evs if e.attribution]
        distinct_benign = {a.lower() for a in attributions if _is_benign(a)}
        clinicians = sorted({e.clinician for e in evs if e.clinician})

        if len(encounters) < MIN_ENCOUNTERS:
            continue
        if len(distinct_benign) < MIN_DISTINCT_ATTRIBUTIONS:
            continue

        workup_seen = any(
            any(m in (e.note or "").lower() or m in (e.attribution or "").lower() for m in WORKUP_MARKERS)
            for e in evs
        )
        span_days = (evs[-1].day - evs[0].day).days
        findings.append(
            RecurrenceFinding(
                symptom=symptom,
                n_encounters=len(encounters),
                attributions=attributions,
                clinicians=clinicians,
                span_days=span_days,
                workup_seen=workup_seen,
                occurrences=[
                    {
                        "date": e.date,
                        "attribution": e.attribution,
                        "clinician": e.clinician,
                    }
                    for e in evs
                ],
            )
        )
    # most-repeated, longest-unaddressed first
    findings.sort(key=lambda f: (not f.workup_seen, f.n_encounters), reverse=True)
    return findings
