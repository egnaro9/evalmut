# Card review template

For an independent reviewer. Copy this block once per card and return it however is easiest.

You are being asked about **card validity and applicability only**. Not about evalmut, not about
a product, not about the reproduction run's conclusion, and not about a score. There is no score.

---

## Card `CB-0NN`

**Classification** (pick one):

- [ ] `valid`, a defect shape a real suite owner would care about missing
- [ ] `invalid`, it is not, or the card mis-describes the defect
- [ ] `unclear`, cannot judge from what is given, and here is what is missing
- [ ] `scope-dependent`, valid for some suite semantics and not others, named below

**Which named suite semantic makes it applicable, or fails to?**

> 

**Rationale, one or two lines:**

> 

**Do you disagree with the card's own applicability judgement?** Four of the twelve are marked
`applicable: false` by the author. Those calls are the author's and are the ones most worth
challenging.

- [ ] agree with the author's applicability call
- [ ] disagree, because:

> 

---

## Ground rules

1. **Rejecting a card is a result, not a failure.** Rejections are published alongside
   acceptances. A review that only confirms is not independent.
2. **Disagreeing with another reviewer is fine and is preserved.** Disagreements are published as
   disagreements; nothing is reconciled into a consensus that nobody held.
3. **"Per-operator validity is the wrong unit of analysis" is an allowed verdict.** If the whole
   framing is wrong, say that instead of grading the cards.
4. Nothing you write is edited before publication except for length, and only with your approval.

## What the cards are bound to

| | |
|---|---|
| frozen corpus commit | `f1c97f3` |
| manifest sha256 | `c29928383f0c086b2716ea9a19c92cff4fa94f368081385290b5c174acf596fc` |
| reproduction run commit | `da97125` |
| cards | `external/corpus_b/cards/CB-0NN.json`, each hashed in `MANIFEST.json` |

The cards were hashed before anything was executed against them, so a card cannot have been
edited to match a result. One card (`CB-003`) predicted the wrong behaviour for its unmutated
input; that falsification is recorded in the run bundle rather than corrected in the card.
