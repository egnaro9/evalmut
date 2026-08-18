# Corpus B Gate Handoff

**Status:** Candidate corpus and external-reproduction evidence exist. Do not promote this to an
evalmut detection result, product validation, or buyer-facing evaluation claim.

This file exists so the plan and its boundaries are not reconstructed from memory after reviewer
feedback arrives. Where it disagrees with a recollection, this file and the commits it names win.

## Canonical commits

- `70d9d57` seal instance 001 and the protocol that binds it
- `7bd365d` record the 001 reseal and gate the cutoff defect
- `f1c97f3` freeze 12 externally sourced Corpus B candidate cards
- `da97125` `run-001`, cards reproduced against promptfoo's own code

## Frozen Corpus B

- 12 cards total, 8 applicable, 4 non-applicable
- `authored_by_egnaro9: 0`, 5 outside authors
- manifest sha256 `c29928383f0c086b2716ea9a19c92cff4fa94f368081385290b5c174acf596fc`
- freeze commit `f1c97f3`

Exclusions are evidence of scope, not omitted failures:

| card | predicate |
|---|---|
| CB-008 | output-mutation-inapplicable, the defect is in an assertion PARAMETER |
| CB-010 | message-only, verdict and score were already correct |
| CB-011 | performance-only, no verdict changes at all |
| CB-012 | live-provider confound, drift is indistinguishable from the defect |

The cards and manifest are frozen. Do not edit them to reconcile results. A corrected successor
card takes a NEW id and references the original.

## External reproduction evidence

`run-001` (`da97125`) is bound to `f1c97f3`, the manifest digest above, per-card hashes, source
URLs, and a recorded environment. It ran promptfoo's own code in an isolated detached worktree and
did not modify `~/promptfoo`.

**run-001 as recorded: 6 VERIFIED, 2 INCOMPLETE, 0 SURVIVED, 0 INVALIDATED.**

`VERIFIED` means the documented defect reproduced before the upstream fix and was absent after it,
with a post-fix control. It does **not** mean evalmut detected the defect.

### Correction: both INCOMPLETE cards have since been resolved

The instruction that produced this file described CB-002 and CB-006 as remaining incomplete. That
was true of `run-001` and is no longer true of the evidence on disk. Recorded here rather than
transcribed stale, because a handoff that contradicts the artifacts it points at is worse than no
handoff.

`external/corpus_b/runs/followup-002.json` **adds** observations and amends nothing. `run-001`
stays byte-unchanged; its INCOMPLETE states were accurate for the harness it had.

- **CB-002 resolved to VERIFIED.** The blocker was the harness, exactly as `run-001` said: bare
  `tsx` failed on an ESM interop error (`js-yaml` default export under Node 24) in a transitive
  import. Re-run through **promptfoo's own vitest runner**, which is how promptfoo executes this
  code itself, the defect reproduces: `SELECT DISTINCT name FROM users` is rejected pre-fix and
  accepted post-fix, while the genuinely ambiguous `SELECT a b FROM t` is rejected on BOTH sides.
  This is a harness correction, not a substituted implementation.
- **CB-006 resolved to VERIFIED.** A real parent-context invocation IS feasible: the module exists
  at the parent commit and the defect is in its own threshold line. With the upstream matcher
  stubbed to a score of 0, the default threshold PASSES pre-fix and FAILS post-fix, while an
  explicitly configured `threshold: 0` still passes on both sides. The stub is the upstream
  scorer, not the code under test, and its raw value is recorded per row as `raw_upstream_score`.

CB-003 remains deliberately preserved as `card_prediction_falsified`: the defect reproduced, but
its frozen clean-side prediction was wrong. Do not edit it away.

## What is still gated

Prohibited until the requirements below are satisfied:

- no evalmut detection-power claim
- no detection rate, score, ranking, or framework comparison
- no native CLI, report format, UI, adapters, gallery, or history
- no product or buyer-facing positioning
- no claim that Corpus B cards are validated operators

**The principal gate is independent card review.** At least 2 independent engineers per card,
each classifying `valid` / `invalid` / `unclear` / `scope-dependent` against a NAMED suite
semantic. Disagreements, rejected cards, refusals and nonresponses are published, not filtered.
Silence is not approval.

| reviewer | status |
|---|---|
| reviewer 1 | request sent 2026-08-17, awaiting response |
| reviewer 2 | drafted, held until a stated date |
| independent classifications | **0** |

Reviewers are identified by role here rather than by name. A person should learn they were asked
by being asked, not by finding themselves on a published schedule.

**The arithmetic, stated so it is not discovered late:** 12 cards x 2 reviews = 24 slots. Two
reviewers, each asked for 5 to 10 cards, tops out at 10 to 20. Two-per-card is unreachable with
two reviewers unless both review all twelve. Either narrow the claim to a named subset, or recruit
further reviewers under a recorded plan. Describing partial coverage as "independently reviewed"
is the failure this note exists to prevent.

## Work allowed before reviews return

1. Prepare the reviewer packet, template, assignment ledger, and conflict/nonresponse protocol.
   *(`external/corpus_b/review/` holds the template and protocol; the assignment ledger is
   kept privately outside this repository because it names people.)*
2. Queue the second request for its held date with the materials frozen. *(Draft ready.)*
3. Resolve CB-002 only by exercising promptfoo's actual code. *(Done, see above.)*
4. Investigate whether CB-006 can be invoked in its real parent context. *(Done, it can.)*
5. Build reusable next-run evidence infrastructure: per-row upstream invocation sentinels, raw
   upstream output capture, a predeclared scorer and denominator inventory, a deliberately broken
   local-scorer negative control, and clean-process support on a second OS and architecture.
   *(evalmut already has sentinels, raw-score capture, a negative control and a two-architecture
   CI matrix for its OWN suite. None has yet been pointed at a Corpus B run. The denominator
   inventory does not exist in any form.)*
6. Arrange, but do not reinterpret or aggregate, a second OS and architecture runner.
   *(`.github/workflows/corpus-b-second-runner.yml` exists and is `workflow_dispatch` only. It
   has **NEVER EXECUTED**. It parses, it verifies the sealed manifest digest before running
   anything, and it fails rather than finishing without an environment record, but none of that
   is the same as having run. No second-platform evidence exists and none may be claimed. The
   first manual dispatch is a control and probe execution, not a Corpus B detection run, and its
   artifacts are retained whether it passes or fails.)*

## Rules for any future run

A run may not be called an evalmut detection run unless all of these hold:

1. Corpus B card validity and applicability independently reviewed
2. fixture and operator manifest committed and hashed before execution
3. complete denominator and exclusion inventory declared before results
4. invocation sentinels prove the intended upstream method executed
5. raw upstream results recorded beside wrapper outcomes
6. a negative control shows the harness can distinguish a deliberately broken scorer
7. clean-process repetition on distinct OS and architecture runners
8. every exclusion carries a named applicability predicate
9. no aggregation into a rate unless its denominator was declared in advance

`INCOMPLETE`, `SURVIVED` and `INVALIDATED` must never be collapsed into a generic failure state.

## Future product sequence

Only after the gates above:

1. confirm a reviewed Corpus B operator-card batch
2. produce a canonical machine-readable evidence bundle
3. consider a native CLI
4. consider minimal read-only rendering
5. run with three external suite owners
6. measure ONE outcome: did a suite owner change a check, add a control, or alter a release
   decision
7. if no owner takes an action, stop building surfaces and investigate operator validity

## Claim boundary

The strongest currently supported statement:

> A frozen, externally sourced candidate corpus contains documented evaluation-suite defect cards.
> Eight cards reproduced against promptfoo's real pre-fix code and did not reproduce after the
> corresponding fix; six in `run-001` and two more in `followup-002` after a harness correction.
> This establishes upstream defect reproduction under the recorded protocol only. It does not
> establish card validity, evalmut detection, detection power, a comparative score, or product
> usefulness.

Do not weaken the qualifiers when writing summaries, messages, slides, READMEs, or release notes.
