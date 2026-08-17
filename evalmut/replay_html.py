"""A watchable replay of a run that already happened.

WHY THIS EXISTS. The report page hands you a finished verdict. That is right for a reader who
wants the answer, and wrong for someone deciding whether to trust the tool, because the single
most suspicious number in an evalmut report is `n/a: 223`. Read cold it looks like the tool
skipped 83% of its work. It is the opposite: an operator declines when it cannot PROVE, for that
case, that its mutation makes the output wrong or leaves it right. Watching that happen, case by
case, is the difference between a claim about rigour and a demonstration of it.

IT IS A REPLAY AND IT SAYS SO. Every row rendered here came from a real run's JSON export. The
page steps through those rows on a timer; it does not execute a grader, does not call a model, and
cannot discover anything the run did not already find. That is stated on the page itself, not just
here, because an interface that paces work theatrically while implying live computation is lying
about where its numbers came from, and this tool would have no standing to make that mistake.

The pacing is honest in the other direction too: real per-mutation timings are not available in
the export, so the replay uses a fixed cadence and says that rather than inventing durations that
would read as measurements.

THIS PAGE CARRIES SCRIPT, DELIBERATELY, AND THE REPORT STILL DOES NOT. `report_html.py` is a
receipt: one file, opens offline, archivable, provably inert, and its tests enforce that. Stepping
through 269 rows needs a runtime. Rather than compromise the receipt, the two are separate
artifacts with separate promises. The script here is inline, touches no network, and reads only
data embedded in the same file.
"""
from __future__ import annotations

import html
import json
from typing import Any

_OUTCOME_META = {
    "caught": ("caught", "--cool", "the grader rejected the mutant, which is correct"),
    "missed": ("MISSED", "--hot", "the grader passed a genuinely wrong output"),
    "flagged": ("FLAGGED", "--warn", "the grader failed an output that was still correct"),
    "error": ("ERROR", "--hot", "the grader raised and produced no verdict"),
    "na": ("declined", "--fg-faint",
           "the operator could not prove this mutant's polarity here, so it refused to guess"),
}


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def render_replay_html(payload: dict, *, title: str = "evalmut replay") -> str:
    rows = payload.get("results") or []
    if not rows:
        raise ValueError("replay needs per-row results: export with --json --all")

    steps = [{"c": r.get("case_name"), "o": r.get("operator_id"), "f": r.get("family"),
              "p": r.get("polarity"), "out": r.get("outcome"),
              "d": (r.get("detail") or "")[:150],
              "m": (r.get("mutant_preview") or "")[:220]} for r in rows]
    tally = payload.get("tally") or {}
    cases = sorted({s["c"] for s in steps})
    data = json.dumps({"steps": steps, "tally": tally, "cases": cases,
                       "score": payload.get("score")}, separators=(",", ":"))

    legend = "".join(
        f'<span class="lg"><i style="background:var({v[1]})"></i>{_e(v[0])}</span>'
        for v in _OUTCOME_META.values())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title>
<style>
:root{{color-scheme:dark light;--ink:#0e1316;--panel:#141c21;--raised:#1b252b;
--line:rgba(255,255,255,.09);--line-2:rgba(255,255,255,.05);
--fg:#dae2e4;--fg-dim:#8a989e;--fg-faint:#5e6c72;
--amber:#f2a53c;--amber-soft:rgba(242,165,60,.13);--amber-line:rgba(242,165,60,.34);
--teal:#48c1ac;--hot:#e0785f;--warn:#f2a53c;--cool:#48c1ac;
--mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;--maxw:880px}}
@media (prefers-color-scheme:light){{:root:not([data-theme=dark]){{
--ink:#e9edee;--panel:#f4f6f6;--raised:#fff;--line:rgba(12,26,32,.12);--line-2:rgba(12,26,32,.07);
--fg:#131c20;--fg-dim:#4d5a60;--fg-faint:#7c888d;--amber:#b7761a;--teal:#1c8f7d;
--hot:#a8412c;--warn:#b7761a;--cool:#1c8f7d}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ink);color:var(--fg);font:15px/1.55 var(--sans)}}
.wrap{{max-width:var(--maxw);margin:0 auto;padding:2.25rem 1.25rem 4rem}}
.shell{{display:flex;align-items:baseline;gap:.75rem;flex-wrap:wrap;
border-bottom:1px solid var(--line);padding-bottom:.8rem;margin-bottom:1.4rem}}
.mark{{font-family:var(--mono);font-size:.82rem;color:var(--amber);font-weight:600}}
.sys{{font-family:var(--mono);font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;
color:var(--fg-faint)}}
.replay-note{{background:var(--amber-soft);border:1px solid var(--amber-line);border-radius:3px;
padding:.6rem .8rem;font-size:.8rem;color:var(--fg-dim);margin:0 0 1.5rem}}
.replay-note b{{color:var(--amber)}}
.ctl{{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin:0 0 1.2rem}}
button{{font-family:var(--mono);font-size:.75rem;color:var(--fg);background:var(--panel);
border:1px solid var(--line);border-radius:999px;padding:.35rem .95rem;cursor:pointer}}
button:hover{{border-color:var(--amber-line);color:var(--amber)}}
button[disabled]{{opacity:.4;cursor:default}}
.spd{{font-family:var(--mono);font-size:.72rem;color:var(--fg-faint);margin-left:auto}}
.bar{{height:3px;background:var(--line-2);border-radius:2px;overflow:hidden;margin:0 0 1.3rem}}
.bar i{{display:block;height:100%;width:0;background:var(--amber);transition:width .12s linear}}
.counts{{display:flex;gap:1.4rem;flex-wrap:wrap;font-family:var(--mono);font-size:.8rem;
color:var(--fg-faint);font-variant-numeric:tabular-nums;margin:0 0 1.4rem}}
.counts b{{color:var(--fg)}}
.counts .k{{color:var(--kc)}}
.now{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--kind,var(--line));
border-radius:3px;padding:1rem 1.1rem;min-height:8.5rem;margin:0 0 1.2rem}}
.now .case{{font-family:var(--mono);font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;
color:var(--fg-faint)}}
.now .op{{font-family:var(--mono);font-size:1rem;color:var(--fg);font-weight:600;margin:.25rem 0}}
.now .verdict{{font-family:var(--mono);font-size:.78rem;color:var(--kind);font-weight:700;
text-transform:uppercase;letter-spacing:.08em;margin:.5rem 0 .3rem}}
.now .why{{color:var(--fg-dim);font-size:.83rem}}
.now .mut{{font-family:var(--mono);font-size:.74rem;background:var(--ink);border:1px solid var(--line);
border-radius:2px;padding:.45rem .6rem;color:var(--fg-dim);margin:.6rem 0 0;overflow-x:auto;
white-space:pre-wrap;word-break:break-word}}
.lg{{display:inline-flex;align-items:center;gap:.35rem;font-family:var(--mono);font-size:.68rem;
color:var(--fg-faint);margin-right:.9rem}}
.lg i{{width:.6rem;height:.6rem;border-radius:2px;display:inline-block}}
.log{{max-height:17rem;overflow-y:auto;border-top:1px solid var(--line);margin-top:1.4rem;
padding-top:.6rem;font-family:var(--mono);font-size:.72rem}}
.log div{{display:flex;gap:.6rem;padding:.15rem 0;color:var(--fg-faint)}}
.log .r{{color:var(--kind);font-weight:600;min-width:4.6rem}}
.log .c{{min-width:9rem;color:var(--fg-dim)}}
footer{{margin-top:2rem;padding-top:1rem;border-top:1px solid var(--line);color:var(--fg-faint);
font-size:.76rem;line-height:1.6}}
</style></head><body><div class="wrap">
<div class="shell"><span class="mark">evalmut</span>
<span class="sys">eval suite &middot; replay</span></div>

<p class="replay-note"><b>This is a replay, not a live run.</b> Every row below came from a run
that already finished; this page steps through its exported rows on a fixed cadence. It executes
no grader and calls no model, so it cannot find anything the run did not. Real per-mutation
timings are not in the export, so the pacing is arbitrary and is not a measurement.</p>

<div class="ctl">
<button id="go">Run</button><button id="step">Step</button><button id="rst">Reset</button>
<span class="spd">speed <button id="sp" style="padding:.2rem .6rem">1x</button></span></div>
<div class="bar"><i id="pb"></i></div>

<div class="counts">
<span>applied <b id="c-app">0</b></span>
<span style="--kc:var(--cool)">caught <b class="k" id="c-caught">0</b></span>
<span style="--kc:var(--hot)">missed <b class="k" id="c-missed">0</b></span>
<span>declined <b id="c-na">0</b></span>
<span id="c-pos">0 / 0</span></div>

<div class="now" id="now"><div class="case">ready</div>
<div class="op">press Run to watch the suite work</div>
<div class="why">Each step applies one operator to one case and shows what the grader did.
The declines are the interesting part: that is the tool refusing to guess.</div></div>

<div>{legend}</div>
<div class="log" id="log"></div>

<footer>Replay of a real export. The report page is the receipt and carries nothing executable;
this page needs a runtime to step, so the two are separate artifacts with separate promises. The
script here is inline, touches no network, and reads only the data embedded in this file.</footer>
</div>
<script id="d" type="application/json">{data}</script>
<script>
const D=JSON.parse(document.getElementById('d').textContent);
const META={json.dumps({k: [v[0], v[1], v[2]] for k, v in _OUTCOME_META.items()})};
let i=0,timer=null,spd=1;
const $=id=>document.getElementById(id);
const n={{caught:0,missed:0,flagged:0,error:0,na:0}};
function paint(s){{
  const m=META[s.out]||['?','--fg-faint',''];
  const now=$('now');
  now.style.setProperty('--kind','var('+m[1]+')');
  now.innerHTML='<div class="case">'+s.c+'  &middot;  '+(s.f||'')+' / '+(s.p||'')+'</div>'+
    '<div class="op">'+s.o+'</div>'+
    '<div class="verdict">'+m[0]+'</div>'+
    '<div class="why">'+m[2]+'</div>'+
    (s.m?'<div class="mut">'+s.m+'</div>':'');
  const l=document.createElement('div');
  l.innerHTML='<span class="r" style="--kind:var('+m[1]+')">'+m[0]+'</span>'+
    '<span class="c">'+s.c+'</span><span>'+s.o+'</span>';
  $('log').prepend(l);
  n[s.out]=(n[s.out]||0)+1;
  const applied=n.caught+n.missed+n.flagged+n.error;
  $('c-app').textContent=applied; $('c-caught').textContent=n.caught;
  $('c-missed').textContent=n.missed; $('c-na').textContent=n.na;
  $('c-pos').textContent=(i)+' / '+D.steps.length;
  $('pb').style.width=(100*i/D.steps.length)+'%';
}}
function step(){{ if(i>=D.steps.length){{stop();return;}} paint(D.steps[i++]); }}
function stop(){{ clearInterval(timer); timer=null; $('go').textContent='Run'; }}
$('go').onclick=()=>{{ if(timer){{stop();return;}} $('go').textContent='Pause';
  timer=setInterval(step, 90/spd); }};
$('step').onclick=()=>{{ stop(); step(); }};
$('rst').onclick=()=>{{ stop(); i=0; for(const k in n)n[k]=0; $('log').innerHTML='';
  $('c-app').textContent=0;$('c-caught').textContent=0;$('c-missed').textContent=0;
  $('c-na').textContent=0;$('c-pos').textContent='0 / '+D.steps.length;$('pb').style.width='0';
  // Reset the CARD too. Zeroing the counters while the last verdict stayed on screen read as
  // a run that had just finished with nothing counted, which is a state that cannot happen.
  const nw=$('now'); nw.style.removeProperty('--kind');
  nw.innerHTML='<div class="case">ready</div>'+
    '<div class="op">press Run to watch the suite work</div>'+
    '<div class="why">Each step applies one operator to one case and shows what the grader did. '+
    'The declines are the interesting part: that is the tool refusing to guess.</div>'; }};
$('sp').onclick=()=>{{ spd=spd===1?4:spd===4?16:1; $('sp').textContent=spd+'x';
  if(timer){{clearInterval(timer);timer=setInterval(step,90/spd);}} }};
$('c-pos').textContent='0 / '+D.steps.length;
</script></body></html>"""
