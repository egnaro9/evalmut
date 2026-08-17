# Status audit: Corpus B evidence and study readiness

Audited 2026-08-17 by inspection of the repository, the outbound records on disk, and the
platforms' own APIs. Nothing here is inferred from a filename, a plan, or a passing test suite.

**Governing question.** Have we acquired and independently validated enough Corpus B evidence to
justify proceeding beyond the methodology and proof-console stage?

**Answer: no.** One reviewer request has been sent and is unanswered. Zero cards carry an
independent classification. The gate that the handoff itself sets, "Corpus B exists and survives
independent review", is not met, and the distance is measured in responses we do not control
rather than in work not yet done.

A correction this audit produced about itself: a first pass classified operator origins with a
loose keyword regex and reported 11 external / 14 internal. That was wrong in both directions.
Re-run against resolvable URLs and `org/repo#N` references only, the split is **9 external / 16
internal**, with zero unresolvable citations. The numbers below are from the second pass.

---

## 1. Corpus B sourcing

### 1a. Candidate identification: PARTIALLY COMPLETE

**Verified.** `docs/operators.json` holds 25 operators, every one carrying a `real_origin`, and
`tests/test_evalmut.py:68 test_every_operator_names_a_real_origin` fails the build if one does
not, checking both length and the presence of a citation token.

**The gate is weaker than it looks, and this matters for the Corpus B question.** Its accepted
tokens are `(".py", ".sh", ".md", ".java", ":", "model-drift", "gradecore")`. Two of those name
our own repositories and one is a bare colon, so the gate enforces "names a concrete artifact",
never "names an EXTERNAL artifact". An operator sourced entirely from our own machinery passes it
cleanly. The citation discipline is real; it is just not the discipline that would establish
Corpus B, and no gate currently enforces that one.

Of those 25, **9 cite a resolvable external artifact**:

| operator | external source |
|---|---|
| `malformed_structure` | promptfoo/promptfoo#9782 (merged) |
| `parser_accepted_variant` | promptfoo/promptfoo#9784 (merged) |
| `numeric_format_variant` | EleutherAI/lm-evaluation-harness#3214 |
| `leading_article_variant` | EleutherAI/lm-evaluation-harness#3399 |
| `identical_to_reference` | google/BIG-bench#463 |
| `spurious_cue_token_insert` | arXiv:1907.07355 (Niven & Kao, ACL 2019) |
| `append_grader_directed_suffix` | arXiv:2403.17710 (Shi et al., CCS 2024) |
| `garbage_answer` | arXiv:2410.07137 |
| `inject_denylisted_tool` | arXiv:2605.12673 |

Two further candidates are mined and deliberately **not** promoted, in
`OPERATOR_BACKLOG.md:106-130`: `delimiter_in_payload` (confident-ai/deepeval#2917, corroborated by
the HF Open LLM Leaderboard DROP post-mortem) and `equivalent_restatement`
(EleutherAI/lm-evaluation-harness#3652, MMLU-Redux). Both are blocked on a declaration evalmut
cannot currently read, and the file says so.

So the count is in the 5 to 10 band the plan asks for, if the band is read as "candidates with
external citations". **Independently verified:** the citations exist as text and the gate test
exists. **Asserted, not verified:** that each cited artifact actually says what the `real_origin`
field claims. I resolved none of the nine URLs during this audit.

**Missing.** The full card schema. Present per operator: `id`, `family`, `polarity`, `op_type`,
`field`, `defect_shape`, `real_origin`. **Absent for every operator:** target layer as a declared
field (family is a proxy, not the same thing), transfer claim, applicability predicate,
counterexample, known risks. Five of the seven required card elements do not exist as data.

**Smallest next action.** Extend the operator record with the five missing fields for the 9
externally-cited operators only, and resolve each URL to confirm the claim. Owner: Claude, one
session, no external dependency.

### 1b. Are they truly Corpus B: INVALID / NEEDS REDO (as a population claim)

**Verified by counting.** 16 of 25 origins trace to Erik's own machinery: `gradecore
adversarial.py` (10), `gradecore graders.py` (2), `gradecore grounding.py`, `gradecore
trajectory.py`, `model-drift providers.py`, and one internal CI proof-gate. The corpus that
produced the published dogfood run is Corpus A by construction.

This is sharper than a gap in coverage. **All four surviving holes in the published run are
Corpus A**: `keyword_present_but_negated` (internal CI gate), `spurious_cue_token_insert`
(external paper, but the case it ran against is ours), and both JSON coverage gaps
(`gradecore adversarial.py:149`). The headline finding on the live proof console rests entirely
on our own evidence machinery. The page now says so in its scope block; that is disclosure, not
resolution.

**Missing.** Any run of the tool against an external suite's own fixtures.

**Smallest next action.** Build a corpus of promptfoo assertions from the two merged PRs above and
run evalmut against it, keeping the result separate from the dogfood bundle. Owner: Claude.

---

## 2. Independent card review

### 2a. Two independent engineers per card: NOT FOUND

Zero cards have been reviewed by anyone. Not one classification exists.

### 2b. Outreach: SENT / AWAITING RESPONSE (one of two)

**Théo Fidry: SENT, verified against GitHub's own API rather than the local log.**
`infection/infection#3018`, comment id `5315940072`, created `2026-08-17T12:19:31Z`, author
`egnaro9`, 1552 bytes. It is the last comment on that thread; the previous one is `theofidry` on
`2026-07-12`. **No reply. No acknowledgement.** Elapsed at audit time: under one day.

**Alex Groce: NOT SENT.** `~/Desktop/Resume/CARD_REVIEW_OUTREACH.md` holds a complete draft
addressed to `Alex.Groce@nau.edu`, deliberately held to **no earlier than 2026-08-20** so two asks
do not hit the same small community in one week. A scheduled task `groce-card-review-email` exists
to fire it. Status is correct and intentional, not a slip.

### 2c. Reviewer identity, timestamps, originals preserved: NOT APPLICABLE YET

The mechanism is in place (public GitHub thread, preserved by the platform; the draft names
attribution terms and states that disagreements get published as disagreements, including the
verdict that per-operator validity is the wrong unit of analysis). Nothing to preserve yet.

### 2d. Disagreements and rejections retained: PARTIALLY COMPLETE

**Verified.** `OPERATOR_BACKLOG.md:106-130` publishes two mined-and-rejected cards with reasons,
and `OPERATOR_BACKLOG.md:103` records a shape judged out of scope for the tool entirely. The
repository already practices publishing what did not make it.

**Missing.** All of it is self-rejection. No external rejection exists because no external review
exists.

**Smallest next action.** Send the Groce email on or after 2026-08-20. Owner: Erik, one word to
release it. Then wait; there is no third name queued, and manufacturing one to fill the slot would
be the failure this program exists to name.

---

## 3. Fixture manifest

### VERIFIED COMPLETE, with one ordering caveat

**Verified.** `docs/dogfood_fixtures.json` exists, `manifest_version: 1`, `case_count: 14`,
`corpus_sha256: d3c9f0fb8ba0da3f...`, and every case carries its own `sha256` plus the full
fixture (`good.text`, `expected`, and the `declared` block naming judges, tolerances and
`tolerates` vocabulary). It is emitted by the same subprocess battery as every other artifact,
per `emit_vac.py:55`, so its bytes are pinned by the same freshness gate.

**Verified by use, this session.** The hole explorer joins survivors to their clean form through
this manifest, and a test proves a renamed case drops the pairing rather than borrowing a wrong
one, so the manifest is load-bearing rather than decorative.

**Caveat, PARTIALLY COMPLETE.** The manifest is committed and content-hashed, but "hashed
**before** any scorer run" is not provable from git history alone: `abb1016` adds the manifests to
the battery, and the battery emits results and manifest in the same commit. The ordering is
enforced by construction (the manifest hashes the INPUTS the run consumed) rather than by
timestamp. That is a defensible design and an undefended claim.

**Missing.** Explicit paired-control behaviour and a stated selection source for the 14 cases.

**Smallest next action.** Add a `selection_source` field and a one-line rationale per case. Owner:
Claude.

---

## 4. Study protocol

### 4a. Predeclared denominator inventory: PARTIALLY COMPLETE

**Verified.** The exclusion RULE is declared and implemented: an operator that cannot establish
polarity returns N/A and leaves the denominator (`evalmut/outcome.py:26`, `:89`,
`evalmut/runner.py:118`, `README.md:85`, `paper/evalmut.md:89`). The published run reports
`na: 223` beside `caught: 42`, so the excluded population is visible rather than hidden.

**Missing.** A predeclared *inventory* of all discovered scorers with a per-exclusion reason. What
exists is a rule plus an aggregate count, not a row-level ledger a reviewer can audit.

### 4b. Invocation sentinels: VERIFIED COMPLETE

`evalmut/sentinel.py` implements `sentinel()`, `Witness`, `require_invoked()`, and
`UpstreamNeverRan`; `tests/test_sentinel.py` covers invoked, not-invoked, and raised. Commit
`035f51a` "Prove the upstream scorer ran, instead of inferring it from an import". A `LIVENESS`
outcome type exists in `evalmut/outcome.py:68`.

### 4c. Raw upstream score captured per row: VERIFIED COMPLETE

`Witness.raw_score()` (`evalmut/sentinel.py:43`) and `as_evidence()` (`:49`) capture the upstream
value beside any wrapper verdict; asserted in `tests/test_sentinel.py:45,56,77`.

### 4d. Deliberately broken scorer as negative control: VERIFIED COMPLETE

`tests/test_negative_control.py`, commit `e29fde9`. The commit message states the gap it closed
plainly: every fixture had been a grader believed correct, so the suite could only demonstrate the
absence of false positives, never that a definitely-broken check gets reported.

### 4e. Distinct OS and architecture runners: VERIFIED COMPLETE

CI matrix is `[ubuntu-latest, macos-14] x [3.11, 3.12]`, which is x86_64 and arm64, with the
reasoning committed in the workflow itself. `gradecore` is pinned to `0.10.0`, the version the
findings are about.

---

## 5. Goodhart / holdout design

### NOT FOUND

No sealed holdout operator set, no hash, no reveal schedule, no anti-gaming rules, no adversarial
review of the design. Searched `evalmut`, `vac-protocol`, `reference-fleet` and `agent-certlab`
for `holdout`, `hold-out`, `sealed` and `goodhart`: zero matches in any repository.

This is the largest untouched item in the audit, and it is the one that decides whether a future
score means anything once the operator set is public. It is also the one with no external
dependency: it can be built today.

**Smallest next action.** Seal a holdout set: reserve N operators, publish only their hashes,
define the reveal schedule and the rule for suite revision between reveals. Owner: Claude, gated
on Erik picking N and the reveal cadence.

---

## 6. External-suite-owner usefulness

### Three owners recruited: NOT FOUND. Any owner ran it: NOT FOUND. Measured owner action: NOT FOUND

**Verified.** `~/Desktop/Resume/OUTREACH_LOG.md` records replay and issuer asks to Mike Czerwinski
and Giulio D'Erme (both `2026-08-14`, follow-up due `2026-08-22`, both **pending**), a further
issuer ask to Giulio on `2026-08-16` on `vac-protocol` PR #2, and METR contacts on `2026-08-15`.
None of these is an owner of a public deterministic eval suite being asked to run this tool on
their own suite, which is the item.

The nearest true instance is indirect and worth naming honestly: two evalmut operators cite
promptfoo PRs #9782 and #9784, both **merged**, and both authored by `i-anubhav-anand` rather than
by us. That is evidence the defect class is real in a real suite. It is not evidence that a suite
owner used this tool, and it must not be reported as the latter.

**Missing.** Any contact with a maintainer of a public deterministic eval suite about running
evalmut against it. Zero of three.

**Smallest next action.** Do not start this until item 2 returns a signal. Recruiting suite owners
before a single card has an independent classification spends the scarcest resource, other
people's attention, on a claim we cannot yet support. Owner: Erik's call.

---

## Gate decision

**PROCEED on methodology and proof-console work. DO NOT PROCEED to framework or product
language, external suite-owner recruitment, or any claim of validated external detection power.**

The three items that would move this gate, in order of what is actually blocking:

1. **Two independent card classifications.** Blocked on other people. 1 of 2 requests sent, 0
   answered. Nothing to do but wait, then send Groce on 2026-08-20.
2. **A run against an external suite's own fixtures.** Not blocked on anyone. This is the item
   that would let the population claim be something other than self-referential.
3. **A sealed holdout set.** Not blocked on anyone.

Items 2 and 3 are buildable now and neither requires a reply. Item 1 cannot be accelerated by
working harder, and the correct response to that is to stop describing the research gate as nearly
closed. One unanswered comment, posted today, is the entire external evidence base.
