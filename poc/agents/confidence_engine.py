"""
AGENT 3 — Confidence Engine.

Per-clause verdicts -> overall MATCH / EXCLUDE / NEEDS_REVIEW with a reasoning trail.

Deterministic, no model call — cheap and easy to defend under questioning.

Verdict semantics (as produced by the reconciler):
  satisfied          = this clause is fine for enrollment
  violated           = this clause BLOCKS enrollment
                       (a tripped exclusion, or a failed inclusion)
  insufficient_data  = chart is silent; we cannot tell

Aggregation rules (TrialGuard hard constraints):
  - Any 'violated' clause  -> EXCLUDE, and it must carry a clause-level citation.
  - Else any 'insufficient_data' -> NEEDS_REVIEW (never a silent pass).
  - Else (all satisfied)   -> MATCH.
The system never silently auto-excludes; a human makes the final call.
"""


def decide(clauses: dict, reconciliation: dict, protocol_version: str) -> dict:
    by_id = {c["id"]: c for c in clauses["clauses"]}
    verdicts = reconciliation["verdicts"]

    blocking = [v for v in verdicts if v["verdict"] == "violated"]
    unknown = [v for v in verdicts if v["verdict"] == "insufficient_data"]

    if blocking:
        overall = "EXCLUDE"
    elif unknown:
        overall = "NEEDS_REVIEW"
    else:
        overall = "MATCH"

    # Reasoning trail: blocking clauses first (they drove the decision), then
    # unknowns, then satisfied.
    order = {"violated": 0, "insufficient_data": 1, "satisfied": 2}
    trail = []
    for v in sorted(verdicts, key=lambda x: order.get(x["verdict"], 3)):
        c = by_id.get(v["clause_id"], {})
        desc = c.get("description", v["clause_id"])
        cite = v.get("evidence", {}).get("resource_summary", "")
        line = f"[{v['verdict']}] ({c.get('polarity','?')}) {desc}"
        if cite:
            line += f"  <- {cite}"
        trail.append(line)

    return {
        "overall": overall,
        "reasoning_trail": trail,
        "protocol_version_checked": protocol_version,
        "blocking_clause_ids": [v["clause_id"] for v in blocking],
        "needs_review_clause_ids": [v["clause_id"] for v in unknown],
    }
