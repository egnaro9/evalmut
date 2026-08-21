"""Per-row proof that the intended gradecore scoring path executed, for the dogfood run.

WHAT WAS UNPROVEN. The dogfood artifact reports that N of M declared mutations were LABELLED
caught. The wrapper proves gradecore was imported (`inspect.getfile`) and that labels were
recorded. Neither fact reaches the thing a reader actually cares about: that for THIS row, the
grader gradecore handed the suite was entered, and that the verdict in the report came back out
of it. `sentinel.py` states the gap and `witnessed.py` refuses rows that cannot close it. The
dogfood demo used neither, so every one of its rows carried a verdict with no proof behind it.

WHAT IS WITNESSED, EXACTLY. The per-row decision is `case.grader(mutant)` in `runner.run_case`,
and the clean control is `case.baseline()`, which is `self.grader(self.good)` in `EvalCase`. The
callable at both sites is the closure the gradecore FACTORY returned (`gradecore.exact("42")` is
`gradecore.graders.exact.<locals>.g`). That closure is the decision path. The factory is not:
patching `gradecore.exact` records a call made once while the suite module was being imported,
which is a fact about suite construction and says nothing about any row. A witness taken there
would be exactly the false witness this module exists to refuse.

HOW A CALL IS ATTRIBUTED. Counting entries into the grader is not enough, because evalmut's own
operators call the grader too while deciding whether they apply (`operators.py` probes it five
different ways). A witness that counted those would report MULTIPLE on healthy rows and could be
satisfied by a probe on rows where the decision never happened. So each entry is attributed by
its CALLER: the calling frame's file, function, and the source text of the calling line. Only a
call made from `run_case` on the line reading `case.grader(mutant)` witnesses a decision, and
only a call from `EvalCase.baseline` on the line reading `self.grader(self.good)` witnesses the
clean control. Anything from `operators.py` is recorded as a probe and can never satisfy either.
Anything else is UNATTRIBUTED and fails the row closed.

WHAT IS NOT CLAIMED. This proves the path was ENTERED and what it HANDED BACK. It says nothing
about whether the grader judged well, and nothing about detection power. A row that is witnessed
is a row whose numbers are about gradecore. That is the entire claim.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata as _md
import linecache
import os
import sys
from dataclasses import dataclass
from types import FrameType
from typing import Any, Callable, Iterable, Optional, Sequence

from .case import EvalCase
from .operator import MutationOperator
from .operators import catalog as _operators_catalog
from .outcome import Outcome, Polarity, outcome_for
from .runner import BaselineError, MutationResult, run_case, run_suite
from . import stamp as _stamp
from .sentinel import Witness
from .witnessed import WitnessInconsistent, WitnessMissing, check_row

PROTOCOL = "evalmut-invocation-witness-v1"

# Per-phase witness statuses. Every one of them is a fact about recorded calls; none of them is a
# default, and there is no status meaning "assumed fine".
WITNESSED = "WITNESSED"      # exactly one attributed call
MISSING = "MISSING"          # no call reached this site
MULTIPLE = "MULTIPLE"        # more than one call reached this site
INCONSISTENT = "INCONSISTENT"  # the counter and the call log disagree; evidence is unusable

# Row statuses.
ROW_WITNESSED = "WITNESSED"
ROW_INCOMPLETE = "INCOMPLETE"
ROW_NOT_AN_OUTCOME = "NOT_AN_OUTCOME"   # the operator declined; there is no defective form

UNATTRIBUTED = "unattributed"
PROBE = "operator_probe"
DECISION = "defect_decision"
CLEAN = "clean_control"


def _real(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))


@dataclass(frozen=True)
class CallSite:
    """One place a grader call may legitimately come from, named precisely enough to be checked.

    `anchor` is the source text the calling line must contain. Matching the file and the function
    alone would accept any call `run_case` happens to make; requiring the line's own text pins the
    witness to the statement this module names in its report, so a reader can open the file and
    see the same thing the artifact claims.
    """

    phase: str
    filename: str
    funcname: Optional[str] = None   # None matches any function in that file
    anchor: Optional[str] = None     # None skips the source-text check

    def matches(self, frame: FrameType) -> bool:
        if _real(frame.f_code.co_filename) != _real(self.filename):
            return False
        if self.funcname is not None and frame.f_code.co_name != self.funcname:
            return False
        if self.anchor is None:
            return True
        return self.anchor in _source_window(frame.f_code.co_filename, frame.f_lineno)

    def described(self) -> dict:
        return {"phase": self.phase, "file": _pkg_relative(self.filename),
                "function": self.funcname, "source_anchor": self.anchor}


def _source_window(filename: str, lineno: int, radius: int = 1) -> str:
    """The calling line plus one on either side.

    The window exists for the multi-line call, where the frame's reported line can be the first
    or the last physical line of the expression depending on the interpreter. It is deliberately
    tiny: widen it and the anchor stops distinguishing one statement from its neighbours.
    """
    lines = [linecache.getline(filename, n) for n in range(max(1, lineno - radius), lineno + radius + 1)]
    return "".join(lines)


# Each site is resolved from the FUNCTION that owns it rather than from a module attribute, so
# the file can never drift from the function whose name the site also checks. (It also sidesteps
# a real trap: `evalmut.case` the module is shadowed on the package by `evalmut.case` the
# constructor function, so `from . import case` hands back a function with no `__file__`.)
DECISION_SITE = CallSite(DECISION, run_case.__code__.co_filename, "run_case",
                         "case.grader(mutant)")
CLEAN_SITE = CallSite(CLEAN, EvalCase.baseline.__code__.co_filename, "baseline",
                      "self.grader(self.good)")
PROBE_SITE = CallSite(PROBE, _operators_catalog.__code__.co_filename)
DEFAULT_SITES = (DECISION_SITE, CLEAN_SITE, PROBE_SITE)


def _pkg_relative(path: str) -> str:
    """A path a stranger can read, relative to the top of its distribution.

    Absolute paths would put this machine's layout in a committed artifact and make the bytes
    unreproducible anywhere else, which would quietly break the freshness gate the fleet relies on.
    """
    p = _real(path)
    parts = p.split(os.sep)
    for anchor in ("evalmut", "gradecore"):
        if anchor in parts:
            i = len(parts) - 1 - parts[::-1].index(anchor)
            return "/".join(parts[i:])
    return os.path.basename(p)


def identify(fn: Callable) -> dict:
    """The fully qualified identity of the callable that will be witnessed.

    Recorded per row rather than once per run: two cases in one suite can carry graders from
    different modules, and a report that named only "gradecore" would hide that.
    """
    code = getattr(fn, "__code__", None)
    module = getattr(fn, "__module__", None)
    qualname = getattr(fn, "__qualname__", None)
    if code is None:  # a callable object rather than a function
        call = getattr(type(fn), "__call__", None)
        code = getattr(call, "__code__", None)
        module = module or getattr(type(fn), "__module__", None)
        qualname = (getattr(type(fn), "__qualname__", None) or "") + ".__call__"
    top = (module or "").split(".")[0]
    try:
        version = _md.version(top) if top else None
    except Exception:
        version = None
    return {
        "identity": f"{module}.{qualname}" if module else str(qualname),
        "defined_at": (f"{_pkg_relative(code.co_filename)}:{code.co_firstlineno}"
                       if code is not None else None),
        "code_sha256": (hashlib.sha256(code.co_code).hexdigest()[:16]
                        if code is not None else None),
        "library": top or None,
        "library_version": version,
    }


def _summarize_return(out: Any) -> dict:
    """The RAW upstream return, projected and hashed, never translated.

    The projected fields are read straight off the object gradecore handed back, before the runner
    turns `passed` into an outcome. The hash covers the whole repr, so a reader can tell that two
    rows carrying the same projection did or did not receive the same object. Nothing here is
    derived from evalmut's verdict about the row, which is the point: a wrapper that transformed a
    score could otherwise be wrong in a way no verdict reveals.
    """
    rec = {"type": type(out).__name__,
           "repr_sha256": hashlib.sha256(repr(out).encode("utf-8")).hexdigest()[:16]}
    for f in ("passed", "score", "severity", "grader_id"):
        if hasattr(out, f):
            v = getattr(out, f)
            rec[f] = bool(v) if f == "passed" else v
    return rec


class WitnessingGrader:
    """A transparent proxy over a suite's grader that records who called it, and what came back.

    Wraps the CALLABLE the suite handed evalmut, which is the closure the gradecore factory
    returned. State is per row and is wiped by `reset()`; nothing is carried between rows and no
    witness is ever synthesised from what a previous row saw.
    """

    def __init__(self, target: Callable, sites: Sequence[CallSite] = DEFAULT_SITES):
        self.target = target
        self.sites = tuple(sites)
        self.identity = identify(target)
        self._log: dict[str, list[dict]] = {}
        self._witness: dict[str, Witness] = {}
        self.reset()

    def reset(self) -> None:
        phases = [s.phase for s in self.sites] + [UNATTRIBUTED]
        self._log = {p: [] for p in phases}
        self._witness = {p: Witness(target=self.identity["identity"]) for p in phases}

    def phases(self) -> tuple[str, ...]:
        return tuple(self._log)

    def witness(self, phase: str) -> Witness:
        """This row's witness for one phase.

        A phase this proxy was never configured to watch (a sentinel switched off, or pointed
        somewhere else) reports an EMPTY witness rather than raising. That is the fail-closed
        answer: zero calls is what "no evidence" looks like downstream, and it drives the row to
        INCOMPLETE. The empty witness is built fresh and never stored, so an unconfigured phase
        can never later read as one that was recorded.
        """
        return self._witness.get(phase) or Witness(target=self.identity["identity"])

    def log(self, phase: str) -> list[dict]:
        return list(self._log.get(phase, ()))

    def _phase_for(self, frame: FrameType) -> str:
        for site in self.sites:
            if site.matches(frame):
                return site.phase
        return UNATTRIBUTED

    def __call__(self, *args, **kwargs):
        frame = sys._getframe(1)
        phase = self._phase_for(frame)
        site = f"{_pkg_relative(frame.f_code.co_filename)}:{frame.f_lineno}"
        w = self._witness[phase]
        w.calls += 1
        n = w.calls
        try:
            out = self.target(*args, **kwargs)
        except BaseException as exc:
            # Recorded and re-raised, never swallowed: a proxy that ate the error would
            # manufacture the silence it was built to detect.
            w.raised.append(f"{type(exc).__name__}: {exc}")
            self._log[phase].append({"call": n, "kind": "raise", "site": site,
                                     "exception": f"{type(exc).__name__}: {exc}"})
            raise
        w.returns.append(out)
        rec = {"call": n, "kind": "return", "site": site}
        rec.update(_summarize_return(out))
        self._log[phase].append(rec)
        return out


def phase_witness(proxy: WitnessingGrader, phase: str) -> dict:
    """One phase's evidence, in the shape `witnessed.check_row` validates.

    `raw_upstream` carries one record per call, a return or a raise, so the count and the log can
    be checked against each other. A disagreement between them is reported as INCONSISTENT rather
    than resolved in either direction: the evidence is unusable, and picking a side would be the
    guess this whole module refuses to make.
    """
    w = proxy.witness(phase)
    log = proxy.log(phase)
    if len(log) != w.calls:
        status = INCONSISTENT
    elif w.calls == 0:
        status = MISSING
    elif w.calls > 1:
        status = MULTIPLE
    else:
        status = WITNESSED
    ident = dict(proxy.identity)
    return {
        "target": ident["identity"],
        "invoked": w.calls > 0,
        "calls": w.calls,
        "raw_upstream": log,
        "status": status,
        "raised": list(w.raised),
        **{k: v for k, v in ident.items() if k != "identity"},
    }


def _refusal(card_id: str, wit: dict) -> Optional[str]:
    """Run the shipped refusal over one phase. Returns the reason, or None if the phase holds.

    `witnessed.check_row` does the deciding, on the recorded facts rather than on the status
    label: it wants the fields present, `invoked` true, exactly one call, and one raw upstream
    record per call. Reading the label instead would let a tampered or mis-derived `status` talk
    its way past the gate, which is the shape of every failure this module is about.
    """
    try:
        check_row({"card_id": card_id, "witness": wit}, expect_calls=1)
    except (WitnessMissing, WitnessInconsistent) as e:
        return str(e)
    if wit.get("status") == INCONSISTENT:
        return (f"{card_id}: the witness is marked {INCONSISTENT}; its evidence is unusable")
    return None


@dataclass(frozen=True)
class WitnessedRow:
    result: MutationResult
    clean: dict
    defect: dict
    probe_calls: int
    unattributed_calls: int
    status: str
    incomplete_reason: Optional[str]

    @property
    def is_outcome(self) -> bool:
        return self.status == ROW_WITNESSED

    @property
    def counts_toward_score(self) -> bool:
        return self.is_outcome and self.result.outcome.counts_toward_score


def classify(result: MutationResult, clean: dict, defect: dict, *,
             probe_calls: int, unattributed_calls: int) -> WitnessedRow:
    """Decide whether this row's numbers are evidence about gradecore, and fail closed if unclear.

    A row is an outcome only when BOTH forms were witnessed and both behaved as the contract they
    were run under declares: the clean control passed (a red baseline is a mis-specified case, not
    a measurement), and the recorded outcome is what `outcome_for` computes from the RAW verdict
    the grader returned. Recomputing from the raw return rather than trusting the recorded label is
    the whole point of keeping the raw value: it is the one check that can catch a wrapper that
    translated a verdict into something the grader never said.
    """
    card = f"{result.case_name}/{result.operator_id}"
    reasons: list[str] = []

    if unattributed_calls:
        reasons.append(
            f"{card}: {unattributed_calls} grader call(s) came from a site this protocol cannot "
            "attribute; ambiguous evidence is refused rather than assigned to a phase")

    na = result.outcome is Outcome.NA
    if na:
        # The operator declined, so no defective form exists and nothing decided this row. That is
        # a legitimate absence, but it is checked rather than assumed: a decision call here would
        # mean the row was decided after all and the report is describing the wrong thing.
        if defect["calls"]:
            reasons.append(f"{card}: outcome is n/a but the decision site was entered "
                           f"{defect['calls']} time(s); the row contradicts itself")
        na_clean_bad = _refusal(card, clean)
        if na_clean_bad:
            reasons.append(na_clean_bad)
        return WitnessedRow(result, clean, defect, probe_calls, unattributed_calls,
                            ROW_NOT_AN_OUTCOME if not reasons else ROW_INCOMPLETE,
                            "; ".join(reasons) or None)

    clean_bad, defect_bad = _refusal(card, clean), _refusal(card, defect)
    reasons.extend(r for r in (clean_bad, defect_bad) if r)

    # The contract checks below read the recorded call. They run only on a phase that survived the
    # refusal above, because reading a witness that was just refused would mean interpreting the
    # evidence this row has already been told it does not have.
    if not clean_bad:
        raw = clean["raw_upstream"][0]
        if raw["kind"] != "return":
            reasons.append(f"{card}: the clean control raised instead of returning a verdict "
                           f"({raw.get('exception')})")
        elif raw.get("passed") is not True:
            reasons.append(f"{card}: the clean control's raw verdict did not pass "
                           f"(passed={raw.get('passed')!r}), so this row has no green baseline "
                           "behind it")

    if not defect_bad:
        raw = defect["raw_upstream"][0]
        if raw["kind"] == "raise":
            if result.outcome is not Outcome.ERROR:
                reasons.append(f"{card}: the decision raised but the row is recorded as "
                               f"{result.outcome.value}")
        else:
            if "passed" not in raw:
                reasons.append(f"{card}: the raw upstream return carries no `passed` field, so "
                               "the recorded outcome cannot be rechecked against it")
            else:
                recomputed = outcome_for(result.polarity, bool(raw["passed"]))
                if recomputed is not result.outcome:
                    reasons.append(
                        f"{card}: recorded outcome {result.outcome.value} does not match "
                        f"{recomputed.value}, recomputed from the raw upstream verdict "
                        f"(passed={raw['passed']!r}, polarity={result.polarity.value})")

    status = ROW_WITNESSED if not reasons else ROW_INCOMPLETE
    return WitnessedRow(result, clean, defect, probe_calls, unattributed_calls,
                        status, "; ".join(reasons) or None)


def witness_case(case: EvalCase, op: MutationOperator,
                 sites: Sequence[CallSite] = DEFAULT_SITES) -> list[WitnessedRow]:
    """Run ONE operator against ONE case behind a fresh proxy, and classify what came out.

    The case is rebuilt with `dataclasses.replace` rather than patched with `object.__setattr__`.
    `EvalCase` is frozen, so `sentinel(case, "grader")` cannot be used on it at all, and of the two
    ways to get around that only `replace` respects what frozen means: it returns a NEW case and
    leaves the suite's own object exactly as the author wrote it. `object.__setattr__` would reach
    past the freeze and mutate the shared instance, so a row that raised before the restore ran
    would leave every later row grading through a proxy from a dead row. That is precisely the
    cross-row contamination a per-row witness is supposed to rule out, so it is not used here.

    One operator per call, because the runner takes the clean control once per `run_case` and the
    two forms have to be witnessed as a pair for the same row.
    """
    proxy = WitnessingGrader(case.grader, sites=sites)
    witnessed_case = dataclasses.replace(case, grader=proxy)
    proxy.reset()
    results = run_case(witnessed_case, [op])
    clean = phase_witness(proxy, CLEAN)
    defect = phase_witness(proxy, DECISION)
    probe = proxy.witness(PROBE).calls if PROBE in proxy.phases() else 0
    unattributed = proxy.witness(UNATTRIBUTED).calls
    return [classify(r, clean, defect, probe_calls=probe, unattributed_calls=unattributed)
            for r in results]


def witness_suite(suite: Sequence[EvalCase], operators: Sequence[MutationOperator],
                  sites: Sequence[CallSite] = DEFAULT_SITES
                  ) -> tuple[list[WitnessedRow], list[BaselineError]]:
    """Every case against every operator, one witnessed pair per row."""
    rows: list[WitnessedRow] = []
    failures: list[BaselineError] = []
    seen_red: set[str] = set()
    for case in suite:
        for op in operators:
            try:
                rows.extend(witness_case(case, op, sites=sites))
            except BaselineError as be:
                # Raised once per operator for the same red baseline; report the case once.
                if case.name not in seen_red:
                    seen_red.add(case.name)
                    failures.append(be)
    return rows, failures


class DriverMismatch(AssertionError):
    """The witnessed driver did not reproduce the plain runner's rows.

    Fatal on purpose. The witnessed run is only allowed to REMOVE rows from the headline for want
    of evidence. If it also changed what a row decided, then the instrument moved the measurement,
    and every number downstream of it would be a fact about the instrument.
    """


def crosscheck(rows: Iterable[WitnessedRow], suite: Sequence[EvalCase],
               operators: Sequence[MutationOperator]) -> dict:
    """Compare the witnessed rows against an unwitnessed `run_suite` of the same suite.

    Proving the instrument before the finding. The proxy sits on the exact callable the runner
    invokes, so it COULD change a verdict, and no amount of reading the code settles whether it
    did. This runs the same suite without it and demands the same rows back.
    """
    plain, _ = run_suite(suite, operators)
    key = lambda r: (r.case_name, r.operator_id)  # noqa: E731
    got = {key(r.result): r.result for r in rows}
    want = {key(r): r for r in plain}
    mismatches: list[str] = []
    for k in sorted(set(got) | set(want)):
        a, b = got.get(k), want.get(k)
        if a is None or b is None:
            mismatches.append(f"{k[0]}/{k[1]}: present in "
                              f"{'witnessed' if b is None else 'plain'} run only")
            continue
        for field in ("outcome", "polarity", "op_type", "detail", "mutant_preview",
                      "grader_error", "grader_id"):
            if getattr(a, field) != getattr(b, field):
                mismatches.append(f"{k[0]}/{k[1]}: {field} {getattr(b, field)!r} -> "
                                  f"{getattr(a, field)!r} under the witness")
    if mismatches:
        raise DriverMismatch(
            f"{len(mismatches)} row(s) changed under the witness:\n  " + "\n  ".join(mismatches))
    # OVERTURNED, not a vacuous gate. An adversarial pass flagged this literal 0 as "a gate that
    # cannot fail". It can: every mismatch is appended above and `raise DriverMismatch` fires
    # before this line is reachable, so 0 here is a fact about a comparison that ran, not a
    # default. Repro for anyone who doubts it: the raise precedes this return in the source, and
    # plain_rows/witnessed_rows are published beside it so a zero-comparison run is visible as
    # 0 rows rather than hiding behind a green count.
    return {"plain_rows": len(plain), "witnessed_rows": len(got), "mismatches": 0}


def _result_dict(r: MutationResult) -> dict:
    d = dataclasses.asdict(r)
    d["polarity"] = r.polarity.value
    d["op_type"] = r.op_type.value
    d["outcome"] = r.outcome.value
    return d


def _row_dict(row: WitnessedRow) -> dict:
    d = _result_dict(row.result)
    d["witness_status"] = row.status
    d["incomplete_reason"] = row.incomplete_reason
    d["witness"] = {"clean_control": row.clean, "defect_decision": row.defect,
                    "operator_probe_calls": row.probe_calls,
                    "unattributed_calls": row.unattributed_calls}
    return d


def witness_payload(suite: Sequence[EvalCase], operators: Sequence[MutationOperator],
                    sites: Sequence[CallSite] = DEFAULT_SITES) -> dict:
    """The witnessed run, in the run-export schema with the witness fields added.

    The headline is recomputed over the witnessed population alone. Incomplete rows are not
    counted as caught, not counted as survived, and not left in the denominator to be averaged
    over: they are listed separately with the reason no verdict about them is available. A run
    where they simply vanished would be the same laundering as a suite that stopped asking.
    """
    rows, failures = witness_suite(suite, operators, sites=sites)
    cross = crosscheck(rows, suite, operators)
    return summarize_rows(rows, failures, cross)


def summarize_rows(rows: Sequence[WitnessedRow], failures: Sequence[BaselineError],
                   cross: dict) -> dict:
    """Assemble the export from already-classified rows.

    Separate from the run so the counting can be exercised directly on rows whose status is
    known, including statuses a healthy suite does not currently produce. A denominator that is
    only ever tested on a run where nothing is incomplete is a denominator nobody has checked.
    """
    from .score import score as _score  # local: score.py imports runner, not this module

    eligible = [r for r in rows if r.is_outcome]
    incomplete = [r for r in rows if r.status == ROW_INCOMPLETE]
    not_outcome = [r for r in rows if r.status == ROW_NOT_AN_OUTCOME]

    gated = _score([r.result for r in eligible])
    ungated = _score([r.result for r in rows])

    tally = dataclasses.asdict(gated.total)
    tally["na"] = len(not_outcome)
    tally["incomplete"] = len(incomplete)

    identities = sorted({r.defect.get("target") or r.clean.get("target") for r in rows})
    libs = sorted({(r.clean.get("library"), r.clean.get("library_version")) for r in rows})

    # null, not 1.0 and not 0.0. Tally.score answers 1.0 for an empty population, which is safe
    # arithmetic and unsafe evidence: it reads as a measured perfect result. 0.0 would read as a
    # measured failure. With no witnessed rows the score is undefined, and the artifact says so
    # rather than choosing a number a reader would believe.
    return {
        "score": gated.score if gated.total.scored else None,
        "tally": tally,
        "holes": {
            "vacuous": [_result_dict(h) for h in gated.vacuous],
            "blind": [_result_dict(h) for h in gated.blind_spots],
            "error": [_result_dict(h) for h in gated.errors],
            "brittle": [_result_dict(h) for h in gated.brittle_spots],
            "coverage_gap": [_result_dict(h) for h in gated.coverage_gaps],
        },
        "baseline_failures": [str(b) for b in failures],
        "incomplete": [_row_dict(r) for r in incomplete],
        "witness_protocol": {
            "protocol": PROTOCOL,
            "decision_call": DECISION_SITE.described(),
            "clean_control_call": CLEAN_SITE.described(),
            "probe_calls_ignored_from": PROBE_SITE.described(),
            "attribution": ("caller frame: file, function, and the source text of the calling "
                            "line; a call from anywhere else is UNATTRIBUTED and fails the row"),
            "callable_witnessed": ("the grader the suite handed evalmut, which is the closure the "
                                   "gradecore factory returned; the factory itself is NOT "
                                   "witnessed, since calling it happens once at suite "
                                   "construction and decides no row"),
            "libraries": [{"name": n, "version": v} for n, v in libs],
            "callable_identities": identities,
            "row_counts": {"rows": len(rows), "witnessed": len(eligible),
                           "incomplete": len(incomplete),
                           "not_an_outcome": len(not_outcome)},
            "driver_crosscheck": cross,
            # Which commit produced these bytes. The last commit touching CODE_PATHS, not HEAD:
            # a test-only or docs-only commit cannot move an artifact, so it must not move a
            # stamp. `dirty` is recorded rather than refused, because tests invoke this command
            # as a subprocess and refusing would make an ordinary edit break the suite. A
            # consumer publishing a claim from this artifact is expected to refuse a dirty stamp.
            "stamp": _stamp.evidence(output_paths=("docs/", "external/", "vac/")),
        },
        "ungated": {
            "score": ungated.score if ungated.total.scored else None,
            "tally": dataclasses.asdict(ungated.total),
            "note": ("what this run reports with no invocation evidence required, i.e. what the "
                     "unwitnessed dogfood artifact counts"),
        },
        "results": [_row_dict(r) for r in rows],
    }


def render_witness_short(payload: dict) -> str:
    t = payload["tally"]
    rc = payload["witness_protocol"]["row_counts"]
    u = payload["ungated"]["tally"]
    applied = t["caught"] + t["missed"] + t["flagged"]
    u_applied = u["caught"] + u["missed"] + u["flagged"]
    # NO DENOMINATOR, NO PERCENTAGE. A run where nothing could be witnessed printed
    # "witnessed 0/0 caught (score 100.0%)", turning an absence of evidence into the strongest
    # claim the tool can make. Zero would be no better: that asserts measured failure. The state
    # is undefined and says so. `score` is None in the payload for the same reason.
    def _pct(sc, n):
        return f"score {sc * 100:.1f}%" if n and sc is not None else "score UNAVAILABLE, no witnessed rows"

    lines = [
        f"witnessed  {t['caught']}/{applied} caught  "
        f"({_pct(payload['score'], applied)}; {t['incomplete']} incomplete, {t['na']} n/a)",
        f"ungated    {u['caught']}/{u_applied} caught  "
        f"({_pct(payload['ungated']['score'], u_applied)})  <- no invocation evidence required",
        f"rows       {rc['rows']} total, {rc['witnessed']} witnessed, "
        f"{rc['incomplete']} incomplete, {rc['not_an_outcome']} not an outcome",
        f"decision   {payload['witness_protocol']['decision_call']['file']} "
        f"{payload['witness_protocol']['decision_call']['source_anchor']}",
    ]
    for name_version in payload["witness_protocol"]["libraries"]:
        lines.append(f"library    {name_version['name']} {name_version['version']}")
    for r in payload["incomplete"]:
        lines.append(f"  INCOMPLETE {r['case_name']}/{r['operator_id']}: {r['incomplete_reason']}")
    return "\n".join(lines)
