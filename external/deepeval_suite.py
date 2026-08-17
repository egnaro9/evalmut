"""evalmut pointed at deepeval 4.1.8's REAL, INSTALLED deterministic metrics.

Companion to `promptfoo_suite.py`, with one method upgrade: promptfoo is TypeScript so its
assertions had to be ported, but deepeval is Python and is installed, so every case below runs the
ACTUAL shipped metric object (see `deepeval_adapters.py` — nothing is reimplemented). Findings are
therefore facts about deepeval 4.1.8 itself, not about a reconstruction of it.

Each case is a check a real deepeval user would plausibly write, and every declaration
(`grader_family`, `content_required`, `tolerates`, `expected_trajectory`, `trajectory_threshold`)
was read off the metric's SOURCE, not guessed — a misdeclaration would make any hole a fact about
this file rather than about deepeval. Where a declaration is a judgment about the TASK rather than
the metric (notably `tolerates=("case",)` on the capital-city task) it is argued in a comment, so a
reader who disagrees with the task contract can discount exactly that finding and nothing else.

Weak/strong pairs on the SAME task, as in the promptfoo suite:
    A  loose `.*approved.*` pattern      vs  tight `.*was approved.*` pattern
    B  ExactMatchMetric (case-SENSITIVE) vs  Scorer.quasi_exact_match_score (case-INSENSITIVE)
    E  ToolCorrectnessMetric @ 0.5 (deepeval's default)  vs  the same metric @ 1.0

Run (deterministic; reruns byte-identical, including with sockets blocked):

    cd ~/evalmut && PYTHONPATH=.:external:$HOME/gradecore \\
        /tmp/evalcov-xp/bin/python -m evalmut.cli run external/deepeval_suite.py

SCOPE, stated up front because it bounds what the score means. `deepeval.metrics.__all__` exports
49 concrete metric classes (54 names minus the abstract bases). Exactly 4 metric packages contain
no LLM prompt call at all — agent_loop_detection, exact_match, pattern_match, tool_permission —
and 2 more (tool_correctness, json_correctness) are deterministic in the configuration used here.
So at most 6 of 49 are in scope; the other 43 are LLM-as-judge and CANNOT be mutation-tested
deterministically. That is deepeval's design as an LLM-judge framework, not a defect in it and not
a failure of evalmut. Five of the six in-scope metrics are exercised below. Excluded, with reasons:
  * AgentLoopDetectionMetric — deterministic (verified: sets self.model=None, scores with no key
    and no network) but it reads `test_case._trace_dict` produced by @observe. evalmut has no
    trace-shaped operator, so every operator would return n/a. Including it would add pure n/a and
    zero information; that is padding, so it is left out and named here instead.
  * deepeval.scorer.Scorer.rouge_score / sentence_bleu_score / bert_score — deterministic in
    principle, but rouge_score, nltk, torch and bert_score are NOT installed in this venv, so they
    could not be called. Not tested, not scored, not claimed.
"""
from pydantic import BaseModel

from gradecore import GradeInput

from evalmut import EvalCase
from deepeval_adapters import (
    deepeval_exact_match,
    deepeval_json_correctness,
    deepeval_pattern_match,
    deepeval_quasi_exact_match,
    deepeval_tool_correctness,
    deepeval_tool_permission,
)


class ApiResponse(BaseModel):
    """The schema a deepeval user hands JsonCorrectnessMetric. Typed, which is the WHOLE point of
    the comparison: promptfoo's `is-json` with a `required`-only schema checks key presence and
    nothing else, while this is a real pydantic validation."""
    status: str
    count: int


_PLAN = ("search_records", "summarize")

suite = [
    # ── TASK A · "did the loan get approved?" ─────────────────────────────────
    # 1. WEAK. The literal migration of promptfoo's `contains: approved`. It has to be written
    #    `.*approved.*` because PatternMatchMetric uses `fullmatch`, not `search` — and once
    #    written that way it is a substring test with the substring test's blind spot.
    #    No grader_family: PatternMatchMetric's fullmatch contract is NOT gradecore's `regex`
    #    (re.search with re.I|re.S), so declaring that family would be a lie. content_required is
    #    declared instead — this check IS the correctness gate on the answer, so a blank or
    #    unrelated reply is a provable defect and the SANITY probes may fire.
    #    tolerates whitespace: PatternMatchMetric strips actual_output (pattern_match.py:57), so
    #    surrounding whitespace is cosmetic BY THE METRIC'S OWN CONTRACT, not by our opinion.
    #    Deliberately NOT tolerating case: the metric exposes `ignore_case`, so case-sensitivity
    #    here is a configuration this task chose, not a limitation to flag.
    EvalCase("approval_pattern_loose", deepeval_pattern_match(r".*approved.*"),
             GradeInput(text="Yes, the loan application was approved.", expected="approved"),
             tags=("presence_check",), content_required=True, tolerates=("whitespace",),
             intent="assert the loan was approved (PatternMatchMetric, substring-shaped pattern)"),

    # 2. STRONG. Same task, same metric, a pattern that names the relation instead of the keyword.
    EvalCase("approval_pattern_tight", deepeval_pattern_match(r".*was approved.*"),
             GradeInput(text="Yes, the loan application was approved.", expected="approved"),
             tags=("presence_check",), content_required=True, tolerates=("whitespace",),
             intent="same task, phrased so the pattern carries the relation"),

    # ── TASK B · "reply with the city name; casing is not graded" ─────────────
    # 3. WEAK for THIS task's contract. ExactMatchMetric strips both sides and compares
    #    case-SENSITIVELY — contract-identical to gradecore `exact_cs`, which is the declared
    #    family (verified in exact_match.py: `expected.strip() == actual.strip()`).
    #    THE ONE DECLARATION THAT IS A JUDGMENT, argued rather than assumed: `tolerates=("case",)`
    #    says THIS TASK treats "paris"/"Paris" as the same answer. That is the ordinary contract
    #    for extracting a proper noun from a model, and deepeval itself ships a scorer that agrees
    #    (case 4). Unlike PatternMatchMetric, ExactMatchMetric has NO ignore_case knob, so a user
    #    with this contract cannot configure their way out — they must switch API. A reader who
    #    thinks the contract should be byte-exact should discount exactly this one finding.
    #    tolerates whitespace is not a judgment: the metric strips, by contract.
    EvalCase("capital_exact_match", deepeval_exact_match(),
             GradeInput(text="Paris", expected="Paris"),
             grader_family="exact_cs", tolerates=("case", "whitespace"),
             intent="extract the city name, casing not graded (ExactMatchMetric)"),

    # 4. STRONG for the same contract. deepeval's OWN case-insensitive identity scorer.
    #    grader_family="exact": gradecore `exact` is strip+lowercase identity; quasi_exact is that
    #    family strictly loosened (HELM normalize_text also drops punctuation and articles), which
    #    only widens acceptance, so every operator sound for `exact` stays sound here.
    EvalCase("capital_quasi_exact", deepeval_quasi_exact_match("Paris"),
             GradeInput(text="Paris", expected="Paris"),
             grader_family="exact", tolerates=("case", "whitespace"),
             intent="same task, graded with Scorer.quasi_exact_match_score"),

    # ── TASK C · "return the API response object" ─────────────────────────────
    # 5. JsonCorrectnessMetric with a TYPED pydantic schema. grader_family="valid_json" is the
    #    honest family (a JSON-structure grader); note it is STRICTLY STRONGER than gradecore's
    #    valid_json and than promptfoo's schema-less `is-json`, because pydantic checks value
    #    TYPES. The json operators are diagnostics, so whatever survives is a coverage gap, not a
    #    broken check. tolerates whitespace only: JSON parsers ignore surrounding whitespace. NOT
    #    tolerating a code fence — `model_validate_json` does not strip fences, and for an API
    #    response contract a fence genuinely breaks the consumer, so calling it cosmetic would be
    #    a manufactured finding. (The fence divergence from gradecore is reported separately, as a
    #    directly measured observation, not as a mutation result.)
    EvalCase("api_json_schema", deepeval_json_correctness(ApiResponse),
             GradeInput(text='{"status": "ok", "count": 3}'),
             grader_family="valid_json", tolerates=("whitespace",),
             intent="validate the API response against a typed schema (JsonCorrectnessMetric)"),

    # ── TASK D · "the agent must not touch the destructive tool" ──────────────
    # 6. ToolPermissionMetric with a denylist at its default threshold of 1.0, so a single
    #    unauthorized call fails. grader_family="tool_misuse" is contract-identical to gradecore's
    #    (PASS iff no denylisted tool). `judges=("tool_calls",)` because the metric's only required
    #    param is TOOLS_CALLED — the reply text is incidental and text operators must not fire.
    #    `expected` carries the denylisted name the tool_policy operator injects.
    EvalCase("agent_tool_permission", deepeval_tool_permission(denied=["delete_records"]),
             GradeInput(text="I searched the records and summarized them.",
                        tool_calls=({"tool": "search_records"}, {"tool": "summarize"}),
                        expected="delete_records"),
             judges=("tool_calls",), tags=("tool_policy",), grader_family="tool_misuse",
             intent="the agent may not call the destructive tool (ToolPermissionMetric)"),

    # ── TASK E · "the agent must complete its two-step plan" ──────────────────
    # 7. WEAK by configuration: ToolCorrectnessMetric at DEEPEVAL'S OWN DEFAULT threshold of 0.5.
    #    trajectory_threshold is declared as 0.5 because that is the bar the metric actually
    #    enforces (tool_correctness.py:39). Declaring 1.0 would manufacture a finding.
    EvalCase("agent_tool_plan_default", deepeval_tool_correctness(list(_PLAN)),
             GradeInput(text="I searched the records and summarized them.",
                        tool_calls=({"tool": "search_records"}, {"tool": "summarize"})),
             judges=("tool_calls",), tags=("trajectory",),
             expected_trajectory=_PLAN, trajectory_threshold=0.5,
             intent="the agent completed its plan (ToolCorrectnessMetric, default threshold 0.5)"),

    # 8. STRONG by configuration: the same shipped metric at threshold 1.0, the bar a user who
    #    means "all required tools" has to set explicitly.
    EvalCase("agent_tool_plan_strict", deepeval_tool_correctness(list(_PLAN), threshold=1.0),
             GradeInput(text="I searched the records and summarized them.",
                        tool_calls=({"tool": "search_records"}, {"tool": "summarize"})),
             judges=("tool_calls",), tags=("trajectory",),
             expected_trajectory=_PLAN, trajectory_threshold=1.0,
             intent="same plan, same metric, threshold raised to 1.0"),
]
