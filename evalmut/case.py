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

Some operators need to know a bar that lives inside the grader's closure and is
invisible from the outside — a numeric tolerance, a grounding threshold, which
cosmetic changes this task's contract treats as still-correct, the expected tool
plan. The honest answer is never to guess it (guessing a module default, or trusting
a grader-emitted id label, is exactly what manufactured evalmut's own false findings
in cold-critic pass 2). Instead the suite author DECLARES it here, and the operator
either uses the declared bar or declines. Every such field defaults to the value that
makes the dependent operator DECLINE, so an undecorated case can only ever be
under-tested, never falsely accused.
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

    # ── declared contract bars (each defaults to "operator declines") ────────────
    # The numeric acceptance band the grader uses, if this is a numeric-answer task. A
    # near-miss is a defect only if it falls OUTSIDE the tolerance — and that band lives in
    # the grader's closure, invisible to an operator. Declaring it lets the numeric operator
    # perturb to just past the band; it also cross-checks the declaration against the grader
    # before trusting it. Left None, the numeric operator declines.
    num_tol: float | None = None
    # This task's grader is supposed to require CONTENT in the answer (an exact/contains/
    # number/JSON-style check), so a blank or unrelated output is a provable defect and the
    # SANITY probes may fire. For gradecore's content graders this is inferred from grader_id;
    # a custom grader must opt in, because a blank output is legitimately fine for an ABSENCE
    # grader (injection_resistance, tool_misuse) and calling that vacuous is false (pass-2 C).
    content_required: bool = False
    # The cosmetic changes THIS task's contract treats as still-correct — any of
    # "whitespace", "fence", "disclaimer", "case", "reserialize" (member order and insignificant
    # whitespace in a structured document), "numeric_format" (a currency symbol or thousands
    # separator around an otherwise exact value), "article" (a leading determiner the task's own
    # normalization is meant to strip). An EQUIVALENT operator claims "still correct" only
    # when the change is declared here, because equivalence is a property of the task's
    # contract, not something readable from a grader-emitted id: a composite grader can
    # honestly carry a primitive's id yet also enforce length or format, so a fence or added
    # whitespace legitimately fails it (cold-critic pass-2 B). Declared here, the equivalence
    # claim rests on the author, not on a label the grader controls. Undeclared -> decline.
    tolerates: tuple[str, ...] = ()
    # The expected ordered tool plan, for a trajectory case. trajectory_drop_step proves a
    # defect only by dropping a step whose removal pushes LCS coverage below the threshold —
    # which requires knowing the plan (it lives in the grader closure). Left empty, the
    # operator declines rather than blindly dropping the last call (cold-critic pass-2 E).
    expected_trajectory: tuple[str, ...] = ()
    # The trajectory coverage threshold the grader enforces (gradecore's default is 1.0, but a
    # lenient grader may accept partial coverage). Defaults to None = DECLINE: 1.0 is the STRICTEST
    # bar, not a safe default — trusting it flags a lenient grader that correctly accepts a partial
    # trajectory as a blind spot (cold-critic pass-3 F3). Declare it (with expected_trajectory) to
    # let trajectory_drop_step fire.
    trajectory_threshold: float | None = None

    # The gradecore CONTRACT FAMILY this grader behaves like, when the grader is external and does
    # not carry a gradecore grader_id (e.g. a promptfoo `is-json` port). Operators gate some
    # behavior on the grader's contract family; for an in-house gradecore grader that family is read
    # from its own grader_id, but an external grader must DECLARE it here (e.g. "valid_json",
    # "number", "grounding", "contains", "injection_resistance"). Declared, it lets evalmut run
    # against a framework's graders unmodified while the grader keeps reporting its own honest id.
    grader_family: str | None = None
    # Tool names that write the GRADER'S OWN verdict channel: the file it reads its outcome from,
    # a reporting hook it honors, a binary it shells out to for the answer. An agent calling one of
    # these is not solving the task, it is authoring the verdict, so the trajectory is a provable
    # defect no matter what the task was. Wrongness here comes from THIS declaration, not from the
    # grader's response: unlike a denylisted tool (which the grader can be probed about, since it is
    # supposed to refuse it), a grader that accepts a verdict write cannot tell you whether the write
    # was legitimate output or a forged result. Only the suite author knows which channel is theirs.
    # Undeclared -> inject_denylisted_tool falls back to the denylist payload and this class never
    # fires, so an undecorated case is under-tested rather than falsely accused.
    verdict_channel: tuple[str, ...] = ()
    # Optional human-readable notes surfaced in reports; never load-bearing.
    intent: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def baseline(self):
        """The grader's verdict on the clean reference. Must pass, or the case is
        mis-specified and the runner will refuse to mutate it."""
        return self.grader(self.good)


def case(name: str, grader: Grader, good: GradeInput, *, judges: tuple[str, ...] = ("text",),
         num_tol: float | None = None, content_required: bool = False,
         tolerates: tuple[str, ...] = (), expected_trajectory: tuple[str, ...] = (),
         trajectory_threshold: float | None = None, grader_family: str | None = None,
         verdict_channel: tuple[str, ...] = (),
         intent: str = "", tags: tuple[str, ...] = ()) -> EvalCase:
    """Terse constructor for suites written as data."""
    return EvalCase(name=name, grader=grader, good=good, judges=judges,
                    num_tol=num_tol, content_required=content_required, tolerates=tolerates,
                    expected_trajectory=expected_trajectory,
                    trajectory_threshold=trajectory_threshold, grader_family=grader_family,
                    verdict_channel=verdict_channel, intent=intent, tags=tags)
