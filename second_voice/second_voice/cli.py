"""Second Voice — patient-facing, transcript-grounded visit companion (CLI POC).

Flow:
  1. load <encounter_id>  -> ingest, run Stage 1 (GROUND)
  2. print the "few hours later" notification
  3. show the Stage 2 plain-language reconstruction (two channels)
  4. offer, never force: [ask a question] [anything I might've missed?] [one thing to remember]
  5. every model output is logged with its grounding to an audit file
"""

from __future__ import annotations

import sys

from . import loaders, pipeline
from .audit import AuditLog

# --- tiny ANSI helpers: the two channels must be visually distinct -----------
_C = {
    "doc": "\033[36m",     # cyan   -> "What your doctor said"
    "gen": "\033[33m",     # yellow -> "General info"
    "warm": "\033[35m",    # magenta-> the companion's voice
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def c(key: str, text: str) -> str:
    return f"{_C[key]}{text}{_C['reset']}"


def hr() -> None:
    print(c("dim", "─" * 66))


def _print_channels(doctor_said: list[dict], general_info: list[dict], enc) -> None:
    if doctor_said:
        print(c("doc", c("bold", "  ▎What your doctor said")))
        for p in doctor_said:
            plain = p.get("plain") or p.get("answer") or ""
            print(c("doc", f"   • {plain}"))
            print(c("dim", f"       “{p['quote']}”  [{p['line_id']}]"))
    if general_info:
        print()
        print(c("gen", c("bold", "  ▎General info (not from your visit — background only)")))
        for d in general_info:
            print(c("gen", f"   • {d['term']}: {d['definition']}"))


def run(encounter_id: str) -> None:
    print()
    print(c("dim", f"loading encounter {encounter_id} …"))
    enc = loaders.load(encounter_id)
    log = AuditLog(enc.id)
    print(c("dim", f"  {enc.visit_title} — {len(enc.turns)} transcript turns"))
    print(c("dim", f"  audit log: {log.path}"))

    # Stage 1: GROUND (silent — it's the substrate everything else traces to)
    print(c("dim", "  grounding the visit (Stage 1) …"))
    g = pipeline.ground(enc, log)
    print(c("dim", "  grounded: "
                   f"{len(g['entities'])} terms, {len(g['instructions'])} instructions, "
                   f"{len(g['return_precautions'])} return-precautions, "
                   f"{len(g['patient_raised'])} patient-raised items"))

    # 2. the "few hours later" notification
    hr()
    first = enc.patient_name.split()[0] if enc.patient_name else "there"
    print(c("warm", f"  🔔  Hi {first} — here's a hand making sense of today's visit whenever"))
    print(c("warm", "      you're ready. No rush."))
    hr()
    try:
        input(c("dim", "  [enter] to open  ·  ctrl-c to leave it for now  "))
    except (EOFError, KeyboardInterrupt):
        print("\n" + c("warm", "  Okay — it'll be here whenever you want it. Take care."))
        return

    # 3. Stage 2 reconstruction
    print(c("dim", "  putting today's visit in plain words (Stage 2) …\n"))
    recon = pipeline.reconstruct(enc, g, log)
    print(c("warm", "  " + recon.get("greeting", "Here's what today's visit was about.")))
    print()
    _print_channels(recon.get("doctor_said", []), recon.get("general_info", []), enc)

    # 4. offer three things
    _menu(enc, g, log)


def _menu(enc, g, log) -> None:
    while True:
        hr()
        print(c("warm", "  What would you like to do? (do any, all, or none)"))
        print("   1  ask a question about the visit")
        print("   2  anything I might've missed?")
        print("   3  one thing to remember")
        print("   q  I'm done")
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "q"

        if choice in ("q", "quit", "exit", ""):
            print(c("warm", "\n  Take care. Your doctor's advice is the plan — this was just to help it land.\n"))
            return
        if choice == "1":
            _ask(enc, g, log)
        elif choice == "2":
            _surface(enc, g, log)
        elif choice == "3":
            _teachback(enc, g, log)
        else:
            print(c("dim", "  (didn't catch that — pick 1, 2, 3, or q)"))


def _ask(enc, g, log) -> None:
    try:
        q = input(c("warm", "  Ask about today's visit: ")).strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not q:
        return
    print(c("dim", "  checking what was said today …\n"))
    a = pipeline.answer(enc, g, q, log)
    if not a.get("in_scope"):
        print(c("warm", "  " + (a.get("refusal") or
              "That's outside what today's visit covered, so I can't speak to it — "
              "your care team is the right place to ask.")))
        return
    if not a.get("doctor_said") and not a.get("general_info"):
        print(c("warm", "  Your doctor didn't cover that in today's visit, so I can't add to it."))
        return
    _print_channels(a.get("doctor_said", []), a.get("general_info", []), enc)


def _surface(enc, g, log) -> None:
    print(c("dim", "  looking for anything you raised that the visit moved past …\n"))
    s = pipeline.surface(enc, g, log)
    items = s.get("items", [])
    if not items:
        print(c("warm", "  Nothing stood out as left hanging — it looks like what you brought up"))
        print(c("warm", "  got addressed. (No news is good news here.)"))
        return
    for it in items:
        print(c("warm", f"  • {it['nudge']}"))
        print(c("dim", f"      you said: “{it['quote']}”  [{it['line_id']}]"))


def _teachback(enc, g, log) -> None:
    print(c("dim", "  finding the single most important thing to hold onto …\n"))
    sel = pipeline.teachback_select(enc, g, log)
    if not sel.get("found"):
        print(c("warm", "  There wasn't a single stand-out must-remember from today — "
              "the plain-language summary above covers it."))
        return
    label = {"return_precaution": "when to get help",
             "med_change": "a medication change",
             "follow_up": "a follow-up"}.get(sel.get("category"), "one key thing")
    print(c("warm", f"  There's one thing worth locking in — it's about {label}."))
    print(c("warm", "  " + sel["prompt"]))
    print(c("dim", "  (or just press enter to skip)"))
    try:
        restate = input("  You: ").strip()
    except (EOFError, KeyboardInterrupt):
        restate = ""
    if not restate:
        print(c("doc", f"  No problem. Here it is, in your doctor's words:"))
        print(c("dim", f"      “{sel['quote']}”  [{sel['line_id']}]"))
        return
    res = pipeline.teachback_check(enc, sel, restate, log)
    tone = "warm" if res.get("verdict") == "match" else "doc"
    print()
    print(c(tone, "  " + res.get("response", "")))
    if res.get("verdict") != "match":
        print(c("dim", f"      your doctor said: “{res['correct_quote']}”  [{res['line_id']}]"))


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] not in ("-h", "--help"):
        run(args[0])
        return
    # no encounter given: show a picker
    print(c("bold", "\n  Second Voice — a companion for your visit\n"))
    curated = loaders.list_curated()
    if not curated:
        print("  usage: python -m second_voice <encounter_id>")
        print("  (also accepts dataset ids or 'dataset:<index>')")
        return
    print("  Available encounters:")
    for i, (stem, title) in enumerate(curated):
        print(f"   {i+1}  {stem}  —  {title}")
    print(c("dim", "   (or pass a dataset id / 'dataset:<index>' as an argument)"))
    try:
        pick = input("\n  choose a number: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if pick.isdigit() and 1 <= int(pick) <= len(curated):
        run(curated[int(pick) - 1][0])


if __name__ == "__main__":
    main()
