"""The four-stage engine. Each stage is one Claude call, then a code-side validation
pass, then an audit-log write. Stages pass structured JSON between each other.
"""

from __future__ import annotations

from typing import Any

from . import prompts, schemas, validate
from .audit import AuditLog
from .llm import call_json
from .loaders import Encounter


def _base_context(enc: Encounter) -> str:
    return (
        f"PATIENT CONTEXT (for your understanding only, do not quote as visit facts):\n"
        f"{enc.patient_summary}\n\n"
        f"VISIT: {enc.visit_title}\n\n"
        f"TRANSCRIPT (line_id | speaker | text):\n{enc.transcript_for_prompt()}\n"
    )


# ---- Stage 1 -----------------------------------------------------------------
def ground(enc: Encounter, log: AuditLog) -> dict[str, Any]:
    out = call_json(
        system=prompts.GROUND,
        user=_base_context(enc) + "\nExtract the four grounded lists now.",
        schema=schemas.GROUND,
        effort="high",
    )
    ents, ent_drops = validate.check_grounded(out.get("entities", []), enc)
    instr, instr_drops = validate.check_grounded(out.get("instructions", []), enc)
    rp, rp_drops = validate.check_grounded(out.get("return_precautions", []), enc)
    pr, pr_drops = validate.check_grounded(out.get("patient_raised", []), enc)
    cleaned = {"entities": ents, "instructions": instr, "return_precautions": rp, "patient_raised": pr}
    log.record(
        "1_ground",
        raw=out,
        kept=cleaned,
        drops={"entities": ent_drops, "instructions": instr_drops,
               "return_precautions": rp_drops, "patient_raised": pr_drops},
    )
    return cleaned


def _stage1_json(g: dict[str, Any]) -> str:
    import json
    return "STAGE 1 GROUNDED ITEMS:\n" + json.dumps(g, ensure_ascii=False, indent=1)


def _entity_terms(g: dict[str, Any]) -> set[str]:
    return {e["term"] for e in g.get("entities", [])}


# ---- Stage 2: reconstruction -------------------------------------------------
def reconstruct(enc: Encounter, g: dict[str, Any], log: AuditLog) -> dict[str, Any]:
    out = call_json(
        system=prompts.CLARIFY_RECON,
        user=_base_context(enc) + "\n" + _stage1_json(g) + "\nBuild the two-channel reconstruction now.",
        schema=schemas.CLARIFY_RECON,
    )
    said, said_drops = validate.check_grounded(out.get("doctor_said", []), enc)
    gi, gi_drops = validate.check_general_info(out.get("general_info", []), enc, _entity_terms(g))
    cleaned = {"greeting": out.get("greeting", ""), "doctor_said": said, "general_info": gi}
    log.record("2_reconstruct", raw=out, kept=cleaned, drops={"doctor_said": said_drops, "general_info": gi_drops})
    return cleaned


# ---- Stage 2: grounded QA ----------------------------------------------------
def answer(enc: Encounter, g: dict[str, Any], question: str, log: AuditLog) -> dict[str, Any]:
    out = call_json(
        system=prompts.CLARIFY_QA,
        user=_base_context(enc) + "\n" + _stage1_json(g) + f"\nPATIENT QUESTION: {question}\nAnswer now.",
        schema=schemas.CLARIFY_QA,
    )
    if out.get("in_scope"):
        said, said_drops = validate.check_grounded(out.get("doctor_said", []), enc)
        gi, gi_drops = validate.check_general_info(out.get("general_info", []), enc, _entity_terms(g))
        cleaned = {"in_scope": True, "refusal": "", "doctor_said": said, "general_info": gi}
        drops = {"doctor_said": said_drops, "general_info": gi_drops}
    else:
        cleaned = {"in_scope": False, "refusal": out.get("refusal", ""), "doctor_said": [], "general_info": []}
        drops = {}
    log.record("2_qa", question=question, raw=out, kept=cleaned, drops=drops)
    return cleaned


# ---- Stage 3: SURFACE --------------------------------------------------------
def surface(enc: Encounter, g: dict[str, Any], log: AuditLog) -> dict[str, Any]:
    user = (
        _base_context(enc)
        + "\n" + _stage1_json(g)
        + f"\nCLINICIAN NOTE (Assessment & Plan is what to diff against):\n{enc.note}\n"
        + "\nFind patient-raised concerns NOT addressed in the note's plan. Return empty if none."
    )
    out = call_json(system=prompts.SURFACE, user=user, schema=schemas.SURFACE, effort="high")
    items, drops = validate.check_grounded(out.get("items", []), enc)
    items = sorted(items, key=lambda x: x.get("rank", 99))[:3]
    cleaned = {"items": items}
    log.record("3_surface", raw=out, kept=cleaned, drops=drops)
    return cleaned


# ---- Stage 4: TEACH-BACK -----------------------------------------------------
def teachback_select(enc: Encounter, g: dict[str, Any], log: AuditLog) -> dict[str, Any]:
    out = call_json(
        system=prompts.TEACHBACK_SELECT,
        user=_base_context(enc) + "\n" + _stage1_json(g) + "\nSelect the single highest-stakes instruction now.",
        schema=schemas.TEACHBACK_SELECT,
        effort="high",
    )
    if out.get("found") and enc.turn(out.get("line_id", "")) is not None:
        kept, drops = validate.check_grounded([out], enc)
        found = bool(kept)
    else:
        found, drops = False, [{"item": out, "reason": "no grounded high-stakes instruction"}]
    cleaned = out if found else {**out, "found": False}
    log.record("4_teachback_select", raw=out, kept=cleaned if found else None, drops=drops)
    return cleaned


def teachback_check(enc: Encounter, selected: dict[str, Any], restatement: str, log: AuditLog) -> dict[str, Any]:
    user = (
        _base_context(enc)
        + f"\nTHE INSTRUCTION (answer key, from the transcript): "
        f"[{selected['line_id']}] \"{selected['quote']}\"\n"
        + f"\nPATIENT RESTATEMENT: {restatement}\n\nCheck it now."
    )
    out = call_json(system=prompts.TEACHBACK_CHECK, user=user, schema=schemas.TEACHBACK_CHECK)
    # keep the correct quote grounded; fall back to the selected instruction's quote
    if enc.turn(out.get("line_id", "")) is None:
        out["line_id"] = selected["line_id"]
        out["correct_quote"] = selected["quote"]
    log.record("4_teachback_check", restatement=restatement, raw=out, kept=out, drops=None)
    return out
