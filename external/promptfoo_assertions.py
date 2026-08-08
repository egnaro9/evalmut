"""Faithful ports of promptfoo's DETERMINISTIC (non-LLM) assertions into gradecore's
`GradeInput -> Verdict` shape, so evalmut can mutation-test the assertions a real, widely-used
eval tool ships.

Source of truth: promptfoo docs, /configuration/expected-outputs/deterministic/ (fetched 2026-08-08).
Each grader below reproduces promptfoo's DOCUMENTED rule exactly; where promptfoo diverges from the
same-named gradecore grader, the divergence is noted, because a mis-port would manufacture findings
that are artifacts of our code rather than facts about promptfoo. The `grader_id` a grader carries is
its CONTRACT classification (what family of check it is), not a cosmetic label — evalmut's operators
key some behavior off it, so a grader gets a gradecore family id ONLY when its contract is identical
to that family's.
"""
from __future__ import annotations

import json
import re

from gradecore import GradeInput, Verdict


def _v(ok: bool, gid: str, detail: str) -> Verdict:
    return Verdict(passed=ok, score=1.0 if ok else 0.0,
                   severity="none" if ok else "med", detail=detail, grader_id=gid)


# ── string matching ──────────────────────────────────────────────────────────

def pf_equals(expected: str):
    """promptfoo `equals`: output matches expected EXACTLY. Case-sensitive, whitespace PRESERVED
    (no strip). Divergence: gradecore `exact` strips+lowercases and `exact_cs` strips — promptfoo
    does neither, so `pf_equals` is byte-exact. Own grader_id (not `exact`/`exact_cs`)."""
    def g(inp: GradeInput) -> Verdict:
        return _v((inp.text or "") == expected, "pf_equals", f"exact-match {expected!r}")
    return g


def pf_contains(needle: str):
    """promptfoo `contains`: substring test, CASE-SENSITIVE. Divergence: gradecore `contains`
    lowercases both sides. Kept case-sensitive here to match promptfoo; own grader_id."""
    def g(inp: GradeInput) -> Verdict:
        return _v(needle in (inp.text or ""), "pf_contains", f"contains {needle!r} (case-sensitive)")
    return g


def pf_icontains(needle: str):
    """promptfoo `icontains`: case-insensitive substring — identical to gradecore `contains`."""
    def g(inp: GradeInput) -> Verdict:
        return _v(needle.lower() in (inp.text or "").lower(), "pf_icontains", f"icontains {needle!r}")
    return g


def pf_contains_all(*needles: str):
    """promptfoo `contains-all`: every value present (case-sensitive)."""
    def g(inp: GradeInput) -> Verdict:
        t = inp.text or ""
        return _v(all(n in t for n in needles), "pf_contains_all", f"contains all {list(needles)}")
    return g


def pf_contains_any(*needles: str):
    """promptfoo `contains-any`: at least one value present (case-sensitive)."""
    def g(inp: GradeInput) -> Verdict:
        t = inp.text or ""
        return _v(any(n in t for n in needles), "pf_contains_any", f"contains any {list(needles)}")
    return g


def pf_starts_with(prefix: str):
    """promptfoo `starts-with`: output begins with the string, case-sensitive."""
    def g(inp: GradeInput) -> Verdict:
        return _v((inp.text or "").startswith(prefix), "pf_starts_with", f"starts-with {prefix!r}")
    return g


def pf_regex(pattern: str):
    """promptfoo `regex`: JS `new RegExp(pattern).test(output)` — search, NO default flags.
    Divergence: gradecore `regex` compiles with re.I | re.S; promptfoo uses none, so this port
    passes no flags (case-sensitive, `.` excludes newline)."""
    rx = re.compile(pattern)
    def g(inp: GradeInput) -> Verdict:
        return _v(rx.search(inp.text or "") is not None, "pf_regex", f"regex {pattern!r}")
    return g


# ── structured ───────────────────────────────────────────────────────────────

def pf_is_json(*required_keys: str):
    """promptfoo `is-json` WITHOUT a JSON schema: the whole output parses as JSON (optionally
    checking that required keys are present). This schema-less contract — parse + key PRESENCE,
    never value TYPE — is IDENTICAL to gradecore's `valid_json`, so it carries grader_id
    'valid_json' (a contract classification, not a rename): that is what tells evalmut it is a
    JSON-structure grader. (WITH a schema promptfoo would catch value types; that is a different,
    stronger assertion and not what a bare `is-json` does.)"""
    def g(inp: GradeInput) -> Verdict:
        raw = (inp.text or "").strip()
        try:
            obj = json.loads(raw)
        except Exception:
            return _v(False, "valid_json", "not valid JSON")
        if not isinstance(obj, dict):
            return _v(not required_keys, "valid_json", f"JSON not an object: {type(obj).__name__}")
        missing = [k for k in required_keys if k not in obj]
        return _v(not missing, "valid_json", f"missing keys {missing}" if missing else "valid JSON")
    return g


def pf_word_count(*, min: int = 0, max: int = 10**9):
    """promptfoo `word-count`: passes if the whitespace-split word count is within [min, max].
    Checks LENGTH only — asserts nothing about the answer's content. Own grader_id."""
    def g(inp: GradeInput) -> Verdict:
        n = len((inp.text or "").split())
        return _v(min <= n <= max, "pf_word_count", f"word-count {n} in [{min},{max}]")
    return g


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


def pf_levenshtein(expected: str, *, threshold: int):
    """promptfoo `levenshtein`: passes if edit distance from `expected` is <= threshold
    (promptfoo uses `distance <= threshold`). Own grader_id."""
    def g(inp: GradeInput) -> Verdict:
        d = _levenshtein(inp.text or "", expected)
        return _v(d <= threshold, "pf_levenshtein", f"levenshtein {d} <= {threshold}")
    return g
