"""Turn a list of mutation results into a score and a list of holes.

The headline number is the eval mutation score: of the mutations that applied, what
fraction did the eval handle correctly (caught a defect, or held firm on an
equivalent). NA is excluded from the denominator — an operator that had nothing to
say about a case is not evidence either way, and folding it in would let a suite
inflate its score by being mostly inapplicable.

NA and ERROR are both out of the denominator, but for different reasons and with a
catch: NA is genuinely inapplicable, while ERROR is an *undetermined* verdict (the
grader crashed). Excluding ERROR is right — a crash is not a catch — but it means a
grader that crashes on the very defects it can't handle would read a clean 100% with an
empty blind-spots list. So `crashing_defects` re-surfaces exactly those (a DEFECT the
grader raised on), and the report prints them beside the blind spots; a defect-crash can
inflate the number but can never hide.

But the number is the least important output. The holes are the product: each MISSED
is a defect class the eval is blind to, each FLAGGED is a correct-output class it
breaks on, and every one names the real documented failure it is the shape of. That
provenance is the difference between "your score is 0.82" (unactionable) and "your
`contains` check passed a reply truncated before the answer — the exact 429/MNAR
shape from model-drift" (a specific thing to fix).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from .outcome import OperatorType, Outcome, Polarity
from .runner import MutationResult


@dataclass(frozen=True)
class Tally:
    caught: int = 0
    missed: int = 0
    flagged: int = 0
    error: int = 0
    na: int = 0

    @property
    def applied(self) -> int:
        # Excludes NA (inapplicable) and ERROR (undetermined — the grader crashed).
        return self.caught + self.missed + self.flagged

    @property
    def holes(self) -> int:
        return self.missed + self.flagged + self.error

    @property
    def score(self) -> float:
        """Caught / applied. 1.0 when there is nothing to catch (vacuously robust);
        callers that care distinguish that with `applied == 0`.

        THE TRAP THIS LEAVES FOR CALLERS. 1.0 is convenient arithmetic and a lie in a report:
        an empty population rendered "100%" in three of this repo's four presentation paths,
        including the CI one-liner, so a run where NOTHING could be measured read as a perfect
        score. Zero would be no better; it would claim measured failure. The honest state is
        undefined, because the denominator is zero. Renderers must call `scored` and print
        nothing numeric when it is False. `report.py`'s per-grader cell already did this."""
        return 1.0 if self.applied == 0 else self.caught / self.applied

    @property
    def scored(self) -> bool:
        """Is there a denominator at all? False means no percentage may be published."""
        return self.applied > 0

    def with_outcome(self, outcome: Outcome) -> "Tally":
        return Tally(
            caught=self.caught + (outcome is Outcome.CAUGHT),
            missed=self.missed + (outcome is Outcome.MISSED),
            flagged=self.flagged + (outcome is Outcome.FLAGGED),
            error=self.error + (outcome is Outcome.ERROR),
            na=self.na + (outcome is Outcome.NA),
        )


@dataclass(frozen=True)
class Report:
    total: Tally
    by_grader: dict[str, Tally]
    by_operator: dict[str, Tally]
    by_family: dict[str, Tally]
    holes: list[MutationResult]      # every MISSED and FLAGGED, most-severe framing first
    results: list[MutationResult] = field(default_factory=list)
    baseline_failures: tuple = ()    # cases whose grader failed its own reference (mis-specified)

    @property
    def score(self) -> float:
        return self.total.score

    @property
    def blind_spots(self) -> list[MutationResult]:
        """A KILL mutation that shipped green: the check is present and BROKEN. The
        most serious finding — a real regression of this shape would pass the suite."""
        return [h for h in self.holes
                if h.outcome is Outcome.MISSED and h.op_type is OperatorType.KILL]

    @property
    def coverage_gaps(self) -> list[MutationResult]:
        """A DIAGNOSTIC mutation that survived: no check in the suite guards this shape.
        Not a broken grader — a missing one. Worth knowing; often expected."""
        return [h for h in self.holes
                if h.outcome is Outcome.MISSED and h.op_type is OperatorType.DIAGNOSTIC]

    @property
    def forged_verdicts(self) -> list[MutationResult]:
        """A LIVENESS mutation that survived: the grader honored a verdict written by the thing
        it was grading. Strictly worse than a blind spot and listed apart from one, because the
        instruction "fix the check" is wrong here. Nothing this grader has ever reported is
        falsifiable while the channel stays writable, including its passes."""
        return [h for h in self.holes
                if h.outcome is Outcome.MISSED and h.op_type is OperatorType.LIVENESS]

    @property
    def vacuous(self) -> list[MutationResult]:
        """A SANITY mutation (blank/garbage) that survived: the grader asserts nothing
        about the answer and cannot fail. The floor is broken."""
        return [h for h in self.holes
                if h.outcome is Outcome.MISSED and h.op_type is OperatorType.SANITY]

    @property
    def brittle_spots(self) -> list[MutationResult]:
        """An EQUIVALENT mutation that got flagged: the check fails a still-correct output
        (a false-positive generator)."""
        return [h for h in self.holes if h.outcome is Outcome.FLAGGED]

    @property
    def errors(self) -> list[MutationResult]:
        """The grader raised on a well-formed mutant — it cannot render a verdict at all."""
        return [h for h in self.holes if h.outcome is Outcome.ERROR]

    @property
    def crashing_defects(self) -> list[MutationResult]:
        """DEFECT mutants the grader CRASHED on rather than rejecting. These are excluded from
        the score as undetermined — but a grader that crashes on a defect did not catch it, so
        they must be surfaced beside the blind spots, never allowed to silently empty that list
        (a grader made to raise on the defects it can't handle would otherwise read as clean —
        cold-critic pass-2 G)."""
        return [h for h in self.errors if h.polarity is Polarity.DEFECT]

    @property
    def clean(self) -> bool:
        return not self.holes


def score(results: Sequence[MutationResult]) -> Report:
    total = Tally()
    by_grader: dict[str, Tally] = defaultdict(Tally)
    by_operator: dict[str, Tally] = defaultdict(Tally)
    by_family: dict[str, Tally] = defaultdict(Tally)

    for r in results:
        total = total.with_outcome(r.outcome)
        by_grader[r.grader_id] = by_grader[r.grader_id].with_outcome(r.outcome)
        by_operator[r.operator_id] = by_operator[r.operator_id].with_outcome(r.outcome)
        by_family[r.family] = by_family[r.family].with_outcome(r.outcome)

    # Order by how alarming the hole is (must match the rank() body below):
    #   0 vacuous     — a SANITY probe survived; the grader asserts nothing, cannot fail
    #   1 blind spot  — a KILL defect shipped green; a present check is broken
    #   2 error       — the grader crashed on a well-formed mutant; no verdict at all
    #   3 brittle     — an EQUIVALENT was flagged; the check false-positives on correct output
    #   4 coverage gap— a DIAGNOSTIC survived; no check guards this shape (often expected)
    def rank(r: MutationResult) -> int:
        if r.outcome is Outcome.MISSED and r.op_type is OperatorType.SANITY:
            return 0
        if r.outcome is Outcome.MISSED and r.op_type is OperatorType.KILL:
            return 1
        if r.outcome is Outcome.ERROR:
            return 2
        if r.outcome is Outcome.FLAGGED:
            return 3
        return 4  # MISSED + DIAGNOSTIC
    holes = sorted(
        (r for r in results if r.outcome.is_hole),
        key=lambda r: (rank(r), r.grader_id, r.operator_id),
    )

    return Report(
        total=total,
        by_grader=dict(by_grader),
        by_operator=dict(by_operator),
        by_family=dict(by_family),
        holes=holes,
        results=list(results),
    )
