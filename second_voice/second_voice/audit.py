"""Append-only audit log. Every model output is written here with its grounding
(quotes + line_ids) and any validation drops, so the whole run can be audited for
ungrounded output after the fact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
LOG_DIR = _HERE.parent.parent / "logs"


class AuditLog:
    def __init__(self, encounter_id: str):
        LOG_DIR.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe = encounter_id.replace(":", "_").replace("/", "_")
        self.path = LOG_DIR / f"{safe}_{stamp}.jsonl"

    def record(self, stage: str, *, raw: object = None, kept: object = None, drops: object = None, **extra) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "raw": raw,
            "kept": kept,
            "drops": drops,
            **extra,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
