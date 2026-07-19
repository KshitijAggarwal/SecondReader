"""
TrialGuard amendment demo driver — the CLI shown in the 60-second video.

Runs ONE synthetic patient against ONE protocol version and prints a color-coded
verdict + cited reasoning trail. The money shot is the SAME patient flipping from
green NEEDS_REVIEW (original protocol) to red EXCLUDE (amended protocol), with the
exact chart fact cited.

Examples:
    ../.venv/bin/python demo.py --list
    ../.venv/bin/python demo.py --patient anemia --protocol v1
    ../.venv/bin/python demo.py --patient anemia --protocol v2
    ../.venv/bin/python demo.py --patient anemia --compare      # both, stacked
    ../.venv/bin/python demo.py --diff                          # amendment diff

For a true side-by-side recording, split your terminal (tmux/iTerm) and run
--protocol v1 on the left, --protocol v2 on the right.

Results are cached under .demo_cache/ so retakes are instant and identical; pass
--fresh to recompute (real LLM calls).
"""
import argparse
import difflib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient
import patient_loader
import trial_client
from agents import criteria_parser, chart_reconciler, confidence_engine

# The two protocol versions this demo contrasts. Update these two constants when
# the trial changes; everything else is trial-agnostic.
PROTO_ORIG = "aom_v1"    # original protocol fixture -> trials/trial_aom_v1.json
PROTO_AMEND = "aom_v2"   # amended protocol fixture  -> trials/trial_aom_v2.json
VERSION_ALIASES = {"v1": PROTO_ORIG, "original": PROTO_ORIG, "orig": PROTO_ORIG,
                   "v2": PROTO_AMEND, "amended": PROTO_AMEND, "amend": PROTO_AMEND}

COHORT = Path(__file__).resolve().parent / "data" / "trial_cohort.jsonl"
CACHE = Path(__file__).resolve().parent / ".demo_cache"

# ANSI
BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, RED, YELLOW, CYAN = "\033[32m", "\033[31m", "\033[33m", "\033[36m"
BG_RED, BG_GREEN = "\033[41m\033[97m", "\033[42m\033[30m"
VERDICT_COLOR = {"MATCH": BG_GREEN, "NEEDS_REVIEW": "\033[43m\033[30m", "EXCLUDE": BG_RED}


def load_cohort():
    by_id = {}
    with open(COHORT) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                by_id[r["metadata"]["demo_id"]] = r
    return by_id


def _cache_get(name, fresh):
    p = CACHE / name
    if not fresh and p.exists():
        return json.load(open(p))
    return None


def _cache_put(name, obj):
    CACHE.mkdir(exist_ok=True)
    json.dump(obj, open(CACHE / name, "w"), indent=2)


def get_clauses(llm, version, fresh):
    cached = _cache_get(f"clauses_{version}.json", fresh)
    if cached:
        return cached
    trial = trial_client.load_trial(version)
    clauses = criteria_parser.parse_criteria(llm, trial, trial_client.trial_to_text(trial))
    _cache_put(f"clauses_{version}.json", clauses)
    return clauses


def get_reconciliation(llm, demo_id, version, clauses, chart_text, fresh):
    cached = _cache_get(f"recon_{demo_id}_{version}.json", fresh)
    if cached:
        return cached
    recon = chart_reconciler.reconcile_chart(llm, clauses, chart_text)
    _cache_put(f"recon_{demo_id}_{version}.json", recon)
    return recon


def run_one(llm, record, version, fresh):
    trial = trial_client.load_trial(version)
    chart = patient_loader.extract_chart(record)
    chart_text = patient_loader.chart_to_text(chart)
    clauses = get_clauses(llm, version, fresh)
    recon = get_reconciliation(llm, record["metadata"]["demo_id"], version, clauses, chart_text, fresh)
    result = confidence_engine.decide(clauses, recon, trial["version"])
    return trial, result


def print_verdict(record, trial, result):
    d = patient_loader.extract_chart(record)["demographics"]
    name = record["patient_context"]["patient"]["name"][0]
    who = f"{' '.join(name['given'])} {name['family']}"
    amend = trial.get("simulated_amendment_date")
    tag = f"AMENDED {amend}" if amend else "ORIGINAL"
    color = VERDICT_COLOR.get(result["overall"], "")

    print(f"\n{BOLD}Patient:{RESET} {who}   {DIM}({d['gender']}, dob {d['birth_date']}, visit {d['visit_date'][:10]}){RESET}")
    print(f"{BOLD}Protocol:{RESET} {trial['trial_id']} v[{trial['version']}]  {DIM}{tag}{RESET}")
    print(f"\n   {color} OVERALL: {result['overall']} {RESET}\n")
    print(f"   {BOLD}Reasoning trail:{RESET}")
    for line in result["reasoning_trail"]:
        if line.startswith("[violated]"):
            print(f"     {RED}{BOLD}▶ {line}{RESET}")
        elif line.startswith("[insufficient_data]"):
            print(f"     {DIM}· {line}{RESET}")
        else:
            print(f"     {GREEN}✓ {line}{RESET}")


def cmd_diff():
    orig = trial_client.load_trial(PROTO_ORIG)
    amend = trial_client.load_trial(PROTO_AMEND)
    print(f"\n{BOLD}Protocol amendment{RESET}  {orig['trial_id']}")
    print(f"  {DIM}original{RESET} v[{orig['version']}]  →  {DIM}amended{RESET} v[{amend['version']}]  "
          f"{YELLOW}{BOLD}(posted {amend.get('simulated_amendment_date')}){RESET}\n")
    a = orig["eligibility_criteria"].replace("* ", "").splitlines()
    b = amend["eligibility_criteria"].replace("* ", "").splitlines()
    for line in difflib.unified_diff(a, b, lineterm="", n=0):
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            print(f"  {GREEN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"  {RED}{line}{RESET}")


# --- Coordinator time-saved model ------------------------------------------------
# TrialGuard per-patient re-screen time: MEASURED end-to-end (parse+reconcile+decide)
# on this cohort, 2026-07-18, model claude-opus-4-8 with extended thinking. Conservative
# (includes one-time criteria parsing that is actually amortized across a batch).
GUARD_SEC_MEASURED = 57
# Manual coordinator re-screen: a LABELED ASSUMPTION, not measured here. Re-checking one
# enrolled patient's full chart against amended eligibility (meds, labs, conditions, dates)
# is commonly estimated at ~15-30 min; we default to a conservative 20. Override with --manual-min.
MANUAL_MIN_DEFAULT = 20


def cmd_savings(n_patients, manual_min, guard_sec):
    manual_h = n_patients * manual_min / 60.0
    guard_h = n_patients * guard_sec / 3600.0
    saved_h = manual_h - guard_h
    pct = 100.0 * saved_h / manual_h if manual_h else 0.0
    print(f"\n{BOLD}Coordinator time saved — re-screening a site after the amendment{RESET}")
    print(f"  {DIM}Scenario: {n_patients} enrolled/screened patients must be re-checked against the "
          f"amended protocol.{RESET}\n")
    print(f"  {'Manual chart review':28} {manual_min:g} min/patient   →  {BOLD}{manual_h:5.1f} hours{RESET}")
    print(f"  {'TrialGuard re-screen':28} {guard_sec:g} sec/patient   →  {BOLD}{guard_h*60:5.1f} minutes{RESET}")
    print(f"  {DIM}{'-'*60}{RESET}")
    print(f"  {GREEN}{BOLD}Time saved: {saved_h:.1f} hours  ({pct:.1f}% reduction){RESET}")
    print(f"  {DIM}+ TrialGuard flags exactly which patients now fail, each with a cited chart fact,\n"
          f"    so the coordinator confirms a short list instead of re-reading every chart.{RESET}")
    print(f"\n  {DIM}TrialGuard time is measured (claude-opus-4-8, extended thinking). Manual time is a\n"
          f"    labeled assumption (~15-30 min/patient); override with --manual-min / --guard-sec.{RESET}")


def main():
    ap = argparse.ArgumentParser(description="TrialGuard amendment demo driver")
    ap.add_argument("--patient", help="demo id (see --list)")
    ap.add_argument("--protocol", default="v1", help="v1|v2 (or fixture version name)")
    ap.add_argument("--compare", action="store_true", help="run both protocols, stacked")
    ap.add_argument("--diff", action="store_true", help="show the amendment diff")
    ap.add_argument("--list", action="store_true", help="list demo patients")
    ap.add_argument("--fresh", action="store_true", help="ignore cache, real LLM calls")
    ap.add_argument("--savings", action="store_true", help="show coordinator time-saved card")
    ap.add_argument("--patients", type=int, default=25, help="site size for --savings")
    ap.add_argument("--manual-min", type=float, default=MANUAL_MIN_DEFAULT, help="manual min/patient")
    ap.add_argument("--guard-sec", type=float, default=GUARD_SEC_MEASURED, help="TrialGuard sec/patient")
    args = ap.parse_args()

    if args.savings:
        cmd_savings(args.patients, args.manual_min, args.guard_sec); return
    if args.diff:
        cmd_diff(); return

    cohort = load_cohort()
    if args.list or not args.patient:
        print(f"\n{BOLD}Demo patients{RESET} (in {COHORT.name}):")
        for did, r in cohort.items():
            d = patient_loader.extract_chart(r)["demographics"]
            print(f"  {CYAN}{did:10}{RESET} {d['gender']:7} dob {d['birth_date']}  {DIM}{r['metadata']['visit_title']}{RESET}")
        print(f"\nUsage: demo.py --patient <id> --protocol v1|v2  [--compare] [--diff] [--fresh]")
        return

    if args.patient not in cohort:
        print(f"unknown patient {args.patient!r}; try --list"); sys.exit(1)
    record = cohort[args.patient]
    llm = LLMClient()

    if args.compare:
        for ver in (PROTO_ORIG, PROTO_AMEND):
            trial, result = run_one(llm, record, ver, args.fresh)
            print_verdict(record, trial, result)
        print()
    else:
        version = VERSION_ALIASES.get(args.protocol, args.protocol)
        trial, result = run_one(llm, record, version, args.fresh)
        print_verdict(record, trial, result)
        print()


if __name__ == "__main__":
    main()
