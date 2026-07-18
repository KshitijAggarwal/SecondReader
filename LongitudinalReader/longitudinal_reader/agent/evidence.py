"""Stage 3 — EVIDENCE GATHERING (optional).

For live hypotheses, assemble the supporting/refuting dated events into a bundle.
In the core POC the decomposition already carries dated `supporting_events` and the
primitives carry the mechanical receipts, so this stage is a deterministic pass-through
that attaches the raw events referenced by each hypothesis. The architectural slot for
an (optional, clinician-as-user) PubMed/OMIM lookup lives here — deliberately left out
of the default path to keep the demo grounded in the chart.
"""

from __future__ import annotations

from typing import Any

from ..events import PatientRecord


def gather_evidence(
    record: PatientRecord, hypotheses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict]] = {}
    for e in record.sorted_events():
        by_date.setdefault(e.date, []).append(e.to_dict())
    for h in hypotheses:
        refs = h.get("supporting_events", [])
        h["evidence_events"] = [
            ev for r in refs for ev in by_date.get(r.get("date", ""), [])
        ]
    return hypotheses
