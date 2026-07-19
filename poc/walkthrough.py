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
     ["Four patients who already made it into a real obesity-med trial (NCT07163650).",
      "Right now, all four meet the inclusion criteria."],
     ["--list"]),

    ("0:07-0:18", "A closer look at one patient",
     ["Patient 'glp1' cleared pre-screen. But his chart lists a semaglutide (a GLP-1)",
      "prescribed by an outside clinic. That's in the medication data, not the visit note,",
      "so a coordinator reading the transcript would never catch it."],
     ["--patient", "glp1", "--protocol", "v1"]),

    ("0:18-0:28", "Checked against the original protocol",
     ["The original protocol (v1) has inclusion criteria only, no exclusions.",
      "So TrialGuard says NEEDS_REVIEW: eligible, just waiting on consent. Green."],
     ["--patient", "glp1", "--protocol", "v1"]),

    ("0:28-0:33", "Then the protocol changes",
     ["On 2026-01-25 the sponsor amended the protocol (v2) and added a set of",
      "exclusions, GLP-1 agonists among them. Here's what changed."],
     ["--diff"]),

    ("0:33-0:48", "Same patient, new rules",
     ["The patient didn't change; the rules did. TrialGuard reads the chart again,",
      "finds the semaglutide, and switches to EXCLUDE, pointing at the exact line",
      "it used. That citation is what makes the call worth trusting. Red."],
     ["--patient", "glp1", "--protocol", "v2"]),

    ("0:48-0:58", "The rest of the group",
     ["The control patient stays put. The other three each drop for a different reason",
      "buried in their chart: a GLP-1, major depression, and a low potassium lab.",
      "Every call comes with the fact behind it."],
     None),  # special-cased: runs --compare for each patient

    ("0:58-1:05", "What it saves",
     ["Re-screening a 25-patient site by hand versus letting TrialGuard do it.",
      "The tool's time is measured; the manual number is an estimate, and we label it as one."],
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
    sys.stdout.flush()  # keep our prints ordered before subprocess output when piped/recorded
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

    print(f"\n{BOLD}{CYAN}TrialGuard{RESET} is a second reader for clinical-trial eligibility.")
    print(f"{DIM}When a protocol gets amended, patients who qualified yesterday can quietly become")
    print(f"ineligible. TrialGuard flags them and shows the chart fact behind each call, so")
    print(f"reviewers just confirm a short list instead of re-reading every chart.{RESET}")

    for tc, title, lines, cmd in BEATS:
        banner(tc, title, lines)
        if cmd is None:  # cohort montage
            for p in COHORT_MONTAGE:
                run(["--patient", p, "--compare"])
        else:
            run(cmd)
        pause(args.auto, args.pace)

    print(f"\n{BOLD}{YELLOW}That's the point:{RESET} the rules changed, one fact was buried in the chart, and TrialGuard caught it and showed its work.\n")


if __name__ == "__main__":
    main()
