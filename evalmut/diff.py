"""What changed between two runs, and specifically whether anything was FIXED.

THE WHOLE POINT. A hole can leave a report two ways, and they are opposites:

  the check now catches the defect        -> the suite got better
  the operator stopped applying           -> the question stopped being asked

Both make the hole count fall. Both make the score rise. A diff that reports them together as
"1 hole fixed" would be laundering exactly the way this tool exists to catch, and it would be
laundering the tool's OWN numbers, which is worse. So every transition is keyed on
(case, operator) and classified by what the outcome DID, and the summary never merges a fix with
a disappearance.

The dishonest paths are cheap and they are not hypothetical: delete the failing case, drop a
`tolerates` declaration so the equivalent operator declines, narrow `judges` so the text operators
skip, rename the case. Each one moves a MISSED to absent or to n/a while touching no grader. The
transitions below are named so the report can say which happened.

WHY (case, operator) AND NOT A HASH OF THE ROW. The mutant preview and detail text change for
innocent reasons (a reworded shape, a longer preview). Keying on those would report churn as
change. The pair (case, operator) is the identity of the QUESTION being asked, and the outcome is
the answer, which is the comparison a reader wants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# transition -> (label, is_progress, is_suspicious, what it means)
TRANSITIONS = {
    "fixed": ("Fixed", True, False,
              "the operator still applies and the check now catches it. Real progress."),
    "regressed": ("Regressed", False, True,
                  "the check used to catch this and no longer does."),
    "still_open": ("Still open", False, False, "unchanged: the check still misses this."),
    "no_longer_tested": ("No longer tested", False, True,
                         "the hole is gone from the report because the operator stopped "
                         "APPLYING, not because anything was fixed. The score improved by "
                         "asking a smaller question."),
    "case_removed": ("Case removed", False, True,
                     "the case that carried this hole is not in the new run at all."),
    "newly_tested": ("Newly tested", False, False,
                     "this question was not asked before."),
    "coverage_lost": ("Coverage lost", False, True,
                      "the operator used to apply and be caught; now it declines. Nothing "
                      "broke, but nothing is checking this either."),
    "unchanged": ("Unchanged", False, False, "same question, same answer."),
}

_HOLE_OUTCOMES = {"missed", "flagged", "error"}


@dataclass(frozen=True)
class Change:
    case: str
    operator: str
    before: str | None      # outcome in the old run, None if the pair is new
    after: str | None       # outcome in the new run, None if the pair is gone
    kind: str

    @property
    def label(self) -> str:
        return TRANSITIONS[self.kind][0]

    @property
    def suspicious(self) -> bool:
        return TRANSITIONS[self.kind][2]


def _index(payload: dict) -> dict[tuple[str, str], str]:
    return {(r.get("case_name"), r.get("operator_id")): r.get("outcome")
            for r in (payload.get("results") or [])}


def _classify(before: str | None, after: str | None) -> str:
    if before is None:
        return "newly_tested"
    if after is None:
        return "case_removed"
    was_hole, is_hole = before in _HOLE_OUTCOMES, after in _HOLE_OUTCOMES
    if was_hole and after == "caught":
        return "fixed"
    if was_hole and after == "na":
        return "no_longer_tested"
    if was_hole and is_hole:
        return "still_open"
    if before == "caught" and is_hole:
        return "regressed"
    if before == "caught" and after == "na":
        return "coverage_lost"
    return "unchanged"


def diff_runs(old: dict, new: dict) -> list[Change]:
    """Every (case, operator) whose answer moved. Requires `results` in BOTH payloads, which
    means `--all`: a diff computed from the holes lists alone cannot see a MISSED become n/a,
    because n/a rows are not holes and never appear there. That blindness would hide the exact
    transition this module exists to surface."""
    a, b = _index(old), _index(new)
    out: list[Change] = []
    for key in sorted(set(a) | set(b)):
        before, after = a.get(key), b.get(key)
        kind = _classify(before, after)
        if kind == "unchanged":
            continue
        out.append(Change(case=key[0], operator=key[1], before=before, after=after, kind=kind))
    return out


def summarize(changes: Iterable[Change]) -> dict[str, int]:
    counts: dict[str, int] = {k: 0 for k in TRANSITIONS}
    for c in changes:
        counts[c.kind] += 1
    return counts


def headline(counts: dict[str, int]) -> str:
    """One line a reader can act on, which never merges a fix with a disappearance.

    Deliberately puts the suspicious count in the same breath as the good one. A summary that
    said '3 fixed' while 2 holes had quietly stopped being tested would be true and misleading,
    and misleading is the failure mode with teeth."""
    fixed = counts["fixed"]
    dodged = counts["no_longer_tested"] + counts["case_removed"]
    regressed = counts["regressed"] + counts["coverage_lost"]
    bits = []
    if fixed:
        bits.append(f"{fixed} fixed")
    if dodged:
        bits.append(f"{dodged} no longer tested")
    if regressed:
        bits.append(f"{regressed} regressed")
    if counts["newly_tested"]:
        bits.append(f"{counts['newly_tested']} newly tested")
    if counts["still_open"]:
        bits.append(f"{counts['still_open']} still open")
    if not bits:
        return "Nothing moved."
    line = ", ".join(bits) + "."
    if dodged and fixed:
        line += (" A fix and a disappearance are not the same event: check the "
                 "no-longer-tested rows before reading this as progress.")
    elif dodged:
        line += (" Nothing was fixed. The holes left because the operators stopped applying, "
                 "which means the score improved by asking a smaller question.")
    return line


def score_delta(old: dict, new: dict) -> tuple[Any, Any, str]:
    """Both scores and a warning when the denominators differ.

    Two mutation scores are only comparable when they were computed over the same set of applied
    mutations. A run that applied 46 and a run that applied 12 can differ by twenty points with
    no grader having changed at all, so the denominators travel with the numbers rather than
    being quietly dropped."""
    a, b = old.get("score"), new.get("score")
    ta, tb = (old.get("tally") or {}), (new.get("tally") or {})
    da = (ta.get("caught", 0) or 0) + (ta.get("missed", 0) or 0) + (ta.get("flagged", 0) or 0)
    db = (tb.get("caught", 0) or 0) + (tb.get("missed", 0) or 0) + (tb.get("flagged", 0) or 0)
    note = ""
    if da != db:
        note = (f"denominators differ ({da} applied then, {db} now): these two scores are not "
                "directly comparable, and the per-transition rows are the honest comparison.")
    return a, b, note
