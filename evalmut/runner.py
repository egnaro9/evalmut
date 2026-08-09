"""Run a set of operators against a suite and record what each mutation did.

The loop is deliberately small and deterministic — no sampling, no LLM, so a run
reproduces exactly, the same property gradecore is built on. For each case it first
confirms the baseline is green (mutation testing on a red baseline is meaningless),
then for each operator applies the mutation and reruns the grader.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from gradecore import GradeInput, Verdict

from .case import EvalCase
from .operator import MutationOperator
from .operators import _clear_grader_id, _prime_grader_id
from .outcome import OperatorType, Outcome, Polarity, outcome_for


class BaselineError(Exception):
    """A case whose grader does not pass its own reference output. Mutation testing
    cannot proceed on it — the reference is mis-specified — so it is reported by name
    rather than silently skipped."""


@dataclass(frozen=True)
class MutationResult:
    case_name: str
    grader_id: str
    operator_id: str
    family: str
    polarity: Polarity
    op_type: OperatorType
    outcome: Outcome
    real_origin: str
    defect_shape: str
    detail: str                       # what the grader said on the mutant
    mutant_preview: str               # a one-line echo of the mutated field
    grader_error: Optional[str] = None  # set if the grader raised on the mutant


def _preview(s: object, n: int = 100) -> str:
    # Show newlines as a visible ⏎ rather than collapsing them: a mutation's newline can be the
    # load-bearing difference (e.g. a same-line vs new-paragraph disclaimer), and silently flattening
    # it misrepresents WHY a grader rejected the mutant (pass-4 aggravator).
    t = " ".join(str(s).replace("\n", " ⏎ ").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _mutated_field_preview(op: MutationOperator, mutant: GradeInput) -> str:
    val = getattr(mutant, op.field, None)
    if isinstance(val, (list, tuple)):
        val = " | ".join(map(str, val))
    return _preview(val if val is not None else mutant.text)


def run_case(case: EvalCase, operators: Sequence[MutationOperator]) -> list[MutationResult]:
    """Apply every operator to one case. Raises BaselineError if the case's baseline
    is not green — a caller that wants to tolerate that should use `run_suite`, which
    collects baseline failures instead of raising."""
    try:
        baseline = case.baseline()
    except Exception as exc:
        # A grader that raises on its own clean reference is mis-specified in the worst
        # way — it cannot render a verdict at all. Report it by name; do not let it abort
        # the whole run (run_suite collects this, same as a red baseline).
        raise BaselineError(
            f"case {case.name!r}: grader raised on its own reference output "
            f"({type(exc).__name__}: {exc}). Fix the grader before mutating."
        )
    if not baseline.passed:
        raise BaselineError(
            f"case {case.name!r}: grader {baseline.grader_id!r} fails its own reference "
            f"output ({baseline.detail}). Fix the reference or the grader before mutating."
        )
    grader_id = baseline.grader_id
    # Seed the per-case grader-id memo so the family-gating operators reuse the baseline's
    # verdict instead of re-invoking the grader on case.good once per operator (wasteful for a
    # slow grader; incorrect for a stateful/side-effecting one). Cleared in finally so id(case)
    # is never left mapped past this case's operator loop.
    prev_grader_id = _prime_grader_id(case, grader_id)

    results: list[MutationResult] = []
    try:
        for op in operators:
            # An operator that mutates a field the grader does not judge is irrelevant to this
            # case, not a finding about it — skip it silently rather than record a false NA that
            # would suggest it had something to say. (Text operators on a tool-only grader, etc.)
            if op.field not in case.judges:
                continue
            try:
                mutant = op.apply(case)
            except Exception as exc:
                # A user operator that crashes while BUILDING the mutant must not abort the whole
                # run and discard every already-collected result. Record it as ERROR naming the
                # OPERATOR (a distinct detail from the grader-crash branch below), surface it,
                # and move on to the next operator.
                results.append(_result(case, grader_id, op, Outcome.ERROR,
                                       f"operator raised: {type(exc).__name__}: {exc}",
                                       mutant_preview=""))
                continue
            if mutant is None:
                results.append(_result(case, grader_id, op, Outcome.NA,
                                        "n/a: operator not applicable here", mutant_preview=""))
                continue

            grader_error: Optional[str] = None
            try:
                v: Verdict = case.grader(mutant)
                outcome = outcome_for(op.polarity, bool(v.passed))
                detail = v.detail
            except Exception as exc:
                # A grader that crashes on a well-formed mutant did not "catch" anything — it
                # failed to produce a verdict. Scoring a crash as a catch would hide a fragile
                # grader (e.g. a rubber-stamp that indexes text[0] and dies on the blank-output
                # probe, then reads as CAUGHT and vanishes from the vacuous report). ERROR is
                # its own outcome, surfaced, excluded from the score.
                outcome = Outcome.ERROR
                detail = f"grader raised: {type(exc).__name__}: {exc}"
                grader_error = f"{type(exc).__name__}: {exc}"

            results.append(_result(case, grader_id, op, outcome, detail,
                                   mutant_preview=_mutated_field_preview(op, mutant),
                                   grader_error=grader_error))
    finally:
        _clear_grader_id(case, prev_grader_id)
    return results


def run_suite(suite: Sequence[EvalCase], operators: Sequence[MutationOperator]
              ) -> tuple[list[MutationResult], list[BaselineError]]:
    """Run every case. Returns (results, baseline_failures). Baseline failures are
    collected rather than raised so one mis-specified case doesn't abort the run — but
    they are returned, not swallowed, so the caller reports them."""
    results: list[MutationResult] = []
    baseline_failures: list[BaselineError] = []
    for case in suite:
        try:
            results.extend(run_case(case, operators))
        except BaselineError as be:
            baseline_failures.append(be)
    return results, baseline_failures


def _result(case: EvalCase, grader_id: str, op: MutationOperator, outcome: Outcome,
            detail: str, *, mutant_preview: str,
            grader_error: Optional[str] = None) -> MutationResult:
    return MutationResult(
        case_name=case.name,
        grader_id=grader_id,
        operator_id=op.id,
        family=op.family,
        polarity=op.polarity,
        op_type=op.op_type,
        outcome=outcome,
        real_origin=op.real_origin,
        defect_shape=op.defect_shape,
        detail=detail,
        mutant_preview=mutant_preview,
        grader_error=grader_error,
    )
