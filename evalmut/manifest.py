"""A hash of the fixture corpus a suite runs on, so the corpus is pinned rather than described.

WHAT THIS DOES AND DOES NOT FIX. evalmut's headline results were produced against fixtures
authored by people who could observe the scorers while writing them. That is a real weakness
(deviation D1 in the handoff), and no hash retires it: hashing a co-adapted corpus gives you a
co-adapted corpus with a checksum. What the manifest fixes is the NEXT weakness along, which is
that nothing stopped the corpus from moving afterwards. A fixture quietly reworded after a
disappointing run, a case dropped because it kept failing, an `expected` nudged until a grader
agreed: all of that was previously invisible, because only the OPERATORS were pinned and the
inputs they ran against were not. Freeze the corpus and every later edit becomes a visible diff
in a committed artifact instead of a silent change of subject.

So: this makes fixture selection AUDITABLE from here on. It does not make the existing fixtures
independent, and a reviewer should keep discounting the current numbers for D1 exactly as before.

WHAT IS HASHED. The data that defines the case as an input: its name, the reference output in
every field a mutation can touch, and every declared contract bar. Declarations are included
deliberately and are the subtle half. `num_tol`, `tolerates`, `expected_trajectory`,
`trajectory_threshold`, `content_required`, `grader_family`, `verdict_channel` are what let an
operator claim a mutant is provably wrong or provably still correct, so widening one is a way to
change what counts as a defect without touching a single fixture. A manifest blind to
declarations would certify a corpus whose meaning had been rewritten underneath it.

WHAT IS NOT HASHED. The grader itself, because it is a live function object with no stable
identity across processes. That is a real gap and it is named here rather than papered over: this
manifest pins the INPUTS, not the checks. The checks are pinned separately, by the suite file's
own sha256 in the VAC bundle's protocol.hashes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .case import EvalCase

# Every declared bar that can change what an operator considers provable. Kept as an explicit
# list rather than "all dataclass fields" so that adding a field to EvalCase is a deliberate
# decision about whether it belongs in the corpus identity, not an accident of introspection.
DECLARED_BARS = (
    "judges", "num_tol", "content_required", "tolerates", "expected_trajectory",
    "trajectory_threshold", "grader_family", "verdict_channel", "tags",
)


def _canonical(value: Any) -> Any:
    """Stable JSON-able form. Tuples and lists collapse to lists, since a suite author writing a
    tuple or a list means the same corpus and should not produce a different digest."""
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def case_fixture(case: EvalCase) -> dict:
    """The case as INPUT DATA: everything a mutation reads or a declaration governs."""
    good = case.good
    return {
        "name": case.name,
        "good": {
            "text": _canonical(getattr(good, "text", None)),
            "expected": _canonical(getattr(good, "expected", None)),
            "contexts": _canonical(getattr(good, "contexts", None)),
            "tool_calls": _canonical(getattr(good, "tool_calls", None)),
        },
        "declared": {bar: _canonical(getattr(case, bar, None)) for bar in DECLARED_BARS},
    }


def case_digest(case: EvalCase) -> str:
    blob = json.dumps(case_fixture(case), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def suite_manifest(suite: Iterable[EvalCase]) -> dict:
    """The pinned corpus. `corpus_sha256` covers the ordered per-case digests, so reordering the
    suite moves it too: order decides which case an operator meets first and, for a stateful
    grader, what it has already seen."""
    cases = [{"name": c.name, "sha256": case_digest(c), "fixture": case_fixture(c)}
             for c in suite]
    spine = json.dumps([c["sha256"] for c in cases], separators=(",", ":"))
    return {
        "manifest_version": 1,
        "case_count": len(cases),
        "corpus_sha256": hashlib.sha256(spine.encode("utf-8")).hexdigest(),
        "cases": cases,
    }


def diff_against(committed: dict, suite: Iterable[EvalCase]) -> list[str]:
    """Human-readable reasons the live suite is not the committed corpus. Empty means identical.

    Reports ADDED, REMOVED and CHANGED separately rather than a single boolean, because the three
    mean different things to a reviewer: a removal after a bad run is the one worth staring at."""
    live = suite_manifest(suite)
    if live["corpus_sha256"] == committed.get("corpus_sha256"):
        return []
    was = {c["name"]: c["sha256"] for c in committed.get("cases", [])}
    now = {c["name"]: c["sha256"] for c in live["cases"]}
    out = []
    for name in was:
        if name not in now:
            out.append(f"REMOVED case {name!r} (was in the committed corpus)")
    for name in now:
        if name not in was:
            out.append(f"ADDED case {name!r} (not in the committed corpus)")
        elif was[name] != now[name]:
            out.append(f"CHANGED case {name!r}: fixture or a declared bar was edited")
    if not out:
        out.append("case ORDER changed: same cases, different sequence")
    return out
