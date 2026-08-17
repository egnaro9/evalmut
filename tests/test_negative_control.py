"""The negative control: graders whose brokenness is known in advance.

Every other test here asks whether evalmut behaves correctly on honest inputs. This one asks the
question a reviewer actually cares about: when a check is definitely broken, does evalmut SAY so?
A mutation tester that reports a comfortable score on a grader that cannot fail is worse than no
tool, because it launders the defect it was bought to find.

The controls are deliberately not subtle. Each has a defect a reader can confirm by looking at
four lines, and each defect is a shape the tool claims to detect. If any of these ever passes
clean, the finding is about evalmut, not about the grader.

Written because 3.7 item 5 asked for exactly this and nothing in the suite provided it: every
existing fixture was a grader believed to be CORRECT, so the whole suite could only ever have
demonstrated the absence of false positives.
"""
from __future__ import annotations

import pytest
from gradecore import GradeInput, Verdict

from evalmut import run
from evalmut.case import EvalCase


def _v(passed: bool, gid: str = "contains") -> Verdict:
    return Verdict(passed=passed, score=1.0 if passed else 0.0,
                   severity="none" if passed else "med", detail="", grader_id=gid)


# ── the controls ─────────────────────────────────────────────────────────────

def always_passes(_inp: GradeInput) -> Verdict:
    """The tautology. `assertTrue(result || !result)`. Cannot fail, so it asserts nothing."""
    return _v(True)


def passes_anything_nonempty(inp: GradeInput) -> Verdict:
    """Checks that SOMETHING was said, and calls that checking the answer."""
    return _v(bool((inp.text or "").strip()))


def checks_only_length(inp: GradeInput) -> Verdict:
    """A shape check wearing a content check's name: any reply of the right size passes."""
    return _v(len((inp.text or "").strip()) >= 3)


CONTROLS = [
    ("always_passes", always_passes),
    ("passes_anything_nonempty", passes_anything_nonempty),
    ("checks_only_length", checks_only_length),
]


@pytest.mark.parametrize("name,grader", CONTROLS, ids=[c[0] for c in CONTROLS])
def test_a_broken_grader_is_reported_as_holed(name, grader):
    """The load-bearing assertion of the whole project: a grader that cannot discriminate must
    not come back clean. content_required is declared because these stand in for content graders,
    which is what makes a blank or garbage reply a provable defect here."""
    case = EvalCase(name, grader, GradeInput(text="the capital is paris", expected="paris"),
                    content_required=True, grader_family="contains")
    report = run([case])
    assert report.total.applied > 0, f"{name}: nothing was mutated, so nothing was tested"
    assert report.holes, (
        f"{name} is a grader that cannot fail, and evalmut reported no holes. "
        f"score={report.score}. This is a defect in evalmut, not in the grader.")
    assert report.score < 1.0, f"{name} scored a perfect {report.score} while being broken"


def test_a_sound_grader_is_not_slandered():
    """The other direction, and it is not optional. A tool that flags everything would pass every
    test above while being useless, so the controls only mean something next to a grader that is
    genuinely discriminating and must come back cleaner than they do."""
    def sound(inp: GradeInput) -> Verdict:
        return _v("paris" in (inp.text or "").lower())

    case = EvalCase("sound", sound, GradeInput(text="the capital is paris", expected="paris"),
                    content_required=True, grader_family="contains")
    report = run([case])
    assert report.total.applied > 0
    assert not report.vacuous, "a discriminating grader was called vacuous"
    broken = run([EvalCase("t", always_passes,
                           GradeInput(text="the capital is paris", expected="paris"),
                           content_required=True, grader_family="contains")])
    assert report.score > broken.score, (
        f"the sound grader ({report.score}) did not score above the tautology "
        f"({broken.score}); evalmut is not separating them at all")


def test_the_tautology_is_called_vacuous_specifically():
    """Not merely holed: a grader that cannot fail must land in the VACUOUS bucket, because that
    is the report that tells an owner the check asserts nothing rather than that it missed one
    defect. Getting the bucket wrong sends them to fix the wrong thing."""
    case = EvalCase("t", always_passes, GradeInput(text="the capital is paris", expected="paris"),
                    content_required=True, grader_family="contains")
    report = run([case])
    assert report.vacuous, (
        "the tautology was not reported as vacuous. Buckets: "
        f"vacuous={len(report.vacuous)} blind={len(report.blind_spots)} "
        f"gaps={len(report.coverage_gaps)}")
