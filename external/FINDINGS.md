# evalmut on a deployed eval suite: promptfoo's deterministic assertions

**What this is.** evalmut (mutation testing for eval graders, no LLM judge) pointed at faithful ports
of [promptfoo](https://www.promptfoo.dev)'s shipped *deterministic* assertions. promptfoo is one of
the most widely used LLM-eval frameworks; its deterministic assertions are exactly our niche — a real
red is a real red, no model in the loop. Every grader in `promptfoo_assertions.py` reproduces
promptfoo's **documented** rule (docs fetched 2026-08-08); divergences from the same-named gradecore
grader are noted in-file so nothing here is an artifact of our own code.

**Run** (deterministic — identical across 3 runs):

```
$ cd ~/evalmut && PYTHONPATH=.:external python3 -m evalmut.cli run external/promptfoo_suite.py
  mutation score    45.5%   (5 caught / 11 applied; 71 n/a)
  holes            6  (2 vacuous, 2 blind, 2 coverage-gap)
```

Six checks a promptfoo user would plausibly write. evalmut found three classes of hole in the weak
ones and gave the two strong ones a clean bill. Each finding below was **independently verified**
against promptfoo's assertion semantics (not just evalmut's report).

---

## Finding 1 — `contains` / `icontains` are blind to negation  *(blind spot)*

A promptfoo user checks "was the loan approved?" with:

```yaml
assert:
  - type: contains
    value: approved
```

`contains` is a substring test (`output.includes("approved")`). evalmut's `keyword_present_but_negated`
mutation turns the reply into **"I did NOT do approved. The step approved was skipped entirely."** —
which still contains the substring, so the assertion **passes an output that says the opposite of what
was required.**

Verified independently: `contains("approved")` passes that negation **but rejects** a genuinely
keyword-absent reply ("the request was denied") — so it is *specifically blind to negation*, not merely
a vacuous check. `icontains` (the case-insensitive variant, a "did it error?" gate) has the identical
blind spot.

Who inherits it: anyone using `contains`/`icontains` as a **correctness** gate for a yes/no or
polarity question. It is safe for pure presence ("does the JSON mention a `total` field?").

## Finding 2 — schema-less / keys-only `is-json` is blind to wrong values (type *and* value)  *(2 coverage gaps)*

Validating an API response with:

```yaml
assert:
  - type: is-json
    value: { required: [status, count] }   # keys, no property types
```

Two mutations survive it. `json_value_type_flip` coerces `count` to a string
(`{"status": "ok", "count": "__3__"}`); `json_value_corruption` changes it to a different value of the
same type (`{"status": "ok", "count": 4}`). Both still parse and still have both keys, so the assertion
**passes a response with a required field's value wrong — whether the type is wrong or just the value.**
The visceral case is a decision field: `{"approved": true}` → `{"approved": false}` sails through.

Verified: `is-json` passes both mutations **but rejects** a missing key and non-JSON — so the gap is
precisely the value (type and content), nothing else. Both are *coverage gaps*, not broken checks:
`is-json` never promised to check values. A `required`-only schema (a very common shortcut) does not;
only a schema with typed, valued `properties` closes it. A **bare** `is-json` (no schema) is weaker
still — it asserts only that the output parses.

## Finding 3 — `word-count` used as a correctness gate is vacuous  *(vacuous)*

"Answer concisely" enforced with `word-count: { max: 50 }` as the check. evalmut's SANITY probes show
the grader passes both a **blank** output (0 words) and **gibberish** ("zxqfp wgbrtl mnkvd frljpz
qptxw", 5 words) — it asserts nothing about the *answer*, only its length.

Verified: `word-count(max=50)` passes blank and gibberish. `word-count` is a perfectly good check for
*"is the answer the right length"*; the finding is that it is vacuous when used as the *only* gate on
correctness — a real misuse evalmut flags.

## The two strong checks — a clean bill  *(the fair half of the story)*

- **`regex: "was approved"`** on the same approval task **caught** the negation mutant (the pattern
  isn't present in "…the step approved was skipped…"). A well-phrased pattern is not blind where
  `contains` is.
- **`equals: "PONG"`** (byte-exact) **caught** both the blank and gibberish probes and was not flagged
  brittle (no whitespace/fence/disclaimer tolerance was declared, so evalmut declined to probe those —
  it does not invent brittleness for a strict check).

evalmut is fair: it named the weak checks broken and the strong ones sound, deterministically, with no
model judging anything.

---

## Honesty notes / scope

- **Faithful port.** Findings are facts about promptfoo's *documented* assertion semantics, reproduced
  in `promptfoo_assertions.py` with every gradecore divergence annotated. They are not claims that
  promptfoo is buggy — `contains` *should* be a substring test; the finding is that **using a weak
  assertion as a correctness gate inherits a blind spot**, and evalmut surfaces exactly which.
- **What is not affected.** A suite that pairs `contains` with a stronger check, uses a fully-typed
  JSON schema, or uses `word-count` only alongside a content check, does not have these holes — and
  evalmut would report them clean.
- **Running against external graders (resolved).** evalmut's grader-family gates key off gradecore's
  `grader_id` vocabulary. To run against arbitrary external graders unmodified, a case now declares
  `grader_family="valid_json"` (etc.) and the grader keeps reporting its own honest id — see the
  `api_isjson` case, which declares the family while `pf_is_json` reports `grader_id="pf_is_json"` on
  the finding card. The declaration is for operator gating only; reporting stays honest.
