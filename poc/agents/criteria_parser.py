"""
AGENT 1 — Criteria Parser.

Trial eligibility free-text -> structured, checkable clauses.

Not the hard reasoning step, so this runs a plain (non-thinking) structured call.
A subagent can later harden the schema, handle compound clauses, lab thresholds,
temporal logic, etc.
"""

GUARDRAILS = (
    "You are part of TrialGuard, a clinical-trial pre-screen verification system. "
    "A human coordinator makes the final call. Rules you must never violate: "
    "never fabricate criteria; only restate what the eligibility text actually says; "
    "always preserve whether a clause is an inclusion or an exclusion."
)

SYSTEM = (
    GUARDRAILS
    + " Parse the trial eligibility text into atomic, individually-checkable clauses."
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "trial_id": {"type": "string"},
        "version": {"type": "string"},
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "polarity": {"type": "string", "enum": ["inclusion", "exclusion"]},
                    "type": {
                        "type": "string",
                        "enum": [
                            "age",
                            "condition",
                            "medication",
                            "lab_value",
                            "procedure",
                            "other",
                        ],
                    },
                    "description": {"type": "string"},
                    "check": {"type": "string"},
                },
                "required": ["id", "polarity", "type", "description", "check"],
            },
        },
    },
    "required": ["trial_id", "version", "clauses"],
}


def parse_criteria(llm, trial: dict, trial_text: str) -> dict:
    user = (
        f"Trial id: {trial['trial_id']}\nProtocol version: {trial['version']}\n\n"
        f"{trial_text}\n\n"
        "Return one clause per atomic eligibility requirement. Give each clause a "
        "stable id (c1, c2, ...). The 'check' field must be a precise condition that "
        "can be tested against a structured patient chart."
    )
    return llm.structured(SYSTEM, user, SCHEMA, thinking=False)
