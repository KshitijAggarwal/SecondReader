"""The Longitudinal Reader — CLI.

  longitudinal-reader run <file.json> [--no-receipts] [--html]
        analyze one patient (event-stream JSON or FHIR bundle) end-to-end.

  longitudinal-reader cohort [dir ...] [--fast] [--html] [--limit N]
        scan a cohort (default: data/heroes + data/cohort + data/synthea),
        print the silence panel, write findings/cohort.html.

  longitudinal-reader primitives <file.json>
        deterministic pass only (no API) — show the raw slopes/recurrences/constellations.

  longitudinal-reader health
        confirm the Anthropic API key works.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import load, render
from .agent import decompose, run

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIRS = [ROOT / "data" / "heroes", ROOT / "data" / "cohort", ROOT / "data" / "synthea"]
FINDINGS = ROOT / "findings"


def _save_json(result_or_list, name: str) -> Path:
    FINDINGS.mkdir(exist_ok=True)
    path = FINDINGS / name
    path.write_text(json.dumps(result_or_list, indent=2))
    return path


def cmd_run(args: list[str]) -> None:
    show_receipts = "--no-receipts" not in args
    want_html = "--html" in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        print("usage: longitudinal-reader run <file.json>")
        return
    rec = load.load_record(files[0])
    print(render.c("dim", f"analyzing {rec.display_name} — {len(rec.events)} events over {rec.span_days()//365}y …\n"))
    result = run.analyze(rec)
    print(render.render_patient(result, show_receipts=show_receipts))
    stem = Path(files[0]).stem
    _save_json(result, f"{stem}.json")
    if want_html:
        path = FINDINGS / f"{stem}.html"
        path.write_text(render.render_html([result], title=rec.display_name or stem))
        print(render.c("dim", f"\n  html: {path}"))


def cmd_primitives(args: list[str]) -> None:
    files = [a for a in args if not a.startswith("--")]
    if not files:
        print("usage: longitudinal-reader primitives <file.json>")
        return
    rec = load.load_record(files[0])
    prim = decompose.run_primitives(rec)
    print(render.c("bold", f"{rec.display_name} — deterministic primitives (no API)\n"))
    if prim["slopes"]:
        print(render.c("line", "SLOPES:"))
        for s in prim["slopes"]:
            print("\n".join(render._slope_receipt(s)))
    if prim["recurrences"]:
        print(render.c("line", "\nRECURRENCES:"))
        for r in prim["recurrences"]:
            print(f"    {r['symptom']}: {r['n_encounters']} encounters, attributions={r['attributions']}, workup_seen={r['workup_seen']}")
    if prim["constellations"]:
        print(render.c("line", "\nCONSTELLATIONS:"))
        for cst in prim["constellations"]:
            print(f"    {cst['label']}: present={cst['present']} missing={cst['missing']} (score {cst['score']})")
    if not decompose.any_signal(prim):
        print(render.c("ok", "  no mechanical signal."))


def cmd_cohort(args: list[str]) -> None:
    fast = "--fast" in args
    want_html = "--html" not in args or True  # always write html for the demo
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    dirs = [a for a in args if not a.startswith("--") and not a.isdigit()]
    search = [Path(d) for d in dirs] if dirs else DEFAULT_DIRS

    records = []
    for d in search:
        if Path(d).exists():
            records.extend(load.load_dir(d))
    if limit:
        records = records[:limit]
    if not records:
        print("no patient files found. Generate a cohort: python tools/gen_cohort.py")
        return

    print(render.c("dim", f"scanning {len(records)} patients ({'fast/deterministic' if fast else 'full pipeline'}) …"))
    results = []
    for rec in records:
        print(render.c("dim", f"  · {rec.display_name} …"))
        results.append(run.analyze(rec, use_llm=not fast))

    print(render.render_cohort_panel(results))
    _save_json(results, "cohort.json")
    if want_html:
        (FINDINGS / "cohort.html").write_text(render.render_html(results))
        print(render.c("dim", f"\n  html: {FINDINGS / 'cohort.html'}"))


def cmd_health(_args: list[str]) -> None:
    from . import llm

    print(llm.health_check())


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    dispatch = {
        "run": cmd_run,
        "cohort": cmd_cohort,
        "primitives": cmd_primitives,
        "health": cmd_health,
    }
    fn = dispatch.get(cmd)
    if not fn:
        print(__doc__)
        return
    fn(rest)


if __name__ == "__main__":
    main()
