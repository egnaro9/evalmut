"""A read-only rendering of a run that already happened.

DELIBERATELY ADDS NOTHING. Every number here is read from the run's own JSON; this module
computes no scores, re-derives no counts, and reaches no verdicts. If the page and the terminal
report ever disagree, the page is wrong. That constraint is why the renderer is a pure function
from the exported payload to a string, with no access to a suite, a grader, or an operator.

THE ONE INFORMATION-DESIGN DECISION. The terminal report leads with the mutation score, which is
right for a CI gate: one number, one exit code. It is wrong for a person reading a result, because
"91.3%" reads as a grade and the actionable fact is "two of your checks are broken." So the page
leads with the holes, by bucket, and the score sits underneath as context. A suite owner who reads
only the first line should come away with what to go fix, not with a feeling about their score.

Buckets are never distinguished by colour alone: each carries a glyph and a spelled-out meaning,
because the difference between "this check is broken" and "no check guards this" decides whether
the reader fixes a grader or writes a new one, and getting that from a hue is a bad bet.

Self-contained on purpose: no build step, no CDN, no font fetch, no script. It opens from a file://
path on a machine with no network, which is the same standard the VAC bundle is held to.
"""
from __future__ import annotations

import html
import json
from typing import Any

# glyph, label, what a hole in this bucket MEANS, what to do about it
BUCKETS = {
    "blind": ("!", "Blind spot", "the check is present and BROKEN: a real regression of this "
                                 "shape would pass the suite", "Fix the check."),
    "vacuous": ("0", "Vacuous", "the check asserts nothing about the answer and cannot fail",
                "Replace the check. It is not measuring anything."),
    "forged": ("#", "Forged verdict", "the check honoured a result written by the thing it was "
                                      "grading, so none of its verdicts are falsifiable",
               "The channel is the bug, not the check."),
    "brittle": ("~", "Brittle spot", "the check FAILED an output that is still correct: it cries "
                                     "wolf on cosmetic change", "Loosen the check, carefully."),
    "error": ("x", "Crash", "the check raised on a well-formed input and rendered no verdict at all",
              "Fix the crash; a crash is not a pass."),
    "coverage_gap": ("-", "Coverage gap", "no check in the suite guards this shape. Not a broken "
                                          "grader, a missing one", "Add a check, if you want this "
                                                                   "shape guarded."),
}
ORDER = ["forged", "vacuous", "blind", "error", "brittle", "coverage_gap"]

_CSS = """
:root{--bg:#fbfaf8;--panel:#fff;--ink:#1c1b19;--ink2:#54514c;--ink3:#8b8781;--rule:#e3e0da;
--accent:#7a4b2a;--hot:#8f2f1d;--warn:#8a6d1f;--cool:#3d5a4a;--mono:ui-monospace,SFMono-Regular,
Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141311;--panel:#1c1a18;
--ink:#eeebe6;--ink2:#b3aea6;--ink3:#7d786f;--rule:#302c28;--accent:#d99a63;--hot:#e0785f;
--warn:#d6b44e;--cool:#7fb595}}
:root[data-theme=dark]{--bg:#141311;--panel:#1c1a18;--ink:#eeebe6;--ink2:#b3aea6;--ink3:#7d786f;
--rule:#302c28;--accent:#d99a63;--hot:#e0785f;--warn:#d6b44e;--cool:#7fb595}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,
"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
h1{font-size:1.05rem;font-weight:600;letter-spacing:.02em;margin:0 0 .15rem;color:var(--ink2)}
.sub{color:var(--ink3);font-size:.82rem;margin:0 0 2rem}
.verdict{font-size:1.95rem;line-height:1.2;font-weight:650;letter-spacing:-.02em;margin:0 0 .5rem}
.verdict .n{color:var(--hot)}
.verdict.clean .n{color:var(--cool)}
.context{color:var(--ink2);font-size:.92rem;margin:0 0 2.25rem;max-width:46rem}
.context b{color:var(--ink);font-weight:600}
.tally{display:flex;flex-wrap:wrap;gap:.4rem 1.6rem;font-family:var(--mono);font-size:.8rem;
color:var(--ink3);border-top:1px solid var(--rule);padding-top:.9rem;margin-bottom:2.5rem;
font-variant-numeric:tabular-nums}
.tally b{color:var(--ink);font-weight:600}
h2{font-size:.72rem;text-transform:uppercase;letter-spacing:.13em;color:var(--ink3);
font-weight:600;margin:2.5rem 0 .9rem;border-bottom:1px solid var(--rule);padding-bottom:.5rem}
.hole{background:var(--panel);border:1px solid var(--rule);border-left:3px solid var(--kind);
border-radius:3px;padding:1rem 1.1rem;margin-bottom:.7rem}
.hkind{display:inline-flex;align-items:center;gap:.45rem;font-family:var(--mono);font-size:.7rem;
text-transform:uppercase;letter-spacing:.1em;color:var(--kind);font-weight:700}
.hkind .g{display:inline-grid;place-items:center;width:1.05rem;height:1.05rem;border-radius:2px;
background:var(--kind);color:var(--panel);font-size:.66rem}
.hmeans{color:var(--ink3);font-size:.78rem;margin:.45rem 0 .8rem;text-transform:none;
letter-spacing:0;font-weight:400}
.hid{font-family:var(--mono);font-size:.92rem;color:var(--ink);font-weight:600;
word-break:break-word}
.hcase{font-family:var(--mono);font-size:.76rem;color:var(--ink3);margin:.2rem 0 .75rem}
.shape{color:var(--ink2);font-size:.88rem;margin:0 0 .8rem}
.mut{font-family:var(--mono);font-size:.76rem;background:var(--bg);border:1px solid var(--rule);
border-radius:2px;padding:.5rem .6rem;color:var(--ink2);overflow-x:auto;white-space:pre-wrap;
word-break:break-word;margin:0 0 .8rem}
.mut .lbl{color:var(--ink3);display:block;font-size:.66rem;text-transform:uppercase;
letter-spacing:.1em;margin-bottom:.3rem}
details.prov{border-top:1px dashed var(--rule);padding-top:.6rem}
details.prov summary{cursor:pointer;color:var(--ink3);font-size:.74rem;letter-spacing:.04em}
details.prov summary:hover{color:var(--accent)}
.prov p{color:var(--ink2);font-size:.8rem;line-height:1.6;margin:.6rem 0 0;word-break:break-word}
.fix{color:var(--ink2);font-size:.8rem;margin:.6rem 0 0}
.fix b{color:var(--ink)}
.none{color:var(--ink3);font-size:.88rem;font-style:italic}
table{width:100%;border-collapse:collapse;font-size:.78rem;font-family:var(--mono)}
th{text-align:left;color:var(--ink3);font-weight:600;font-size:.68rem;text-transform:uppercase;
letter-spacing:.09em;border-bottom:1px solid var(--rule);padding:.45rem .5rem}
td{padding:.4rem .5rem;border-bottom:1px solid var(--rule);color:var(--ink2)}
td.o{font-weight:600}
.wrapx{overflow-x:auto}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--rule);color:var(--ink3);
font-size:.76rem;line-height:1.6}
"""

_KIND_VAR = {"blind": "--hot", "vacuous": "--hot", "forged": "--hot", "error": "--hot",
             "brittle": "--warn", "coverage_gap": "--ink3"}


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _hole_card(h: dict, kind: str) -> str:
    glyph, label, means, fix = BUCKETS[kind]
    mutant = (h.get("mutant_preview") or "").strip()
    mut = (f'<div class="mut"><span class="lbl">what was injected</span>{_e(mutant)}</div>'
           if mutant else "")
    return f"""<div class="hole" style="--kind:var({_KIND_VAR[kind]})">
<div class="hkind"><span class="g">{_e(glyph)}</span>{_e(label)}</div>
<div class="hmeans">{_e(means)}</div>
<div class="hid">{_e(h.get('operator_id'))}</div>
<div class="hcase">case <b>{_e(h.get('case_name'))}</b> &middot; grader {_e(h.get('grader_id'))}
 &middot; {_e(h.get('family'))} / {_e(h.get('polarity'))}</div>
<div class="shape">{_e(h.get('defect_shape'))}</div>
{mut}
<div class="fix"><b>What this means:</b> {_e(fix)}</div>
<details class="prov"><summary>Where this operator comes from</summary>
<p>{_e(h.get('real_origin'))}</p></details>
</div>"""


def render_html(payload: dict, *, title: str = "evalmut run") -> str:
    """Render an `evalmut run --json` payload. Reads; never recomputes."""
    holes = payload.get("holes", {}) or {}
    tally = payload.get("tally", {}) or {}
    score = payload.get("score")
    counts = {k: len(holes.get(k, []) or []) for k in ORDER}
    total = sum(counts.values())
    serious = counts["forged"] + counts["vacuous"] + counts["blind"] + counts["error"] + counts["brittle"]

    if total == 0:
        verdict = '<p class="verdict clean">No holes found<span class="n">.</span></p>'
        context = ("Every mutation this suite could apply was answered correctly. That is a "
                   "statement about the operators that <b>applied</b>, not about the suite in "
                   "general: an operator that declined had nothing to say here.")
    else:
        bits = [f'<span class="n">{counts[k]}</span> {BUCKETS[k][1].lower()}'
                + ("s" if counts[k] != 1 else "") for k in ORDER if counts[k]]
        verdict = f'<p class="verdict">{", ".join(bits)}</p>'
        context = ("A <b>blind spot</b> is a check that is present and broken. A <b>coverage "
                   "gap</b> is a shape nothing guards. They read alike in a score and mean "
                   "opposite things to whoever has to act on them.")

    sections = []
    for kind in ORDER:
        rows = holes.get(kind, []) or []
        if not rows:
            continue
        sections.append(f"<h2>{_e(BUCKETS[kind][1])} &middot; {len(rows)}</h2>"
                        + "".join(_hole_card(h, kind) for h in rows))

    results = payload.get("results") or []
    table = ""
    if results:
        body = "".join(
            f"<tr><td>{_e(r.get('case_name'))}</td><td>{_e(r.get('operator_id'))}</td>"
            f"<td>{_e(r.get('polarity'))}</td><td class=o>{_e(r.get('outcome'))}</td>"
            f"<td>{_e((r.get('detail') or '')[:90])}</td></tr>" for r in results)
        table = ("<h2>Every mutation attempted &middot; " + str(len(results)) + "</h2>"
                 '<div class="wrapx"><table><thead><tr><th>case</th><th>operator</th>'
                 "<th>polarity</th><th>outcome</th><th>detail</th></tr></thead>"
                 f"<tbody>{body}</tbody></table></div>")

    na = tally.get("na", 0)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>evalmut</h1>
<p class="sub">does your eval actually check anything?</p>
{verdict}
<p class="context">{context}</p>
<div class="tally">
<span>mutation score <b>{_e(f"{score:.1%}" if isinstance(score, (int, float)) else score)}</b></span>
<span>caught <b>{_e(tally.get('caught', 0))}</b></span>
<span>missed <b>{_e(tally.get('missed', 0))}</b></span>
<span>flagged <b>{_e(tally.get('flagged', 0))}</b></span>
<span>errored <b>{_e(tally.get('error', 0))}</b></span>
<span>declined <b>{_e(na)}</b></span>
</div>
{"".join(sections)}
{table}
<footer>
Rendered from a run that already happened. Every number on this page is read from that run's
JSON export; nothing here is recomputed, so if this page and the terminal report disagree, this
page is wrong.<br><br>
<b>declined ({_e(na)})</b> is not skipped. An operator declines when it cannot establish, for that
case, that its mutant is provably wrong or provably still correct. Those are excluded from the
score rather than guessed at, which is why the denominator is smaller than the attempt count.
</footer>
</div></body></html>"""


def render_html_from_json(text: str, **kw) -> str:
    return render_html(json.loads(text), **kw)
