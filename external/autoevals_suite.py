"""evalmut pointed at Braintrust **autoevals**' REAL, INSTALLED deterministic scorers.

DIFFERENCE FROM THE PROMPTFOO LEG. promptfoo is TypeScript, so `promptfoo_assertions.py` had to
be a faithful PORT. autoevals is Python and is installed in this environment, so this file
**ports nothing**. Every case calls the shipped scorer object — `autoevals.ExactMatch()`,
`autoevals.Levenshtein()`, `autoevals.NumericDiff()`, `autoevals.json.ValidJSON`,
`autoevals.json.JSONDiff()` — and the only code between evalmut and that object is the ~15-line
`_gate()` bridge below. Findings here are facts about autoevals 0.3.0's shipped behaviour.

    cd ~/evalmut && PYTHONPATH=.:external:$HOME/gradecore \\
        /tmp/evalcov-xp/bin/python -m evalmut.cli run external/autoevals_suite.py

────────────────────────────────────────────────────────────────────────────────────────────
THE MAPPING, stated up front because it is the one place a false finding could enter.
────────────────────────────────────────────────────────────────────────────────────────────
gradecore's `Verdict` is pass/fail. An autoevals `Score` is a FLOAT with **no threshold** —
`Score.score` is only constrained to 0..1 (autoevals/score.py:__post_init__). autoevals does not
ship a pass/fail contract, so "caught" is not defined by autoevals; the experimenter must supply
a threshold, and that threshold is then a parameter of the finding, not a property of autoevals.

The bridge is exactly:

    passed = (score is not None) and (score >= threshold)

and nothing else. No rescaling, no clamping, no normalisation, no fallback scoring. `Verdict.score`
carries autoevals' raw float through unchanged so it is visible in `--json` output.

TWO CLASSES OF CASE, and only one of them depends on the threshold:

  * THRESHOLD-FREE. `ExactMatch` and `ValidJSON` emit only literal 0 or 1 (measured, both
    directions, every mutant in this suite). With threshold=1.0 the verdicts are identical for
    ANY threshold in (0, 1]. Every JSON finding below is therefore threshold-independent.
  * THRESHOLD-DEPENDENT. `Levenshtein`, `JSONDiff` and `NumericDiff` are continuous. Their
    thresholds are stated on each case with the measured raw scores that bracket them, so a
    reader can see how far the verdict is from flipping.

ONE PIECE OF NON-AUTOEVALS LOGIC, disclosed. `NumericDiff` grades number-vs-number and raises
`TypeError` on a string, while evalmut mutates a TEXT field. `_gate(..., numeric=True)` therefore
does `float(inp.text)` first, and a text that will not parse is failed by the BRIDGE, not by
autoevals — those verdicts carry the literal marker `[bridge]` in their detail so they are
identifiable in the report. This affects exactly the two SANITY probes on `total_numericdiff`.

DECLARATIONS. `grader_family` is declared only where the scorer's contract is IDENTICAL to that
gradecore family (see each case). `tolerates` states what THIS TASK treats as cosmetic — an author
claim about the task, never a claim about autoevals — and is declared consistently per task type.
The two schema-variant cases carry a deliberately MINIMAL declaration set so the schema comparison
they exist for is not confounded by cosmetic probes.
"""
from __future__ import annotations

import json

from gradecore import GradeInput, Verdict

from evalmut import EvalCase

# The REAL shipped scorers. Nothing below reimplements any of them.
from autoevals import ExactMatch, Levenshtein, NumericDiff
from autoevals.json import JSONDiff, ValidJSON


# ── the entire bridge ────────────────────────────────────────────────────────────────────────

def _gate(scorer, *, threshold: float, grader_id: str, pass_expected: bool = True,
          numeric: bool = False):
    """Wrap a real autoevals scorer as a gradecore `GradeInput -> Verdict` grader.

    `pass_expected=False` is for ValidJSON, whose second positional parameter is `schema`, NOT
    `expected` (autoevals/json.py:`_run_eval_sync(self, output, schema=None, **kwargs)`) — passing
    the case's `expected` there would silently install it as a schema.
    """
    def g(inp: GradeInput) -> Verdict:
        out: object = inp.text or ""
        if numeric:
            try:
                out = float(str(inp.text).strip())
            except (TypeError, ValueError):
                return Verdict(passed=False, score=0.0, severity="med", grader_id=grader_id,
                               detail=f"[bridge] output is not a number: {(inp.text or '')[:24]!r}")
        s = scorer.eval(out, inp.expected) if pass_expected else scorer.eval(out)
        raw = s.score
        ok = raw is not None and raw >= threshold
        return Verdict(passed=ok, score=float(raw or 0.0), severity="none" if ok else "med",
                       detail=f"{s.name} score={raw!r} vs threshold {threshold}",
                       grader_id=grader_id)
    return g


# ── shared fixtures ──────────────────────────────────────────────────────────────────────────

LOAN = "The loan application was approved."
API_JSON = '{"approved": true, "count": 3}'
# A typed + valued schema: `const` pins the decision field, `type` pins the count.
API_SCHEMA = {
    "type": "object",
    "properties": {"approved": {"const": True}, "count": {"type": "number"}},
    "required": ["approved", "count"],
}


suite = [
    # 1. STRONG / STRICT — a byte-exact protocol reply. autoevals `ExactMatch` on two plain
    #    strings is `str(output) == str(expected)`: no strip, no case-fold (value.py
    #    normalize_value). It should get a clean bill: blank and garbage both fail it, and no
    #    cosmetic tolerance is declared for a byte-exact protocol check, so evalmut must not
    #    invent brittleness (the `ping_equals` precedent from the promptfoo leg).
    #    NOT declared grader_family="exact_cs": gradecore's exact_cs STRIPS, ExactMatch does not,
    #    so the contracts are not identical and declaring it would be a misdeclaration.
    EvalCase("pong_exactmatch", _gate(ExactMatch(), threshold=1.0,
                                      grader_id="autoevals.ExactMatch"),
             GradeInput(text="PONG", expected="PONG"),
             content_required=True,
             intent="exact protocol reply (ExactMatch; threshold-free, emits only 0/1)"),

    # 2. THE FUZZY GATE — `Levenshtein` >= 0.7, the "close enough" check a user reaches for when
    #    ExactMatch is too strict. Measured raw scores on this task: identical 1.0, blank 0.0,
    #    garbage 0.088, trailing-space 0.971, "  x  \n" 0.872, SWAPCASE 0.147.
    #    tolerates: a natural-language decision sentence is still correct with surrounding
    #    whitespace, with its casing changed, and with a disclaimer appended — three author claims
    #    about THIS TASK. (Prediction to check against the report: the disclaimer probe should
    #    DECLINE, because the minimal in-class probe scores 0.872 and passes while the full one
    #    scores 0.343 and fails, i.e. the rejection rides LENGTH, not disclaimer-intolerance.)
    EvalCase("approval_levenshtein", _gate(Levenshtein(), threshold=0.7,
                                           grader_id="autoevals.Levenshtein"),
             GradeInput(text=LOAN, expected=LOAN),
             content_required=True, tolerates=("whitespace", "case", "disclaimer"),
             intent="loan decision graded by edit-distance similarity >= 0.7"),

    # 3. THE WEAK JSON CHECK — `ValidJSON()` with no schema. Its contract is parse + container
    #    ("is the output valid JSON") and it NEVER inspects values (json.py:valid_json), which is
    #    exactly gradecore's `valid_json` family contract, so declaring the family is honest and
    #    the grader keeps reporting its own id. Divergences from gradecore's valid_json, both
    #    measured: autoevals accepts a top-level LIST as well as an object, and it does NOT strip
    #    a markdown fence (gradecore's does) — the fence probe below is what surfaces that.
    EvalCase("api_validjson_noschema", _gate(ValidJSON(), threshold=1.0, pass_expected=False,
                                             grader_id="autoevals.ValidJSON(no schema)"),
             GradeInput(text=API_JSON),
             grader_family="valid_json", tolerates=("whitespace", "fence"),
             intent="validate the API response (ValidJSON, no schema)"),

    # 4. THE SAME CHECK, CONFIGURED THE WAY autoevals' OWN DOCSTRINGS SHOW — `ValidJSON(schema=…)`
    #    then `.eval(output)`. json.py:30 (`self.validator = ValidJSON(schema=schema)`) and the
    #    ValidJSON class docstring (`validator = ValidJSON(schema=schema)` … `validator.eval_async(
    #    output=…)`) both use this form. If the schema were applied, this case must behave like
    #    case 5. Whether it does is the point of the pairing; evalmut decides it, not this comment.
    #    Minimal declarations on purpose: no cosmetic probes, so the comparison is clean.
    EvalCase("api_validjson_ctor_schema",
             _gate(ValidJSON(schema=API_SCHEMA), threshold=1.0, pass_expected=False,
                   grader_id="autoevals.ValidJSON(schema= via constructor)"),
             GradeInput(text=API_JSON),
             grader_family="valid_json",
             intent="same validation, schema passed to the constructor (the documented form)"),

    # 5. CONTRAST / STRONG — the same schema installed via `ValidJSON.partial(schema=…)`, the
    #    shipped `ScorerWithPartial` API (partial.py). Same scorer class, same schema, different
    #    plumbing. This is the fair half of the story: if a typed+valued schema is actually
    #    applied, both JSON value mutations must be caught.
    EvalCase("api_validjson_partial_schema",
             _gate(ValidJSON.partial(schema=API_SCHEMA)(), threshold=1.0, pass_expected=False,
                   grader_id="autoevals.ValidJSON(schema= via .partial)"),
             GradeInput(text=API_JSON),
             grader_family="valid_json",
             intent="same validation, schema installed via .partial() (typed + `const` valued)"),

    # 6. THE CONTINUOUS JSON GATE — `JSONDiff()` >= 0.8, in its DEFAULT configuration (string
    #    comparisons by Levenshtein, numbers by NumericDiff). Measured on this task: identical 1.0,
    #    blank 0.074, garbage 0.061, whitespace 1.0, fenced 0.54.
    #    NOT declared grader_family="valid_json": JSONDiff recursively compares VALUES, so it is
    #    not the structure-only family, and declaring it would be a misdeclaration that hands the
    #    JSON coverage-gap operators a case they have no business grading.
    EvalCase("api_jsondiff", _gate(JSONDiff(), threshold=0.8, grader_id="autoevals.JSONDiff"),
             GradeInput(text=API_JSON, expected=json.loads(API_JSON)),
             content_required=True, tolerates=("whitespace", "fence"),
             intent="compare the API response to a reference object (JSONDiff >= 0.8)"),

    # 7. THE NUMERIC GATE — `NumericDiff()` >= 0.8, i.e. 1 - |e-o|/(|e|+|o|) >= 0.8. Solving that
    #    for e=100 gives an acceptance band of [66.667, 150.0] — measured: NumericDiff(150, 100)
    #    scores exactly 0.8. num_tol=50.0 is that band's UPPER half-width, which is the side
    #    near_miss_number probes; the band is asymmetric (the lower half-width is 33.3), so 50.0
    #    over-states the downward side, which is never exercised. evalmut cross-checks the
    #    declaration against the grader before trusting it and declines if it is understated.
    #    See the module docstring for the `[bridge]` float() disclosure that affects this case's
    #    two SANITY probes.
    EvalCase("total_numericdiff", _gate(NumericDiff(), threshold=0.8,
                                        grader_id="autoevals.NumericDiff", numeric=True),
             GradeInput(text="100", expected=100),
             grader_family="number", num_tol=50.0,
             intent="numeric answer graded by normalised difference >= 0.8"),
]
