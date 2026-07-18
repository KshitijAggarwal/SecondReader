"""Primitive 3 — the constellation matcher. Pure Python, no LLM.

Small, deliberate map of high-morbidity multi-system diseases that only *assemble*
over time: findings that are individually low-alarm and specialty-scattered, but
diagnostic when laid on one timeline. Returns partial matches — the *missing*
element is often exactly the next step.

Kept intentionally tiny (a handful of patterns). The slope + recurrence primitives
cover the disease-agnostic long tail; this buys a few named, high-value catches.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..events import PatientRecord
from .recurrence import _canonical

# Each element: canonical name -> synonyms/substrings that count as "present".
# A pattern fires when >= min_hits of its elements are present in the timeline.
PATTERNS: dict[str, dict] = {
    "systemic_sclerosis": {
        "label": "Systemic sclerosis (scleroderma)",
        "min_hits": 3,
        "systems": ["vascular", "gi", "immunologic", "skin"],
        "elements": {
            "raynaud": ["raynaud", "cold fingers", "color change fingers"],
            "dysphagia": ["dysphagia", "difficulty swallowing", "food sticking"],
            "positive_ana": ["positive ana", "ana positive", "antinuclear"],
            "skin_tightening": ["skin tightening", "sclerodactyly", "thick skin", "puffy fingers"],
            "gerd": ["reflux", "gerd", "heartburn"],
            "telangiectasia": ["telangiectasia"],
        },
    },
    "sle": {
        "label": "Systemic lupus erythematosus (SLE)",
        "min_hits": 3,
        "systems": ["immunologic", "renal", "skin", "musculoskeletal"],
        "elements": {
            "malar_rash": ["malar rash", "butterfly rash", "facial rash"],
            "arthralgia": ["arthralgia", "joint pain", "polyarthritis"],
            "positive_ana": ["positive ana", "ana positive", "antinuclear"],
            "photosensitivity": ["photosensitiv", "sun rash"],
            "cytopenia": ["low platelet", "leukopenia", "anemia", "low white"],
            "proteinuria": ["proteinuria", "protein in urine", "lupus nephritis"],
            "oral_ulcers": ["oral ulcer", "mouth ulcer"],
        },
    },
    "hemochromatosis": {
        "label": "Hereditary hemochromatosis (iron overload)",
        "min_hits": 3,
        "systems": ["hepatic", "endocrine", "musculoskeletal"],
        "elements": {
            "high_ferritin": ["elevated ferritin", "high ferritin"],
            "high_transferrin_sat": ["high transferrin", "elevated transferrin", "iron overload"],
            "arthralgia": ["arthralgia", "joint pain"],
            "diabetes": ["diabetes", "elevated a1c", "high a1c"],
            "elevated_lfts": ["elevated alt", "elevated ast", "elevated lfts", "transaminitis"],
            "fatigue": ["fatigue"],
            "hyperpigmentation": ["hyperpigmentation", "bronze skin"],
        },
    },
    "multiple_myeloma": {
        "label": "Multiple myeloma (CRAB)",
        "min_hits": 3,
        "systems": ["hematologic", "renal", "skeletal", "metabolic"],
        "elements": {
            "hypercalcemia": ["high calcium", "hypercalcemia", "elevated calcium"],
            "renal_insufficiency": ["rising creatinine", "elevated creatinine", "renal insufficiency"],
            "anemia": ["anemia", "low hemoglobin", "falling hemoglobin"],
            "bone_pain": ["bone pain", "back pain", "lytic lesion", "pathologic fracture"],
            "paraprotein": ["paraprotein", "m spike", "monoclonal", "high total protein"],
        },
    },
    "ckd_progression": {
        "label": "Progressive chronic kidney disease",
        "min_hits": 2,
        "systems": ["renal", "cardiovascular", "hematologic"],
        "elements": {
            "rising_creatinine": ["rising creatinine", "elevated creatinine"],
            "falling_egfr": ["falling egfr", "low egfr", "declining gfr"],
            "hypertension": ["hypertension", "high blood pressure"],
            "anemia": ["anemia", "low hemoglobin"],
            "proteinuria": ["proteinuria", "albuminuria"],
        },
    },
    "hypothyroidism": {
        "label": "Hypothyroidism",
        "min_hits": 2,
        "systems": ["endocrine", "constitutional"],
        "elements": {
            "high_tsh": ["high tsh", "elevated tsh", "rising tsh"],
            "fatigue": ["fatigue"],
            "weight_gain": ["weight gain"],
            "cold_intolerance": ["cold intoleran"],
            "constipation": ["constipation"],
        },
    },
    "cushings": {
        "label": "Cushing's syndrome",
        "min_hits": 3,
        "systems": ["endocrine", "cardiovascular", "metabolic"],
        "elements": {
            "central_weight_gain": ["central weight", "weight gain", "moon face", "buffalo hump"],
            "hypertension": ["hypertension", "high blood pressure"],
            "hyperglycemia": ["hyperglycemia", "elevated a1c", "high a1c", "diabetes"],
            "easy_bruising": ["easy bruising", "bruis"],
            "striae": ["striae", "stretch marks"],
            "proximal_weakness": ["proximal weakness", "muscle weakness"],
        },
    },
}


@dataclass
class ConstellationFinding:
    pattern: str
    label: str
    present: list[str]
    missing: list[str]
    systems: list[str]
    span_days: int
    score: float  # present / total elements
    evidence: list[dict]  # which feature satisfied each present element

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "label": self.label,
            "present": self.present,
            "missing": self.missing,
            "systems": self.systems,
            "span_days": self.span_days,
            "score": round(self.score, 2),
            "evidence": self.evidence,
        }


def _lab_status_features(record: PatientRecord, slopes) -> list[tuple[str, str]]:
    """Derive (feature_text, dated_source) flags from the latest value of each lab
    and from any detected trajectory."""
    feats: list[tuple[str, str]] = []
    labs = record.labs()
    by_code: dict[str, list] = {}
    for e in labs:
        if e.code:
            by_code.setdefault(e.code, []).append(e)

    for code, evs in by_code.items():
        evs = sorted(evs, key=lambda e: e.day)
        last = evs[-1]
        src = f"{code} {last.value}{last.unit or ''} on {last.date}"
        if last.ref_high is not None and last.value is not None and last.value > last.ref_high:
            feats.append((f"elevated {code}", src))
            feats.append((f"high {code}", src))
        if last.ref_low is not None and last.value is not None and last.value < last.ref_low:
            feats.append((f"low {code}", src))
        # positive ANA encoded as a nonzero titer or explicit value
        if code == "ana" and last.value:
            feats.append(("positive ana", src))

    # trajectory features from the slope primitive
    for s in slopes or []:
        feats.append((f"{s.direction} {s.code}", f"{s.code} {s.first[1]}->{s.last[1]}"))
    return feats


def match_constellations(record: PatientRecord, slopes=None) -> list[ConstellationFinding]:
    # Build the bag of dated features present anywhere in the timeline.
    features: list[tuple[str, str]] = []
    for e in record.events:
        if e.type == "condition" and e.code:
            features.append((e.code.lower(), f"condition '{e.code}' onset {e.onset or e.date}"))
        if e.type == "symptom" and e.text:
            canon = _canonical(e.text) or ""
            features.append((e.text.lower(), f"symptom '{e.text}' on {e.date}"))
            if canon:
                features.append((canon, f"symptom '{e.text}' on {e.date}"))
        if e.note:
            features.append((e.note.lower(), f"note on {e.date}"))
    for c in record.active_conditions:
        features.append((c.lower(), f"active condition '{c}'"))
    features.extend(_lab_status_features(record, slopes))

    span = record.span_days()
    findings: list[ConstellationFinding] = []
    for name, spec in PATTERNS.items():
        present, missing, evidence = [], [], []
        for element, synonyms in spec["elements"].items():
            hit = None
            for feat_text, src in features:
                if any(syn in feat_text for syn in synonyms):
                    hit = src
                    break
            if hit:
                present.append(element)
                evidence.append({"element": element, "from": hit})
            else:
                missing.append(element)
        if len(present) >= spec["min_hits"]:
            findings.append(
                ConstellationFinding(
                    pattern=name,
                    label=spec["label"],
                    present=present,
                    missing=missing,
                    systems=spec["systems"],
                    span_days=span,
                    score=len(present) / len(spec["elements"]),
                    evidence=evidence,
                )
            )
    findings.sort(key=lambda f: (len(f.present), f.score), reverse=True)
    return findings
