# TrialGuard — Amendment Demo

A "second reader" for clinical-trial eligibility. When a trial **protocol is amended**,
patients who qualified yesterday may silently become ineligible — and the disqualifying
fact is often buried in the structured chart, never mentioned in the visit. A human
coordinator misses it. **TrialGuard re-reads the whole chart and catches it, with a citation.**

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
inclusion criteria**; each flip patient carries exactly **one buried disqualifying fact** that
never appears in the transcript/note — only in the structured chart.

| `--patient` | age | buried fact | aom_v1 | aom_v2 |
|---|---|---|---|---|
| `control`     | 42 | (none)                         | NEEDS_REVIEW | NEEDS_REVIEW |
| `glp1` ★hero  | 45 | semaglutide (GLP-1) from outside clinic | NEEDS_REVIEW | **EXCLUDE** |
| `depression`  | 37 | major depressive disorder on problem list | NEEDS_REVIEW | **EXCLUDE** |
| `hypokalemia` | 50 | serum potassium 3.0 mmol/L on outside labs | NEEDS_REVIEW | **EXCLUDE** |

> "Eligible" in this pipeline = **NEEDS_REVIEW** (informed consent is never in a chart, so it's
> always an open item — the system never silently passes). The demo flip is **NEEDS_REVIEW → EXCLUDE**.

## Setup

```bash
cd poc
# one-time: ../.venv already has anthropic + python-dotenv; poc/.env holds ANTHROPIC_API_KEY
../.venv/bin/python build_cohort.py      # (re)build the 4 patients
../.venv/bin/python generate_prose.py    # (re)fill transcripts/notes
```

## Demo commands (map to the 60-second beat sheet)

```bash
# 0-7s   list the cast
../.venv/bin/python demo.py --list

# 7-18s  show the hero's chart (buried semaglutide is in the med list, not the convo)
../.venv/bin/python demo.py --patient glp1 --protocol v1     # scroll the chart digest

# 18-28s ORIGINAL protocol -> passes pre-screen (green)
../.venv/bin/python demo.py --patient glp1 --protocol v1

# 28-33s the amendment
../.venv/bin/python demo.py --diff

# 33-48s AMENDED protocol -> flips to EXCLUDE, citing the buried fact (red)
../.venv/bin/python demo.py --patient glp1 --protocol v2

# 48-58s cohort montage: control holds, three flip for different reasons
for p in control glp1 depression hypokalemia; do
  ../.venv/bin/python demo.py --patient $p --compare
done

# closing beat: tangible ROI — coordinator time saved re-screening a site
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

**Money shot (strongest 10s):** split your terminal (tmux/iTerm), run `--protocol v1` on the
left and `--protocol v2` on the right for the *same* patient — green `NEEDS_REVIEW` beside red
`EXCLUDE` + citation.

## Recording tips

- Verdicts are ANSI-colored: green `NEEDS_REVIEW`, red `EXCLUDE`; the blocking line is bold red `▶`.
- Runs are cached in `.demo_cache/` so retakes are **instant and identical**. Use `--fresh` to
  recompute against the live API (slower; shows the model actually thinking).
- Bump terminal font to ~20pt; freeze ~2s on the cited `▶` line — that citation is the credibility.
- Lead with `glp1` (most topical — "they're on Ozempic from another clinic and never mentioned it").
  Use `hypokalemia` as the "buried lab" beat and `depression` in the cohort montage.

## How it works (pipeline)

`demo.py` → `patient_loader` (flatten chart) + `trial_client` (load protocol) →
`criteria_parser` (LLM: text → clauses) → `chart_reconciler` (LLM+thinking: clause vs full chart) →
`confidence_engine` (deterministic: any `violated` → EXCLUDE; else any `insufficient_data` →
NEEDS_REVIEW; else MATCH). The amendment changes only the trial fixture; the same chart flips.
