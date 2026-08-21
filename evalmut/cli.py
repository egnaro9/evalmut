"""`evalmut` — point it at an eval suite and see what its checks don't check.

    evalmut run path/to/suite.py        # run mutations, print the report
    evalmut run suite.py --json         # machine-readable results
    evalmut run suite.py --short        # one line, for CI
    evalmut operators                   # list the mined catalog, each with its provenance
    evalmut witness suite.py --json     # same rows, plus per-row proof the grader ran

A suite module exposes `suite` (a list of EvalCase) and optionally `operators`
(a list of MutationOperator; defaults to the full mined catalog).

Exit code: 0 if clean or only coverage-gaps; 1 if any vacuous / blind / brittle hole —
so a suite that stopped checking things fails CI the way a red test would.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path

from . import catalog, run
from .report import render, render_short
from .manifest import diff_against as manifest_diff, suite_manifest
from .diff import diff_runs, headline, score_delta, summarize
from .invocation_witness import render_witness_short, witness_payload
from .replay_html import render_replay_html
from .report_html import render_diff_html, render_html
from .runner import MutationResult


def _load_suite(path: str):
    p = Path(path).resolve()
    if not p.exists():
        sys.exit(f"evalmut: no such suite file: {path}")
    spec = importlib.util.spec_from_file_location("_evalmut_suite", p)
    if spec is None or spec.loader is None:
        sys.exit(f"evalmut: cannot load suite from {path}")
    mod = importlib.util.module_from_spec(spec)
    # Let a suite import sibling modules (a suite.py next to a my_graders.py) and let it self-import:
    # register the module before exec so dataclasses / pickling resolve to this same object.
    sys.path.insert(0, str(p.parent))
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        if not hasattr(mod, "suite"):
            sys.exit(f"evalmut: {path} must define `suite` (a list of EvalCase)")
        return list(mod.suite), (list(mod.operators) if hasattr(mod, "operators") else None)
    except Exception as e:  # a raising import or a non-iterable `suite` shouldn't dump a raw traceback
        sys.exit(f"evalmut: error loading {path}: {type(e).__name__}: {e}")


def _result_dict(r: MutationResult) -> dict:
    d = dataclasses.asdict(r)
    d["polarity"] = r.polarity.value
    d["op_type"] = r.op_type.value
    d["outcome"] = r.outcome.value
    return d


def _cmd_run(args) -> int:
    suite, operators = _load_suite(args.suite)
    report = run(suite, operators)

    if args.json or args.html or args.replay:
        payload = {
            "score": report.score,
            "tally": dataclasses.asdict(report.total),
            "holes": {
                "vacuous": [_result_dict(h) for h in report.vacuous],
                "blind": [_result_dict(h) for h in report.blind_spots],
                "error": [_result_dict(h) for h in report.errors],
                "brittle": [_result_dict(h) for h in report.brittle_spots],
                "coverage_gap": [_result_dict(h) for h in report.coverage_gaps],
            },
            "baseline_failures": [str(b) for b in getattr(report, "baseline_failures", ())],
            "results": [_result_dict(r) for r in report.results] if args.all else None,
        }
        if args.replay:
            Path(args.replay).write_text(render_replay_html(payload), encoding="utf-8")
            print(f"wrote {args.replay}", file=sys.stderr)
        if args.html:
            Path(args.html).write_text(render_html(payload), encoding="utf-8")
            print(f"wrote {args.html}", file=sys.stderr)
        elif args.json:
            print(json.dumps(payload, indent=2))
    elif args.short:
        print(render_short(report))
    else:
        print(render(report, verbose=args.verbose))

    # An empty suite (or one where no operator could apply) produced a 100%/no-holes report
    # above — but nothing was actually mutated or checked, which is the exact lie this tool
    # exists to catch. Fail the gate rather than green-light it.
    if report.total.applied == 0:
        if not args.json:
            print("evalmut: no mutations applied — the suite is empty or no case has a "
                  "mutable, gradeable field. Nothing was checked; this is not a pass.",
                  file=sys.stderr)
        return 1

    # CI gate: coverage-gaps alone do not fail (they name missing graders, not broken
    # ones); vacuous / blind / error / brittle do.
    serious = (report.vacuous or report.blind_spots or report.errors
               or report.brittle_spots)
    return 1 if (serious or getattr(report, "baseline_failures", ())) else 0


def _cmd_witness(args) -> int:
    """Run the suite with a per-row invocation witness on the grader.

    Same rows as `run`, with one extra requirement: a row is counted as an outcome only when the
    clean control and the defective form were both seen entering the grader the suite handed
    evalmut, and both behaved as the contract they ran under declares. Rows that cannot show that
    leave the headline denominator and are listed as INCOMPLETE with the reason.

    Exit code: 1 if any row is INCOMPLETE (evidence is missing and the number moved because of
    it), or on the same serious holes / baseline failures that fail `run`. Missing evidence is a
    failure, never a default.
    """
    suite, operators = _load_suite(args.suite)
    ops = tuple(operators) if operators is not None else catalog()
    payload = witness_payload(suite, ops)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_witness_short(payload))
    holes = payload["holes"]
    serious = holes["vacuous"] or holes["blind"] or holes["error"] or holes["brittle"]
    return 1 if (payload["incomplete"] or serious or payload["baseline_failures"]) else 0


def _cmd_diff(args) -> int:
    """Compare two `evalmut run --json --all` exports."""
    old = json.loads(Path(args.old).read_text(encoding="utf-8"))
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    if not (old.get("results") and new.get("results")):
        sys.exit("evalmut: both exports must include per-row results (run with --json --all). "
                 "A diff from the holes lists alone cannot see a MISSED become n/a, which is "
                 "the transition most worth catching.")
    changes = diff_runs(old, new)
    counts = summarize(changes)
    line = headline(counts)
    scores = score_delta(old, new)
    if args.html:
        Path(args.html).write_text(render_diff_html(changes, counts, line, scores),
                                   encoding="utf-8")
        print(f"wrote {args.html}", file=sys.stderr)
    else:
        print(line)
        if scores[2]:
            print(f"  note: {scores[2]}")
        for c in changes:
            print(f"  {c.label:18} {c.case} / {c.operator}  "
                  f"{c.before or 'absent'} -> {c.after or 'absent'}")
    # A disappearance is a finding, so it fails the gate: a suite that stopped asking is not a
    # suite that improved, and a green exit there would be the laundering this tool exists to stop.
    dodged = counts["no_longer_tested"] + counts["case_removed"]
    return 1 if (dodged or counts["regressed"] or counts["coverage_lost"]) else 0


def _cmd_manifest(args) -> int:
    """Emit, or verify against, the pinned fixture corpus for a suite."""
    suite, _ = _load_suite(args.suite)
    if args.check:
        committed = json.loads(Path(args.check).read_text(encoding="utf-8"))
        reasons = manifest_diff(committed, suite)
        if reasons:
            print(f"evalmut: {args.suite} is NOT the corpus pinned in {args.check}",
                  file=sys.stderr)
            for r in reasons:
                print(f"  {r}", file=sys.stderr)
            print("\n  A fixture edited after a run is a change of subject, not a change of "
                  "code. Re-pin deliberately if the edit is intended.", file=sys.stderr)
            return 1
        print(f"corpus matches {args.check} ({len(suite)} cases)")
        return 0
    print(json.dumps(suite_manifest(suite), indent=2))
    return 0


def _cmd_operators(args) -> int:
    ops = catalog()
    if args.json:
        print(json.dumps([
            {"id": o.id, "family": o.family, "polarity": o.polarity.value,
             "op_type": o.op_type.value, "field": o.field,
             "defect_shape": o.defect_shape, "real_origin": o.real_origin}
            for o in ops], indent=2))
        return 0
    print(f"evalmut — {len(ops)} mined operators (every one names the real defect it reproduces)\n")
    for o in sorted(ops, key=lambda x: (x.family, x.id)):
        print(f"  {o.id}  [{o.family} · {o.polarity.value} · {o.op_type.value} · {o.field}]")
        print(f"      shape : {o.defect_shape}")
        print(f"      mined : {o.real_origin}\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evalmut", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run mutations against a suite file")
    r.add_argument("suite", help="path to a Python file defining `suite`")
    r.add_argument("--json", action="store_true", help="machine-readable output")
    r.add_argument("--short", action="store_true", help="one line, for CI")
    r.add_argument("--all", action="store_true", help="(with --json) include every result, not just holes")
    r.add_argument("-v", "--verbose", action="store_true", help="per-grader table + mutant previews")
    r.add_argument("--replay", metavar="FILE",
                   help="write a watchable step-by-step replay of this run (carries script)")
    r.add_argument("--html", metavar="FILE",
                   help="write a standalone read-only HTML rendering of this run")
    r.set_defaults(fn=_cmd_run)

    wt = sub.add_parser("witness", help="run with a per-row proof the grader was actually entered")
    wt.add_argument("suite", help="path to a Python file defining `suite`")
    wt.add_argument("--json", action="store_true", help="machine-readable output (all rows)")
    wt.set_defaults(fn=_cmd_witness)

    o = sub.add_parser("operators", help="list the mined operator catalog")
    o.add_argument("--json", action="store_true")
    o.set_defaults(fn=_cmd_operators)

    m = sub.add_parser("manifest", help="emit or verify a suite's pinned fixture corpus")
    m.add_argument("suite")
    m.add_argument("--check", metavar="FILE",
                   help="verify the suite still matches this committed manifest (exit 1 if not)")
    m.set_defaults(fn=_cmd_manifest)

    d = sub.add_parser("diff", help="what changed between two run exports")
    d.add_argument("old"); d.add_argument("new")
    d.add_argument("--html", metavar="FILE", help="write a standalone HTML rendering")
    d.set_defaults(fn=_cmd_diff)

    # The report uses box-drawing / warning glyphs; on a non-UTF-8 stdout (Windows cp1252,
    # a redirected CI pipe) printing them would crash with UnicodeEncodeError and lose the
    # whole report. Degrade unrepresentable glyphs to a placeholder instead of dying.
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    if enc not in ("utf-8", "utf8") and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
