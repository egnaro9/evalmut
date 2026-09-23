"""Emit a finding when a grader's behaviour drifts under evalmut.

evalmut is deterministic: point it at the same suite with the same gradecore
and it returns the same holes forever. That makes it useless as a schedule and
excellent as a tripwire, because any change in the result means something
underneath it moved.

CI pins `gradecore==0.10.2` on purpose, with the comment "a newer gradecore
that widens a grader would (rightly) change the findings". This does the
opposite deliberately: it runs the same ported suites against gradecore's
CURRENT main and reports when the hole set diverges from the committed
baseline. A grader that quietly widened is exactly the thing an eval owner
needs told, and it is news the day it happens rather than the day someone
notices.

Writes notes/findings.json, which model-drift reads and turns into a draft
post. Emits an EMPTY findings list when nothing moved: a quiet week is a
result, not a gap, and an emitter that always has something to say is the
failure mode this whole pipeline exists to avoid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCHEMA = "drift-notes/finding@1"

# Each target is a faithful port of a shipped framework's deterministic
# assertions. The name is the framework, because that is what a reader cares
# about: the finding is about promptfoo's checks, not about our port of them.
TARGETS = [
    {"key": "promptfoo", "suite": "external/promptfoo_suite.py",
     "label": "promptfoo's deterministic assertions"},
    {"key": "deepeval", "suite": "external/deepeval_suite.py",
     "label": "deepeval's deterministic metrics"},
    {"key": "autoevals", "suite": "external/autoevals_suite.py",
     "label": "autoevals' deterministic scorers"},
]

Hole = Tuple[str, str, str, str]


def run_suite(suite: str, python: str = sys.executable) -> Dict[str, Any]:
    """One evalmut run, as JSON.

    The exit code is NOT the error signal here. evalmut returns 1 when the
    suite has serious holes (cli.py: `return 1 if (incomplete or serious or
    baseline_failures) else 0`), which is a valid and in fact expected result:
    finding holes is what it is for. Treating that as a crash would make every
    real result look like a broken job, and would make a genuinely broken job
    indistinguishable from a working one.

    So the result is whatever parses as JSON on stdout, and only a run that
    produced no parseable JSON is an error. Those are the sys.exit() paths -
    a missing file, a suite that will not import - and they are findings about
    us rather than about the target.
    """
    proc = subprocess.run(
        [python, "-m", "evalmut.cli", "run", suite, "--json", "--all"],
        capture_output=True, text=True, env={**_env(), "PYTHONPATH": ".:external"})
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        detail = (proc.stderr.strip() or proc.stdout.strip() or "no output")[:300]
        raise RuntimeError(f"{suite} produced no result (exit {proc.returncode}): {detail}")


def _env() -> Dict[str, str]:
    import os
    return dict(os.environ)


def holes_of(result: Dict[str, Any]) -> Set[Hole]:
    """The identity of a hole: which case, which grader, which operator, which class.

    Not the count. Two runs can both report "6 holes" with a different six, and
    a count-only comparison would call that unchanged.
    """
    out: Set[Hole] = set()
    for kind, rows in (result.get("holes") or {}).items():
        for h in rows or []:
            out.add((str(h.get("case_name", "")), str(h.get("grader_id", "")),
                     str(h.get("operator_id", "")), str(kind)))
    return out


def _fingerprint(target: str, holes: Set[Hole]) -> str:
    """Stable id for a hole SET, so the same drift is not reported every week.

    The run_key is the state arrived at, not the date it was noticed. That is
    the same identity rule the model-drift detector uses, for the same reason:
    a standing condition re-derives forever and would be re-reported forever.
    """
    blob = "\n".join("|".join(h) for h in sorted(holes))
    return f"{target}@{hashlib.sha256(blob.encode()).hexdigest()[:16]}"


def _describe(h: Hole) -> str:
    case, grader, op, kind = h
    return f"{grader} on `{case}` under `{op}` ({kind})"


def compare(target: Dict[str, str], baseline: Dict[str, Any],
            current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A finding, or None when nothing moved."""
    was, now = holes_of(baseline), holes_of(current)
    opened, closed = sorted(now - was), sorted(was - now)
    if not opened and not closed:
        return None

    label = target["label"]
    if opened and closed:
        head = (f"{len(opened)} hole(s) opened and {len(closed)} closed in "
                f"{label} under the current gradecore")
    elif opened:
        head = (f"{len(opened)} new hole(s) in {label}: a planted defect now "
                f"walks past checks that used to catch it")
    else:
        head = f"{len(closed)} hole(s) closed in {label} under the current gradecore"

    evidence: List[Dict[str, str]] = [
        {"claim": f"the baseline recorded {len(was)} hole(s) in {label}",
         "how": f"notes/baselines/{target['key']}.json, mutation score "
                f"{baseline.get('score', 0):.1%}"},
        {"claim": f"the current run records {len(now)}",
         "how": f"evalmut run {target['suite']} --json --all, mutation score "
                f"{current.get('score', 0):.1%}"},
    ]
    for h in opened[:4]:
        evidence.append({"claim": "a check that used to catch a planted defect no longer does",
                         "how": _describe(h)})
    for h in closed[:4]:
        evidence.append({"claim": "a check that used to miss a planted defect now catches it",
                         "how": _describe(h)})
    evidence.append({
        "claim": "the run is deterministic, so this is a real change and not sampling",
        "how": "no model in the loop; evalmut plants a known defect and asks which "
               "graders stayed green"})

    return {
        "kind": "grader-drift",
        # A hole in a grader is a fact about the checking layer, never about a
        # model. Filing it under models would be the exact category error the
        # receiving pipeline refuses.
        "about": "harness",
        "subject": target["key"],
        "headline": head,
        "run_key": [_fingerprint(target["key"], now)],
        "evidence": evidence,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baselines", default="notes/baselines")
    ap.add_argument("--out", default="notes/findings.json")
    ap.add_argument("--update-baselines", action="store_true",
                    help="write the current results as the new baseline")
    ap.add_argument("--stamp", default="", help="ISO date for the emitted file")
    a = ap.parse_args(argv)

    base_dir = Path(a.baselines)
    base_dir.mkdir(parents=True, exist_ok=True)
    findings, problems = [], []

    for t in TARGETS:
        if not Path(t["suite"]).exists():
            problems.append(f"{t['key']}: {t['suite']} not found")
            continue
        try:
            current = run_suite(t["suite"])
        except Exception as e:  # noqa: BLE001 - the reason travels
            problems.append(f"{t['key']}: {type(e).__name__}: {str(e)[:200]}")
            continue

        bpath = base_dir / f"{t['key']}.json"
        if not bpath.exists():
            # First sight of a target is not a finding. There is nothing to
            # have drifted from, and calling a baseline a discovery is how a
            # tripwire turns into an announcement.
            bpath.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
            print(f"  {t['key']}: baseline written, {len(holes_of(current))} hole(s)")
            continue

        baseline = json.loads(bpath.read_text(encoding="utf-8"))
        f = compare(t, baseline, current)
        if f:
            findings.append(f)
            print(f"  {t['key']}: DRIFT — {f['headline']}")
        else:
            print(f"  {t['key']}: unchanged, {len(holes_of(current))} hole(s)")
        if a.update_baselines:
            bpath.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")

    for p in problems:
        print(f"  PROBLEM: {p}")

    payload: Dict[str, Any] = {"schema": SCHEMA, "source": "evalmut", "findings": findings}
    if a.stamp:
        payload["generated"] = a.stamp
    if problems:
        payload["problems"] = problems
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    print(f"\n{len(findings)} finding(s) written to {a.out}"
          + ("" if findings else " — nothing drifted, which is a result"))
    # Always 0. A quiet week is the expected outcome and must not read as a
    # broken job.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
