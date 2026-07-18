"""
TrialGuard POC orchestrator — wires the functionally-separate steps together.

Pipeline:
  0. health_check        (llm_client)      -- dummy query, prove the API works
  1. load patient chart  (patient_loader)  -- the chart side
  2. load trial criteria (trial_client)    -- the trial side (cached from CT.gov)
  3. parse criteria      (agents.criteria_parser)   -> structured clauses
  4. reconcile chart     (agents.chart_reconciler)  -> per-clause verdicts
  5. decide              (agents.confidence_engine) -> MATCH/EXCLUDE/NEEDS_REVIEW

Each step is intentionally its own module/class so it can be handed to a
subagent later and hardened independently.
"""

import json
import sys

from llm_client import LLMClient
import patient_loader
import trial_client
from agents import criteria_parser, chart_reconciler, confidence_engine


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    llm = LLMClient()

    section("STEP 0 — API health check (dummy query)")
    ok = llm.health_check()
    print(f"  model={llm.model}  ->  {ok}")
    if "OK" not in ok:
        print("  API did not respond as expected; aborting.")
        sys.exit(1)

    section("STEP 1 — Load ONE patient's full structured chart")
    record = patient_loader.load_record()
    chart = patient_loader.extract_chart(record)
    chart_text = patient_loader.chart_to_text(chart)
    print(chart_text)

    section("STEP 2 — Load trial eligibility criteria (cached from ClinicalTrials.gov)")
    trial = trial_client.load_trial("v1")
    trial_text = trial_client.trial_to_text(trial)
    print(trial_text)

    section("STEP 3 — Criteria Parser: eligibility text -> structured clauses")
    clauses = criteria_parser.parse_criteria(llm, trial, trial_text)
    print(json.dumps(clauses, indent=2))

    section("STEP 4 — Chart Reconciler: check every clause vs the FULL chart")
    reconciliation = chart_reconciler.reconcile_chart(llm, clauses, chart_text)
    print(json.dumps(reconciliation, indent=2))

    section("STEP 5 — Confidence Engine: aggregate verdict + reasoning trail")
    result = confidence_engine.decide(clauses, reconciliation, trial["version"])
    print(f"\n  OVERALL: {result['overall']}")
    print(f"  Protocol version checked: {result['protocol_version_checked']}")
    print("  Reasoning trail:")
    for line in result["reasoning_trail"]:
        print(f"    - {line}")

    section("DONE — pipeline ran end to end")


if __name__ == "__main__":
    main()
