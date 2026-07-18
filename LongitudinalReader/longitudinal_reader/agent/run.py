"""End-to-end orchestration: patient record -> findings.

  load (caller) -> primitives -> decompose -> (evidence) -> reconcile -> result dict

The result dict is fully serializable (JSON) and is what render.py consumes.
"""

from __future__ import annotations

from typing import Any

from ..events import PatientRecord
from . import decompose as _decompose
from . import evidence as _evidence
from . import reconcile as _reconcile


def _strip_objects(primitives: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in primitives.items() if not k.startswith("_")}


def analyze(
    record: PatientRecord,
    *,
    use_llm: bool = True,
    gather: bool = False,
) -> dict[str, Any]:
    """Run the pipeline over one patient. Returns a serializable result dict."""
    primitives = _decompose.run_primitives(record)
    signal = _decompose.any_signal(primitives)

    result: dict[str, Any] = {
        "patient": {
            "id": record.patient_id,
            "name": record.display_name,
            "age": record.age,
            "sex": record.sex,
            "active_conditions": record.active_conditions,
            "n_events": len(record.events),
            "span_years": round(record.span_days() / 365, 1),
        },
        "source": record.source,
        "primitive_signal": signal,
        "primitives": _strip_objects(primitives),
    }

    if not use_llm:
        # Deterministic screen only — used for a fast cohort pass. No restraint
        # scoring; we just report whether any mechanical signal exists.
        result.update(
            hypotheses=[],
            findings=[],
            near_misses=[],
            silence_rationale=(
                "No mechanical trajectory, recurrence, or constellation detected."
                if not signal
                else "Mechanical signal present — run full analysis for scored findings."
            ),
            silent=not signal,
            mode="deterministic",
        )
        return result

    hypotheses = _decompose.decompose(record, primitives)
    if gather:
        hypotheses = _evidence.gather_evidence(record, hypotheses)
    recon = _reconcile.reconcile(record, hypotheses, primitives)

    findings = recon.get("findings", [])
    result.update(
        hypotheses=hypotheses,
        findings=findings,
        near_misses=recon.get("near_misses", []),
        silence_rationale=recon.get("silence_rationale", ""),
        silent=len(findings) == 0,
        mode="full",
    )
    return result
