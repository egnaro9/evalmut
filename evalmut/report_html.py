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
/* The suite's house tokens, copied verbatim from egnaro9.github.io rather than reinvented.
   These pages are panels of one system and looked like four different products; the point of
   the shell is that a reader recognises the second panel from having seen the first.
   Copied, not fetched: a linked stylesheet would give the page a network dependency and it has
   to open from a file:// path on a machine with no network. Identity without a fetch. */
:root{color-scheme:dark light;
--ink:#0e1316;--panel:#141c21;--raised:#1b252b;
--line:rgba(255,255,255,.09);--line-2:rgba(255,255,255,.05);
--fg:#dae2e4;--fg-dim:#8a989e;--fg-faint:#5e6c72;
--amber:#f2a53c;--amber-soft:rgba(242,165,60,.13);--amber-line:rgba(242,165,60,.34);
--teal:#48c1ac;--teal-soft:rgba(72,193,172,.12);--teal-line:rgba(72,193,172,.34);
--mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
--maxw:880px}
@media (prefers-color-scheme:light){:root:not([data-theme=dark]){
--ink:#e9edee;--panel:#f4f6f6;--raised:#ffffff;
--line:rgba(12,26,32,.12);--line-2:rgba(12,26,32,.07);
--fg:#131c20;--fg-dim:#4d5a60;--fg-faint:#7c888d;
--amber:#b7761a;--amber-soft:rgba(200,128,26,.12);--amber-line:rgba(200,128,26,.4);
--teal:#1c8f7d;--teal-soft:rgba(28,143,125,.1);--teal-line:rgba(28,143,125,.4)}}
:root[data-theme=light]{--ink:#e9edee;--panel:#f4f6f6;--raised:#ffffff;
--line:rgba(12,26,32,.12);--fg:#131c20;--fg-dim:#4d5a60;--fg-faint:#7c888d;
--amber:#b7761a;--amber-soft:rgba(200,128,26,.12);--amber-line:rgba(200,128,26,.4);
--teal:#1c8f7d;--teal-soft:rgba(28,143,125,.1);--teal-line:rgba(28,143,125,.4)}
/* severity is its own scale, not the brand accent: amber is identity, these are state */
:root{--hot:#e0785f;--warn:#f2a53c;--cool:#48c1ac}
@media (prefers-color-scheme:light){:root:not([data-theme=dark]){--hot:#a8412c;--warn:#b7761a;--cool:#1c8f7d}}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--fg);font:15px/1.55 var(--sans);
-webkit-font-smoothing:antialiased}
.wrap{max-width:var(--maxw);margin:0 auto;padding:2.25rem 1.25rem 4rem}
.shell{display:flex;align-items:baseline;gap:.75rem;flex-wrap:wrap;
border-bottom:1px solid var(--line);padding-bottom:.8rem;margin-bottom:1.6rem}
.shell .mark{font-family:var(--mono);font-size:.82rem;letter-spacing:.02em;color:var(--amber);
font-weight:600}
.shell .sys{font-family:var(--mono);font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;
color:var(--fg-faint)}
.shell nav{margin-left:auto;display:flex;gap:.9rem;flex-wrap:wrap}
.shell nav a{font-family:var(--mono);font-size:.72rem;color:var(--fg-faint);text-decoration:none;
border-bottom:1px solid transparent;padding-bottom:1px}
.shell nav a:hover{color:var(--amber);border-bottom-color:var(--amber-line)}
.shell nav a[aria-current]{color:var(--fg);border-bottom-color:var(--amber)}
h1{font-size:1.05rem;font-weight:600;letter-spacing:.02em;margin:0 0 .15rem;color:var(--fg-dim)}
.sub{color:var(--fg-faint);font-size:.82rem;margin:0 0 1.9rem}
.verdict{font-size:1.95rem;line-height:1.2;font-weight:650;letter-spacing:-.02em;margin:0 0 .5rem}
.verdict .n{color:var(--hot)}
.verdict.clean .n{color:var(--cool)}
.context{color:var(--fg-dim);font-size:.92rem;margin:0 0 2rem;max-width:46rem}
.context b{color:var(--fg);font-weight:600}
.tally{display:flex;flex-wrap:wrap;gap:.4rem 1.6rem;font-family:var(--mono);font-size:.8rem;
color:var(--fg-faint);border-top:1px solid var(--line);padding-top:.9rem;margin-bottom:2.25rem;
font-variant-numeric:tabular-nums}
.tally b{color:var(--fg);font-weight:600}
h2{font-size:.72rem;text-transform:uppercase;letter-spacing:.13em;color:var(--fg-faint);
font-weight:600;margin:2.25rem 0 .9rem;border-bottom:1px solid var(--line);padding-bottom:.5rem}
.hole{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--kind);
border-radius:3px;padding:1rem 1.1rem;margin-bottom:.7rem}
.hkind{display:inline-flex;align-items:center;gap:.45rem;font-family:var(--mono);font-size:.7rem;
text-transform:uppercase;letter-spacing:.1em;color:var(--kind);font-weight:700}
.hkind .g{display:inline-grid;place-items:center;width:1.05rem;height:1.05rem;border-radius:2px;
background:var(--kind);color:var(--ink);font-size:.66rem}
.hmeans{color:var(--fg-faint);font-size:.78rem;margin:.45rem 0 .8rem;text-transform:none;
letter-spacing:0;font-weight:400}
.hid{font-family:var(--mono);font-size:.92rem;color:var(--fg);font-weight:600;word-break:break-word}
.hcase{font-family:var(--mono);font-size:.76rem;color:var(--fg-faint);margin:.2rem 0 .75rem}
.shape{color:var(--fg-dim);font-size:.88rem;margin:0 0 .8rem}
.mut{font-family:var(--mono);font-size:.76rem;background:var(--ink);border:1px solid var(--line);
border-radius:2px;padding:.5rem .6rem;color:var(--fg-dim);overflow-x:auto;white-space:pre-wrap;
word-break:break-word;margin:0 0 .8rem}
.mut .lbl{color:var(--fg-faint);display:block;font-size:.66rem;text-transform:uppercase;
letter-spacing:.1em;margin-bottom:.3rem}
details.prov{border-top:1px dashed var(--line);padding-top:.6rem}
details.prov summary{cursor:pointer;color:var(--fg-faint);font-size:.74rem;letter-spacing:.04em}
details.prov summary:hover{color:var(--amber)}
.prov p{color:var(--fg-dim);font-size:.8rem;line-height:1.6;margin:.6rem 0 0;word-break:break-word}
.fix{color:var(--fg-dim);font-size:.8rem;margin:.6rem 0 0}
.fix b{color:var(--fg)}
.none{color:var(--fg-faint);font-size:.88rem;font-style:italic}
table{width:100%;border-collapse:collapse;font-size:.78rem;font-family:var(--mono)}
th{text-align:left;color:var(--fg-faint);font-weight:600;font-size:.68rem;text-transform:uppercase;
letter-spacing:.09em;border-bottom:1px solid var(--line);padding:.45rem .5rem}
td{padding:.4rem .5rem;border-bottom:1px solid var(--line-2);color:var(--fg-dim)}
td.o{font-weight:600}
.wrapx{overflow-x:auto}
/* Scriptless filter: radio inputs plus sibling selectors. The page must open from a file:// path
   on a machine with no network, and executable markup is the one thing this renderer will not
   ship, so the interaction is CSS. (The comment avoids naming that tag literally, because the
   self-contained test scans for the string.) */
.filt{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 1.4rem}
.filt input{position:absolute;opacity:0;width:0;height:0}
.filt label{font-family:var(--mono);font-size:.72rem;letter-spacing:.04em;color:var(--fg-faint);
border:1px solid var(--line);border-radius:999px;padding:.25rem .7rem;cursor:pointer;
background:var(--panel);user-select:none}
.filt label:hover{color:var(--amber);border-color:var(--amber-line)}
.filt input:focus-visible+label{outline:2px solid var(--amber);outline-offset:2px}
.filt input:checked+label{color:var(--ink);background:var(--amber);border-color:var(--amber)}
.filt b{font-variant-numeric:tabular-nums}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line);color:var(--fg-faint);
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
    return f"""<div class="hole" data-fam="{_e(h.get('family') or 'other')}" style="--kind:var({_KIND_VAR[kind]})">
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

    # Filter chips, one per operator family present among the HOLES. Families with no hole are
    # omitted rather than shown empty: a chip that can only ever yield nothing is a dead control.
    fams: dict[str, int] = {}
    for kind in ORDER:
        for h in holes.get(kind, []) or []:
            f = h.get("family") or "other"
            fams[f] = fams.get(f, 0) + 1
    filt = ""
    if len(fams) > 1:
        chips = [('<input type="radio" name="fam" id="fam-all" checked>'
                  f'<label for="fam-all">all <b>{total}</b></label>')]
        rules = []
        for i, (f, n) in enumerate(sorted(fams.items())):
            fid = f"fam-{i}"
            chips.append(f'<input type="radio" name="fam" id="{fid}">'
                         f'<label for="{fid}">{_e(f)} <b>{n}</b></label>')
            # :has() rather than a sibling combinator. The first version used `~ .holes` and
            # every unit test passed while clicking a chip hid nothing, because the inputs sit
            # INSIDE .filt and are therefore not siblings of the list. :has() is scoped from the
            # root and does not care where the input lives.
            rules.append(f'body:has(#{fid}:checked) .hole:not([data-fam="{_e(f)}"])'
                         f'{{display:none}}'
                         f'body:has(#{fid}:checked) .holes h2{{display:none}}')
        filt = (f'<div class="filt">{"".join(chips)}</div>'
                f"<style>{''.join(rules)}</style>")
        sections = [f'<div class="holes">{"".join(sections)}</div>']

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
{filt}
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


# ── run-over-run diff ────────────────────────────────────────────────────────

_DIFF_KIND_VAR = {"fixed": "--cool", "regressed": "--hot", "no_longer_tested": "--hot",
                  "case_removed": "--hot", "coverage_lost": "--warn",
                  "still_open": "--ink3", "newly_tested": "--ink3"}
_DIFF_ORDER = ["no_longer_tested", "case_removed", "regressed", "coverage_lost",
               "fixed", "still_open", "newly_tested"]


def render_diff_html(changes, counts, line, scores, *, title="evalmut diff") -> str:
    """Render a run-over-run diff. Suspicious transitions come FIRST, above the fixes.

    Ordering is the argument. A reader scanning top-down should meet 'these stopped being tested'
    before 'these were fixed', because the first can explain the second away and the reverse
    reading is how a suite congratulates itself."""
    from .diff import TRANSITIONS
    old_s, new_s, note = scores
    fmt = lambda v: f"{v:.1%}" if isinstance(v, (int, float)) else _e(v)

    groups = []
    for kind in _DIFF_ORDER:
        rows = [c for c in changes if c.kind == kind]
        if not rows:
            continue
        label, _prog, susp, means = TRANSITIONS[kind]
        cards = "".join(
            f'<div class="hole" style="--kind:var({_DIFF_KIND_VAR[kind]})">'
            f'<div class="hid">{_e(c.operator)}</div>'
            f'<div class="hcase">case <b>{_e(c.case)}</b> &middot; '
            f'{_e(c.before or "absent")} &rarr; {_e(c.after or "absent")}</div></div>'
            for c in rows)
        groups.append(
            f'<h2>{_e(label)} &middot; {len(rows)}{" &middot; worth a look" if susp else ""}</h2>'
            f'<p class="context" style="margin-bottom:.9rem">{_e(means)}</p>{cards}')

    warn = (f'<p class="context" style="color:var(--warn)"><b>Scores are not comparable here.</b> '
            f'{_e(note)}</p>' if note else "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>evalmut</h1><p class="sub">what changed between two runs</p>
<p class="verdict">{_e(line)}</p>
<div class="tally"><span>score before <b>{fmt(old_s)}</b></span>
<span>score after <b>{fmt(new_s)}</b></span>
<span>transitions <b>{len(changes)}</b></span></div>
{warn}
{"".join(groups) or '<p class="none">Nothing moved.</p>'}
<footer>Keyed on (case, operator), which is the identity of the QUESTION being asked; the outcome
is the answer. Mutant text and detail strings change for innocent reasons and are ignored, so
churn is not reported as change.<br><br>
A hole can leave a report because the check now catches it, or because the operator stopped
applying. Both shrink the hole count and lift the score. They are never merged here.</footer>
</div></body></html>"""
