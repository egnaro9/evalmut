"""The diff held to its one job: never call a disappearance a fix.

Each dishonest path below is cheap and real. Delete the failing case, drop a `tolerates` so the
equivalent operator declines, narrow `judges` so the text operators skip. Every one drives the
hole count down and the score up while no grader changed. If the diff reports any of them as
progress, the tool is laundering its own numbers, which is a worse failure than missing a bug.
"""
from __future__ import annotations

from evalmut.diff import diff_runs, headline, score_delta, summarize


def run(rows, score=0.5, tally=None):
    return {"score": score, "tally": tally or {}, "holes": {},
            "results": [{"case_name": c, "operator_id": o, "outcome": out} for c, o, out in rows]}


def test_a_real_fix_is_reported_as_fixed():
    old = run([("capital", "garbage_answer", "missed")])
    new = run([("capital", "garbage_answer", "caught")])
    c = diff_runs(old, new)
    assert [x.kind for x in c] == ["fixed"]
    assert "1 fixed" in headline(summarize(c))


def test_an_operator_that_stopped_applying_is_NOT_called_fixed():
    """The load-bearing test. The hole is gone from the report and the score went up, and
    nothing was fixed: the operator declined."""
    old = run([("capital", "garbage_answer", "missed")], score=0.50)
    new = run([("capital", "garbage_answer", "na")], score=1.00)
    c = diff_runs(old, new)
    assert [x.kind for x in c] == ["no_longer_tested"]
    line = headline(summarize(c))
    # The claim that matters is the COUNT. "Nothing was fixed" legitimately contains the word.
    assert "1 fixed" not in line and "fixed," not in line
    assert "Nothing was fixed" in line
    assert c[0].suspicious


def test_deleting_the_failing_case_is_flagged_not_rewarded():
    old = run([("capital", "garbage_answer", "missed"), ("ok", "blank_output", "caught")])
    new = run([("ok", "blank_output", "caught")])
    c = diff_runs(old, new)
    assert [x.kind for x in c] == ["case_removed"]
    assert c[0].suspicious
    assert "no longer tested" in headline(summarize(c))


def test_a_fix_and_a_disappearance_are_never_merged():
    """Three holes leave: one genuinely fixed, two dodged. A summary that said '3 fixed' would be
    the exact laundering this module exists to prevent."""
    old = run([("a", "op1", "missed"), ("b", "op2", "missed"), ("c", "op3", "missed")])
    new = run([("a", "op1", "caught"), ("b", "op2", "na")])
    line = headline(summarize(diff_runs(old, new)))
    assert "1 fixed" in line
    assert "2 no longer tested" in line
    assert "3 fixed" not in line
    assert "not the same event" in line


def test_a_regression_is_caught():
    old = run([("a", "op1", "caught")])
    new = run([("a", "op1", "missed")])
    c = diff_runs(old, new)
    assert [x.kind for x in c] == ["regressed"]
    assert c[0].suspicious


def test_coverage_lost_is_distinguished_from_a_regression():
    """caught -> na broke nothing, but nothing is checking it either. Different fix, so a
    different label."""
    old = run([("a", "op1", "caught")])
    new = run([("a", "op1", "na")])
    assert [x.kind for x in diff_runs(old, new)] == ["coverage_lost"]


def test_unchanged_rows_are_not_reported():
    old = run([("a", "op1", "caught"), ("b", "op2", "na")])
    new = run([("a", "op1", "caught"), ("b", "op2", "na")])
    assert diff_runs(old, new) == []
    assert headline(summarize([])) == "Nothing moved."


def test_still_open_is_not_silently_dropped():
    old = run([("a", "op1", "missed")])
    new = run([("a", "op1", "missed")])
    c = diff_runs(old, new)
    assert [x.kind for x in c] == ["still_open"]
    assert "1 still open" in headline(summarize(c))


def test_incomparable_denominators_are_called_out():
    """A run that applied 46 mutations and one that applied 12 can differ by twenty points with
    no grader having changed."""
    old = {"score": 0.91, "tally": {"caught": 42, "missed": 4, "flagged": 0}, "results": []}
    new = {"score": 1.00, "tally": {"caught": 12, "missed": 0, "flagged": 0}, "results": []}
    a, b, note = score_delta(old, new)
    assert (a, b) == (0.91, 1.00)
    assert "not directly comparable" in note
    assert "46" in note and "12" in note


def test_equal_denominators_carry_no_warning():
    same = {"tally": {"caught": 5, "missed": 1, "flagged": 0}, "results": []}
    assert score_delta({**same, "score": 0.8}, {**same, "score": 0.8})[2] == ""
