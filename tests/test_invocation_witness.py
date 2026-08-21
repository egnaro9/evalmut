"""The invocation witness held to the standard it enforces: shown failing, not just passing.

Every test here is about the same question: can this thing tell a row whose numbers came out of
gradecore from a row that merely looks like one? A witness that has only ever been seen agreeing
is worth nothing, so the load-bearing cases are the negative ones. The sentinel switched off, a
witness taken on the FACTORY instead of the grader, zero calls, two calls, and the raw upstream
return thrown away. Each has to end in INCOMPLETE, and INCOMPLETE has to stay out of the headline
while staying visible in the report.
"""
from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys

import pytest
from gradecore import GradeInput, contains, exact
import gradecore.graders as gradecore_graders

from evalmut import EvalCase, catalog
from evalmut.outcome import OperatorType, Outcome, Polarity
from evalmut.runner import MutationResult
from evalmut.invocation_witness import (
    CLEAN, DECISION, MISSING, MULTIPLE, PROBE, ROW_INCOMPLETE, ROW_NOT_AN_OUTCOME,
    ROW_WITNESSED, UNATTRIBUTED, WITNESSED, CallSite, WitnessingGrader, classify,
    phase_witness, summarize_rows, witness_case, witness_payload,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs" / "dogfood_gradecore_witnessed.json"


def op(op_id: str):
    for o in catalog():
        if o.id == op_id:
            return o
    raise AssertionError(f"operator {op_id!r} is not in the catalog")


def exact_case() -> EvalCase:
    return EvalCase("exact", exact("42"), GradeInput(text="42", expected="42"),
                    tolerates=("whitespace",))


def contains_case() -> EvalCase:
    return EvalCase("contains", contains("capital"),
                    GradeInput(text="Paris is the capital of France.", expected="capital"),
                    tags=("presence_check",), tolerates=("whitespace",))


def a_caught_row():
    (row,) = witness_case(exact_case(), op("blank_output"))
    return row


def a_missed_row():
    (row,) = witness_case(contains_case(), op("keyword_present_but_negated"))
    return row


def stub(outcome=Outcome.CAUGHT, polarity=Polarity.DEFECT) -> MutationResult:
    return MutationResult(case_name="exact", grader_id="exact", operator_id="blank_output",
                          family="sanity", polarity=polarity, op_type=OperatorType.SANITY,
                          outcome=outcome, real_origin="", defect_shape="", detail="",
                          mutant_preview="")


# ── a real run: the positive case, stated precisely enough to be worth something ──────

def test_a_real_run_witnesses_the_gradecore_closure_for_an_exercised_row():
    row = a_caught_row()
    assert row.status == ROW_WITNESSED and row.is_outcome
    assert row.result.outcome is Outcome.CAUGHT
    for wit in (row.clean, row.defect):
        assert wit["status"] == WITNESSED and wit["calls"] == 1 and wit["invoked"] is True
        assert wit["target"] == "gradecore.graders.exact.<locals>.g"
        assert wit["defined_at"].startswith("gradecore/graders.py:")
        assert wit["library"] == "gradecore" and wit["library_version"]
    clean_call = row.clean["raw_upstream"][0]
    decision_call = row.defect["raw_upstream"][0]
    assert clean_call["site"].startswith("evalmut/case.py:")
    assert decision_call["site"].startswith("evalmut/runner.py:")
    # the raw verdicts, as gradecore handed them back: green on the reference, red on the mutant
    assert clean_call["passed"] is True and decision_call["passed"] is False
    assert decision_call["grader_id"] == "exact"


def test_operator_probes_never_satisfy_either_witness():
    """The operators call the grader too, while deciding whether they apply. Counting those would
    both inflate healthy rows to MULTIPLE and let a probe stand in for a decision that never
    happened, so they are attributed to their own phase and used for neither."""
    case = exact_case()
    proxy = WitnessingGrader(case.grader)
    import dataclasses

    from evalmut.runner import run_case
    run_case(dataclasses.replace(case, grader=proxy), [op("blank_output")])
    assert proxy.witness(PROBE).calls >= 1, "expected this operator to probe the grader"
    assert proxy.witness(DECISION).calls == 1
    assert proxy.witness(CLEAN).calls == 1
    assert proxy.witness(UNATTRIBUTED).calls == 0
    for rec in proxy.log(PROBE):
        assert rec["site"].startswith("evalmut/operators.py:")


def test_a_declining_operator_is_not_an_outcome_row():
    """An operator that declines produces no defective form, so the absence of a decision is
    correct here. It is still checked rather than assumed: the row asserts zero decision calls."""
    (row,) = witness_case(exact_case(), op("near_miss_number"))
    assert row.result.outcome is Outcome.NA
    assert row.status == ROW_NOT_AN_OUTCOME
    assert row.defect["status"] == MISSING and row.defect["calls"] == 0
    assert row.clean["status"] == WITNESSED
    assert not row.counts_toward_score


# ── the sentinel switched off ─────────────────────────────────────────────────────────

def test_a_disabled_sentinel_yields_incomplete_not_a_silent_pass():
    """The whole run still happens and the runner still labels the row CAUGHT. With nothing
    attributing the calls, that label is exactly the unbacked verdict this module refuses."""
    (row,) = witness_case(exact_case(), op("blank_output"), sites=())
    assert row.result.outcome is Outcome.CAUGHT, "the label is unchanged; only the evidence is gone"
    assert row.status == ROW_INCOMPLETE and not row.is_outcome
    assert row.clean["status"] == MISSING and row.defect["status"] == MISSING
    assert row.unattributed_calls >= 2, "the calls happened; nothing was watching the right place"
    assert "never invoked" in row.incomplete_reason
    assert "cannot attribute" in row.incomplete_reason


# ── the witness pointed at the wrong callable ────────────────────────────────────────

def test_a_witness_on_the_factory_witnesses_no_row_at_all():
    """gradecore's graders are factories. Patching `gradecore.exact` records one call, made while
    the suite module was being imported, and none per row. The identity alone gives it away: the
    factory is `gradecore.graders.exact`, the decision path is `...exact.<locals>.g`."""
    factory_proxy = WitnessingGrader(gradecore_graders.exact)
    grader = factory_proxy("42")          # suite construction, the only call it will ever see
    case = EvalCase("exact", grader, GradeInput(text="42", expected="42"))

    (row,) = witness_case(case, op("blank_output"))
    assert row.status == ROW_WITNESSED, "the row's own witness, on the closure, is fine"

    assert factory_proxy.identity["identity"] == "gradecore.graders.exact"
    assert row.defect["target"] == "gradecore.graders.exact.<locals>.g"
    assert factory_proxy.identity["identity"] != row.defect["target"]

    assert factory_proxy.witness(DECISION).calls == 0
    assert factory_proxy.witness(CLEAN).calls == 0
    assert factory_proxy.witness(UNATTRIBUTED).calls == 1

    from_factory = classify(row.result,
                            phase_witness(factory_proxy, CLEAN),
                            phase_witness(factory_proxy, DECISION),
                            probe_calls=0,
                            unattributed_calls=factory_proxy.witness(UNATTRIBUTED).calls)
    assert from_factory.status == ROW_INCOMPLETE
    assert "never invoked" in from_factory.incomplete_reason


# ── zero, and more than one ──────────────────────────────────────────────────────────

def test_zero_invocations_is_incomplete():
    proxy = WitnessingGrader(exact("42"))          # built, never called
    wit = phase_witness(proxy, DECISION)
    assert wit["status"] == MISSING
    assert wit["calls"] == 0 and wit["invoked"] is False and wit["raw_upstream"] == []
    row = classify(stub(), a_caught_row().clean, wit, probe_calls=0, unattributed_calls=0)
    assert row.status == ROW_INCOMPLETE
    assert "never invoked" in row.incomplete_reason


def _call_twice(proxy, inp):
    proxy(inp)
    proxy(inp)


def test_two_invocations_are_classified_explicitly_not_ignored():
    """A second entry into the decision site means the row is not the single decision it reports.
    It is named MULTIPLE and refused, rather than collapsed to "invoked, therefore fine"."""
    site = CallSite(DECISION, __file__, "_call_twice", "proxy(inp)")
    proxy = WitnessingGrader(exact("42"), sites=(site,))
    _call_twice(proxy, GradeInput(text="42", expected="42"))

    wit = phase_witness(proxy, DECISION)
    assert wit["status"] == MULTIPLE
    assert wit["calls"] == 2 and len(wit["raw_upstream"]) == 2
    row = classify(stub(), a_caught_row().clean, wit, probe_calls=0, unattributed_calls=0)
    assert row.status == ROW_INCOMPLETE
    assert "witness saw 2" in row.incomplete_reason


# ── the raw upstream capture ─────────────────────────────────────────────────────────

def test_removing_the_raw_upstream_capture_is_a_failure():
    row = a_caught_row()
    stripped = {k: v for k, v in row.defect.items() if k != "raw_upstream"}
    refused = classify(row.result, row.clean, stripped, probe_calls=0, unattributed_calls=0)
    assert refused.status == ROW_INCOMPLETE
    assert "raw_upstream" in refused.incomplete_reason


def test_a_count_that_disagrees_with_the_call_log_is_refused():
    row = a_caught_row()
    tampered = copy.deepcopy(row.defect)
    tampered["calls"] = 2                      # counter says two, the log still carries one
    refused = classify(row.result, row.clean, tampered, probe_calls=0, unattributed_calls=0)
    assert refused.status == ROW_INCOMPLETE
    assert "must not be interpreted" in refused.incomplete_reason


def test_the_recorded_outcome_is_rechecked_against_the_raw_return():
    """The reason the raw value is kept at all. The row says the defect was CAUGHT; the raw verdict
    says the grader passed the mutant. Both cannot be true, and the raw side is the one that came
    out of gradecore."""
    row = a_caught_row()
    assert row.result.outcome is Outcome.CAUGHT and row.result.polarity is Polarity.DEFECT
    tampered = copy.deepcopy(row.defect)
    tampered["raw_upstream"][0]["passed"] = True
    refused = classify(row.result, row.clean, tampered, probe_calls=0, unattributed_calls=0)
    assert refused.status == ROW_INCOMPLETE
    assert "recomputed from the raw upstream verdict" in refused.incomplete_reason


def test_a_clean_control_that_did_not_pass_is_refused():
    row = a_caught_row()
    tampered = copy.deepcopy(row.clean)
    tampered["raw_upstream"][0]["passed"] = False
    refused = classify(row.result, tampered, row.defect, probe_calls=0, unattributed_calls=0)
    assert refused.status == ROW_INCOMPLETE
    assert "no green baseline" in refused.incomplete_reason


# ── the headline ─────────────────────────────────────────────────────────────────────

def test_the_headline_excludes_incomplete_rows_and_counts_them_separately():
    import dataclasses

    caught, missed = a_caught_row(), a_missed_row()
    assert caught.result.outcome is Outcome.CAUGHT and missed.result.outcome is Outcome.MISSED

    before = summarize_rows([caught, missed], [], {"mismatches": 0})
    assert before["tally"]["caught"] == 1 and before["tally"]["missed"] == 1
    assert before["tally"]["incomplete"] == 0
    assert len(before["holes"]["blind"]) == 1
    assert before["score"] == pytest.approx(0.5)

    blinded = dataclasses.replace(missed, status=ROW_INCOMPLETE,
                                  incomplete_reason="simulated missing evidence")
    after = summarize_rows([caught, blinded], [], {"mismatches": 0})

    assert after["tally"]["incomplete"] == 1
    assert after["tally"]["missed"] == 0, "an unwitnessed row is not counted as survived"
    assert after["tally"]["caught"] == 1, "and not counted as caught either"
    denominator = after["tally"]["caught"] + after["tally"]["missed"] + after["tally"]["flagged"]
    assert denominator == 1, "the incomplete row left the denominator"
    assert after["holes"]["blind"] == [], "and left the holes it can no longer support"
    assert [r["case_name"] for r in after["incomplete"]] == ["contains"]
    assert after["incomplete"][0]["incomplete_reason"] == "simulated missing evidence"
    assert after["witness_protocol"]["row_counts"] == {
        "rows": 2, "witnessed": 1, "incomplete": 1, "not_an_outcome": 0}


def test_the_witnessed_driver_reproduces_the_plain_runner():
    """The proxy sits on the callable the runner invokes, so it could move a verdict. This is the
    check that it did not: same suite, no witness, same rows."""
    payload = witness_payload([exact_case(), contains_case()], catalog())
    assert payload["witness_protocol"]["driver_crosscheck"]["mismatches"] == 0
    assert payload["score"] == payload["ungated"]["score"]


# ── the committed artifact ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_the_committed_artifact_is_what_the_code_re_emits(artifact):
    proc = subprocess.run([sys.executable, "-m", "evalmut.cli", "witness",
                           "demos/dogfood_gradecore.py", "--json"],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode in (0, 1), proc.stderr
    assert proc.stdout == ARTIFACT.read_text(encoding="utf-8"), (
        "docs/dogfood_gradecore_witnessed.json is not what the code re-emits; re-run "
        "`evalmut witness demos/dogfood_gradecore.py --json` and commit the diff")


def test_the_committed_artifact_counts_only_witnessed_rows(artifact):
    t = artifact["tally"]
    rc = artifact["witness_protocol"]["row_counts"]
    assert rc["witnessed"] == t["caught"] + t["missed"] + t["flagged"] + t["error"]
    assert rc["incomplete"] == t["incomplete"] == len(artifact["incomplete"])
    assert rc["not_an_outcome"] == t["na"]
    assert rc["rows"] == len(artifact["results"])
    applied = t["caught"] + t["missed"] + t["flagged"]
    assert artifact["score"] == pytest.approx(t["caught"] / applied)


def test_every_counted_row_in_the_artifact_carries_both_witnesses(artifact):
    counted = [r for r in artifact["results"] if r["witness_status"] == ROW_WITNESSED]
    assert len(counted) == artifact["witness_protocol"]["row_counts"]["witnessed"]
    for r in counted:
        for phase in ("clean_control", "defect_decision"):
            wit = r["witness"][phase]
            assert wit["status"] == WITNESSED and wit["calls"] == 1
            assert wit["library"] == "gradecore"
            assert wit["target"].startswith("gradecore.")
            assert len(wit["raw_upstream"]) == 1
        assert r["witness"]["defect_decision"]["raw_upstream"][0]["site"].startswith(
            "evalmut/runner.py:")
        assert r["witness"]["unattributed_calls"] == 0


def test_the_artifact_names_the_library_version_and_the_decision_call(artifact):
    wp = artifact["witness_protocol"]
    assert wp["libraries"] == [{"name": "gradecore", "version": "0.10.0"}]
    assert wp["decision_call"]["function"] == "run_case"
    assert wp["decision_call"]["source_anchor"] == "case.grader(mutant)"
    assert wp["clean_control_call"]["source_anchor"] == "self.grader(self.good)"
    assert wp["driver_crosscheck"]["mismatches"] == 0


# --- No denominator, no percentage. ------------------------------------------------------
# A run where nothing could be witnessed printed "witnessed 0/0 caught (score 100.0%)". That
# turns an absence of evidence into the strongest claim the tool can make, which is the exact
# failure this module exists to detect. Zero would be no better: it asserts measured failure.
# These test render_witness_short DIRECTLY, not through the CLI, because the defect lived in a
# function no test ever executed.

import pytest
from evalmut.invocation_witness import render_witness_short, witness_payload
from evalmut.score import Tally


def _payload(*, caught=0, missed=0, incomplete=0, na=0, witnessed=0, score=None):
    applied = caught + missed
    return {
        "tally": {"caught": caught, "missed": missed, "flagged": 0, "incomplete": incomplete,
                  "na": na},
        "score": score,
        "witness_protocol": {
            "row_counts": {"rows": witnessed + incomplete + na, "witnessed": witnessed,
                           "incomplete": incomplete, "not_an_outcome": na},
            "decision_call": {"file": "evalmut/runner.py", "source_anchor": "case.grader(mutant)"},
            "libraries": [{"name": "gradecore", "version": "0.10.0"}]},
        "ungated": {"tally": {"caught": caught, "missed": missed, "flagged": 0}, "score": score},
        "incomplete": [{"case_name": "c", "operator_id": f"op{i}",
                        "incomplete_reason": "missing-invocation-witness"}
                       for i in range(incomplete)],
    }


def test_zero_witnessed_with_incomplete_rows_publishes_no_percentage():
    out = render_witness_short(_payload(incomplete=3, witnessed=0, score=None))
    assert "%" not in out, f"a run with no witnessed rows published a percentage:\n{out}"
    assert "UNAVAILABLE" in out
    assert "100" not in out


def test_zero_witnessed_all_not_applicable_publishes_no_percentage():
    """No incompletes either, every row simply inapplicable. Still no denominator."""
    out = render_witness_short(_payload(na=12, witnessed=0, score=None))
    assert "%" not in out, f"an all-N/A run published a percentage:\n{out}"
    assert "UNAVAILABLE" in out


def test_a_witnessed_population_does_render_its_score():
    """The guard must not suppress a real measurement."""
    out = render_witness_short(_payload(caught=42, missed=4, witnessed=46, na=223, score=42 / 46))
    assert "91.3%" in out, out
    assert "UNAVAILABLE" not in out


def test_a_score_of_one_on_an_empty_population_is_still_refused():
    """The mutation that reintroduces the defect: hand the renderer 1.0 with a zero denominator.

    This is the shape the bug had. Tally.score answers 1.0 for an empty population, so a caller
    that forwards it without checking the denominator prints 100.0% over nothing."""
    out = render_witness_short(_payload(incomplete=1, witnessed=0, score=1.0))
    assert "%" not in out, f"score=1.0 with a zero denominator still printed a rate:\n{out}"
    assert "100.0" not in out


def test_tally_exposes_whether_a_denominator_exists():
    assert Tally().scored is False
    assert Tally(caught=1).scored is True
    assert Tally(na=99).scored is False, "n/a rows are not a denominator"
    assert Tally().score == 1.0, (
        "the arithmetic default is unchanged on purpose; the guard is scored, not score")


def test_an_empty_eligible_population_makes_the_artifact_score_null():
    """Exercise the null branch, not merely the branch the committed artifact happens to take.

    An earlier version of this file only asserted against the shipped artifact, which HAS 46
    witnessed rows, so the `score is None` path never executed and the test stayed GREEN when the
    fallback to 1.0 was reintroduced. A test that only covers the healthy branch cannot detect a
    defect that lives in the other one. This drives summarize_rows with zero eligible rows."""
    from evalmut.invocation_witness import summarize_rows
    payload = summarize_rows([], [], {"plain_rows": 0, "witnessed_rows": 0, "mismatches": 0})
    assert payload["score"] is None, (
        f"an empty eligible population produced score={payload['score']!r}; "
        "1.0 reads as measured success and 0.0 as measured failure, both false")
    assert payload["ungated"]["score"] is None
    rendered = render_witness_short(payload)
    assert "%" not in rendered, f"the empty payload still rendered a percentage:\n{rendered}"


def test_the_committed_witness_artifact_has_a_real_denominator():
    """If the dogfood artifact ever ships with score null, that is a genuine finding, not a
    formatting question, and this test should be read rather than deleted."""
    import json, pathlib
    a = json.loads((pathlib.Path(__file__).parent.parent
                    / "docs/dogfood_gradecore_witnessed.json").read_text())
    t = a["tally"]
    applied = t["caught"] + t["missed"] + t["flagged"]
    if applied == 0:
        assert a["score"] is None, "no witnessed rows, so the artifact must not carry a score"
    else:
        assert a["score"] is not None and abs(a["score"] - t["caught"] / applied) < 1e-9
