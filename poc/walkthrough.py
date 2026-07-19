"""
TrialGuard guided walkthrough — the 60-second demo, narrated ON SCREEN.

Instead of a voiceover, each beat prints a clearly-visible narration banner that
explains what you're about to see, then runs the real demo command underneath.

    ../.venv/bin/python walkthrough.py            # step through, press Enter per beat
    ../.venv/bin/python walkthrough.py --auto      # run straight through, no pauses
    ../.venv/bin/python walkthrough.py --auto --pace 1.5   # auto with 1.5s between beats
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = str((HERE.parent / ".venv" / "bin" / "python"))

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
CYAN, YELLOW, MAGENTA = "\033[36m", "\033[33m", "\033[95m"
BG_BLUE = "\033[44m\033[97m"

# Each beat: (timecode, TITLE, narration lines, demo.py args)
BEATS = [
    ("0:00-0:07", "MEET THE COHORT",
     ["Four patients already screened INTO a real obesity-med trial (NCT07163650).",
      "Every one of them meets all the inclusion criteria today."],
     ["--list"]),

    ("0:07-0:18", "THE HERO'S CHART — READ IT CLOSELY",
     ["Patient 'glp1' passes pre-screen. But buried in the STRUCTURED chart —",
      "not the transcript, not the note — is an outside-clinic semaglutide (a GLP-1).",
      "A human coordinator skimming the visit never sees it."],
     ["--patient", "glp1", "--protocol", "v1"]),

    ("0:18-0:28", "ORIGINAL PROTOCOL  →  PATIENT LOOKS FINE",
     ["Against the ORIGINAL protocol (v1, inclusion-only, no exclusions),",
      "TrialGuard returns NEEDS_REVIEW — i.e. eligible, pending consent. Green."],
     ["--patient", "glp1", "--protocol", "v1"]),

    ("0:28-0:33", "THE AMENDMENT LANDS",
     ["The sponsor amends the protocol (v2, posted 2026-01-25) and adds a big new",
      "exclusion list — including GLP-1 agonists. Here's the exact diff."],
     ["--diff"]),

    ("0:33-0:48", "AMENDED PROTOCOL  →  SAME PATIENT FLIPS TO EXCLUDE",
     ["Nothing about the patient changed. Only the rules did. TrialGuard re-reads the",
      "whole chart, finds the buried semaglutide, and flips NEEDS_REVIEW → EXCLUDE —",
      "citing the exact chart fact. THIS citation is the credibility. Red."],
     ["--patient", "glp1", "--protocol", "v2"]),

    ("0:48-0:58", "THE WHOLE COHORT, BEFORE vs AFTER",
     ["Control holds steady. Three others each flip for a DIFFERENT buried reason:",
      "GLP-1, major depression, and a hypokalemia lab value — each with its citation."],
     None),  # special-cased: runs --compare for each patient

    ("0:58-1:05", "THE PAYOFF — COORDINATOR TIME SAVED",
     ["Re-screening a 25-patient site by hand vs. TrialGuard. Measured runtime vs.",
      "a labeled manual-review assumption. This is the tangible ROI of a second reader."],
     ["--savings", "--patients", "25"]),
]

COHORT_MONTAGE = ["control", "glp1", "depression", "hypokalemia"]


def banner(tc, title, lines):
    width = 78
    print()
    print(f"{BG_BLUE}{BOLD} {tc:<10} {title:<{width-13}}{RESET}")
    for ln in lines:
        print(f"{DIM}{MAGENTA}│{RESET} {ln}")
    print(f"{DIM}{MAGENTA}└{'─'*(width-1)}{RESET}")


def run(args):
    cmd = [PY, str(HERE / "demo.py")] + args
    print(f"{DIM}$ python demo.py {' '.join(args)}{RESET}")
    subprocess.run(cmd, cwd=HERE)


def pause(auto, pace):
    if auto:
        if pace:
            time.sleep(pace)
        return
    try:
        input(f"\n{DIM}   [Enter] for next beat…{RESET}")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="TrialGuard narrated walkthrough")
    ap.add_argument("--auto", action="store_true", help="no Enter pauses between beats")
    ap.add_argument("--pace", type=float, default=0.0, help="seconds between beats in --auto")
    args = ap.parse_args()

    print(f"\n{BOLD}{CYAN}TrialGuard{RESET} — a second reader for clinical-trial eligibility.")
    print(f"{DIM}When a protocol is amended, patients who qualified yesterday can silently")
    print(f"become ineligible. TrialGuard re-reads the full chart and catches it, with a citation.{RESET}")

    for tc, title, lines, cmd in BEATS:
        banner(tc, title, lines)
        if cmd is None:  # cohort montage
            for p in COHORT_MONTAGE:
                run(["--patient", p, "--compare"])
        else:
            run(cmd)
        pause(args.auto, args.pace)

    print(f"\n{BOLD}{YELLOW}That's TrialGuard.{RESET} Same patient, amended rules, one buried fact — caught and cited.\n")


if __name__ == "__main__":
    main()
