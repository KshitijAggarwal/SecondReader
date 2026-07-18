"""
STEP: API connectivity.

Thin wrapper around the Anthropic SDK. Owns the client and the model choice, and
exposes health_check() — the 'dummy query' that proves the API works before we
spend effort on the real pipeline.

The three agents (criteria_parser, chart_reconciler, confidence_engine) share
this one client instance. A subagent can later add retries, prompt caching
tuning, streaming, cost tracking, etc. here in one place.
"""

import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MODEL = "claude-opus-4-8"  # latest, most capable; guardrails need strong reasoning


class LLMClient:
    def __init__(self, model: str = MODEL):
        # Reads ANTHROPIC_API_KEY from the environment (loaded from poc/.env).
        self.client = anthropic.Anthropic()
        self.model = model

    def health_check(self) -> str:
        """Dummy query — confirms the API key and model are reachable."""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=64,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly: TRIALGUARD_OK",
                }
            ],
        )
        return next(b.text for b in resp.content if b.type == "text").strip()

    def structured(self, system: str, user: str, schema: dict, thinking: bool = False):
        """
        One structured-output call. Returns the parsed dict.

        thinking=True turns on adaptive extended thinking (used by the reconciler,
        where matching free-text clauses to indirect chart evidence is the hard part).
        """
        kwargs = dict(
            model=self.model,
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"]["effort"] = "high"
        resp = self.client.messages.create(**kwargs)
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)


if __name__ == "__main__":
    print(LLMClient().health_check())
