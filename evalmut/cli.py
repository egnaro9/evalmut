"""`evalmut` — point it at an eval suite and see what its checks don't check.

    evalmut run path/to/suite.py        # run mutations, print the report
    evalmut run suite.py --json         # machine-readable results
    evalmut run suite.py --short        # one line, for CI
    evalmut operators                   # list the mined catalog, each with its provenance

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
from .runner import MutationResult


def _load_suite(path: str):
    p = Path(path).resolve()
    if not p.exists():
        sys.exit(f"evalmut: no such suite file: {path}")
    spec = importlib.util.spec_from_file_location("_evalmut_suite", p)
    if spec is None or spec.loader is None:
        sys.exit(f"evalmut: cannot load suite from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "suite"):
        sys.exit(f"evalmut: {path} must define `suite` (a list of EvalCase)")
    return list(mod.suite), (list(mod.operators) if hasattr(mod, "operators") else None)


def _result_dict(r: MutationResult) -> dict:
    d = dataclasses.asdict(r)
    d["polarity"] = r.polarity.value
    d["op_type"] = r.op_type.value
    d["outcome"] = r.outcome.value
    return d


def _cmd_run(args) -> int:
    suite, operators = _load_suite(args.suite)
    report = run(suite, operators)

    if args.json:
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
        print(json.dumps(payload, indent=2))
    elif args.short:
        print(render_short(report))
    else:
        print(render(report, verbose=args.verbose))

    # CI gate: coverage-gaps alone do not fail (they name missing graders, not broken
    # ones); vacuous / blind / error / brittle do.
    serious = (report.vacuous or report.blind_spots or report.errors
               or report.brittle_spots)
    return 1 if (serious or getattr(report, "baseline_failures", ())) else 0


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
    r.set_defaults(fn=_cmd_run)

    o = sub.add_parser("operators", help="list the mined operator catalog")
    o.add_argument("--json", action="store_true")
    o.set_defaults(fn=_cmd_operators)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
