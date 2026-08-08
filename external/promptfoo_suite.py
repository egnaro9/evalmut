"""evalmut pointed at promptfoo's shipped deterministic assertions.

Each case is a check a promptfoo user would plausibly write, graded by a FAITHFUL port of the
corresponding promptfoo assertion (see promptfoo_assertions.py). Declarations are CONSISTENT with
each assertion's real contract — no misdeclaration — so any hole evalmut reports is a fact about
promptfoo's assertion, not about a contradictory suite. The suite deliberately pairs a weak check
with a stronger one on the SAME task, so the report shows both the blind spot and the fix.

    cd ~/evalmut && PYTHONPATH=.:external python3 -m evalmut.cli run external/promptfoo_suite.py -v
"""
from gradecore import GradeInput

from evalmut import EvalCase
from promptfoo_assertions import (
    pf_contains, pf_icontains, pf_regex, pf_is_json, pf_word_count, pf_equals,
)

suite = [
    # 1. HEADLINE — "was the loan approved?" checked with `contains: approved`. A substring check
    #    is blind to negation: an output that says the OPPOSITE still contains the keyword.
    EvalCase("approval_contains", pf_contains("approved"),
             GradeInput(text="Yes, the loan application was approved.", expected="approved"),
             tags=("presence_check",), intent="assert the loan was approved (contains)"),

    # 2. Same blind spot on the case-insensitive variant, a "did it error?" gate.
    EvalCase("error_icontains", pf_icontains("error"),
             GradeInput(text="The request completed; an error was raised in validation.",
                        expected="error"),
             tags=("presence_check",), intent="flag error responses (icontains)"),

    # 3. CONTRAST — the SAME approval task expressed as a pattern catches the negation `contains`
    #    misses, so the report is fair: it names the weak check broken and the strong one sound.
    EvalCase("approval_regex", pf_regex(r"was approved"),
             GradeInput(text="Yes, the loan application was approved.", expected="approved"),
             tags=("presence_check",), intent="same task, phrased as a regex"),

    # 4. `is-json` (no schema) validating an API response — blind to value-TYPE violations: a
    #    required numeric field returned as a string still parses and still has the key.
    EvalCase("api_isjson", pf_is_json("status", "count"),
             GradeInput(text='{"status": "ok", "count": 3}'),
             tags=("json",), grader_family="valid_json",  # external grader declares its contract family
             intent="validate the API response shape (is-json, no schema)"),

    # 5. `word-count` used as the correctness gate — asserts nothing about the answer: any output
    #    within the length bound passes, including a blank or gibberish one.
    EvalCase("concise_wordcount", pf_word_count(max=50),
             GradeInput(text="Paris is the capital of France.", expected="Paris"),
             content_required=True, intent="answer concisely (word-count as the only check)"),

    # 6. CONTRAST — a strict `equals` protocol reply. evalmut should give it a clean bill: a
    #    byte-exact check is neither blind (blank/garbage fail) nor brittle (no tolerance declared).
    EvalCase("ping_equals", pf_equals("PONG"),
             GradeInput(text="PONG"), content_required=True, intent="exact protocol reply (equals)"),
]
