# SecondReader

**A pre-screen eligibility verification agent for clinical-trial referrals.**

SecondReader is a *second reader* for AI-generated trial-candidate flags. It sits
**downstream** of any system that flags "this patient looks like a candidate for
trial X" (e.g. an ambient-documentation tool) and independently re-checks that
flag against (a) the trial's eligibility criteria and (b) the patient's **full
structured chart** — not just what came up in the visit conversation. It returns
a per-clause, reason-coded verdict so a site coordinator doesn't spend days
manually reconciling false positives.

> It is **not** a trial search/matching engine. It doesn't hunt for trials for a
> patient. Given a `(patient, trial)` pair it answers: *is this flagged candidate
> actually eligible — and if not, exactly which clause disqualifies them, with a
> citation from the chart?*

## Why this matters

Industry data shows **40–60% of AI-flagged trial candidates get disqualified on
first pass** for reasons unrelated to clinical relevance:

1. **Stale protocol version** — screening against an out-of-date criteria set.
2. **Exclusion criteria that never came up in conversation** — e.g. a medication
   or resolved diagnosis that only exists in the structured chart.
3. **Incompletely captured diagnoses.**

SecondReader targets exactly those three failure modes by reasoning over the
whole chart, and by never making the final call itself.

### Hard product constraint

The system **never silently auto-excludes a patient.** Every output is one of
`MATCH`, `EXCLUDE`, or `NEEDS_REVIEW`:

- `EXCLUDE` requires a specific, citable clause violation.
- If a clause can't be resolved from the structured data, the verdict is
  `insufficient_data` → `NEEDS_REVIEW`, **never a guess**.

A human (coordinator / PI) makes the final decision. This guardrail is baked into
every agent's system prompt, not just documentation.

---

## What's in here (current status: working proof-of-concept)

This is a hacky-but-honest POC that runs the full pipeline for **one patient ×
one real trial**, end to end. Each step is a separate, independently-improvable
module — deliberately structured so the pieces can be hardened in parallel.

```
poc/
├── run_poc.py               # orchestrator — runs all 5 steps for ONE (patient, trial)
├── demo.py                  # amendment demo driver (verdicts, --diff, --compare, --savings)
├── walkthrough.py           # narrated, on-screen guided run of the amendment demo
├── DEMO.md                  # the amendment-demo beat sheet + recording tips
├── llm_client.py            # STEP 0: Anthropic client + health_check() (API smoke test)
├── patient_loader.py        # STEP 1: load ONE patient, flatten the FULL chart → digest
├── trial_client.py          # STEP 2: fetch/cache a trial from ClinicalTrials.gov
├── agents/
│   ├── criteria_parser.py   # STEP 3: eligibility free-text → structured, checkable clauses
│   ├── chart_reconciler.py  # STEP 4: clauses × full chart → per-clause verdicts  ← core reasoning
│   └── confidence_engine.py # STEP 5: verdicts → MATCH / EXCLUDE / NEEDS_REVIEW  (deterministic)
├── trials/trial_v1.json           # cached real trial fixture (NCT06921902, prediabetes)
├── trials/trial_aom_v1.json       # NCT07163650 — ORIGINAL protocol (inclusion only)
├── trials/trial_aom_v2.json       # NCT07163650 — AMENDED protocol (adds exclusions)
├── build_cohort.py          # (re)build the 4-patient synthetic amendment cohort
├── generate_prose.py        # (re)fill the cohort transcripts/notes
├── data/                    # bundled synthetic FHIR dataset + trial_cohort.jsonl
└── requirements.txt
```

### The pipeline

```
                 ┌─────────────────────────────────────────────────────────┐
   patient ─────▶│ STEP 1  patient_loader   → full structured chart digest  │
                 └─────────────────────────────────────────────────────────┘
                 ┌─────────────────────────────────────────────────────────┐
   trial ───────▶│ STEP 2  trial_client     → eligibility criteria (CT.gov) │
                 └─────────────────────────────────────────────────────────┘
                              │                         │
                              ▼                         ▼
   STEP 3  criteria_parser  ──────▶  structured clauses (inclusion/exclusion, checks)
                              │
                              ▼
   STEP 4  chart_reconciler ──────▶  per-clause verdict: satisfied / violated /
             (extended thinking)     insufficient_data + evidence citation
                              │
                              ▼
   STEP 5  confidence_engine ─────▶  MATCH / EXCLUDE / NEEDS_REVIEW + reasoning trail
             (deterministic, no LLM)
```

This maps 1:1 onto the intended production architecture — **Criteria Parser →
Chart Reconciler → Confidence Engine** — so the POC modules are the seeds of the
real agents.

### Design choices worth knowing

- **The Chart Reconciler reads the entire structured record**, not just facts
  related to the visit. That's the whole reason SecondReader exists — if it only
  reasoned over the transcript, it would rebuild what upstream tools already do.
- **Extended thinking** is on only for the reconciler (the one genuinely hard
  step: matching free-text clause intent to indirect chart evidence). Parsing and
  aggregation don't need it.
- **The Confidence Engine is deterministic Python, no model call** — cheap, and
  easy to defend under questioning.
- Uses the Anthropic Python SDK with `claude-opus-4-8` and structured outputs
  (JSON-schema-constrained responses).

---

## Headline demo: the protocol amendment (v1 → v2)

When a trial **protocol is amended**, patients who qualified yesterday can
silently become ineligible — and the disqualifying fact is often buried in the
structured chart, never mentioned in the visit. This is the demo that shows
SecondReader earning its keep.

Trial: [NCT07163650](https://clinicaltrials.gov/study/NCT07163650) — *"Evaluating
Anti-Obesity Medications 6 Months After Metabolic Surgery,"* which has a **real
recorded eligibility amendment** (`aom_v1` → `aom_v2`, a large new exclusion list).

The cohort is four synthetic patients who all meet inclusion. Each flip patient
carries exactly **one buried disqualifying fact** that appears only in the
structured chart:

| `--patient` | age | buried fact | `aom_v1` | `aom_v2` |
|---|---|---|---|---|
| `control`     | 42 | (none)                                | NEEDS_REVIEW | NEEDS_REVIEW |
| `glp1` ★hero  | 45 | semaglutide (GLP-1) from an outside clinic | NEEDS_REVIEW | **EXCLUDE** |
| `depression`  | 37 | major depressive disorder on problem list | NEEDS_REVIEW | **EXCLUDE** |
| `hypokalemia` | 50 | serum potassium 3.0 mmol/L on outside labs | NEEDS_REVIEW | **EXCLUDE** |

The money shot: the **same** patient flips `NEEDS_REVIEW → EXCLUDE` when only the
protocol changes — citing the exact chart fact (e.g. *"Medication list includes
Semaglutide 1 MG/0.75 ML Injection, a GLP-1 receptor agonist."*).

```bash
cd poc

# narrated, on-screen guided run (each beat explains itself, then runs)
../.venv/bin/python walkthrough.py            # Enter between beats
../.venv/bin/python walkthrough.py --auto      # straight through

# or drive it by hand
../.venv/bin/python demo.py --list
../.venv/bin/python demo.py --patient glp1 --compare   # v1 vs v2, stacked
../.venv/bin/python demo.py --diff                      # the amendment diff
../.venv/bin/python demo.py --savings --patients 25     # coordinator time saved
```

Verdicts are cached under `poc/.demo_cache/` so runs are instant and identical;
pass `--fresh` to recompute against the live API. Full beat sheet in
[`poc/DEMO.md`](poc/DEMO.md).

---

## Original demo: the reasoning that makes it worth building

Patient: 22-year-old with **prediabetes** (HbA1c 6.24%, BMI 31.4).
Trial: [NCT06921902](https://clinicaltrials.gov/study/NCT06921902), a real
recruiting prediabetes study.

The reconciler reasons over **structured chart facts that never surfaced as
trial-relevant**:

| Clause (exclusion) | Verdict | Why |
|---|---|---|
| Diagnosis of type 1/2 or gestational diabetes | **satisfied** (not excluded) | Distinguished *pre*diabetes from diabetes using the conditions list |
| On any diabetes treatment | **satisfied** | Read the full med list (cetirizine + epinephrine auto-injector) → none present |
| On any weight-loss medication | **satisfied** | Same med list → none present |
| Known allergy to adhesive / alcohol | **insufficient_data** | No allergy list documented — flagged, not guessed |
| Currently pregnant | **insufficient_data** | Chart is silent — flagged, not guessed |

**Overall verdict: `NEEDS_REVIEW`** — because consent, diet, pregnancy, and
allergy status are genuinely undocumented. That's the guardrail working: it
surfaces exactly what a human must confirm instead of silently passing or
failing the patient.

---

## Running it

**Requirements:** Python 3.9+ and an Anthropic API key.

```bash
# from the repo root
pip install -r poc/requirements.txt

cp poc/.env.example poc/.env        # then edit poc/.env and add your ANTHROPIC_API_KEY

cd poc
python3 run_poc.py                  # full pipeline, all 5 steps, printed output
```

`run_poc.py` makes 3 real API calls (health check + criteria parse + chart
reconcile), takes ~20–40s, and costs a few cents.

Each step also runs standalone (the data steps need no API key or network):

```bash
python3 llm_client.py       # STEP 0 only — prints TRIALGUARD_OK if the API is reachable
python3 patient_loader.py   # STEP 1 only — prints the patient's full chart digest
python3 trial_client.py     # STEP 2 only — prints the cached trial criteria
```

To pull a fresh trial from ClinicalTrials.gov (re-saves `trials/trial_v1.json`):

```bash
python3 -c "import trial_client; trial_client.fetch_trial('NCT06921902')"
```

### Data

The synthetic FHIR dataset (25 fully synthetic ambient encounters) is bundled
under `poc/data/`. Point elsewhere with `SECONDREADER_DATA=/path/to.jsonl`.

---

## What makes sense to build next

The POC proves the pipeline. The value comes from breadth and rigor, not a change
of direction. Roughly in priority order:

1. **Many patients × one trial → a ranked shortlist.**
   Loop the existing pipeline over all 25 patients and emit the reason-coded,
   ranked shortlist a coordinator would actually use. *This is the deliverable
   that best shows the product value* (kill the false positives, keep the
   real candidates).

2. ~~**The "stale protocol version" demo (v1 vs v2).**~~ **✅ Shipped** — see the
   headline amendment demo above (`trials/trial_aom_v1.json` → `trial_aom_v2.json`,
   NCT07163650, with a `simulated_amendment_date`). The same patient flips
   `NEEDS_REVIEW → EXCLUDE` when only the protocol changes, with a cited chart fact.
   (No live amendment-history feed — the two-version fixture is the honest stand-in.)

3. **Harden the core Chart Reconciler.**
   Prompt caching on the chart block (same patient is re-checked against every
   clause), few-shot evidence examples, tighter handling of lab thresholds and
   temporal logic, and validation that every cited fact actually exists in the chart.

4. **Robustness across the full dataset.**
   Make `patient_loader` handle all 25 records cleanly (missing fields, multiple
   resource types, longitudinal history).

5. **Eval harness.**
   Hand-label a handful of golden `(patient, trial)` cases, synthesize adversarial
   ones with the API, score the pipeline's agreement rate, and track a before/after
   number as prompts improve. This is what turns "it runs" into "it's accurate."

6. **Thin API + demo UI.**
   One endpoint that takes `(patient_id, trial_version)` and returns the full
   trace (all intermediate outputs, not just the final verdict); a single-page UI
   that renders the stages left-to-right with the reasoning trail and a distinct
   visual state for `NEEDS_REVIEW`.

### Explicitly out of scope (by design)

No IRB/consent workflow, no scheduling/site-capacity logic, no live
ClinicalTrials.gov amendment-history feed, no auth/multi-tenant concerns. These
are real parts of the problem but not what this prototype is proving.

---

## Data & honesty notes

- All patient data is **fully synthetic** (Synthea-generated FHIR R4).
- The trial criteria are **real**, pulled from the public ClinicalTrials.gov API,
  but pinned to a **cached fixture version** — the demo checks against fixtures
  and says so plainly; it does not claim to verify "live" or "current" protocol data.
