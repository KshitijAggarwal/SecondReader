# TrialGuard — Amendment Demo

A second reader for clinical-trial eligibility. When a trial **protocol is amended**, patients
who qualified yesterday can quietly become ineligible, and the disqualifying fact is often buried
in the structured chart where it never comes up in the visit. A coordinator reading the note
misses it. **TrialGuard flags the patient and shows the chart fact behind the call, so reviewers
confirm a short list instead of re-reading every chart.**

> 10-second intro (spoken): *"When a protocol gets amended, patients who qualified yesterday can
> quietly become ineligible. TrialGuard flags them and shows the chart fact behind each call, so
> reviewers just confirm a short list instead of re-reading every chart."*

## The trial (real, from ClinicalTrials.gov)

**NCT07163650 — "Evaluating Anti-Obesity Medications 6 Months After Metabolic Surgery."**
It has a genuine recorded eligibility amendment:

| Version | Posted | Eligibility |
|---|---|---|
| `aom_v1` (original) | 2025-09-01 | Inclusion only: 6 mo post metabolic surgery, age 18–55, BMI ≥ 28. **No exclusions.** |
| `aom_v2` (amended)  | 2026-01-25 | Same inclusion **+ a large new exclusion list**: GLP-1 agonists, weight-loss meds, depression/psychiatric history, malignancy, cardiac disease, **hypokalemia**, HIV/hepatitis, … |

Fixtures: `trials/trial_aom_v1.json`, `trials/trial_aom_v2.json`.

## The cohort (synthetic, dataset-style)

Four patients in `data/trial_cohort.jsonl`, built by `build_cohort.py`. Each **meets all
inclusion criteria**. Three of them have one disqualifying fact in the structured chart that
the amended protocol now excludes on.

In the walkthrough the audience sees them only as **Patient 1–4**; the disqualifying fact is
never used as a label, it just shows up as the cited reason when the patient is flagged. The
`--patient` id below is the internal handle the presenter uses on the command line.

| shown as | `--patient` (internal) | age | disqualifying fact | aom_v1 | aom_v2 |
|---|---|---|---|---|---|
| Patient 1 | `control`     | 42 | (none)                                     | NEEDS_REVIEW | NEEDS_REVIEW |
| Patient 2 | `glp1`        | 45 | semaglutide (a GLP-1) from an outside clinic | NEEDS_REVIEW | **EXCLUDE** |
| Patient 3 | `depression`  | 37 | major depressive disorder on problem list    | NEEDS_REVIEW | **EXCLUDE** |
| Patient 4 | `hypokalemia` | 50 | serum potassium 3.0 mmol/L on outside labs   | NEEDS_REVIEW | **EXCLUDE** |

> "Eligible" in this pipeline = **NEEDS_REVIEW** (informed consent is never in a chart, so it's
> always an open item — the system never silently passes). The flip shown is **NEEDS_REVIEW → EXCLUDE**.

## Setup

```bash
cd poc
# one-time: ../.venv already has anthropic + python-dotenv; poc/.env holds ANTHROPIC_API_KEY
../.venv/bin/python build_cohort.py      # (re)build the 4 patients
../.venv/bin/python generate_prose.py    # (re)fill transcripts/notes
```

## Running the demo

The whole flow is narrated on screen by `walkthrough.py` — meet the patients, the trial
amends its criteria, re-screen everyone and see who now fails (and why), what it saves:

```bash
../.venv/bin/python walkthrough.py          # step through, press Enter per beat
../.venv/bin/python walkthrough.py --auto    # run straight through
```

To drive the same beats by hand:

```bash
# 1. Meet the patients (Patient 1–4, all currently eligible)
../.venv/bin/python demo.py --list

# 2. The trial amends its criteria
../.venv/bin/python demo.py --diff

# 3. Re-screen everyone against the amended protocol; who flips, and why.
#    --compare stacks v1 (green NEEDS_REVIEW) above v2 (red EXCLUDE + cited fact);
#    --label anonymizes the verdict header to "Patient N".
i=1; for p in control glp1 depression hypokalemia; do
  ../.venv/bin/python demo.py --patient $p --compare --label "Patient $i"
  i=$((i+1))
done

# 4. Conclude: coordinator time saved re-screening a site
../.venv/bin/python demo.py --savings --patients 25
```

### Coordinator time-saved card (`--savings`)

Quantifies the payoff of automated re-screening after an amendment. TrialGuard's
per-patient time is **measured** (~57s, `claude-opus-4-8` + extended thinking);
the manual baseline is a **labeled assumption** (~20 min/patient, override with
`--manual-min` / `--guard-sec`; site size via `--patients`).

```bash
../.venv/bin/python demo.py --savings --patients 120 --manual-min 20
```

**Strongest 10s:** the moment a patient's verdict flips from green `NEEDS_REVIEW` to red
`EXCLUDE` on the amended protocol, with the cited chart fact right beneath it. `--compare`
puts both verdicts on screen at once; freeze on the red `▶` line.

## Recording tips

- Verdicts are ANSI-colored: green `NEEDS_REVIEW`, red `EXCLUDE`; the blocking line is bold red `▶`.
- Runs are cached in `.demo_cache/` so retakes are **instant and identical**. Use `--fresh` to
  recompute against the live API (slower; shows the model actually thinking).
- Bump terminal font to ~20pt; freeze ~2s on the cited `▶` line — that citation is the credibility.
- Three patients flip for three different reasons (a GLP-1, depression, a low potassium lab), so
  the re-screening beat shows breadth, not one lucky catch. Patient 1 holding steady is the control.

## How it works (pipeline)

`demo.py` → `patient_loader` (flatten chart) + `trial_client` (load protocol) →
`criteria_parser` (LLM: text → clauses) → `chart_reconciler` (LLM+thinking: clause vs full chart) →
`confidence_engine` (deterministic: any `violated` → EXCLUDE; else any `insufficient_data` →
NEEDS_REVIEW; else MATCH). The amendment changes only the trial fixture; the same chart flips.
