"""JSON Schemas for each stage's structured output.

Structured outputs require additionalProperties:false and every property listed in
`required`. We keep the schemas flat and constraint-free (no minLength/maxItems), per
the API's structured-output limitations.
"""


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


_S = {"type": "string"}
_INT = {"type": "integer"}


# ---- Stage 1: GROUND ----------------------------------------------------------
_ENTITY = _obj(
    {
        "term": _S,
        "type": {"type": "string", "enum": ["drug", "test", "procedure", "diagnosis", "term"]},
        "quote": _S,
        "line_id": _S,
    },
    ["term", "type", "quote", "line_id"],
)
_ITEM = _obj({"text": _S, "quote": _S, "line_id": _S}, ["text", "quote", "line_id"])

GROUND = _obj(
    {
        "entities": {"type": "array", "items": _ENTITY},
        "instructions": {"type": "array", "items": _ITEM},
        "return_precautions": {"type": "array", "items": _ITEM},
        "patient_raised": {"type": "array", "items": _ITEM},
    },
    ["entities", "instructions", "return_precautions", "patient_raised"],
)


# ---- Stage 2: CLARIFY (reconstruction) ---------------------------------------
_RECON_POINT = _obj(
    {"plain": _S, "quote": _S, "line_id": _S},
    ["plain", "quote", "line_id"],
)
_GENERAL_DEF = _obj(
    {"term": _S, "definition": _S, "grounded_line_id": _S},
    ["term", "definition", "grounded_line_id"],
)
CLARIFY_RECON = _obj(
    {
        "greeting": _S,
        "doctor_said": {"type": "array", "items": _RECON_POINT},
        "general_info": {"type": "array", "items": _GENERAL_DEF},
    },
    ["greeting", "doctor_said", "general_info"],
)


# ---- Stage 2: CLARIFY (grounded QA) ------------------------------------------
CLARIFY_QA = _obj(
    {
        "in_scope": {"type": "boolean"},
        "refusal": _S,  # non-empty only when in_scope is false
        "doctor_said": {"type": "array", "items": _RECON_POINT},
        "general_info": {"type": "array", "items": _GENERAL_DEF},
    },
    ["in_scope", "refusal", "doctor_said", "general_info"],
)


# ---- Stage 3: SURFACE (unasked-question nudge) -------------------------------
_NUDGE = _obj(
    {"quote": _S, "line_id": _S, "nudge": _S, "rank": _INT},
    ["quote", "line_id", "nudge", "rank"],
)
SURFACE = _obj({"items": {"type": "array", "items": _NUDGE}}, ["items"])


# ---- Stage 4: TEACH-BACK -----------------------------------------------------
TEACHBACK_SELECT = _obj(
    {
        "found": {"type": "boolean"},
        "category": {
            "type": "string",
            "enum": ["return_precaution", "med_change", "follow_up", "none"],
        },
        "instruction_text": _S,
        "quote": _S,
        "line_id": _S,
        "prompt": _S,  # warm, non-interrogating invitation for the patient to restate
    },
    ["found", "category", "instruction_text", "quote", "line_id", "prompt"],
)
TEACHBACK_CHECK = _obj(
    {
        "verdict": {"type": "string", "enum": ["match", "partial", "off"]},
        "response": _S,          # warm confirmation or gentle re-surfacing
        "correct_quote": _S,
        "line_id": _S,
    },
    ["verdict", "response", "correct_quote", "line_id"],
)
