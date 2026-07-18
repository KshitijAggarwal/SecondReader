"""
AGENT 2 — Chart Reconciler (the core agent).

Structured clauses + the FULL patient chart -> one verdict per clause.

Critical design point: the model must check each clause against the ENTIRE
structured record, not just what is thematically related to the visit. Chart
facts that never came up in conversation (a medication, a resolved condition, a
lab value) are exactly what a downstream false-positive filter needs to catch.

Runs with adaptive extended thinking — this is where the reasoning is genuinely
hard. A subagent can later add prompt caching on the chart block, few-shot
examples, and per-clause evidence validation.
"""

GUARDRAILS = (
    "You are the Chart Reconciler in TrialGuard, a clinical-trial pre-screen "
    "verification system. A human coordinator makes the final call, so your job is "
    "to surface evidence, not to decide enrollment. Rules you must never violate: "
    "(1) Never fabricate a chart fact. If a clause cannot be resolved from the "
    "provided structured data, the verdict is 'insufficient_data', never a guess. "
    "(2) Check each clause against the ENTIRE structured chart below, not only facts "
    "related to today's visit. (3) Every 'violated' or 'satisfied' verdict must cite "
    "the exact chart fact used."
)

SYSTEM = GUARDRAILS

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "clause_id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["satisfied", "violated", "insufficient_data"],
                    },
                    "evidence": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "resource_type": {"type": "string"},
                            "resource_summary": {"type": "string"},
                            "found_in": {"type": "string"},
                        },
                        "required": [
                            "resource_type",
                            "resource_summary",
                            "found_in",
                        ],
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": ["clause_id", "verdict", "evidence", "confidence"],
            },
        }
    },
    "required": ["verdicts"],
}


def reconcile_chart(llm, clauses: dict, chart_text: str) -> dict:
    import json

    user = (
        "PATIENT CHART (the full structured record — reason over ALL of it):\n"
        f"{chart_text}\n\n"
        "CLAUSES TO CHECK (from the parsed trial criteria):\n"
        f"{json.dumps(clauses['clauses'], indent=2)}\n\n"
        "For each clause, decide satisfied / violated / insufficient_data by "
        "testing its 'check' against the chart above. For 'satisfied' and "
        "'violated', cite the exact chart fact in evidence.resource_summary. Note: "
        "'satisfied' means the requirement is met — for an inclusion clause the "
        "patient qualifies on it; for an exclusion clause 'violated' means the "
        "patient hits the exclusion. If the chart is silent, use insufficient_data."
    )
    return llm.structured(SYSTEM, user, SCHEMA, thinking=True)
