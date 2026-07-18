# The Longitudinal Reader

**A diagnostic agent whose only job is the time axis.**

Care happens in snapshots; disease happens over time. The signal that matters — the
slowly drifting lab, the symptom reattributed away by three clinicians, the
multi-system constellation that only closes over years — lives *between* the visits,
and no role in medicine is assigned to look there. This agent reads a patient's entire
multi-year record, every time, across every specialty silo, and surfaces **0–3
high-confidence longitudinal findings** — or, on most patients, stays **silent**.

> Care happens in snapshots; disease happens over time. We built the first agent whose
> only job is the axis nobody owns — and it knows when to stay silent.

See [`../../PLAN_LONGITUDINAL.md`](../../PLAN_LONGITUDINAL.md) for the full thesis.

---

## What it does

```
FHIR bundle / event-stream ─▶ [1] TIMELINE ASSEMBLY (deterministic)
                              [2] DECOMPOSITION  — 3 primitives + 1 Claude call
                              [3] EVIDENCE       — dated receipts per hypothesis
                              [4] RESTRAINT GATE — score, drop, cap at 3, or SILENCE
                              [5] OUTPUT         — cards + sparkline + silence panel
```

**Three deterministic primitives do the load-bearing work and keep the model honest.**
They compute the numbers the LLM is *not allowed to invent*:

| Primitive | File | Catches |
|---|---|---|
| **Slope detector** | `primitives/slope.py` | a lab drifting monotonically through/toward a reference bound (creatinine 0.9→1.5, each value "normal" at its visit) |
| **Recurrence counter** | `primitives/recurrence.py` | the same symptom across ≥3 encounters with ≥2 benign, differing attributions and no workup |
| **Constellation matcher** | `primitives/constellation.py` | partial matches to ~7 high-morbidity multi-system patterns (scleroderma, SLE, hemochromatosis, myeloma, CKD, …) |

The LLM does timeline interpretation, hypothesis generation, and the **restraint gate**.
A finding without a dated receipt is dropped.

---

## How the pipeline works, stage by stage

The whole run is `analyze(record)` in `agent/run.py`. Here is exactly what happens to
a patient, and why each step exists.

### Stage 1 — Timeline assembly (`load.py`, deterministic)

Input: either a **FHIR R4 bundle** (Synthea) or the **simplified event-stream JSON**
(heroes / cohort). Both are flattened into ONE contract — a `PatientRecord` holding a
list of dated, per-system-tagged `Event`s (`events.py`):

```
{"date":"2023-04-02","type":"lab","system":"renal","code":"creatinine",
 "value":1.2,"unit":"mg/dL","ref_low":0.6,"ref_high":1.1,"encounter_id":"e2023"}
```

From FHIR we pull Observations (labs → mapped to a normalized code slug + body system
via `LAB_MAP`), Conditions (onset dates), MedicationRequests, and Procedures. Reference
ranges come from the bundle, with coarse adult fallbacks in `REF_RANGES`. **Everything
downstream reads this event stream, never raw FHIR** — so every stage boundary is a
plain, inspectable JSON object.

### Stage 2 — Decomposition (`agent/decompose.py`)

Two things happen, primitives **before** the model:

**2a–2c. The three deterministic primitives run first** (pure Python, no LLM):

- **`slope.py`** — for each lab with ≥3 points: sort by date, compute the least-squares
  slope and count reversals. Flag only if the drift is near-monotone (≤1 reversal), the
  total change exceeds **50% of the reference-range width** (the meaningfulness gate),
  *and* the series is crossing or approaching a reference bound. Output includes the
  points, slope/year, and `crosses_ref`. This is the mechanically undeniable receipt.
- **`recurrence.py`** — normalize symptom text through a synonym map (fatigue/tired/
  exhaustion → `fatigue`), group across encounters, and flag if the same symptom appears
  in **≥3 encounters** with **≥2 distinct benign attributions** (stress, perimenopause,
  viral…) and no workup on record.
- **`constellation.py`** — build a bag of dated "features" from conditions, symptoms,
  and lab-status flags (e.g. `positive ana`, `rising creatinine` from the slope output),
  then match against ~7 hardcoded high-morbidity patterns. A pattern fires on a partial
  match (`min_hits`); it returns which elements are **present** and which are **missing**
  — the missing element is often the next step.

**2d. One Claude call** (`claude-opus-4-8`, adaptive thinking, `DECOMPOSE_SCHEMA`) then
receives the event stream **plus** the primitives' structured output. Its job: sanity-
check the mechanical flags in clinical context and add grounded free-text hypotheses.
The prompt (`prompts.py`) forbids inventing values and requires every hypothesis to cite
**specific dated events**. Output: a list of hypotheses, each with a mechanism, dated
`supporting_events`, which primitive backs it, and a candidate next step.

### Stage 3 — Evidence (`agent/evidence.py`, optional)

For the core POC this is a deterministic pass-through that attaches the raw events each
hypothesis references. It's the architectural slot where an optional PubMed/OMIM lookup
would go (clinician-as-user); deliberately off the default path to keep the demo grounded
in the chart.

### Stage 4 — Reconciliation + restraint gate (`agent/reconcile.py`)

**This is the product.** A second Claude call (`RECONCILE_SCHEMA`) scores each candidate:

```
score = severity (0–3)  ×  trajectory_strength (0–1)  ×  unaddressed (0–1)
```

It drops anything already worked up, benign, or incidental — logging each as a
`near_miss` with a reason so the **silence is auditable, not just absent** — and keeps at
most the 3 highest-scoring findings (cap enforced in code). If nothing clears the bar it
returns an **empty set** with a `silence_rationale`. On a typical patient, that empty set
is the correct output.

### Stage 5 — Output (`render.py`)

Each surfaced finding renders as a card: a clinician-readable headline, the scoring, the
**dated event chain (the receipt)**, an ASCII **sparkline** of the backing slope (the
"there's the line" moment), a candidate explanation, and one concrete next step. Across a
cohort it renders the **silence panel** (`N scanned · k flagged · N−k silent`) and a
self-contained `findings/cohort.html`.

### The data flow in one line

```
FHIR/JSON ─▶ PatientRecord ─▶ {slopes, recurrences, constellations} + event stream
          ─▶ [Claude] hypotheses ─▶ [Claude] scored findings (or silence) ─▶ cards + panel
```

Two Claude calls per patient; the numbers are always the primitives', never the model's.

---

## Quickstart

Uses [`uv`](https://docs.astral.sh/uv/). The Anthropic key is read from (in order)
`ANTHROPIC_API_KEY`, a local `.env`, or `../poc/.env`.

```bash
cd LongitudinalReader
uv venv --python 3.11
uv pip install -e .
source .venv/bin/activate

# 0. deterministic layer only — no API cost, proves the receipts
python -m longitudinal_reader primitives data/heroes/hero1_drifting_creatinine.json

# 1. the catch — full pipeline on a hero patient
python -m longitudinal_reader run data/heroes/hero1_drifting_creatinine.json --html

# 2. the silence — scan the whole cohort, write findings/cohort.html
python tools/gen_cohort.py 8          # benign stand-in cohort (reproducible)
python -m longitudinal_reader cohort
```

`longitudinal-reader` is also installed as a console script (same commands).

### The three hero patients (hand-authored, labeled test cases)

- **`hero1_drifting_creatinine`** — creatinine 0.9→1.5 over 4 years, in/near range each
  visit, never acted on. eGFR falls in lockstep. *The mechanically undeniable receipt —
  lead with this.*
- **`hero2_reattributed_fatigue`** — fatigue said 4× to 3 clinicians over 13 months
  (stress / perimenopause / viral / sleep) + an orphan low ferritin never followed up.
- **`hero3_assembling_constellation`** — Raynaud's → dysphagia → orphan +ANA → skin
  tightening = systemic sclerosis assembling over 3 years.

### The cohort (silence)

`tools/gen_cohort.py` generates a reproducible **benign** cohort (stable, in-range,
non-monotone labs) so the "runs silently across N, surfaces on few" story works today.
The **production substrate is Synthea** — the same simulator behind the Abridge
patients, which natively emits full longitudinal FHIR R4 bundles:

```bash
./scripts/gen_synthea.sh 30      # requires Java 11+; drops bundles in data/synthea/
python -m longitudinal_reader cohort
```

`load.py` parses real Synthea FHIR R4 bundles and the simplified event-stream JSON into
the same normalized contract — drop bundles in `data/synthea/` and they're picked up
automatically.

---

## Why this data, not the provided dataset

The provided Abridge set is **25 patients × 1 encounter each** — longitudinal depth
zero, structurally the wrong shape for this idea. We say so openly: *you gave us
cross-sections; we generate longitudinal records to show the axis the dataset omits.*
The **mechanical** catch — a creatinine climbing through the normal band — is real
regardless of who authored the row.

---

## Layout

```
LongitudinalReader/
  longitudinal_reader/
    load.py            # FHIR bundle / event-stream -> normalized event stream
    events.py          # the dated event-stream contract between stages
    primitives/        # slope.py · recurrence.py · constellation.py  (pure Python)
    agent/             # decompose.py · evidence.py · reconcile.py · run.py
    prompts.py         # versioned stage prompts
    schemas.py         # strict JSON schemas for the two LLM stages
    render.py          # finding cards + sparkline + silence panel + HTML
    cli.py             # run / cohort / primitives / health
  data/heroes/         # 3 hand-authored hero patients
  data/cohort/         # generated benign cohort (tools/gen_cohort.py)
  data/synthea/        # drop Synthea FHIR bundles here
  scripts/gen_synthea.sh
  findings/            # output json + html
```

## Model

`claude-opus-4-8` via the Anthropic Messages API, structured outputs + adaptive
thinking. Model-agnostic reasoning over a fixed substrate: every model release improves
trend sensitivity, constellation coverage, and restraint precision with zero pipeline
changes.
