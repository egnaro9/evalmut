"""A thin bridge from gradecore's `GradeInput -> Verdict` to deepeval's REAL, INSTALLED metrics.

This is NOT a port. Unlike `promptfoo_assertions.py` (promptfoo is TypeScript, so its assertions
had to be reproduced), deepeval is Python and is installed, so every grader below calls the actual
shipped object — `deepeval.metrics.ExactMatchMetric`, `PatternMatchMetric`, `ToolPermissionMetric`,
`ToolCorrectnessMetric`, `JsonCorrectnessMetric`, `deepeval.scorer.Scorer` — and reads deepeval's
own score and its own `is_successful()` verdict. Nothing here reimplements a scoring rule. If a
finding falls out, it is a fact about deepeval 4.1.8, not about our code.

WHAT THE BRIDGE IS ALLOWED TO DO (and nothing more):
  1. Shape a `GradeInput` into the `LLMTestCase` deepeval requires. `text` -> `actual_output`,
     `expected` -> `expected_output`, `tool_calls` [{"tool": name}] -> `tools_called` [ToolCall].
     The reference `expected_tools` and the metric config live in the closure, because in deepeval
     they belong to the test case / metric, not to the model's output.
  2. Report `passed = metric.is_successful()` — DEEPEVAL'S OWN threshold decision, never a bar we
     picked. (The one exception is documented on `deepeval_quasi_exact_match` below: `Scorer` is a
     bag of classmethods that returns a bare 0/1 with no threshold object, so the caller must
     supply the comparison. We use `== 1`, which is the only reading of a 0/1 scorer.)
  3. Let exceptions PROPAGATE. deepeval's `evaluate()` defaults are `ignore_errors=False` and
     `skip_on_missing_params=False` (evaluate/configs.py:45-47), so raising IS deepeval's default
     behaviour, and evalmut records it honestly as ERROR ("the grader could not render a verdict")
     rather than as a catch. Swallowing it here would have manufactured a cleaner score.
  4. Hand each grader call a FRESH metric, using deepeval's OWN `copy_metrics` — the exact function
     `evaluate()` calls per test case (evaluate/execute/e2e.py:402,470). This is not a nicety. The
     first version of this bridge reused one metric instance across calls and the run came back
     with verdicts that contradicted their own reasons ("failed the mutant / The actual and
     expected outputs are exact matches"). Cause: `check_llm_test_case_params` writes
     `metric.error` (metrics/utils.py:377) and NOTHING in `measure()` ever clears it, while
     `is_successful()` returns False whenever `error is not None` (base_metric.py:96) — so one
     blank-output probe pins every later verdict on that instance to False regardless of score.
     That is a real deepeval 4.1.8 behaviour, reproducible in eight lines with no evalmut in the
     picture; copying per call is what deepeval itself does, so it is the faithful bridge and not
     a workaround that hides something.

ENVIRONMENT NOTE, stated because it is load-bearing: `ToolCorrectnessMetric` and
`JsonCorrectnessMetric` call `initialize_model(None)` in `__init__`, which constructs
`OpenAIModel(model=None)` and raises without an OPENAI_API_KEY — even though the computation both
then perform is pure. So this module sets a PLACEHOLDER key if none is present. No request is ever
made: `JsonCorrectnessMetric` is built with `include_reason=False` (its only model call is
`generate_reason`, json_correctness.py:187-190, which returns `None` immediately when
include_reason is False) and `ToolCorrectnessMetric` is built with `available_tools=None` (its only
model call is `_get_tool_selection_score`, tool_correctness.py:103, which is skipped when
available_tools is falsy). This was verified, not assumed: the whole suite reruns BYTE-IDENTICALLY
(md5 e409dc446423bc2e30121ee5660f7685) with `socket.socket.connect` and `socket.create_connection`
patched to raise, and that block was itself liveness-checked by confirming an outbound HTTPS call
raises under it.

    cd ~/evalmut && PYTHONPATH=.:external:$HOME/gradecore \\
        /tmp/evalcov-xp/bin/python -m evalmut.cli run external/deepeval_suite.py
"""
from __future__ import annotations

import os

# Set BEFORE importing deepeval: the two metrics above construct their model at __init__ time.
os.environ.setdefault("OPENAI_API_KEY", "sk-placeholder-evalmut-offline-never-sent")
# deepeval ships PostHog telemetry that fires on import. Opting out keeps the run hermetic and is
# the documented switch (deepeval/telemetry/__init__.py:8).
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")

from pydantic import BaseModel  # noqa: E402

from gradecore import GradeInput, Verdict  # noqa: E402

from deepeval.metrics.utils import copy_metrics  # noqa: E402
from deepeval.metrics import (  # noqa: E402
    ExactMatchMetric,
    JsonCorrectnessMetric,
    PatternMatchMetric,
    ToolCorrectnessMetric,
    ToolPermissionMetric,
)
from deepeval.scorer import Scorer  # noqa: E402
from deepeval.test_case import LLMTestCase, ToolCall  # noqa: E402


def _fresh(template):
    """A per-call metric copy, via deepeval's own `copy_metrics` — the same function `evaluate()`
    uses for every test case. Required for correctness, not tidiness: see note 4 in the module
    docstring (a latched `metric.error` otherwise pins every later verdict to False)."""
    return copy_metrics([template])[0]


def _tool_calls(inp: GradeInput) -> list[ToolCall]:
    """evalmut's tool operators speak [{'tool': name}]; deepeval speaks [ToolCall(name=...)]."""
    return [ToolCall(name=str(c.get("tool", ""))) for c in (inp.tool_calls or ())]


def _verdict(metric, score: float, gid: str, extra: str = "") -> Verdict:
    """Read deepeval's OWN verdict. `is_successful()` applies the metric's own threshold."""
    passed = bool(metric.is_successful())
    detail = (metric.reason or "").strip() or f"score {score}"
    if extra:
        detail = f"{extra}: {detail}"
    return Verdict(passed=passed, score=float(score),
                   severity="none" if passed else "med",
                   detail=detail[:160], grader_id=gid)


# ── string / pattern metrics ──────────────────────────────────────────────────

def deepeval_exact_match():
    """`deepeval.metrics.ExactMatchMetric` (exact_match/exact_match.py). Strips BOTH sides then
    `expected == actual`; CASE-SENSITIVE; threshold 1. Contract-identical to gradecore `exact_cs`
    (strip, case-sensitive), which is what the suite declares as its `grader_family`. Requires
    input, actual_output AND expected_output; an empty actual_output RAISES
    MissingTestCaseParamsError before any comparison (metrics/utils.py:373-378)."""
    template = ExactMatchMetric()

    def g(inp: GradeInput) -> Verdict:
        m = _fresh(template)
        tc = LLMTestCase(input="(task prompt)", actual_output=inp.text,
                         expected_output=str(inp.expected))
        return _verdict(m, m.measure(tc, _show_indicator=False), "deepeval.ExactMatchMetric")
    return g


def deepeval_pattern_match(pattern: str, *, ignore_case: bool = False):
    """`deepeval.metrics.PatternMatchMetric` (pattern_match/pattern_match.py). NOTE THE SEMANTIC:
    line 59 uses `fullmatch`, NOT `search` — so a promptfoo-style `regex: 'was approved'` scores
    0.0 here and must be written `.*was approved.*`. Case-sensitive unless ignore_case=True.
    Strips actual_output; threshold 1.0. Empty actual_output RAISES (same gate as above).
    Deliberately NOT declared as gradecore's `regex` family: gradecore's regex is a re.search with
    re.I|re.S, a different contract, and a false family declaration would make any finding an
    artifact of the suite rather than a fact about deepeval."""
    template = PatternMatchMetric(pattern=pattern, ignore_case=ignore_case)

    def g(inp: GradeInput) -> Verdict:
        m = _fresh(template)
        tc = LLMTestCase(input="(task prompt)", actual_output=inp.text)
        return _verdict(m, m.measure(tc, _show_indicator=False),
                        "deepeval.PatternMatchMetric", f"pattern {pattern!r}")
    return g


def deepeval_quasi_exact_match(target: str):
    """`deepeval.scorer.Scorer.quasi_exact_match_score` (scorer/scorer.py:114-117) — deepeval's OWN
    shipped case-INSENSITIVE identity scorer, the counterpart to ExactMatchMetric on the same task.
    It applies HELM/QuAC `normalize_text` (deepeval/utils.py:514: lowercase, strip punctuation,
    drop articles, collapse whitespace) to both sides and compares.

    `Scorer` is a bag of classmethods with no metric object and no threshold, so the pass/fail
    comparison has to come from the caller. `== 1` is the only reading of a scorer whose two
    possible return values are 0 and 1, and it is the ONLY thing this wrapper adds — the scoring
    itself is deepeval's shipped function, called directly. Declared `grader_family="exact"`:
    gradecore's `exact` is strip+lowercase identity, and quasi_exact is the same family strictly
    LOOSENED (it also drops punctuation and articles), which only widens what it accepts."""
    def g(inp: GradeInput) -> Verdict:
        score = Scorer.quasi_exact_match_score(target, inp.text or "")
        passed = score == 1
        return Verdict(passed=passed, score=float(score),
                       severity="none" if passed else "med",
                       detail=f"quasi-exact vs {target!r} -> {score}",
                       grader_id="deepeval.Scorer.quasi_exact_match_score")
    return g


# ── structured output ─────────────────────────────────────────────────────────

def deepeval_json_correctness(schema: type[BaseModel]):
    """`deepeval.metrics.JsonCorrectnessMetric` (json_correctness/json_correctness.py). Score is
    `schema.model_validate_json(actual_output)` — a real pydantic validation, so unlike promptfoo's
    schema-less `is-json` it DOES check value types. strict_mode defaults True (threshold 1).

    include_reason=False and async_mode=False are set deliberately and are the difference between a
    deterministic grader and a networked one: with include_reason=True the FAILING path (and only
    the failing path) calls the model to explain itself. The scoring is untouched either way."""
    template = JsonCorrectnessMetric(expected_schema=schema, include_reason=False,
                                     async_mode=False)

    def g(inp: GradeInput) -> Verdict:
        m = _fresh(template)
        tc = LLMTestCase(input="(task prompt)", actual_output=inp.text)
        score = m.measure(tc, _show_indicator=False)
        passed = bool(m.is_successful())
        return Verdict(passed=passed, score=float(score),
                       severity="none" if passed else "med",
                       detail=f"pydantic {schema.__name__} validation -> {score}",
                       grader_id="deepeval.JsonCorrectnessMetric")
    return g


# ── agent / tool metrics ──────────────────────────────────────────────────────

def deepeval_tool_permission(*, allowed: list[str] | None = None,
                             denied: list[str] | None = None):
    """`deepeval.metrics.ToolPermissionMetric` (tool_permission/tool_permission.py). Fully
    deterministic by its own docstring; sets `self.model = None`. Score = fraction of tool calls
    that were authorized, threshold 1.0 by default, so ONE denylisted call fails the metric.
    Declared `grader_family="tool_misuse"`: gradecore's tool_misuse is 'PASS iff no denylisted
    tool', which is exactly this metric at its default threshold."""
    template = ToolPermissionMetric(allowed_tools=allowed, denied_tools=denied)

    def g(inp: GradeInput) -> Verdict:
        m = _fresh(template)
        tc = LLMTestCase(input="(task prompt)", actual_output=inp.text or "(n/a)",
                         tools_called=_tool_calls(inp))
        return _verdict(m, m.measure(tc, _show_indicator=False), "deepeval.ToolPermissionMetric")
    return g


def deepeval_tool_correctness(expected_tools: list[str], *, threshold: float = 0.5):
    """`deepeval.metrics.ToolCorrectnessMetric` (tool_correctness/tool_correctness.py) in its
    DEFAULT scoring configuration: should_exact_match=False, should_consider_ordering=False,
    available_tools=None -> score is the fraction of expected tools that were called
    (_calculate_non_exact_match_score), and the DEFAULT THRESHOLD IS 0.5 (line 39).

    `threshold` is exposed so the suite can run the same metric twice, once at deepeval's default
    and once at the strict 1.0 a careful user would set, and declare each case's real bar honestly.

    available_tools is left None on purpose: passing it switches on LLM tool-SELECTION scoring
    (`_get_tool_selection_score`), which would make the metric non-deterministic and put it out of
    scope. async_mode=False selects the sync branch of an if/else whose two arms are the same
    arithmetic; it changes no score. The reference plan is passed here because in deepeval
    `expected_tools` is a field of the TEST CASE, not of the model output GradeInput carries."""
    template = ToolCorrectnessMetric(async_mode=False, threshold=threshold)
    expected = [ToolCall(name=n) for n in expected_tools]

    def g(inp: GradeInput) -> Verdict:
        m = _fresh(template)
        tc = LLMTestCase(input="(task prompt)", actual_output=inp.text or "(n/a)",
                         tools_called=_tool_calls(inp), expected_tools=list(expected))
        return _verdict(m, m.measure(tc, _show_indicator=False), "deepeval.ToolCorrectnessMetric")
    return g
