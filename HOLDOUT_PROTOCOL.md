# Holdout protocol

A public operator set gets optimized against. This document fixes, in advance, a set of operators
the suite is not allowed to see, so that a later reveal measures **transfer** rather than fit.

It is written before any holdout run, and it says what the mechanism cannot do as plainly as what
it can.

---

## 1. What a seal here proves, and what it does not

A commitment normally buys two properties:

| property | meaning | available here |
|---|---|---|
| **binding** | the committed value cannot be changed afterwards | **yes** |
| **hiding** | the commitment reveals nothing about the value | **only for a preregistered rule** |

A hash published by the same person who revises the suite is **binding and not hiding.** It proves
the holdout was fixed before the suite moved. It cannot prove the author never looked, because the
author already holds the plaintext.

Every commitment therefore carries a `hiding` field naming who the value is actually hidden from.
A self-held seal records `hiding: "nobody"`. Any future claim that a holdout result is
independent must point at that field, and a `"nobody"` there means the result is a **self-report
with a tamper-evident timestamp**, not an independent measurement.

The honest way to get hiding is a second party who holds the salt. There is no second party yet.
See the audit's item 2: independent review currently stands at zero.

### Salts are load-bearing, not hygiene

If a holdout is "k of the operator ids in this repo", the space of possible sets is small:

```
C(25,2) =    300
C(25,3) =  2,300
C(25,5) = 53,130
```

An unsalted digest over a canonical listing is invertible by enumeration in under a second, so it
would be neither binding-and-hiding nor even weakly private. Every commitment mixes a 32-byte
random salt, withheld until reveal. `holdout.digest()` refuses a salt shorter than 32 characters.

---

## 2. Why instance 001 is a rule, not a set

**There is currently no legitimate holdout material.** Every externally sourced defect this
project knows about is either already implemented as an operator, or already published in
`OPERATOR_BACKLOG.md`. Sealing an already-public item would be theatre: the suite has seen it.

A commitment over material that **does not yet exist** is hiding against everyone, including its
author, because there is nothing to peek at. So instance 001 seals a **preregistered selection
rule**: a predicate plus a cutoff, applied later to defect reports that had not been filed when
the seal was made.

The predicate itself is published in full. Publishing it is safe and desirable: knowing the rule
does not tell you which future reports will satisfy it, and it lets anyone check that the reveal
applied the rule they were shown rather than a rule invented afterwards.

---

## 3. Selection

**Development operators (public).** Everything currently in `docs/operators.json`. These may be
studied, revised, and optimized against without restriction. That is what a development set is
for.

**Holdout operators (sealed).** Selected by the instance's rule or set, and never implemented,
named, tested against, or referenced anywhere in the public tree until reveal.

A candidate is eligible for holdout only if it satisfies the same bar as any operator here: a
concrete, documented external instance, cited. A holdout of authored guesses would measure
imagination, which is the blind spot this tool exists to find.

---

## 4. Revision boundary

A **suite revision** is any commit reachable from `HEAD` but not from the seal commit that touches
any of:

```
evalmut/operators.py
evalmut/operator.py
evalmut/case.py
demos/
external/
```

This is a commit range over named paths, not a date and not a recollection. Ambiguity about when a
revision happened is how a disappointing holdout result gets argued away afterwards, so the
boundary is countable: `holdout.revisions_since()` returns the exact list.

The seal commit must be an ancestor of `HEAD` (`holdout.seal_precedes_revisions()`). A commitment
anchored to an unreachable commit proves nothing about ordering, which is the whole point.

---

## 5. Reveal schedule

A holdout is revealed when **either** condition is met, whichever comes first:

1. **Ten or more suite revisions** have landed since the seal, as counted in section 4; or
2. the instance's `reveal_after` date has passed.

At reveal, publish the salt and the payload, and record the result as a **transfer diagnostic**:

- how many holdout operators the suite's checks caught,
- beside the same figure for the development set at the same commit.

The gap between those two numbers is the finding. A single holdout number on its own is not
interpretable, because it confounds transfer with the difficulty of the holdout items.

### What a failed transfer means

**A low holdout result is evidence that public-set improvements may be overfit. It is not proof of
cheating, and it must never be reported as one.** The likeliest explanations, in the order they
should be considered:

1. the development operators were narrower than the class they were meant to represent;
2. the holdout items are harder, or from a different layer, and the comparison is unfair;
3. the suite genuinely regressed on shapes it once handled;
4. someone optimized against the holdout.

Only the fourth is misconduct, and the mechanism here cannot distinguish it from the first three.
Report the gap and the candidate explanations together, or do not report it.

---

## 6. Rotation

A revealed holdout is dead as a holdout. On reveal:

1. the revealed operators become development operators and may be implemented;
2. a new instance is sealed **before** any of them is implemented, so there is never a window in
   which the suite is being revised with no holdout outstanding;
3. the new instance's number increments; commitments are append-only and never edited.

If no eligible material exists at rotation time, seal a preregistered rule instead of skipping.
Skipping is how a holdout quietly stops existing.

---

## 7. Anti-gaming rules

1. **No reseal after a bad result.** A holdout that fails verification is discarded, not
   re-sealed. `holdout.verify()` raises with both digests rather than returning a boolean, so a
   failure cannot be shrugged off.
2. **No editing a commitment.** Commitments are append-only files. A change to a committed file is
   a protocol violation regardless of intent, and git history makes it visible.
3. **No holdout identifier in the public tree before reveal.** Enforced by
   `holdout.scan_for_disclosure()` in CI, which fails the build on a leak in any file. This is the
   likeliest failure mode and it needs no malice, only autocomplete.
4. **No implementing an operator that a reader would recognize as a holdout item.** Where this is
   a judgement call, the judgement is recorded in the reveal notes.
5. **The reveal reports the development-set figure at the same commit.** A holdout number without
   its control is not a measurement.
6. **No score language.** The reveal produces a transfer diagnostic. It is not a certification, a
   grade, or a leaderboard entry, and the word "score" does not belong on it.

---

## 8. Files

| path | contents |
|---|---|
| `holdout/commitment-NNN.json` | public: digest, the recipe for recomputing it, dates, boundary, rotation, and for a rule, the rule |
| `holdout/reveal-NNN.json` | published at reveal: salt, payload, transfer diagnostic |
| `~/.evalmut-holdout/` | plaintext for a sealed SET, deliberately outside the repo so a push cannot leak it |

The commitment file never contains holdout content. That is a property of the `Commitment`
dataclass, not a convention, and a test asserts it by SHAPE: no 64-hex token other than the digest
may appear in the file.

Each commitment also records its own `algorithm`: hash, input construction, canonical-JSON rules,
and salt width. An auditor holding only the published JSON can therefore recompute the seal
without this repository's code, and a test does exactly that with a standalone reimplementation
rather than by calling `digest()` again. A commitment verified only by the function that produced
it proves that the function agrees with itself.
