"""What a mutation did to an eval — the four outcomes, and the two ways an eval lies.

A mutation injects a *known* change into the system-under-test's output and reruns
the grader that was supposed to be watching. There are two kinds of change, and an
eval can be wrong about either:

  DEFECT mutation  — the output is now genuinely WRONG. A correct grader must reject
                     it. If the grader still passes, the eval is BLIND to that defect
                     class: a real regression of that shape would ship green.

  EQUIVALENT mutation — the output changed but is still CORRECT (whitespace, a
                     trailing disclaimer after a complete answer, a reordering the
                     spec allows). A correct grader must still pass it. If the grader
                     now fails, the eval is BRITTLE: it cries wolf on cosmetic change,
                     and a brittle check is quietly recalibrated or ignored until it
                     stops catching the real thing too.

Most eval tooling only ever asks the first question. Both are real failure modes in
the corpus this tool is mined from — a suite that misses regressions and a suite that
flags correct answers are both suites you cannot trust — so both are first-class here.

The classic mutation-testing subtlety (the "equivalent mutant" problem) is handled
structurally rather than statistically: an operator only *applies* to a case when it
can establish which polarity it is in for THAT case — i.e. that the mutated output is
provably wrong (DEFECT) or provably still correct (EQUIVALENT) relative to the case's
own reference answer. Where it cannot establish that, it returns NA and is excluded
from the score. So a MISSED/FLAGGED is never a guess: by construction the mutant had a
known correct answer and the grader disagreed with it.
"""
from __future__ import annotations

from enum import Enum


class Polarity(str, Enum):
    """Whether a mutation makes the output wrong, or leaves it correct."""

    DEFECT = "defect"          # mutated output is WRONG; a correct grader must REJECT it
    EQUIVALENT = "equivalent"  # mutated output is still CORRECT; a correct grader must ACCEPT it


class OperatorType(str, Enum):
    """What a survival *means* — the difference between a broken grader and a missing one.

    A DEFECT mutation that survives is always a hole, but not always the grader's fault,
    and saying which is the difference between a fair report and an unfair one:

      KILL       — a sound grader of this kind MUST catch this. Survival is a BLIND SPOT:
                   the check is present and broken. Fix the check.
      DIAGNOSTIC — this grader family is structurally blind to this shape BY DESIGN (e.g.
                   gradecore's valid_json checks key presence, never value type, and says
                   so). Survival is a COVERAGE GAP: no check in the suite guards this, which
                   is worth knowing but is not this grader misbehaving. Add a check.
      SANITY     — a floor probe (blank / garbage output). Survival means the grader asserts
                   nothing about the answer at all — a VACUOUS check that cannot fail.
    """

    KILL = "kill"
    DIAGNOSTIC = "diagnostic"
    SANITY = "sanity"


class Outcome(str, Enum):
    """What the grader actually did, judged against what a correct grader should do."""

    CAUGHT = "caught"    # grader behaved correctly (rejected a defect / accepted an equivalent)
    MISSED = "missed"    # DEFECT survived: grader passed a genuinely-wrong output  -> BLIND SPOT
    FLAGGED = "flagged"  # EQUIVALENT broke: grader failed a still-correct output   -> BRITTLE SPOT
    ERROR = "error"      # grader raised on a well-formed mutant -> it cannot render a verdict at all
    NA = "na"            # operator could not apply here (no correctness boundary it could cross)

    @property
    def is_hole(self) -> bool:
        """A hole is any way the eval got the answer wrong: a miss, a false flag, or a
        crash. A grader that raises on a valid mutant is broken in its own way — it cannot
        even produce a verdict — so it counts as a hole, reported apart from the others."""
        return self in (Outcome.MISSED, Outcome.FLAGGED, Outcome.ERROR)

    @property
    def counts_toward_score(self) -> bool:
        """NA and ERROR are excluded from the mutation score. NA is inapplicable; ERROR is
        an undetermined verdict (the grader crashed, so it neither caught nor missed) —
        counting a crash as a catch would let a fragile grader inflate its score, which is
        exactly the conflation the SANITY probes exist to expose."""
        return self not in (Outcome.NA, Outcome.ERROR)


def outcome_for(polarity: Polarity, grader_passed: bool) -> Outcome:
    """Given the mutation's polarity and whether the grader passed the mutant, what
    happened. This is the whole judgment, and it is deliberately tiny: the honesty
    lives in the operator deciding its polarity per case, not in a fuzzy threshold here.
    """
    if polarity is Polarity.DEFECT:
        # A wrong output. Correct grader rejects it (not passed) -> CAUGHT.
        return Outcome.CAUGHT if not grader_passed else Outcome.MISSED
    # EQUIVALENT: a still-correct output. Correct grader accepts it (passed) -> CAUGHT.
    return Outcome.CAUGHT if grader_passed else Outcome.FLAGGED
