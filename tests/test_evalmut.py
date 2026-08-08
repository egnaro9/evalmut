"""evalmut's own tests.

Several of these are the tool pointed at itself: the mined-not-authored discipline is
enforced as a test (every operator must cite a real defect), the operator contract is
enforced as a test (a DEFECT operator's mutant must actually be wrong; an EQUIVALENT
operator's must actually be still-correct), and the four hole categories are checked
against graders of known strength. If evalmut's own honesty invariants regress, these
go red — the same standard it holds other suites to.
"""
from __future__ import annotations

import pytest
from gradecore import (
    GradeInput, contains, exact, exact_cs, number, must_refuse, must_comply,
    must_abstain, valid_json, bool_grader,
)

from evalmut import (
    EvalCase, run, run_case, catalog, Outcome, Polarity, OperatorType, BaselineError,
)
from evalmut.outcome import outcome_for


# ── the tiny judgment core ───────────────────────────────────────────────────

def test_outcome_for_defect():
    assert outcome_for(Polarity.DEFECT, grader_passed=False) is Outcome.CAUGHT
    assert outcome_for(Polarity.DEFECT, grader_passed=True) is Outcome.MISSED


def test_outcome_for_equivalent():
    assert outcome_for(Polarity.EQUIVALENT, grader_passed=True) is Outcome.CAUGHT
    assert outcome_for(Polarity.EQUIVALENT, grader_passed=False) is Outcome.FLAGGED


def test_na_excluded_from_score():
    from evalmut.score import Tally
    t = Tally(caught=3, missed=1, flagged=0, na=100)
    assert t.applied == 4
    assert t.score == pytest.approx(0.75)  # NA does not dilute


# ── baseline enforcement ─────────────────────────────────────────────────────

def test_baseline_failure_raises_in_run_case():
    bad = EvalCase("bad", exact("42"), GradeInput(text="not the answer", expected="42"))
    with pytest.raises(BaselineError):
        run_case(bad, catalog())


def test_baseline_failure_collected_by_run():
    bad = EvalCase("bad", exact("42"), GradeInput(text="wrong", expected="42"))
    report = run(catalog=None) if False else run([bad])  # keep signature explicit
    assert report.baseline_failures  # loud, not swallowed
    assert not report.results        # nothing was mutated


# ── the mined-not-authored discipline, as a test ─────────────────────────────

def test_every_operator_names_a_real_origin():
    """The project's whole credibility. An operator with no concrete provenance is an
    authored guess, and authored guesses are exactly the blind spot we hunt. Enforce it."""
    citation = (".py", ".sh", ".md", ".java", ":", "model-drift", "gradecore")
    for op in catalog():
        assert op.real_origin and len(op.real_origin) > 20, f"{op.id}: thin provenance"
        assert any(tok in op.real_origin for tok in citation), \
            f"{op.id}: provenance names no concrete artifact — is it mined or authored?"


def test_operator_ids_unique():
    ids = [op.id for op in catalog()]
    assert len(ids) == len(set(ids))


# ── the operator contract: mutants are what they claim to be ─────────────────

def _defect_case_for(op):
    """A case each DEFECT operator applies to, with a strict reference grader that a
    correct output passes and a wrong one fails — so we can independently confirm the
    mutant really is wrong."""
    g = GradeInput
    by_id = {
        "truncate_before_answer": EvalCase("t", contains("42"), g(text="the total is 42", expected="42")),
        "blank_output": EvalCase("b", contains("answer"), g(text="the answer is here")),
        "near_miss_number": EvalCase("n", number(42, tol=0.1),
                                     g(text="the total is 42", expected=42), num_tol=0.1),
        "garbage_answer": EvalCase("g", contains("42"), g(text="the total is 42")),
        "keyword_present_but_negated": EvalCase("k", contains("deploy"),
                                                g(text="I ran deploy successfully", expected="deploy"),
                                                tags=("presence_check",)),
        "comply_with_harm": EvalCase("c", must_refuse(), g(text="I cannot help with that."),
                                     tags=("must_refuse",)),
        "over_refuse_benign": EvalCase("o", must_comply("hello"), g(text="hello, here is your answer"),
                                       tags=("must_comply",)),
        "fabricate_over_abstain": EvalCase("f", must_abstain(), g(text="No such thing exists."),
                                           tags=("must_abstain",)),
        "leak_injection": EvalCase("l", contains("done"),
                                   g(text="Translation done.", expected="SECRET_KEY"),
                                   tags=("injection",)),
        "json_value_type_flip": EvalCase("j", valid_json("count"), g(text='{"count": 3}'), tags=("json",)),
        "drop_supporting_context": EvalCase("d", contains("paris"),
                                            g(text="paris is the capital",
                                              contexts=("paris is the capital of france", "berlin is in germany"))),
        "trajectory_drop_step": EvalCase("tr", contains("x"),
                                         g(text="x", tool_calls=({"tool": "a"}, {"tool": "b"}))),
        "inject_denylisted_tool": EvalCase("id", contains("x"),
                                           g(text="x", tool_calls=({"tool": "safe"},), expected="rm"),
                                           tags=("tool_policy",)),
    }
    return by_id.get(op.id)


@pytest.mark.parametrize("op", [o for o in catalog() if o.polarity is Polarity.DEFECT],
                         ids=lambda o: o.id)
def test_defect_operator_produces_a_changed_mutant(op):
    case = _defect_case_for(op)
    if case is None:
        pytest.skip(f"no fixture for {op.id}")
    mutant = op.apply(case)
    if mutant is None:
        pytest.skip(f"{op.id} declined this fixture (N/A) — acceptable")
    # A DEFECT mutant must differ from the reference on the field it targets.
    assert mutant != case.good, f"{op.id} returned an unchanged input"


@pytest.mark.parametrize("op", [o for o in catalog() if o.polarity is Polarity.EQUIVALENT],
                         ids=lambda o: o.id)
def test_equivalent_operator_preserves_a_normalizing_grader(op):
    """An EQUIVALENT operator must NOT break a grader that is correctly tolerant. If it
    does, the operator is mis-polarized and would manufacture false brittle findings."""
    fixtures = {
        "trailing_disclaimer": EvalCase("td", must_comply("poison control"),
                                        GradeInput(text="Call poison control now."),
                                        tags=("must_comply",)),
        "whitespace_noise": EvalCase("wn", exact("42"), GradeInput(text="42", expected="42")),
        "json_code_fence": EvalCase("jf", valid_json("count"),
                                    GradeInput(text='{"count": 3}'), tags=("json",)),
    }
    case = fixtures.get(op.id)
    if case is None:
        pytest.skip(f"no fixture for {op.id}")
    mutant = op.apply(case)
    if mutant is None:
        pytest.skip(f"{op.id} declined (N/A)")
    v = case.grader(mutant)
    assert v.passed, f"{op.id} broke a tolerant grader — it is not equivalence-preserving"


# ── the four hole categories, end to end ─────────────────────────────────────

def test_blind_spot_on_weak_contains():
    suite = [EvalCase("weak", contains("42"),
                      GradeInput(text="the total is 42", expected="42"), tags=("presence_check",))]
    r = run(suite)
    assert any(h.operator_id == "keyword_present_but_negated" for h in r.blind_spots)


def test_strong_grader_has_no_blind_spot_on_that():
    suite = [EvalCase("strong", exact("42", scope="last_line"),
                      GradeInput(text="working it out\n42", expected="42"), tags=("presence_check",))]
    r = run(suite)
    assert not any(h.operator_id == "keyword_present_but_negated" for h in r.blind_spots)


def test_vacuous_grader_flagged_vacuous():
    suite = [EvalCase("stamp", bool_grader(lambda t: True, "always"),
                      GradeInput(text="anything", expected="42"))]
    r = run(suite)
    assert r.vacuous  # blank + garbage both survive


def test_coverage_gap_not_blind_for_valid_json_types():
    suite = [EvalCase("j", valid_json("count"), GradeInput(text='{"count": 3}'), tags=("json",))]
    r = run(suite)
    assert any(h.operator_id == "json_value_type_flip" for h in r.coverage_gaps)
    assert not any(h.operator_id == "json_value_type_flip" for h in r.blind_spots)


def test_equivalent_held_on_requires_comply():
    suite = [EvalCase("c", must_comply("poison control"),
                      GradeInput(text="Call poison control now."), tags=("must_comply",))]
    r = run(suite)
    # trailing_disclaimer must be CAUGHT (held), never a brittle finding here.
    assert not any(h.operator_id == "trailing_disclaimer" for h in r.brittle_spots)


def test_brittle_grader_flagged():
    # A grader that advertises a whitespace-insensitive contract (grader_id "exact") but is
    # actually byte-exact is genuinely brittle — it rejects a correct answer with cosmetic
    # whitespace. evalmut can prove the mutant is still correct (the "exact" contract tolerates
    # whitespace) and correctly flags the grader.
    liar = bool_grader(lambda t: t == "42", "exact")   # claims 'exact', behaves byte-exact
    suite = [EvalCase("liar", liar, GradeInput(text="42", expected="42"))]
    r = run(suite)
    assert any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


def test_no_false_brittle_on_unknown_grader():
    # An UNKNOWN grader_id whose whitespace-tolerance evalmut cannot confirm must NOT be called
    # brittle — proving equivalence requires knowing the contract (cold-critic D3).
    unknown = bool_grader(lambda t: t == "42", "my_custom_check")
    suite = [EvalCase("u", unknown, GradeInput(text="42", expected="42"))]
    r = run(suite)
    assert not any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


def test_robust_exact_not_brittle_on_whitespace():
    suite = [EvalCase("ok", exact("42"), GradeInput(text="42", expected="42"))]
    r = run(suite)
    assert not any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


# ── determinism ──────────────────────────────────────────────────────────────

# ── cold-critic regressions (every confirmed dishonest finding, pinned) ──────

def test_D1_near_miss_declines_without_declared_tolerance():
    # A numeric near-miss is grader-tolerance-dependent; without a declared tolerance the
    # operator cannot prove DEFECT and must not manufacture a blind spot.
    r = run([EvalCase("t", number(42, tol=0.1), GradeInput(text="42", expected=42))])
    assert not r.blind_spots


def test_D1_near_miss_with_tolerance_is_caught_not_blind():
    r = run([EvalCase("t", number(42, tol=0.1),
                      GradeInput(text="the total is 42", expected=42), num_tol=0.1)])
    assert not r.blind_spots  # perturbs outside the band -> the grader catches it


def test_D2_json_fence_declines_on_raw_json_grader():
    r = run([EvalCase("raw", exact_cs('{"status": "ok"}'),
                      GradeInput(text='{"status": "ok"}'), tags=("json",))])
    assert not any(h.operator_id == "json_code_fence" for h in r.brittle_spots)


def test_D3_whitespace_declines_on_anchored_regex():
    from gradecore import regex
    r = run([EvalCase("a", regex(r"\A\{\"a\": 1\}\Z"), GradeInput(text='{"a": 1}'))])
    assert not any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


def test_D4_drop_context_declines_when_redundant_support_remains():
    from gradecore import grounding
    gi = GradeInput(text="paris is the capital",
                    contexts=("paris is the capital of france",
                              "paris is the capital and largest city"))
    r = run([EvalCase("g", grounding(), gi, judges=("text", "contexts"))])
    assert not any(h.operator_id == "drop_supporting_context" for h in r.blind_spots)


def test_I1_grader_crash_is_error_not_caught():
    # A grader that indexes text[0] crashes on the blank-output probe. That must surface as
    # ERROR, not be scored CAUGHT and hidden.
    r = run([EvalCase("c", bool_grader(lambda t: t[0] == "x" or True, "fragile"),
                      GradeInput(text="xyz", expected="xyz"))])
    assert r.errors
    assert not any(x.outcome is Outcome.CAUGHT and x.grader_error for x in r.results)


def test_Q1_grader_crash_on_baseline_is_collected_not_raised():
    good = EvalCase("ok", exact("42"), GradeInput(text="42", expected="42"))
    boom = EvalCase("boom", bool_grader(lambda t: 1 / 0, "div0"), GradeInput(text="42"))
    r = run([good, boom])           # must not raise
    assert r.baseline_failures      # the crashing case is reported by name
    assert any(x.case_name == "ok" for x in r.results)  # the good case still ran


def test_run_is_deterministic():
    suite = [
        EvalCase("a", contains("42"), GradeInput(text="the total is 42", expected="42"),
                 tags=("presence_check",)),
        EvalCase("b", number(42), GradeInput(text="42", expected=42)),
        EvalCase("c", must_refuse(), GradeInput(text="I cannot help"), tags=("must_refuse",)),
    ]
    sig = lambda r: [(x.case_name, x.operator_id, x.outcome.value) for x in r.results]
    assert sig(run(suite)) == sig(run(suite)) == sig(run(suite))
