"""evalmut — mutation testing for evals.

Your eval suite passes. Does it actually check anything? evalmut injects known
defects into the system-under-test's output — mutations mined from real, documented
eval failures — and reruns the graders that were supposed to be watching. A mutation
the grader catches is a check doing its job. A mutation that survives is a hole: a
class of defect that would ship green (a blind spot) or a class of correct output the
check breaks on (a brittle spot). Every operator names the real failure it reproduces.

    from evalmut import EvalCase, run, catalog
    from gradecore import GradeInput, contains

    suite = [EvalCase("adds", contains("42"), GradeInput(text="the answer is 42"),
                      intent="reply must contain the sum")]
    report = run(suite)
    print(report.score, "-", len(report.holes), "holes")
    for h in report.blind_spots:
        print(h.grader_id, "is blind to", h.real_origin)
"""
from __future__ import annotations

from typing import Optional, Sequence

from .case import EvalCase, case
from .operator import MutationOperator, applies_to_tag, operator, with_text
from .operators import CORE_OPERATORS, catalog
from .outcome import OperatorType, Outcome, Polarity, outcome_for
from .report import render, render_short
from .runner import BaselineError, MutationResult, run_case, run_suite
from .score import Report, Tally, score

__version__ = "0.1.0"


def run(suite: Sequence[EvalCase],
        operators: Optional[Sequence[MutationOperator]] = None) -> Report:
    """The one-call entry point: run the (default or given) operators over the suite
    and return a scored report. Baseline failures are attached to the report so a
    mis-specified case is loud, not silent."""
    import dataclasses
    ops = tuple(operators) if operators is not None else catalog()
    results, baseline_failures = run_suite(suite, ops)
    report = score(results)
    if baseline_failures:
        report = dataclasses.replace(report, baseline_failures=tuple(baseline_failures))
    return report


__all__ = [
    "EvalCase", "case", "run", "run_case", "run_suite",
    "MutationOperator", "operator", "applies_to_tag", "with_text",
    "CORE_OPERATORS", "catalog",
    "Outcome", "Polarity", "OperatorType", "outcome_for",
    "Report", "Tally", "score", "MutationResult", "BaselineError",
    "render", "render_short",
]
