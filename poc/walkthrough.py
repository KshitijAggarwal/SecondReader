"""
TrialGuard guided walkthrough — the demo, narrated ON SCREEN.

Instead of a voiceover, each beat prints a clearly-visible narration banner that
explains what you're about to see, then runs the real command underneath.

Flow: meet the patients → the trial amends its criteria → re-screen everyone and
see who now fails (and why) → what it saves. Patients are shown as "Patient 1..4";
what makes each one fail only shows up in the re-screening, as a cited chart fact.

    ../.venv/bin/python walkthrough.py            # step through, press Enter per beat
    ../.venv/bin/python walkthrough.py --auto      # run straight through, no pauses
    ../.venv/bin/python walkthrough.py --auto --pace 1.5   # auto with 1.5s between beats
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = str((HERE.parent / ".venv" / "bin" / "python"))
sys.path.insert(0, str(HERE))
import patient_loader

COHORT = HERE / "data" / "trial_cohort.jsonl"

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
CYAN, YELLOW, MAGENTA = "\033[36m", "\033[33m", "\033[95m"
BG_BLUE = "\033[44m\033[97m"

# Display order. The label a patient is shown under ("Patient N") is just its
# position here; nothing about why they pass or fail is encoded in the label.
PATIENTS = ["control", "glp1", "depression", "hypokalemia"]


def load_cohort():
    by_id = {}
    with open(COHORT) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                by_id[r["metadata"]["demo_id"]] = r
    return by_id


def age_of(rec):
    d = patient_loader.extract_chart(rec)["demographics"]
    bd, vd = d["birth_date"], d["visit_date"]
    return int(vd[:4]) - int(bd[:4]) - (1 if vd[5:10] < bd[5:10] else 0)


def banner(tc, title, lines):
    width = 78
    print()
    print(f"{BG_BLUE}{BOLD} {tc:<10} {title:<{width-13}}{RESET}")
    for ln in lines:
        print(f"{DIM}{MAGENTA}│{RESET} {ln}")
    print(f"{DIM}{MAGENTA}└{'─'*(width-1)}{RESET}")


def intro_table(cohort):
    for i, pid in enumerate(PATIENTS, 1):
        rec = cohort[pid]
        d = patient_loader.extract_chart(rec)["demographics"]
        print(f"   {CYAN}{BOLD}Patient {i}{RESET}   {d['gender']:7} age {age_of(rec)}"
              f"   {DIM}meets all inclusion criteria{RESET}")


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
        input(f"\n{DIM}   [Enter] to continue…{RESET}")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="TrialGuard narrated walkthrough")
    ap.add_argument("--auto", action="store_true", help="no Enter pauses between beats")
    ap.add_argument("--pace", type=float, default=0.0, help="seconds between beats in --auto")
    args = ap.parse_args()

    cohort = load_cohort()

    print(f"\n{BOLD}{CYAN}TrialGuard{RESET} is a second reader for clinical-trial eligibility.")
    print(f"{DIM}When a protocol gets amended, patients who qualified yesterday can quietly become")
    print(f"ineligible. TrialGuard flags them and shows the chart fact behind each call, so")
    print(f"reviewers just confirm a short list instead of re-reading every chart.{RESET}")

    # 1. Meet the patients
    banner("0:00-0:12", "Meet the patients",
           ["Four people already screened into a real obesity-med trial (NCT07163650).",
            "On the current criteria, every one of them is eligible."])
    intro_table(cohort)
    pause(args.auto, args.pace)

    # 2. The trial amends its criteria
    banner("0:12-0:22", "The trial changes its criteria",
           ["The sponsor amends the protocol and adds a list of exclusion criteria.",
            "Here's what's new."])
    run(["--diff"])
    pause(args.auto, args.pace)

    # 3. Re-screen everyone; who now fails, and why
    banner("0:22-0:50", "Re-screening everyone against the new criteria",
           ["TrialGuard re-reads each chart against the amended protocol and flags anyone",
            "who now fails, with the exact chart fact behind the call. Watch the verdict",
            "flip from NEEDS_REVIEW (green) to EXCLUDE (red) for the patients who no longer fit."])
    for i, pid in enumerate(PATIENTS, 1):
        run(["--patient", pid, "--compare", "--label", f"Patient {i}"])
    pause(args.auto, args.pace)

    # 4. Conclude — what it saves
    banner("0:50-1:00", "What it saves",
           ["Re-screening a whole site by hand versus letting TrialGuard do it.",
            "The tool's time is measured; the manual number is an estimate, labeled as one."])
    run(["--savings", "--patients", "25"])
    pause(args.auto, args.pace)

    print(f"\n{BOLD}{YELLOW}That's the point:{RESET} the criteria changed, and TrialGuard re-checked "
          f"every chart,\nflagged the patients who no longer qualify, and showed the fact behind each call.\n")


if __name__ == "__main__":
    main()
