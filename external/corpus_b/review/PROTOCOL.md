# Corpus B review protocol

How an independent classification is requested, recorded, and counted. Written before any review
arrived, so the rules cannot be shaped by the answers.

The bottleneck is independent classification, not tooling. Everything here exists to make a
reviewer's judgement cheap to give and impossible to quietly improve after the fact.

---

## 1. Scope of the ask

A reviewer judges **card validity and applicability against a named suite semantic**. Nothing
else. Not evalmut, not a product, not the reproduction run's conclusion, and not a score. There is
no score.

Four labels, and all four are real outcomes:

| label | means |
|---|---|
| `valid` | a defect shape a real suite owner would care about missing |
| `invalid` | it is not, or the card mis-describes the defect |
| `unclear` | cannot judge from what is given; the response says what is missing |
| `scope-dependent` | valid under some suite semantics and not others, both named |

`invalid` and `unclear` are first-class. A protocol that makes them awkward to give collects
agreement rather than review.

## 2. What a response must contain

Per card: the label, a rationale of at least a few words, and the **named suite semantic** the
judgement turns on. `validate_response.py` refuses a response missing any of these.

The validator also refuses a submission where **every** card is `valid` with rationales below a
minimum length. That combination is indistinguishable from a rubber stamp, and a review that
cannot be distinguished from a rubber stamp is not evidence. A reviewer who genuinely finds every
card valid can say so and clear the check by writing real rationales.

## 3. Independence

Two reviews of the same card count as independent only if the reviewers share no affiliation and
no co-authorship. Recorded per pair, not assumed.

**A live example of why this is checked rather than assumed:** two of the strongest candidates in
this field are long-standing co-authors on every relevant paper between them. Either would be a
fine reviewer; the pair would not be two. Names are held in the private ledger rather than
published here, since a person should not discover their own eligibility assessment before being
asked.

Never independent: Erik, any agent acting for him, and anyone who helped write or revise the card
under review.

## 4. Nonresponse

Silence is a recorded state, never an approval and never a rejection.

1. Send. Record `sent_at`.
2. Wait the predeclared interval: **14 days**.
3. One follow-up, once. Record `followed_up_at`.
4. Wait **7 more days**. If still silent, record `NONRESPONSE` with both dates and stop
   contacting that reviewer about this batch.
5. Approach a replacement using the same packet and the same assignment rule.

Nonresponse is published alongside classifications. A reviewer who declines is recorded as
`REFUSED`, which is also published, and is not a mark against them.

## 5. Disagreement

Two reviewers disagreeing on a card is a result, not a problem to fix.

- **Both rationales are preserved verbatim.** Neither is summarised into the other.
- **The card is not edited to reconcile them.** A card is frozen; a correction takes a new id
  that references the original.
- **No tiebreaker is sought to produce a majority.** A third review may be added for information,
  but it does not overturn or average the first two.
- The published record shows the disagreement as a disagreement.

The verdict "per-operator validity is the wrong unit of analysis" is allowed and is recorded as
such rather than forced into one of the four labels.

## 6. Assignment

The assignment ledger lives outside this repository because it names people.

Assign so that no two reviewers of a card share an affiliation or co-authorship, and so each of
the four `applicable: false` cards reaches at least one reviewer, since those calls are the
author's own and are the most likely to be wrong.

**The arithmetic, stated up front:** 12 cards x 2 reviews = 24 slots. Two reviewers asked for 5 to
10 cards each tops out at 10 to 20. Two-per-card is unreachable with two reviewers unless both
review all twelve. Either narrow the claim to a named subset or recruit further reviewers under a
recorded plan. Reporting partial coverage as "independently reviewed" is the failure this protocol
exists to prevent.

## 7. Files

| path | what |
|---|---|
| `review/PROTOCOL.md` | this file |
| `review/TEMPLATE.md` | what a reviewer fills in |
| `review/response_schema.json` | the machine-checkable shape of a returned review |
| `review/validate_response.py` | refuses malformed, thin, or rubber-stamp submissions |
| `review/responses/` | returned reviews, one file per reviewer, unedited |

Returned reviews are committed **verbatim**. Formatting may be normalised; wording is not.
