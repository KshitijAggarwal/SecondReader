"""Ingest an encounter and normalize it into the shape the engine expects.

Two supported sources, one output shape:
  1. A curated encounter file in second_voice/data/<id>.json
  2. Any record from the provided synthetic-ambient-fhir-25 dataset (by index or id)

Both use the dataset's record shape: transcript/note/after_visit_summary are plain
strings, patient_context holds the FHIR Patient + a chart summary. The dataset's
transcript is a `DR:`/`PT:` string with no line ids, so we parse it into diarized,
line_id'd turns here. That parsed transcript is the single source of truth for the
grounding contract downstream: every model claim must cite one of these line_ids.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
DATA_DIR = _HERE.parent.parent / "data"
DATASET = (
    _HERE.parent.parent.parent.parent
    / "synthetic-ambient-fhir-25"
    / "synthetic-ambient-fhir-25.json"
)

_SPEAKER_MAP = {
    "DR": "clinician",
    "PT": "patient",
    "NURSE": "nurse",
    "FAMILY": "family",
}
_TURN_RE = re.compile(r"^\s*(DR|PT|NURSE|FAMILY)\s*:\s*(.*)$", re.IGNORECASE)


@dataclass
class Turn:
    line_id: str
    speaker: str
    text: str


@dataclass
class Encounter:
    id: str
    patient_name: str
    patient_summary: str          # age / sex / conditions / meds / allergies, one line
    visit_title: str
    turns: list[Turn]
    note: str
    avs: str
    raw: dict[str, Any] = field(default_factory=dict)

    def transcript_for_prompt(self) -> str:
        return "\n".join(f"[{t.line_id}] {t.speaker}: {t.text}" for t in self.turns)

    def line_ids(self) -> set[str]:
        return {t.line_id for t in self.turns}

    def turn(self, line_id: str) -> Turn | None:
        return next((t for t in self.turns if t.line_id == line_id), None)


def _parse_transcript(raw_transcript: str) -> list[Turn]:
    turns: list[Turn] = []
    n = 0
    for line in raw_transcript.splitlines():
        m = _TURN_RE.match(line)
        if not m:
            # continuation of the previous speaker's turn
            if turns and line.strip():
                turns[-1].text += " " + line.strip()
            continue
        n += 1
        tag, text = m.group(1).upper(), m.group(2).strip()
        turns.append(Turn(line_id=f"L{n:03d}", speaker=_SPEAKER_MAP.get(tag, tag.lower()), text=text))
    return turns


def _patient_summary(patient_context: dict[str, Any]) -> tuple[str, str]:
    p = patient_context.get("patient", {})
    names = p.get("name", [{}])
    given = " ".join(names[0].get("given", [])) if names else ""
    family = names[0].get("family", "") if names else ""
    name = (given + " " + family).strip() or "the patient"
    gender = p.get("gender", "unknown")
    birth = p.get("birthDate")
    age = "?"
    if birth:
        try:
            b = date.fromisoformat(birth)
            today = date(2026, 7, 18)
            age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        except ValueError:
            pass
    ls = patient_context.get("longitudinal_summary", {})
    conditions = ls.get("condition_labels", []) or patient_context.get("active_conditions", [])
    meds = ls.get("medication_labels", []) or patient_context.get("medications", [])
    allergies = patient_context.get("allergies", [])
    parts = [f"{name}, {age}yo {gender}"]
    if conditions:
        parts.append("active conditions: " + ", ".join(conditions[:8]))
    parts.append("medications: " + (", ".join(meds) if meds else "none on file"))
    parts.append("allergies: " + (", ".join(allergies) if allergies else "none on file"))
    return name, " | ".join(parts)


def _from_record(rec: dict[str, Any]) -> Encounter:
    name, summary = _patient_summary(rec.get("patient_context", {}))
    meta = rec.get("metadata", {})
    return Encounter(
        id=meta.get("encounter_id") or rec.get("id", "unknown"),
        patient_name=name,
        patient_summary=summary,
        visit_title=meta.get("visit_title", rec.get("visit_title", "Clinic visit")),
        turns=_parse_transcript(rec.get("transcript", "")),
        note=rec.get("note", ""),
        avs=rec.get("after_visit_summary", ""),
        raw=rec,
    )


def list_curated() -> list[tuple[str, str]]:
    out = []
    for f in sorted(DATA_DIR.glob("*.json")):
        rec = json.loads(f.read_text())
        out.append((f.stem, rec.get("metadata", {}).get("visit_title", f.stem)))
    return out


def load(encounter_id: str) -> Encounter:
    """Load by curated filename stem, dataset id, or dataset index (e.g. 'dataset:3')."""
    curated = DATA_DIR / f"{encounter_id}.json"
    if curated.exists():
        return _from_record(json.loads(curated.read_text()))

    if not DATASET.exists():
        raise FileNotFoundError(f"No curated encounter '{encounter_id}' and dataset not found.")
    records = json.loads(DATASET.read_text())
    if encounter_id.startswith("dataset:"):
        idx = int(encounter_id.split(":", 1)[1])
        return _from_record(records[idx])
    for rec in records:
        if encounter_id in (rec.get("id"), rec.get("metadata", {}).get("encounter_id")):
            return _from_record(rec)
    raise KeyError(f"Encounter '{encounter_id}' not found.")
