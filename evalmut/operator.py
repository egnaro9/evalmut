"""A mutation operator: a mined defect shape, and the rule for injecting it.

Every operator carries the concrete, documented failure it is the shape of
(`real_origin`). This is not decoration — it is the project's whole claim to
honesty. An *authored* mutation operator only tests what its author already
imagined a check might miss, which is exactly the blind spot you are trying to
find. A *mined* operator reproduces a defect that actually happened and actually
got past a check. Every operator in this package must name one; an operator that
cannot is cut.

`apply(good) -> GradeInput | None` is the contract. It returns a mutated input, or
None when the operator cannot establish its polarity for this case. That None is
the equivalent-mutant defense: rather than mutate blindly and then guess whether a
survival is a real hole, an operator applies ONLY where it can guarantee the
mutant's correctness relative to the reference — provably wrong for a DEFECT
operator, provably still-correct for an EQUIVALENT operator. Everywhere else it
declines. So a MISSED or FLAGGED outcome downstream is a fact about the grader, not
an artifact of an ambiguous mutant.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable, Optional

from gradecore import GradeInput

from .outcome import OperatorType, Polarity

if TYPE_CHECKING:
    from .case import EvalCase

# A pure function from a case to a mutated input, or None (N/A). It receives the whole
# case, not just the input, so a semantic operator can read the ground truth it needs:
# `case.good.expected` (the canonical answer, for number/exact/truncation operators) and
# `case.tags` (the task class, for safety/abstention operators whose correctness depends
# on what the task is FOR, which the output text alone cannot reveal).
ApplyFn = Callable[["EvalCase"], Optional[GradeInput]]


@dataclass(frozen=True)
class MutationOperator:
    id: str
    family: str
    polarity: Polarity
    defect_shape: str     # one line: the class of real defect this injects
    real_origin: str      # the concrete documented failure it is mined from
    field: str            # which GradeInput field it perturbs (for reports/filtering)
    _apply: ApplyFn
    op_type: OperatorType = OperatorType.KILL  # what a survival means (see OperatorType)

    def apply(self, case: "EvalCase") -> Optional[GradeInput]:
        """Mutate the case's reference input, or return None if not applicable here.

        Invariant every operator must uphold: a non-None result is, relative to
        `case.good`, a genuinely wrong output when polarity is DEFECT, and a
        genuinely still-correct output when polarity is EQUIVALENT. Operators
        enforce this by declining (returning None) wherever they cannot guarantee
        it — e.g. a number-corrupting operator returns None on an input with no
        number to corrupt; a truncation operator returns None when it cannot locate
        the answer span it would need to cut away.
        """
        mutant = self._apply(case)
        if mutant is None:
            return None
        # A structural no-op is not a mutation. Guard it here so no operator can
        # accidentally report a verdict about an unchanged input.
        if _same_input(mutant, case.good):
            return None
        return mutant


def operator(id: str, *, family: str, polarity: Polarity, defect_shape: str,
             real_origin: str, field: str,
             op_type: OperatorType = OperatorType.KILL
             ) -> Callable[[ApplyFn], MutationOperator]:
    """Decorator form, so an operator reads as its apply-rule with provenance attached.

        @operator("truncate_before_answer", family="truncation",
                  polarity=Polarity.DEFECT, field="text",
                  defect_shape="reply cut off before it reaches the answer",
                  real_origin="model-drift 429/MNAR: a cut-off reply and a wrong "
                              "reply fail differently and must not share a metric")
        def _(good): ...
    """
    def wrap(fn: ApplyFn) -> MutationOperator:
        return MutationOperator(
            id=id, family=family, polarity=polarity, defect_shape=defect_shape,
            real_origin=real_origin, field=field, _apply=fn, op_type=op_type,
        )
    return wrap


def applies_to_tag(*tags: str):
    """Guard helper: a semantic operator that is only meaningful for a task class.
    Wrap an apply-fn so it returns None unless the case carries one of `tags`. Keeps
    the correctness contract honest — a refusal-swap is only a defect on a task that
    was supposed to refuse, and we know that from the case tag, not the output text."""
    wanted = set(tags)

    def deco(fn: ApplyFn) -> ApplyFn:
        def guarded(case: "EvalCase") -> Optional[GradeInput]:
            if wanted.isdisjoint(case.tags):
                return None
            return fn(case)
        return guarded
    return deco


def with_text(good: GradeInput, text: str) -> GradeInput:
    """Return a copy of `good` with its `text` replaced — the common mutation move."""
    return replace(good, text=text)


def _same_input(a: GradeInput, b: GradeInput) -> bool:
    """Structural equality across every field a grader might read. Frozen dataclass
    equality would work too, but sequences may arrive as list vs tuple from different
    call sites, so compare field-wise and normalize sequences to tuples."""
    def seq(x):
        return tuple(x) if x is not None else ()
    return (
        a.text == b.text
        and a.prompt == b.prompt
        and seq(a.retrieved) == seq(b.retrieved)
        and seq(a.contexts) == seq(b.contexts)
        and seq(a.citations) == seq(b.citations)
        and tuple(map(_freeze, a.tool_calls)) == tuple(map(_freeze, b.tool_calls))
        and seq(a.gold_ids) == seq(b.gold_ids)
        and a.expected == b.expected
    )


def _freeze(d):
    """A hashable, comparable view of a tool-call dict for equality checks."""
    if isinstance(d, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in d.items()))
    if isinstance(d, (list, tuple)):
        return tuple(_freeze(x) for x in d)
    return d
