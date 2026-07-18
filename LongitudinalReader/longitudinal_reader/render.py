"""Stage 5 — OUTPUT / REVIEW.

Turn a result dict into (a) clinician-readable finding cards with the dated receipt
and an ASCII sparkline, (b) the cohort silence panel, and (c) a self-contained HTML
report. The sparkline is the "there's the line" moment: the drift nobody drew.
"""

from __future__ import annotations

import html as _html
from typing import Any

# --- ANSI (matches the SecondReader house style) -----------------------------
_C = {
    "flag": "\033[31m",   # red    -> a surfaced finding
    "ok": "\033[32m",     # green  -> silence / no findings
    "line": "\033[36m",   # cyan   -> the receipt / sparkline
    "warm": "\033[35m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

_BLOCKS = "▁▂▃▄▅▆▇█"


def c(key: str, text: str) -> str:
    return f"{_C[key]}{text}{_C['reset']}"


def sparkline(points: list[dict], ref_low=None, ref_high=None) -> str:
    """Unicode sparkline over a numeric series, annotated with first/last values."""
    vals = [p["value"] for p in points]
    lo, hi = min(vals), max(vals)
    if ref_low is not None:
        lo = min(lo, ref_low)
    if ref_high is not None:
        hi = max(hi, ref_high)
    rng = (hi - lo) or 1.0
    spark = "".join(_BLOCKS[min(len(_BLOCKS) - 1, int((v - lo) / rng * (len(_BLOCKS) - 1)))] for v in vals)
    return spark


def _slope_receipt(s: dict) -> list[str]:
    lines = []
    spark = sparkline(s["points"], s.get("ref_low"), s.get("ref_high"))
    first, last = s["first"], s["last"]
    ref = ""
    if s.get("ref_low") is not None and s.get("ref_high") is not None:
        ref = f"  (ref {s['ref_low']}–{s['ref_high']} {s.get('unit') or ''})"
    lines.append(c("line", f"    {spark}   {s['code']}: {first['value']} → {last['value']} {s.get('unit') or ''}{ref}"))
    trail = "  ".join(f"{p['date'][:7]}:{p['value']}" for p in s["points"])
    lines.append(c("dim", f"      {trail}"))
    tag = "crosses reference bound" if s["crosses_ref"] else "approaching reference bound"
    lines.append(c("dim", f"      {s['direction']}, {tag}, ~{s['slope_per_year']}/yr over {round(s['span_days']/365,1)}y"))
    return lines


def render_patient(result: dict[str, Any], *, show_receipts: bool = True) -> str:
    out: list[str] = []
    p = result["patient"]
    header = f"{p.get('name') or p['id']}  ·  {p.get('age') or '?'}{(p.get('sex') or '')[:1]}  ·  {p['n_events']} events / {p['span_years']}y"
    out.append(c("bold", header))
    out.append(c("dim", f"  source: {result.get('source')}   ·   mode: {result.get('mode', 'full')}"))

    findings = result.get("findings", [])
    if not findings:
        out.append("")
        out.append(c("ok", "  ✓  No longitudinal findings — staying silent."))
        if result.get("silence_rationale"):
            out.append(c("dim", f"     {result['silence_rationale']}"))
        nm = result.get("near_misses", [])
        if nm:
            out.append(c("dim", "     considered & dropped:"))
            for m in nm:
                out.append(c("dim", f"       · {m['hypothesis_id']}: {m['reason_dropped']}"))
        return "\n".join(out)

    prim_slopes = {s["code"]: s for s in result.get("primitives", {}).get("slopes", [])}

    for i, f in enumerate(findings, 1):
        out.append("")
        out.append(c("flag", c("bold", f"  ▲ FINDING {i}/{len(findings)}  {f['headline']}")))
        out.append(c("dim", f"    severity {f['severity']}/3 · trajectory {f['trajectory_strength']} · unaddressed {f['unaddressed']} · score {round(f['score'],2)}"))
        out.append("")
        out.append(f"    {f['explanation']}")
        if show_receipts:
            out.append("")
            out.append(c("dim", "    the receipt:"))
            for ev in f.get("event_chain", []):
                out.append(c("line", f"      {ev['date']}  {ev['detail']}"))
            # attach the mechanical sparkline if a slope backs this finding
            for code, s in prim_slopes.items():
                if any(code in (ev.get("detail", "").lower()) for ev in f.get("event_chain", [])):
                    out.append("")
                    out.extend(_slope_receipt(s))
                    break
        out.append("")
        out.append(c("warm", f"    → next step: {f['next_step']}"))
    return "\n".join(out)


def render_cohort_panel(results: list[dict[str, Any]]) -> str:
    """The silence dashboard: N scanned, most ✓ no findings, a few flagged."""
    out = ["", c("bold", "  COHORT SILENCE PANEL"), ""]
    flagged = 0
    for r in results:
        p = r["patient"]
        n = len(r.get("findings", []))
        name = (p.get("name") or p["id"])[:28].ljust(28)
        meta = f"{p['n_events']:>3} ev / {p['span_years']:>4}y"
        if n:
            flagged += 1
            top = r["findings"][0]["headline"]
            out.append(c("flag", f"  ▲  {name} {meta}  →  {top[:44]}"))
        else:
            out.append(c("ok", f"  ✓  {name} {meta}  →  no findings"))
    total = len(results)
    out.append("")
    out.append(c("bold", f"  {total} patients scanned · {flagged} flagged · {total - flagged} silent"))
    out.append(c("dim", "  The product isn't the alarm. It's knowing when to stay silent."))
    return "\n".join(out)


# --- HTML (self-contained, for findings/*.html) ------------------------------

def render_html(results: list[dict[str, Any]], title: str = "Longitudinal Reader") -> str:
    def esc(s):
        return _html.escape(str(s))

    rows = []
    cards = []
    flagged = 0
    for r in results:
        p = r["patient"]
        fs = r.get("findings", [])
        status = "flag" if fs else "ok"
        if fs:
            flagged += 1
        summary = fs[0]["headline"] if fs else (r.get("silence_rationale") or "no findings")
        rows.append(
            f'<tr class="{status}"><td>{esc(p.get("name") or p["id"])}</td>'
            f'<td>{esc(p.get("age") or "?")}{esc((p.get("sex") or "")[:1])}</td>'
            f'<td>{p["n_events"]} / {p["span_years"]}y</td>'
            f'<td>{"▲ " + esc(summary) if fs else "✓ silent"}</td></tr>'
        )
        for f in fs:
            chain = "".join(
                f'<li><span class="date">{esc(ev["date"])}</span> {esc(ev["detail"])}</li>'
                for ev in f.get("event_chain", [])
            )
            spark = ""
            for s in r.get("primitives", {}).get("slopes", []):
                if any(s["code"] in ev.get("detail", "").lower() for ev in f.get("event_chain", [])):
                    spark = (
                        f'<div class="spark">{esc(sparkline(s["points"], s.get("ref_low"), s.get("ref_high")))}'
                        f' &nbsp;{esc(s["code"])}: {s["first"]["value"]} → {s["last"]["value"]} {esc(s.get("unit") or "")}</div>'
                    )
                    break
            cards.append(
                f'<div class="card"><h3>▲ {esc(f["headline"])}</h3>'
                f'<p class="meta">severity {f["severity"]}/3 · trajectory {f["trajectory_strength"]} · unaddressed {f["unaddressed"]}</p>'
                f'<p>{esc(f["explanation"])}</p>{spark}'
                f'<p class="rk">the receipt</p><ul>{chain}</ul>'
                f'<p class="next">→ {esc(f["next_step"])}</p>'
                f'<p class="who">{esc(p.get("name") or p["id"])}</p></div>'
            )

    total = len(results)
    css = """
      body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;background:#fafafa}
      h1{font-size:1.5rem} .sub{color:#666;margin-top:-.5rem}
      table{border-collapse:collapse;width:100%;margin:1.5rem 0;font-size:14px}
      td{padding:.4rem .6rem;border-bottom:1px solid #eee}
      tr.flag td{background:#fff4f4} tr.ok td{color:#557}
      .card{border:1px solid #e5c2c2;border-left:4px solid #c0392b;border-radius:8px;padding:1rem 1.25rem;margin:1rem 0;background:#fff}
      .card h3{margin:.2rem 0;color:#a02} .meta{color:#888;font-size:12px;margin:.2rem 0}
      .spark{font-size:22px;letter-spacing:2px;color:#0a7;margin:.6rem 0;font-family:monospace}
      .rk{font-size:11px;text-transform:uppercase;color:#999;letter-spacing:1px;margin:.6rem 0 .2rem}
      ul{margin:.2rem 0;padding-left:1.1rem} li{margin:.15rem 0} .date{color:#0a7;font-family:monospace;font-size:12px}
      .next{background:#f0f7ff;padding:.5rem .7rem;border-radius:6px;margin-top:.6rem}
      .who{color:#aaa;font-size:12px;text-align:right;margin:.4rem 0 0}
    """
    return (
        f"<!doctype html><meta charset=utf-8><title>{esc(title)}</title><style>{css}</style>"
        f"<h1>The Longitudinal Reader</h1>"
        f'<p class="sub">{total} patients scanned · {flagged} flagged · {total-flagged} silent — the axis nobody owns.</p>'
        f"<h2>Findings</h2>{''.join(cards) or '<p>No findings across the cohort.</p>'}"
        f"<h2>Cohort</h2><table><tr><th>patient</th><th>age</th><th>record</th><th>result</th></tr>{''.join(rows)}</table>"
    )
