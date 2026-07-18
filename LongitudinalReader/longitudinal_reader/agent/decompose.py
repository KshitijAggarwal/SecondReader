"""Stage 2 — DECOMPOSITION.

Run the three deterministic primitives, then one Claude call that sanity-checks the
mechanical flags in clinical context and adds grounded free-text hypotheses. Returns
the raw primitive outputs (the receipts) plus the model's hypotheses.
"""

from __future__ import annotations

import json
from typing import Any

from .. import llm
from ..events import PatientRecord
from ..primitives import detect_slopes, find_recurrences, match_constellations
from ..prompts import DECOMPOSE_SYSTEM, decompose_user
from ..schemas import DECOMPOSE_SCHEMA


def run_primitives(record: PatientRecord) -> dict[str, Any]:
    """Deterministic pass. Slopes first (constellation consumes trajectory flags)."""
    slopes = detect_slopes(record)
    recurrences = find_recurrences(record)
    constellations = match_constellations(record, slopes=slopes)
    return {
        "_objects": {  # kept for programmatic use (render); stripped before serializing
            "slopes": slopes,
            "recurrences": recurrences,
            "constellations": constellations,
        },
        "slopes": [s.to_dict() for s in slopes],
        "recurrences": [r.to_dict() for r in recurrences],
        "constellations": [c.to_dict() for c in constellations],
    }


def any_signal(primitives: dict[str, Any]) -> bool:
    return bool(primitives["slopes"] or primitives["recurrences"] or primitives["constellations"])


def decompose(record: PatientRecord, primitives: dict[str, Any]) -> list[dict[str, Any]]:
    """One Claude call -> grounded hypotheses."""
    prim_for_llm = {k: v for k, v in primitives.items() if not k.startswith("_")}
    result = llm.call_json(
        system=DECOMPOSE_SYSTEM,
        user=decompose_user(
            json.dumps(record.to_dict(), indent=1),
            json.dumps(prim_for_llm, indent=1),
        ),
        schema=DECOMPOSE_SCHEMA,
        effort="high",
    )
    return result.get("hypotheses", [])
