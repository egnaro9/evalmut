"""Copy this file, point it at YOUR grader, delete the comments. Runs in about ten minutes.

    evalmut run template.py --html report.html --all

You do not need gradecore. A grader is any callable that takes a GradeInput and returns something
with a `.passed` bool; the shim below wraps a plain function so you can point this at a checker you
already have. If your grader is a pytest assertion, wrap it in a try/except and return passed=False
on AssertionError.

WHAT YOU ARE ABOUT TO SEE, so a first run is not alarming.

A large `n/a` count is normal and is not "skipped". An operator declines when it cannot prove, for
YOUR case, that its mutation makes the output wrong (or leaves it right). Declining is the whole
reason a reported hole is a fact rather than a guess, so most operators sit out most cases. If you
want more of them to fire, declare more (see the bars below), never loosen them.

Holes are separated on purpose:
  blind spot    the check is present and BROKEN. Fix the check.
  vacuous       the check asserts nothing and cannot fail. Replace it.
  coverage gap  nothing guards this shape. Not a broken grader, a missing one.
  brittle       the check FAILED an output that was still correct. Loosen it, carefully.
"""
from __future__ import annotations

from gradecore import GradeInput, Verdict

from evalmut import EvalCase


# ── 1. wrap your grader ───────────────────────────────────────────────────────
# Replace the body with a call into your own checker. The only contract is: return something
# with `.passed`. `score`, `severity` and `detail` are for the report; `grader_id` is free text.

def my_grader(inp: GradeInput) -> Verdict:
    passed = "paris" in (inp.text or "").lower()          # <- YOUR CHECK GOES HERE
    return Verdict(passed=passed, score=1.0 if passed else 0.0,
                   severity="none" if passed else "med",
                   detail="", grader_id="my_contains_check")


# ── 2. give it one output your grader ALREADY PASSES ──────────────────────────
# This is the reference, and it must be green. evalmut refuses to score a case whose baseline is
# red, because "would this check catch a defect I introduce" is unanswerable when the check is
# already failing. A mis-specified reference is a loud error here, not a silent skip.

suite = [
    EvalCase(
        "capital-of-france",
        my_grader,
        GradeInput(
            text="The capital of France is Paris.",   # an output your grader passes today
            expected="Paris",                          # the canonical answer for this task
        ),

        # ── 3. declare what your task's contract actually says ────────────────
        # Every bar below defaults to "the operator declines". Nothing here is inferred from your
        # grader, on purpose: a composite grader can honestly report a primitive's id while
        # enforcing more, and trusting that label is what manufactured this tool's own false
        # findings. Declare only what is TRUE of your task. An undeclared case is under-tested;
        # a wrongly-declared one produces a finding about this file rather than about your check.

        # Your grader requires answer CONTENT, so a blank or garbage reply is provably wrong.
        # Leave False for an absence check ("did it avoid leaking X", "did it refuse").
        content_required=True,

        # Which gradecore family your grader behaves like, if it is external. One of:
        # exact, exact_cs, one_of, number, contains, regex, valid_json, grounding,
        # injection_resistance, tool_misuse. Wrong value here means wrong operators fire.
        grader_family="contains",

        # Cosmetic changes YOUR task treats as still correct. Each one lets an EQUIVALENT
        # operator fire and catch a brittle check. Any of: whitespace, fence, disclaimer, case,
        # reserialize, numeric_format, article.
        tolerates=("whitespace", "case"),

        # For a numeric task: the acceptance band your grader uses. Without it the numeric
        # operator declines rather than guessing a tolerance.
        # num_tol=0.01,

        # Tags switch on operators whose correctness depends on what the task is FOR:
        #   presence_check  your grader greps for a keyword as a PROXY for a real property
        #   must_refuse / must_comply / must_abstain / injection / json / trajectory / tool_policy
        tags=("presence_check",),
    ),

    # ── 4. ONE CASE IS NOT A SUITE ────────────────────────────────────────────
    # The case above is a starting point, not a finished suite. Every operator is evaluated
    # per case, so a one-case suite tells you about one grader on one input and nothing else.
    # Add a case for each DISTINCT THING your suite checks: each grader you rely on, and for
    # each grader the shapes of answer it is supposed to handle. Ten cases across four graders
    # is a real first pass; one case is a smoke test.
    #
    # Cheapest way to add value: include a case whose grader you SUSPECT is weak. The tool is
    # most useful where you are least confident, and a suite of only the checks you trust will
    # tell you what you already believe.
    #
    # EvalCase(
    #     "refuses-harmful-request",
    #     my_safety_grader,
    #     GradeInput(text="I can't help with that."),
    #     tags=("must_refuse",),
    # ),
]
