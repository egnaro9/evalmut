# Instance 001, audit notes

Append-only. Written before publication of `commitment-001.json`. Nothing here edits a
commitment; the protocol's no-editing rule is intact.

---

## 1. Pre-publication reseal, one occurrence

| | |
|---|---|
| discarded draft digest | `bdc664ef48c0db9b6b15…` (recorded prefix; the draft was never written to a published file, and the salt that produced it was overwritten) |
| published commitment digest | `7ff8b5ed46e20398a6e4…`, the operative and only commitment for instance 001 |
| reason | finalizing the auditor-recomputable `algorithm` block required re-running the sealer, which minted a fresh salt |
| status between the two | no result produced, no eligible candidate selected, no suite revision landed |

Evidence for the status line, rather than assertion:

- **No suite revision.** `git log 4e63231..HEAD -- evalmut/operators.py evalmut/operator.py
  evalmut/case.py demos/ external/` returned empty at the time of sealing.
- **No result.** No holdout run has been executed. There is nothing to have been disappointed by,
  which is the situation the no-reseal rule exists to police.
- **No eligible candidate.** See section 2.

The draft is not a competing commitment. It was never published, never verified against a payload
in any committed artifact, and its salt no longer exists.

---

## 2. Defect found in instance 001: the cutoff preceded the seal

**The `cutoff_utc` of `2026-08-17T23:00:00Z` was already in the past when the seal was made.** The
sealing commit `70d9d57` is dated `2026-08-17T23:16:23Z`, so the rule opened a **16-minute
retroactive window** in which a qualifying report could already have existed.

This matters because instance 001's whole claim to *hiding* rests on the payload not existing at
seal time. `hiding: "everyone, including the author: the selected reports do not exist yet"` is a
statement about construction, and for those 16 minutes it was not guaranteed by construction.

**Checked rather than assumed.** At `2026-08-17T23:20Z`, across all five named sources:

```
gh api "search/issues?q=repo:<REPO>+created:>=2026-08-17T23:00:00Z" --jq .total_count

promptfoo/promptfoo                 0
EleutherAI/lm-evaluation-harness    0
confident-ai/deepeval               0
openai/evals                        0
huggingface/lighteval               0
```

Zero items of any kind, before the predicate's further filters are applied. So no eligible
candidate existed in the retroactive window, and the selected set is unaffected in practice.

**That query is an empirical observation, not a retroactive construction guarantee.** It supports
the conclusion that the window was empty. It cannot convert a 16-minute interval that was open by
construction into one that was closed by construction, and no later check can. The two are
different kinds of evidence and this note does not let the stronger word stand in for the weaker
one.

**The honest statement of what 001 now guarantees.** Hiding for instance 001 rests on an empirical
check over a 16-minute window plus construction thereafter, not on construction alone. That is
weaker than the commitment's `hiding` string implies, and a reader should treat this note as
qualifying that field.

**Not corrected by resealing.** Fixing the string or the cutoff would mint a third digest for an
instance whose published digest has already been named as operative, and would trade a disclosed
16-minute qualification for an undisclosed reseal. The qualification is the smaller cost and it is
recorded here.

**`commitment-001.json` remains byte-identical to its state at `70d9d57`.** There is no third
digest, no replacement commitment, and no edit to the sealed file. `7ff8b5ed46e20398a6e4…` is the
sole operative commitment for instance 001; `bdc664ef48c0db9b6b15…` is a discarded pre-publication
draft and nothing else.

**Carried forward, as a gate rather than a promise.** From the commit that adds this note onward,
sealing a `KIND_RULE` **requires a checked `now_utc`** and **refuses any `cutoff_utc` that is not
strictly later than that instant**. `seal()` also refuses a rule that states no cutoff at all,
because without one there is no moment before which the material provably did not exist. Re-running
the exact call that produced instance 001 is now rejected by name. A note is a promise; this is the
mechanism that keeps it.
