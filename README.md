# evalmut. Mutation testing for evals

**Your eval suite passes. Does it actually check anything?**

You write a grader, watch it pass on a good output, and ship it. You never ask the
other question: would it *also* pass on a plausibly-broken output? A `contains("42")`
check passes `"the total is 42"`. And it passes `"I did NOT reach 42"` just as
happily. A JSON check that confirms a `count` field is present says nothing about
whether `count` is a number or the string `"three"`. A refusal check that scans for
"I can't help" is fooled by a reply that refuses in its first line and then delivers
the harm below. These aren't hypotheticals; each is a real defect that shipped past a
real check.

`evalmut` finds them. It takes an eval case your grader passes, injects a *known*
defect into the output. A defect **mined from a documented real-world eval failure**,
not invented. And reruns the grader. If the grader still passes a genuinely-wrong
output, that's a **hole**: a class of regression your eval would let ship green.

It's the same idea as code mutation testing (PIT, Stryker, mutmut), which nobody had
built for the model-plus-prompt-plus-grader stack. Because there a "mutation" isn't a
flipped boolean, it's a semantic perturbation whose ground truth you have to establish.
That's the hard part, and it's what `evalmut` does.

```
$ evalmut run suite.py   # your suite; see 'Install & use' below
────────────────────────────────────────────────────────────────────────
  evalmut. Does your eval actually check anything?
────────────────────────────────────────────────────────────────────────
  mutation score    91.4%   (32 caught / 35 applied; 150 n/a)
  holes            3  (1 blind, 2 coverage-gap)

  BLIND SPOTS: a real defect shipped green; the check is present and broken
    • contains / contains
        mutation : keyword_present_but_negated. The checked keyword appears,
                   but in a context that means the opposite
        mined from: a CI proof-gate that greps its own transcript for a
                   token; the block message contains it, so mentioning it passes
  COVERAGE GAPS: no check guards this shape (a missing grader, not a broken one)
    • valid_json / valid_json
        mutation : json_value_type_flip. A required field's value coerced to
                   the wrong type (number -> string)
    • valid_json / valid_json
        mutation : json_value_corruption. A required field's value changed to a
                   different value of the same type (3 -> 4)
        mined from: gradecore valid_json checks key PRESENCE only, never value
```

That run is `evalmut` pointed at **its own dependency's** graders. It found three real
holes and, this is the point, it was **fair about them**: it called the `contains`
weakness a *blind spot* (a present check that's broken) and the two `valid_json` scopings
*coverage gaps* (a missing check, not a broken one), because `valid_json` only ever
claimed to check key presence. A tool that cries "broken!" at a correctly-scoped check
is a tool you learn to ignore.

**The holes above are replayable evidence, not anecdotes.** Every claim this repo
publishes ships as a closed, stamped bundle in [`vac/`](vac), registered in the
program-wide [evidence registry](https://egnaro9.github.io/vac-protocol/)
([registry.json](https://github.com/egnaro9/vac-protocol/blob/main/registry.json)) -
and [REPLAY_REQUEST.md](https://github.com/egnaro9/vac-protocol/blob/main/REPLAY_REQUEST.md)
is the ten-minute path to trying to falsify one.

## The two ways an eval lies

Most eval tooling only asks the first of these. Both are real, and `evalmut` tests both:

- **Blind spot**: a real defect ships green. Inject a *wrong* output; a sound grader
  must reject it. If it passes, the check is present and broken.
- **Brittle spot**: a correct output gets flagged. Inject an *equivalent* change (a
  trailing disclaimer after a complete answer, cosmetic whitespace, a JSON code fence);
  a sound grader must still pass it. If it fails, the check false-positives, and a
  false-positive check is quietly recalibrated until it stops catching the real thing.

## The honesty guarantee

The whole tool rests on one rule, and it is what defeats the classic equivalent-mutant
problem:

> **It never infers a hole from a verdict flip. It infers a hole from
> `(output-proven-wrong AND grader-passed)`, where wrongness is established against the
> case's own ground truth. Independently of the grader being tested.**

An operator applies to a case *only* where it can establish the mutant's polarity for
that case: provably wrong (a defect) or provably still-correct (an equivalent). Where it
can't. No number to corrupt, no answer span to truncate, a field the grader doesn't
judge. It returns **N/A** and is excluded from the score. So a reported hole is never a
guess about an ambiguous mutant; by construction the mutant had a known correct answer
and the grader disagreed with it.

When the bar that decides wrongness lives inside the grader's closure. A numeric
tolerance, an expected tool plan, whether whitespace is cosmetic for the task. The
operator does **not** guess it from a module default or trust a label the grader reports
about itself (a composite grader can honestly carry a primitive's id yet enforce more).
The suite *declares* that bar on the case (`num_tol`, `expected_trajectory`, `tolerates`,
`content_required`), and the operator uses it. Cross-checking it against the grader where
it can. Or declines. This is the discipline **eight rounds of adversarial cold-critique**
paid for: every false hole those passes found was an operator asserting polarity without
recomputing the graded property against the grader's *real* acceptance condition. A
hardcoded threshold, a self-reported id, a fixed-magnitude mutant that tripped an
orthogonal constraint, a formatting quirk that defeated a cross-check, a text
transformation the grader's own tokenizer re-read differently, a decline-gate one operator
carried and its siblings didn't. The early rounds fixed the bulk (a dozen at the peak);
by round six the tool-fault false positives on a well-formed suite reached **zero** and
held through rounds seven and eight, which surfaced only gate-symmetry issues that bite a
misdeclared case, never a well-formed one. The regression tests (`test_D1`–`D4`,
`test_P2A`–`P2K`, `test_P3F1`–`F8`, `test_P4_*`, `test_P5_*`, `test_P6_*`, `test_P7_*`) pin
every one. The through-line is a single invariant:
**an operator asserts a hole only where it can recompute the graded property against the
grader's real acceptance condition; everywhere else it declines.**

## Mined, not authored

Every operator names the concrete, documented failure it reproduces. And that citation
is enforced as a test (`test_every_operator_names_a_real_origin`). This is not
decoration. An *authored* mutation only tests what its author already imagined a check
might miss, which is exactly the blind spot you're trying to find. A *mined* operator
reproduces a defect that actually happened. `evalmut`'s operators come from a real
corpus: model-drift's 429/MNAR truncation finding, a property test that ran with
`tries=1`, a proof gate that grepped a transcript for a token, an assertion that read
`assertTrue(result || !result)`, and gradecore's own documented grader scoping.

```
$ evalmut operators        # every one, with its provenance
```

## Install & use

```bash
pip install evalmut         # from PyPI (or: pip install -e . from a clone)
```

```python
from gradecore import GradeInput, contains
from evalmut import EvalCase, run

suite = [EvalCase("sum", contains("42"),
                  GradeInput(text="the total is 42", expected="42"),
                  tags=("presence_check",))]

report = run(suite)
print(f"{report.score:.0%} :  {len(report.blind_spots)} blind spots")
for h in report.blind_spots:
    print(h.grader_id, "is blind to", h.operator_id, "-", h.real_origin)
```

Or from the shell, with a CI-worthy exit code (nonzero on any vacuous/blind/brittle hole):

```bash
evalmut run path/to/your_suite.py -v
evalmut run your_suite.py --short     # one line for CI
evalmut run your_suite.py --json      # machine-readable
```

A suite file just defines `suite` (a list of `EvalCase`) and, optionally, `operators`.

> **Security. Evalmut executes your suite.** Loading a suite imports and runs it, and
> mutation runs invoke your grader code, so `evalmut run` executes arbitrary Python from
> the suite file (the same trust model as `pytest`). Only run suites you trust. If you wire
> it into CI as a PR gate, do **not** run it against forks/untrusted PRs, and give the job no
> secrets it doesn't need. A malicious suite file would otherwise run with your CI credentials.
> Prefer a sandboxed/isolated runner for untrusted input.

## Design

- `outcome.py`. The four outcomes (caught / missed / flagged / n-a), the two polarities,
  the three operator types (KILL / DIAGNOSTIC / SANITY) that separate a *broken* check
  from a *missing* one.
- `case.py`. An `EvalCase`: a grader, the reference-correct input it passes, which
  fields it judges, and the declared contract bars (`num_tol`, `tolerates`,
  `expected_trajectory`, `content_required`) an operator reads instead of guessing.
- `operator.py` / `operators.py`. The operator contract and the mined catalog.
- `runner.py`. Baseline-green enforcement, apply, regrade, classify. Deterministic, no
  LLM-as-judge, so a run reproduces exactly.
- `score.py` / `report.py`. The score, and the holes grouped by how alarming they are.

Built on [`gradecore`](../gradecore), the deterministic no-LLM-judge grading engine. So
`evalmut`'s own verdicts are as reproducible as the graders it tests.
