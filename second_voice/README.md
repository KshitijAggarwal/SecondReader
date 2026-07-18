# Second Voice

**A patient-facing, transcript-grounded visit companion (CLI proof-of-concept).**

A patient just had a doctor's visit. An ambient scribe captured the conversation.
A few hours later the patient opens Second Voice. Its entire job is to make the
advice the doctor **already gave** actually land — it never generates new medical
advice, diagnoses, or predictions.

> This is **not** a medical-advice tool and **not** a general chatbot. Everything it
> says traces to (a) a verbatim transcript quote + line_id, (b) a clearly-labeled
> general-education definition of a term the doctor named, or (c) the patient's own
> words reflected back. No quote + line_id → it doesn't exist.

Built for the Abridge + Anthropic hackathon. Runs on `claude-opus-4-8` via the
Anthropic API.

---

## The engine: four stages, four separate Claude calls

The engine is deliberately **not** one mega-prompt. Each stage is an independent
`claude-opus-4-8` call with structured JSON in and out, so every stage is auditable
and independently evaluable. Between the model and the patient sits a **code-side
validation pass** that re-checks the grounding contract and drops anything ungrounded
— the prompt and the validator are two independent lines of defense.

| Stage | Name | What it does |
|------|------|--------------|
| 1 | **GROUND** | Extract every patient-relevant item from the transcript — named entities, instructions/plans, return-precautions/red-flags, and things the *patient* raised — each with a verbatim quote + line_id. Everything downstream traces back to this. |
| 2 | **CLARIFY** | A plain-language (~6th-grade) reconstruction of the visit in **two visually distinct channels** — *"What your doctor said"* (grounded, quoted) vs *"General info"* (labeled education) — plus a grounded QA function that **refuses** anything outside this visit. |
| 3 | **SURFACE** | Diff what the *patient* raised against the note's Assessment & Plan; surface at most 2–3 genuinely dropped concerns as pure conversational recall ("You mentioned X; the visit moved on. You may want to raise it next time."). If nothing qualifies, it returns nothing — **silence is the correct result.** |
| 4 | **TEACH-BACK** | Pick the SINGLE highest-stakes instruction (return-precaution > critical med change > critical follow-up), invite the patient to restate it in their own words, and check that restatement **against the transcript** (the transcript is the answer key — we check the patient against their own doctor, never against our medical judgment). |

### Core principles, encoded as constraints (not just docs)

- **No new medical information.** Every visit-specific claim needs a verbatim quote + line_id, or it's dropped.
- **Two-channel separation** — doctor-said vs general-info never blur.
- **Scope leash** — anything outside this encounter is refused, not answered.
- **Non-alarming** — never introduce a worry the patient didn't raise or the doctor didn't state.
- **Restraint is the product** — empty output is valid and expected.

These live in `prompts.py` (per-stage system prompts) **and** are re-enforced in
`validate.py` after every call.

---

## Run it

```bash
cd second_voice
pip install -r requirements.txt

# The API key is read from (in order): $ANTHROPIC_API_KEY,
# second_voice/.env, or SecondReader/poc/.env.

python -m second_voice                              # interactive picker
python -m second_voice enc01_migraine_amitriptyline # a specific encounter
python -m second_voice dataset:3                    # any of the 25 synthetic records
python -m second_voice enc01_... --show-sources     # render quotes inline (audit view)
```

### Citations: grounded, but not in the patient's face

The grounding contract (a verbatim quote + line_id behind every claim) is what makes
this safe — but it's an **audit artifact, not patient UX**. So by default the patient
sees clean plain-language prose; the quotes are still validated on every call and
written in full to the audit log. To see a claim's exact source words, the patient
types `s` ("see your doctor's exact words"); an auditor or clinician can launch with
`--show-sources` to render every quote inline.

The CLI: loads the encounter and runs Stage 1 → prints the "few hours later"
notification → shows the two-channel reconstruction → offers (never forces) three
things: **[ask a question]**, **[anything I might've missed?]**, **[one thing to
remember]**. Do any, all, or none; quit anytime.

Every model output is written with its grounding (quotes + line_ids) and any
validation drops to an append-only audit log in `logs/`, so you can verify nothing
ungrounded ever reached the patient.

---

## The three demo encounters

Hand-crafted (in the real dataset's record shape) so each stage has something real
to catch:

| Encounter | Designed to show |
|-----------|------------------|
| `enc01_migraine_amitriptyline` | **Stage 4** — a return-precaution ("worst headache of your life… go to the ER") the doctor rattles off *on the way out the door*. The teach-back closer catches exactly this. |
| `enc02_diabetes_followup` | **Stage 3** — the patient raises foot numbness/tingling; the visit moves straight to A1c and metformin and the note's plan never addresses it. Surfaced as a dropped concern. |
| `enc03_hypertension_lisinopril` | **Restraint** — a clean visit with a clear return-precaution but no dropped concern, so Stage 3 correctly returns **nothing**. |

You can also load any of the 25 provided synthetic encounters (`dataset:<index>` or
by id) — the loader parses their `DR:`/`PT:` transcript string into diarized,
line_id'd turns, which is the grounding substrate for everything else.

---

## Layout

```
second_voice/
├── second_voice/
│   ├── cli.py          # interactive loop + two-channel rendering
│   ├── loaders.py      # ingest + parse transcript → line_id'd turns
│   ├── llm.py          # one structured claude-opus-4-8 call per stage
│   ├── prompts.py      # per-stage system prompts (the guardrails)
│   ├── schemas.py      # structured-output JSON schemas per stage
│   ├── pipeline.py     # the 4 stages, wired together
│   ├── validate.py     # the grounding-contract enforcer (drops ungrounded output)
│   └── audit.py        # append-only audit log
├── data/               # 3 curated demo encounters
└── logs/               # per-run audit logs (gitignored)
```
