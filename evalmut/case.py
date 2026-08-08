"""An eval case: a grader and a reference-correct output it passes.

This is the unit a mutation is applied to. The crucial field is `good`: a
GradeInput the grader is known to PASS. Mutation testing needs a green baseline
for the same reason code mutation testing does — you cannot ask "would this check
catch a defect I introduce?" if the check is already failing on the clean input.
The runner refuses to score a case whose baseline is red and tells you which, so a
mis-specified reference is a loud error rather than a silently skipped one.

`good` is also the ground truth every operator reasons against. Because the grader
passes it, `good` is by definition a correct output for this task; an operator that
transforms `good` into something wrong has, relative to this reference, injected a
real defect — no separate oracle required.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gradecore import GradeInput, Grader


@dataclass(frozen=True)
class EvalCase:
    name: str
    grader: Grader
    good: GradeInput
    # Which GradeInput fields the grader actually judges. A mutation is only a defect
    # relative to what the task grades: blanking `text` is a real defect for "answer the
    # question" but not for "did the agent avoid a denylisted tool", where the text is
    # incidental and the grader rightly ignores it. Defaulting to ("text",) covers the
    # overwhelming majority (scalar/text/safety graders); a tool or retrieval case names
    # its own fields so text operators don't fire on it and manufacture false findings.
    judges: tuple[str, ...] = ("text",)
    # The numeric acceptance band the grader uses, if this is a numeric-answer task. A
    # near-miss is a defect only if it falls OUTSIDE the tolerance — and that band lives in
    # the grader's closure, invisible to an operator. Declaring it here lets the numeric
    # operator perturb to just past the band (a provable defect) instead of guessing a delta
    # that a tolerant grader is right to accept. Left None, the numeric operator declines.
    num_tol: float | None = None
    # Optional human-readable notes surfaced in reports; never load-bearing.
    intent: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def baseline(self):
        """The grader's verdict on the clean reference. Must pass, or the case is
        mis-specified and the runner will refuse to mutate it."""
        return self.grader(self.good)


def case(name: str, grader: Grader, good: GradeInput, *, judges: tuple[str, ...] = ("text",),
         num_tol: float | None = None, intent: str = "", tags: tuple[str, ...] = ()) -> EvalCase:
    """Terse constructor for suites written as data."""
    return EvalCase(name=name, grader=grader, good=good, judges=judges,
                    num_tol=num_tol, intent=intent, tags=tags)
