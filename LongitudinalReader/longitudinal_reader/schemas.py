"""JSON schemas for the two LLM stages. Strict, so the API validates each stage's
contract before we ever see it. Kept minimal — the receipts live in the event
stream and primitive outputs, so the model references dated events, never invents
values.
"""

from __future__ import annotations

# ---- Stage 2d: decomposition -> grounded hypotheses --------------------------

DECOMPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["hypotheses"],
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "title",
                    "systems",
                    "mechanism",
                    "supporting_events",
                    "primitive_support",
                    "next_step",
                ],
                "properties": {
                    "id": {"type": "string", "description": "short slug, e.g. 'ckd-drift'"},
                    "title": {
                        "type": "string",
                        "description": "one clinician-readable line naming the pattern across time",
                    },
                    "systems": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "body systems this spans",
                    },
                    "mechanism": {
                        "type": "string",
                        "description": "candidate explanation for the trajectory",
                    },
                    "supporting_events": {
                        "type": "array",
                        "description": "the dated receipt: events (by date) that constitute the pattern",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["date", "detail"],
                            "properties": {
                                "date": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                        },
                    },
                    "primitive_support": {
                        "type": "string",
                        "enum": ["slope", "recurrence", "constellation", "none"],
                        "description": "which deterministic primitive backs this, if any",
                    },
                    "next_step": {
                        "type": "string",
                        "description": "one concrete next action (a lab, referral, or question)",
                    },
                },
            },
        }
    },
}

# ---- Stage 4: reconciliation + restraint gate -------------------------------

RECONCILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings", "near_misses", "silence_rationale"],
    "properties": {
        "findings": {
            "type": "array",
            "description": "0-3 surfaced findings (cap enforced in code). Empty is the correct, common answer.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "hypothesis_id",
                    "headline",
                    "severity",
                    "trajectory_strength",
                    "unaddressed",
                    "score",
                    "explanation",
                    "next_step",
                    "event_chain",
                ],
                "properties": {
                    "hypothesis_id": {"type": "string"},
                    "headline": {
                        "type": "string",
                        "description": "the pattern in one clinician-readable sentence",
                    },
                    "severity": {
                        "type": "integer",
                        "description": "0 benign .. 3 high-morbidity if the trajectory is real (0-3)",
                    },
                    "trajectory_strength": {
                        "type": "number",
                        "description": "how clean/undeniable the across-time signal is, 0.0-1.0",
                    },
                    "unaddressed": {
                        "type": "number",
                        "description": "1.0 = never worked up; 0.0 = already investigated/resolved",
                    },
                    "score": {
                        "type": "number",
                        "description": "severity * trajectory_strength * unaddressed",
                    },
                    "explanation": {"type": "string"},
                    "next_step": {"type": "string"},
                    "event_chain": {
                        "type": "array",
                        "description": "dated receipt, chronological",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["date", "detail"],
                            "properties": {
                                "date": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "near_misses": {
            "type": "array",
            "description": "candidates considered and dropped — makes the silence auditable",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["hypothesis_id", "reason_dropped"],
                "properties": {
                    "hypothesis_id": {"type": "string"},
                    "reason_dropped": {"type": "string"},
                },
            },
        },
        "silence_rationale": {
            "type": "string",
            "description": "if findings is empty, one line on why staying silent is correct here",
        },
    },
}
