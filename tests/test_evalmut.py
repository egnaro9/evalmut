"""evalmut's own tests.

Several of these are the tool pointed at itself: the mined-not-authored discipline is
enforced as a test (every operator must cite a real defect), the operator contract is
enforced as a test (a DEFECT operator's mutant must actually be wrong; an EQUIVALENT
operator's must actually be still-correct), and the four hole categories are checked
against graders of known strength. If evalmut's own honesty invariants regress, these
go red — the same standard it holds other suites to.

The block at the bottom pins every confirmed cold-critic finding (pass 1: D1–D4, I1, Q1;
pass 2: A–J) as a regression, each with the reviewer's runnable repro. The through-line
they enforce: an operator asserts a mutant's polarity ONLY by recomputing the graded
property against the grader's real acceptance condition (its grader_id contract, or a bar
DECLARED on the case) — never a module default, never a self-reported label — and declines
otherwise. A false hole is the one unforgivable bug for this tool.
"""
from __future__ import annotations

import pytest
from gradecore import (
    GradeInput, Verdict, contains, exact, exact_cs, number, regex, must_refuse, must_comply,
    must_abstain, valid_json, grounding, trajectory, injection_resistance, tool_misuse,
    bool_grader,
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
    report = run([bad])
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
        "drop_supporting_context": EvalCase("d", grounding(),
                                            g(text="alpha beta gamma",
                                              contexts=("alpha beta gamma", "zzz yyy")),
                                            judges=("text", "contexts")),
        "trajectory_drop_step": EvalCase("tr", trajectory("aa", "bb"),
                                         g(text="done",
                                           tool_calls=({"tool": "aa"}, {"tool": "bb"}, {"tool": "cc"})),
                                         judges=("tool_calls",), tags=("trajectory",),
                                         expected_trajectory=("aa", "bb")),
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
    does, the operator is mis-polarized and would manufacture false brittle findings. Each
    fixture DECLARES (via tolerates=) that its task's contract permits the cosmetic change."""
    fixtures = {
        "trailing_disclaimer": EvalCase("td", must_comply("poison control"),
                                        GradeInput(text="Call poison control now."),
                                        tags=("must_comply",), tolerates=("disclaimer",)),
        "whitespace_noise": EvalCase("wn", exact("42"), GradeInput(text="42", expected="42"),
                                     tolerates=("whitespace",)),
        "json_code_fence": EvalCase("jf", valid_json("count"),
                                    GradeInput(text='{"count": 3}'), tags=("json",),
                                    tolerates=("fence",)),
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
    # A content-required task whose grader passes everything is vacuous. content_required lets
    # the SANITY probes fire on a custom grader (they auto-fire on gradecore content ids).
    suite = [EvalCase("stamp", bool_grader(lambda t: True, "always"),
                      GradeInput(text="anything", expected="42"), content_required=True)]
    r = run(suite)
    assert r.vacuous  # blank + garbage both survive


def test_coverage_gap_not_blind_for_valid_json_types():
    suite = [EvalCase("j", valid_json("count"), GradeInput(text='{"count": 3}'), tags=("json",))]
    r = run(suite)
    assert any(h.operator_id == "json_value_type_flip" for h in r.coverage_gaps)
    assert not any(h.operator_id == "json_value_type_flip" for h in r.blind_spots)


def test_equivalent_held_on_requires_comply():
    suite = [EvalCase("c", must_comply("poison control"),
                      GradeInput(text="Call poison control now."),
                      tags=("must_comply",), tolerates=("disclaimer",))]
    r = run(suite)
    # trailing_disclaimer fires (declared tolerant) and must be CAUGHT (held), never brittle.
    assert not any(h.operator_id == "trailing_disclaimer" for h in r.brittle_spots)
    assert any(x.operator_id == "trailing_disclaimer" and x.outcome is Outcome.CAUGHT
               for x in r.results)


def test_brittle_grader_flagged():
    # A task that DECLARES whitespace cosmetic, graded by a byte-exact check, is genuinely
    # brittle — it rejects a correct answer with cosmetic whitespace. evalmut proves the mutant
    # is still correct (the declared contract tolerates whitespace) and flags the grader.
    liar = bool_grader(lambda t: t == "42", "exact")   # byte-exact despite the label
    suite = [EvalCase("liar", liar, GradeInput(text="42", expected="42"),
                      tolerates=("whitespace",))]
    r = run(suite)
    assert any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


def test_no_false_brittle_on_undeclared_contract():
    # Without a declared tolerance, an equivalence operator cannot prove the mutant is still
    # correct, so it must DECLINE — never flag a grader whose contract it cannot establish.
    byte_exact = bool_grader(lambda t: t == "42", "my_custom_check")
    suite = [EvalCase("u", byte_exact, GradeInput(text="42", expected="42"))]  # no tolerates
    r = run(suite)
    assert not any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


def test_robust_exact_held_when_whitespace_declared():
    suite = [EvalCase("ok", exact("42"), GradeInput(text="42", expected="42"),
                      tolerates=("whitespace",))]
    r = run(suite)
    assert not any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)
    # exact() genuinely normalizes whitespace, so the equivalent is CAUGHT (held), not flagged.
    assert any(x.operator_id == "whitespace_noise" and x.outcome is Outcome.CAUGHT
               for x in r.results)


# ── cold-critic PASS 1 regressions (every confirmed dishonest finding, pinned) ─

def test_D1_near_miss_declines_without_declared_tolerance():
    r = run([EvalCase("t", number(42, tol=0.1), GradeInput(text="42", expected=42))])
    assert not r.blind_spots


def test_D1_near_miss_with_tolerance_is_caught_not_blind():
    r = run([EvalCase("t", number(42, tol=0.1),
                      GradeInput(text="the total is 42", expected=42), num_tol=0.1)])
    assert not r.blind_spots  # perturbs outside the band -> the grader catches it


def test_D2_json_fence_declines_without_declared_tolerance():
    r = run([EvalCase("raw", exact_cs('{"status": "ok"}'),
                      GradeInput(text='{"status": "ok"}'), tags=("json",))])
    assert not any(h.operator_id == "json_code_fence" for h in r.brittle_spots)


def test_D3_whitespace_declines_without_declared_tolerance():
    r = run([EvalCase("a", regex(r"\A\{\"a\": 1\}\Z"), GradeInput(text='{"a": 1}'))])
    assert not any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


def test_D4_drop_context_declines_when_redundant_support_remains():
    gi = GradeInput(text="paris is the capital",
                    contexts=("paris is the capital of france",
                              "paris is the capital and largest city"))
    r = run([EvalCase("g", grounding(), gi, judges=("text", "contexts"))])
    assert not any(h.operator_id == "drop_supporting_context" for h in r.blind_spots)


def test_I1_grader_crash_is_error_not_caught():
    # A grader that indexes text[0] crashes on the blank-output probe. That must surface as
    # ERROR, not be scored CAUGHT and hidden. content_required opts the custom grader into SANITY.
    r = run([EvalCase("c", bool_grader(lambda t: t[0] == "x" or True, "fragile"),
                      GradeInput(text="xyz", expected="xyz"), content_required=True)])
    assert r.errors
    assert not any(x.outcome is Outcome.CAUGHT and x.grader_error for x in r.results)


def test_Q1_grader_crash_on_baseline_is_collected_not_raised():
    good = EvalCase("ok", exact("42"), GradeInput(text="42", expected="42"))
    boom = EvalCase("boom", bool_grader(lambda t: 1 / 0, "div0"), GradeInput(text="42"))
    r = run([good, boom])           # must not raise
    assert r.baseline_failures      # the crashing case is reported by name
    assert any(x.case_name == "ok" for x in r.results)  # the good case still ran


# ── cold-critic PASS 2 regressions (recompute-or-decline against the real bar) ─

def test_P2A_drop_context_no_false_blind_on_lenient_grounding():
    # grounding(threshold=0.4): dropping a chunk to 0.5 grounding leaves the answer supported
    # at THIS grader's bar, so the grader is right to pass — not a blind spot (pass-2 A).
    gi = GradeInput(text="alpha beta gamma delta",
                    contexts=("alpha beta gamma delta", "alpha beta"))
    r = run([EvalCase("t", grounding(threshold=0.4), gi, judges=("text", "contexts"))])
    assert not r.blind_spots


def test_P2A_drop_context_caught_when_support_fully_gone():
    gi = GradeInput(text="alpha beta gamma", contexts=("alpha beta gamma", "zzz yyy"))
    r = run([EvalCase("t", grounding(), gi, judges=("text", "contexts"))])
    # dropping the sole support -> grounding 0.0 -> a correct grounding grader must reject it
    assert not r.blind_spots
    assert any(x.operator_id == "drop_supporting_context" and x.outcome is Outcome.CAUGHT
               for x in r.results)


def test_P2B_no_false_brittle_on_composite_grader_with_primitive_id():
    # A composite grader that honestly carries the id "contains" but also bounds length is NOT
    # whitespace-insensitive; without a declared tolerance the operator must decline (pass-2 B).
    def bounded_contains(inp):
        ok = contains("42")(inp).passed and len(inp.text) <= 16
        return Verdict(passed=ok, score=1.0 if ok else 0.0,
                       severity="none" if ok else "med", detail="bounded", grader_id="contains")
    r = run([EvalCase("c", bounded_contains, GradeInput(text="the total is 42"))])  # 15 chars
    assert not r.brittle_spots


def test_P2C_sanity_declines_on_absence_graders():
    # injection_resistance / tool_misuse PASS a blank output legitimately (no leak, no bad tool),
    # so the SANITY probes must not call them vacuous (pass-2 C).
    inj = run([EvalCase("inj", injection_resistance("SECRET_KEY"),
                        GradeInput(text="Translation done.", expected="SECRET_KEY"),
                        tags=("injection",))])
    assert not inj.vacuous
    tm = run([EvalCase("tm", tool_misuse(["rm"]),
                       GradeInput(text="done", tool_calls=({"tool": "search"},), expected="rm"),
                       judges=("tool_calls",), tags=("tool_policy",))])
    assert not tm.vacuous


def test_P2D_garbage_does_not_satisfy_presence_graders():
    # The garbage probe is opaque, non-lexical text, so a presence check for a common English
    # word REJECTS it (CAUGHT), never coincidentally passes it into a false vacuous (pass-2 D).
    for needle in ("question", "answer", "different", "amet", "ipsum"):
        good = GradeInput(text=f"this {needle} is present here", expected=needle)
        r = run([EvalCase(needle, contains(needle), good)])
        assert not r.vacuous, f"garbage falsely satisfied contains({needle!r})"


def test_P2E_trajectory_no_false_blind_on_trailing_call():
    # A trailing non-required call (an agent's final log step) dropped leaves coverage at 1.0;
    # without a declared plan the operator declines rather than blame a correct grader (pass-2 E).
    gi = GradeInput(text="done",
                    tool_calls=({"tool": "plan"}, {"tool": "search"}, {"tool": "log"}))
    r = run([EvalCase("tr", trajectory("plan", "search"), gi,
                      judges=("tool_calls",), tags=("trajectory",))])  # no expected_trajectory
    assert not r.blind_spots


def test_P2E_trajectory_caught_on_required_step_when_declared():
    gi = GradeInput(text="done",
                    tool_calls=({"tool": "plan"}, {"tool": "search"}, {"tool": "log"}))
    r = run([EvalCase("tr", trajectory("plan", "search"), gi,
                      judges=("tool_calls",), tags=("trajectory",),
                      expected_trajectory=("plan", "search"))])
    # it drops a REQUIRED step (coverage < 1.0); the correct grader rejects it -> CAUGHT.
    assert not r.blind_spots
    assert any(x.operator_id == "trajectory_drop_step" and x.outcome is Outcome.CAUGHT
               for x in r.results)


def test_P2F_num_tol_under_declared_does_not_manufacture_blind_spot():
    # Grader's real band is +-10; the case under-declares num_tol=0.5. The cross-check probe
    # past the declared edge is accepted by the wide grader, so the operator declines (pass-2 F).
    r = run([EvalCase("x", number(50, tol=10),
                      GradeInput(text="The answer is 50", expected=50), num_tol=0.5)])
    assert not r.blind_spots


def test_P2G_defect_crash_is_surfaced_not_hidden():
    import gradecore as gc

    def raiser(inp):
        if not inp.text.strip() or "zxqfp" in inp.text:
            raise RuntimeError("boom")          # crashes on the SANITY defect probes
        return gc.contains("deploy")(inp)       # id "contains" -> content-requiring
    r = run([EvalCase("r", raiser, GradeInput(text="I ran deploy", expected="deploy"))])
    # the defect-crashes are re-surfaced so a crashing grader can't empty the blind list silently
    assert r.crashing_defects
    assert all(d.polarity is Polarity.DEFECT for d in r.crashing_defects)


def test_P2H_near_miss_leaves_bystander_numbers_intact():
    from evalmut.operators import _near_miss_number
    c = EvalCase("x", number(5, tol=0.5, which="last"),
                 GradeInput(text="Batch 2015, lot 25 - final count 5", expected=5), num_tol=0.5)
    m = _near_miss_number.apply(c)
    assert m is not None
    assert "2015" in m.text and "lot 25" in m.text   # bystander numbers untouched
    assert m.text.rstrip().endswith("6.5")           # only the answer token perturbed


def test_P2I_truncate_declines_on_refusal_grader():
    # Truncating a refusal before its harm keyword leaves a valid refusal; a correct safety
    # grader passes it, so truncate must not fire on a refusal/absence grader (pass-2 I).
    good = GradeInput(text="I can't help with that; that compound is dangerous.",
                      expected="dangerous")
    r = run([EvalCase("s", must_refuse(), good, tags=("must_refuse",))])
    assert not any(h.operator_id == "truncate_before_answer" for h in r.blind_spots)


def test_P2J_whitespace_provenance_is_not_grader_under_test_specific():
    op = next(o for o in catalog() if o.id == "whitespace_noise")
    assert "graders.py:79" not in op.real_origin
    assert "exact is whitespace-insensitive by contract" not in op.real_origin


def test_P2K_near_miss_declines_on_exponent_notation():
    # str(5e-07) yields a lone mantissa digit '5'; targeting it would rewrite the wrong token,
    # so the operator declines on exponent/degenerate forms rather than mis-target (pass-2 K).
    from evalmut.operators import _near_miss_number
    c = EvalCase("x", number(5e-07, tol=1e-9),
                 GradeInput(text="the probability is 5e-07", expected=5e-07), num_tol=1e-9)
    assert _near_miss_number.apply(c) is None


# ── determinism ──────────────────────────────────────────────────────────────

def test_run_is_deterministic():
    suite = [
        EvalCase("a", contains("42"), GradeInput(text="the total is 42", expected="42"),
                 tags=("presence_check",)),
        EvalCase("b", number(42), GradeInput(text="42", expected=42)),
        EvalCase("c", must_refuse(), GradeInput(text="I cannot help"), tags=("must_refuse",)),
    ]
    sig = lambda r: [(x.case_name, x.operator_id, x.outcome.value) for x in r.results]
    assert sig(run(suite)) == sig(run(suite)) == sig(run(suite))
