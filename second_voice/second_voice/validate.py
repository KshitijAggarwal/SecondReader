"""The grounding-contract enforcer — the final validation pass.

The model is instructed to ground every claim, but we do not trust that; we verify
it. Any visit-specific claim whose line_id is not in the transcript, or whose quote
is not actually present on the cited line, is DROPPED here. This is the code-side
half of the two independent lines of defense (the prompt is the other half).

Returns (kept_items, drops) so the CLI shows only clean output and the audit log
records exactly what was removed and why.
"""

from __future__ import annotations

import re
from typing import Any

from .loaders import Encounter

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> list[str]:
    return _WORD.findall(s.lower())


def _quote_supported(quote: str, turn_text: str) -> bool:
    """A quote is verbatim-enough if it is (nearly) a substring of the cited line."""
    q, t = " ".join(_tokens(quote)), " ".join(_tokens(turn_text))
    if not q:
        return False
    if q in t or t in q:
        return True
    # allow minor transcription drift: most quote tokens appear on the line
    qt = set(_tokens(quote))
    tt = set(_tokens(turn_text))
    if not qt:
        return False
    return len(qt & tt) / len(qt) >= 0.6


def check_grounded(
    items: list[dict[str, Any]], enc: Encounter, *, quote_key: str = "quote", line_key: str = "line_id"
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept, drops = [], []
    for it in items:
        line_id = it.get(line_key, "")
        turn = enc.turn(line_id)
        if turn is None:
            drops.append({"item": it, "reason": f"line_id {line_id!r} not in transcript"})
            continue
        if not _quote_supported(it.get(quote_key, ""), turn.text):
            drops.append({"item": it, "reason": f"quote not verbatim on {line_id}"})
            continue
        kept.append(it)
    return kept, drops


def check_general_info(
    defs: list[dict[str, Any]], enc: Encounter, entity_terms: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """General-education defs must reference a term the doctor actually named."""
    kept, drops = [], []
    terms_lc = {t.lower() for t in entity_terms}
    for d in defs:
        line_id = d.get("grounded_line_id", "")
        if enc.turn(line_id) is None:
            drops.append({"item": d, "reason": f"grounded_line_id {line_id!r} not in transcript"})
            continue
        term = d.get("term", "").lower()
        if term and not any(term in e or e in term for e in terms_lc):
            drops.append({"item": d, "reason": f"term {d.get('term')!r} not named in this visit"})
            continue
        kept.append(d)
    return kept, drops
