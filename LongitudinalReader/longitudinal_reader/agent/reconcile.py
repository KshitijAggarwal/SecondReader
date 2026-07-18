"""Stage 4 — RECONCILIATION + RESTRAINT GATE.

Score each candidate severity * trajectory_strength * unaddressed, drop anything
already worked up or benign, cap at 3, and force the empty set when nothing clears.
Near-misses are logged so the silence is auditable, not just absent.
"""

from __future__ import annotations

import json
from typing import Any

from .. import llm
from ..events import PatientRecord
from ..prompts import RECONCILE_SYSTEM, reconcile_user
from ..schemas import RECONCILE_SCHEMA


def _patient_summary(record: PatientRecord) -> str:
    bits = [f"{record.display_name or record.patient_id}"]
    if record.age is not None:
        bits.append(f"{record.age}y")
    if record.sex:
        bits.append(record.sex)
    span_years = round(record.span_days() / 365, 1)
    bits.append(f"{len(record.events)} events over {span_years}y")
    if record.active_conditions:
        bits.append("active: " + ", ".join(record.active_conditions[:6]))
    return " | ".join(bits)


def reconcile(
    record: PatientRecord,
    hypotheses: list[dict[str, Any]],
    primitives: dict[str, Any],
) -> dict[str, Any]:
    if not hypotheses:
        return {
            "findings": [],
            "near_misses": [],
            "silence_rationale": "No hypotheses survived decomposition — nothing across time to weigh.",
        }
    prim_for_llm = {k: v for k, v in primitives.items() if not k.startswith("_")}
    result = llm.call_json(
        system=RECONCILE_SYSTEM,
        user=reconcile_user(
            _patient_summary(record),
            json.dumps(hypotheses, indent=1),
            json.dumps(prim_for_llm, indent=1),
        ),
        schema=RECONCILE_SCHEMA,
        effort="high",
    )
    # Cap enforced in code (the API's structured-output schema can't express maxItems):
    # keep the 3 highest-scoring findings, strongest first.
    findings = sorted(result.get("findings", []), key=lambda f: f.get("score", 0), reverse=True)
    result["findings"] = findings[:3]
    return result
