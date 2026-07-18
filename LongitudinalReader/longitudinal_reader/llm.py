"""Thin wrapper around the Anthropic Messages API for structured, auditable stage calls.

Each LLM stage is ONE Claude call (claude-opus-4-8) returning schema-validated JSON,
with adaptive extended thinking so the model reasons over the long, messy timeline
before committing. Matches the pattern used elsewhere in SecondReader.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

MODEL = "claude-opus-4-8"  # latest, most capable; restraint over long context needs it

# The key lives in SecondReader/poc/.env for this hackathon; also honor a local
# .env or a real environment variable. We search up from this file so it works
# from a git worktree too.
_HERE = Path(__file__).resolve()
_CANDIDATE_ENVS = [
    _HERE.parent.parent / ".env",                      # LongitudinalReader/.env
    _HERE.parent.parent.parent / "poc" / ".env",       # SecondReader/poc/.env (sibling)
    _HERE.parent.parent.parent.parent / "poc" / ".env",  # from a nested worktree layout
]


def _load_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    for env_path in _CANDIDATE_ENVS:
        if env_path.exists():
            load_dotenv(env_path)
            if os.environ.get("ANTHROPIC_API_KEY"):
                return


_load_key()
_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY not found. Put it in LongitudinalReader/.env, "
                "SecondReader/poc/.env, or export it."
            )
        _client = anthropic.Anthropic()
    return _client


def call_json(
    *,
    system: str,
    user: str,
    schema: dict[str, Any],
    effort: str = "high",
    max_tokens: int = 16000,
) -> dict[str, Any]:
    """Run one grounded stage. Returns the parsed, schema-valid JSON object."""
    resp = client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError(f"No text block in response (stop_reason={resp.stop_reason}).")
    return json.loads(text)


def health_check() -> str:
    resp = client().messages.create(
        model=MODEL,
        max_tokens=32,
        messages=[{"role": "user", "content": "Reply with exactly: LONGITUDINAL_OK"}],
    )
    return next(b.text for b in resp.content if b.type == "text").strip()


if __name__ == "__main__":
    print(health_check())
