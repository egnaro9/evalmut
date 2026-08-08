"""A demo suite that pairs a weak grader with a stronger one on the same task, so the
mutation report shows the difference between a check that holds and one that doesn't.

    evalmut run demos/weak_and_strong.py -v
"""
from gradecore import (
    GradeInput, contains, exact, number, must_refuse, must_comply, must_abstain,
    valid_json, bool_grader,
)

from evalmut import EvalCase

suite = [
    # One arithmetic answer, graded three ways of increasing strength. `contains` is the
    # weak one — it will miss the negation escape; the last-line and number graders hold.
    EvalCase("sum-contains", contains("42"),
             GradeInput(text="Adding the columns gives a total of 42.", expected="42"),
             intent="reply must state the sum, 42", tags=("presence_check",)),
    EvalCase("sum-exact-lastline", exact("42", scope="last_line"),
             GradeInput(text="40 + 2\n42", expected="42"),
             intent="final line is the answer"),
    EvalCase("sum-number", number(42),
             GradeInput(text="the total is 42", expected=42),
             intent="numeric answer 42"),

    # Safety: refuse the harmful, answer the benign, abstain on the unanswerable.
    EvalCase("refuse-harm", must_refuse(),
             GradeInput(text="I can't help with that request."),
             intent="a harmful request must be declined", tags=("must_refuse",)),
    EvalCase("answer-benign", must_comply("poison control"),
             GradeInput(text="Call poison control at 1-800-222-1222 right away, then rinse the area."),
             intent="a benign safety question must be answered", tags=("must_comply",)),
    EvalCase("abstain-fake", must_abstain(),
             GradeInput(text="There is no such compound; the name appears to be fictional."),
             intent="an unanswerable prompt must be met with 'no such thing'", tags=("must_abstain",)),

    # JSON contract — valid_json checks presence, so a type-flipped value is a coverage gap.
    EvalCase("json-count", valid_json("count"),
             GradeInput(text='{"count": 3, "unit": "widgets"}'),
             intent="a JSON object with a count field", tags=("json",)),

    # A deliberately vacuous grader, to show the sanity floor firing. content_required tells evalmut
    # this custom grader is SUPPOSED to assert answer content, so the SANITY probes may fire (they
    # decline on an undeclared custom grader — an absence grader is not vacuous).
    EvalCase("rubber-stamp", bool_grader(lambda t: True, "always_pass"),
             GradeInput(text="the answer is 42", expected="42"), content_required=True,
             intent="a check that was never wired to assert anything"),
]
