"""An empty population has no observed result, so it cannot truthfully report 0% or 100%.

THE DEFECT THIS PINS. `Tally.score` answers 1.0 when `applied == 0`, which is convenient
arithmetic and a lie in a report. Three of this repo's four presentation paths forwarded it
without checking the denominator, so a run where NOTHING could be measured published a perfect
score. The worst of them is `render_short`, whose own docstring reads "One line, for CI: score,
hole counts, exit-worthy": a CI check that prints `evalmut 100%` after measuring nothing.

Zero would be no better than 1.0. It asserts measured failure where there was no measurement.
The honest state is undefined, and the reporting layer now says so.

`report.py`'s per-grader cell already guarded this correctly (`if t.applied else "  —"`), which
is how we know the rule existed in the codebase and three callers had lost it.
"""
import pytest

from evalmut.report import render, render_short
from evalmut.score import Tally, score


def test_tally_separates_the_arithmetic_from_the_permission_to_publish_it():
    assert Tally().score == 1.0, (
        "the arithmetic default is unchanged on purpose; the guard is `scored`, not `score`")
    assert Tally().scored is False
    assert Tally(caught=1).scored is True
    assert Tally(na=99).scored is False, "inapplicable rows are not a denominator"
    assert Tally(missed=1).scored is True, "a miss is still a measurement"


def test_the_ci_one_liner_never_prints_a_rate_over_nothing():
    out = render_short(score([]))
    assert "%" not in out, f"the CI line published a rate over an empty population:\n{out}"
    assert "NO-SCORE" in out
    assert "100" not in out


def test_the_full_report_never_prints_a_rate_over_nothing():
    line = [l for l in render(score([])).splitlines() if "mutation score" in l]
    assert line, "the report no longer names a mutation score line at all"
    assert "%" not in line[0], f"the report published a rate over an empty population: {line[0]}"
    assert "UNAVAILABLE" in line[0]


def test_a_real_population_still_reports_its_rate():
    """The guard must not suppress a genuine measurement, which is the obvious way to
    over-correct this."""
    from evalmut.outcome import Outcome
    t = Tally(caught=42, missed=4, na=223)
    assert t.scored is True
    assert abs(t.score - 42 / 46) < 1e-9
