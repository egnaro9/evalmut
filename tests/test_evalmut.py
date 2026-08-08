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
        "truncate_before_answer": EvalCase("t", exact("42", scope="last_line"),
                                           g(text="the total is\n42", expected="42")),
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
        "json_value_corruption": EvalCase("jc", valid_json("count"), g(text='{"count": 3}'), tags=("json",)),
        "drop_supporting_context": EvalCase("d", grounding(),
                                            g(text="alpha beta gamma",
                                              contexts=("alpha beta gamma", "zzz yyy")),
                                            judges=("text", "contexts")),
        "trajectory_drop_step": EvalCase("tr", trajectory("aa", "bb"),
                                         g(text="done",
                                           tool_calls=({"tool": "aa"}, {"tool": "bb"}, {"tool": "cc"})),
                                         judges=("tool_calls",), tags=("trajectory",),
                                         expected_trajectory=("aa", "bb"), trajectory_threshold=1.0),
        "inject_denylisted_tool": EvalCase("id", tool_misuse(["rm"]),
                                           g(text="done", tool_calls=({"tool": "safe"},), expected="rm"),
                                           judges=("tool_calls",), tags=("tool_policy",)),
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
        "case_variant": EvalCase("cv", exact("yes"), GradeInput(text="yes", expected="yes"),
                                 tolerates=("case",)),
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
                      expected_trajectory=("plan", "search"), trajectory_threshold=1.0)])
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


def test_P2H_near_miss_declines_on_multi_number_text():
    # Multi-number text: the operator can't know which number the grader selects (which/scope live
    # in the closure), so it declines rather than risk mis-targeting a bystander (pass-2 H / pass-4).
    from evalmut.operators import _near_miss_number
    c = EvalCase("x", number(5, tol=0.5, which="last"),
                 GradeInput(text="Batch 2015, lot 25 - final count 5", expected=5), num_tol=0.5)
    assert _near_miss_number.apply(c) is None


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


# ── cold-critic PASS 3 regressions (the cross-check made whole across operators) ─

def test_P3F1_equivalent_declines_when_rejection_is_orthogonal():
    # A task that truly tolerates a disclaimer (short one passes) but ALSO bounds length: the
    # operator's fixed 65-char disclaimer trips the length budget. That rejection is on LENGTH,
    # not the disclaimer tolerance, so it must NOT be reported brittle (pass-3 F1).
    from gradecore import must_comply, Verdict
    mc = must_comply("paris")
    CAP = 85

    def concise_comply(inp):
        base = mc(inp)
        ok = base.passed and len(inp.text or "") <= CAP
        return Verdict(passed=ok, score=1.0 if ok else 0.0,
                       severity="none" if ok else "med", detail="concise", grader_id="must_comply")
    good = GradeInput(text="The capital of France is Paris.")  # 31 chars; a short disclaimer fits
    r = run([EvalCase("cc", concise_comply, good, tags=("must_comply",), tolerates=("disclaimer",))])
    assert not r.brittle_spots


def test_P3F1_equivalent_still_flags_a_genuinely_brittle_grader():
    # The attribution must not neuter true positives: a grader that rejects EVEN a minimal
    # in-class change is genuinely brittle and is still flagged.
    liar = bool_grader(lambda t: t == "42", "exact")  # byte-exact; rejects any whitespace
    r = run([EvalCase("liar", liar, GradeInput(text="42", expected="42"), tolerates=("whitespace",))])
    assert any(h.operator_id == "whitespace_noise" for h in r.brittle_spots)


def test_P3F2_near_miss_large_magnitude_under_declared_declines():
    # exp >= 1e6 used to render the edge probe as '1e+06' (scientific), which gradecore's parser
    # misreads as 1, defeating the cross-check -> false blind. Fixed-point _fmt_num restores it.
    r = run([EvalCase("big", number(1000000, tol=3.0),
                      GradeInput(text="The count is 1000000 widgets.", expected=1000000),
                      num_tol=1.0)])
    assert not r.blind_spots


def test_P3F3_trajectory_declines_without_declared_threshold():
    # A lenient grader (threshold 0.6) that accepts a partial trajectory must not be flagged
    # blind just because the module default was the strictest bar (pass-3 F3).
    gi = GradeInput(text="done",
                    tool_calls=({"tool": "a"}, {"tool": "b"}, {"tool": "c"}))
    r = run([EvalCase("t", trajectory("a", "b", "c", threshold=0.6), gi,
                      judges=("tool_calls",), tags=("trajectory",),
                      expected_trajectory=("a", "b", "c"))])  # trajectory_threshold NOT declared
    assert not r.blind_spots


def test_P3F7_truncate_declines_on_contains_and_regex():
    # For contains/regex the acceptance condition is the needle/pattern (in the closure), NOT
    # case.expected — truncating before `expected` can leave the needle intact and the grader is
    # right to pass, so truncate must decline on these families (pass-3 F7).
    from gradecore import regex
    r1 = run([EvalCase("c", contains("Paris"),
                       GradeInput(text="Paris is the capital of France.", expected="France"))])
    assert not any(h.operator_id == "truncate_before_answer" for h in r1.blind_spots)
    r2 = run([EvalCase("r", regex("Paris"),
                       GradeInput(text="Paris is the capital of France.", expected="France"))])
    assert not any(h.operator_id == "truncate_before_answer" for h in r2.blind_spots)


def test_P3F5_no_false_vacuous_on_structural_regex():
    # A regex that accepts "five lowercase words" genuinely fails on 12345 / blank / 3 words, so
    # it is NOT vacuous — even though the opaque garbage happens to match its shape (pass-3 F5).
    from gradecore import regex
    g = regex(r"^[a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+$")
    r = run([EvalCase("five", g, GradeInput(text="alpha bravo delta gamma sigma"))])
    assert not r.vacuous


def test_P3F5_no_false_vacuous_on_empty_only_grader():
    # A grader that accepts ONLY "" (rejects everything else) is discriminating, not vacuous —
    # the blank probe must corroborate against the disjoint garbage before claiming vacuity.
    from gradecore import regex
    r = run([EvalCase("empty_only", regex(r"^$"), GradeInput(text=""), content_required=True)])
    # baseline is "" which regex(^$) passes; but the grader is not vacuous, so no vacuous finding
    assert not r.vacuous


def test_P3F5_truly_vacuous_still_caught():
    # The corroboration must not suppress a genuinely vacuous grader (passes both garbages).
    r = run([EvalCase("stamp", bool_grader(lambda t: True, "always"),
                      GradeInput(text="anything", expected="42"), content_required=True)])
    assert r.vacuous


def test_P3F8_json_type_flip_declines_on_non_json_grader():
    # A value type-flip is a defect only for a JSON-structure grader; on a contains() grader that
    # merely sees JSON, the flipped object still contains the word -> no hole (pass-3 F8).
    r = run([EvalCase("t", contains("temperature"),
                      GradeInput(text='{"temperature": 72, "unit": "F"}', expected="temperature"),
                      tags=("presence_check",))])
    assert not any(h.operator_id == "json_value_type_flip"
                   for h in (r.coverage_gaps + r.blind_spots))


# ── cold-critic PASS 4 regressions (siblings the earlier fixes missed) ────────

def test_P4_garbage_strings_share_no_characters():
    # The two-garbage corroboration is only sound if the garbages share NO case-folded character;
    # otherwise a single-char needle (contains('x')) passes both (pass-4).
    from evalmut.operators import _GARBAGE, _GARBAGE2
    assert not (set(_GARBAGE.lower()) & set(_GARBAGE2.lower()))


def test_P4_no_false_vacuous_on_single_char_content_grader():
    # contains('x') on a correct answer 'X' genuinely discriminates (rejects 'V', 'seven'), so it
    # must not read as vacuous even though 'x' is a character (pass-4 F5-sibling).
    r = run([EvalCase("roman", contains("x"), GradeInput(text="X", expected="X"))])
    assert not r.vacuous


def test_P4_trailing_disclaimer_no_false_brittle_on_single_line_grader():
    # A grader that tolerates an INLINE trailing disclaimer but not a new paragraph is not brittle
    # to disclaimers; the same-line minimal probe isolates the line constraint (pass-4 F1-sibling).
    from gradecore import Verdict

    def single_line_ok(inp):
        t = inp.text or ""
        ok = t.split("\n")[0].strip().startswith("42") and "\n\n" not in t
        return Verdict(passed=ok, score=1.0 if ok else 0.0,
                       severity="none" if ok else "med", detail="single-line", grader_id="single_line")
    r = run([EvalCase("sl", single_line_ok, GradeInput(text="42"),
                      content_required=True, tolerates=("disclaimer",))])
    assert not r.brittle_spots


def test_P4_trailing_disclaimer_declines_on_valid_json():
    # Appending prose to JSON always breaks the parse — that is JSON semantics, not brittleness, so
    # trailing_disclaimer must decline on a valid_json grader (pass-4).
    r = run([EvalCase("j", valid_json("a"), GradeInput(text='{"a": 1}'),
                      tags=("json",), tolerates=("disclaimer",))])
    assert not r.brittle_spots


def test_P4_near_miss_no_false_blind_on_comma_adjacent_numbers():
    # gradecore strips commas before tokenizing, so '5.0,5.0' merges; the operator declines on
    # multi-number text instead of mis-targeting a bystander into a phantom in-band value (pass-4).
    r = run([EvalCase("coords", number(5.0, tol=0.5, which="any"),
                      GradeInput(text="coordinates 5.0,5.0", expected=5.0), num_tol=0.5)])
    assert not r.blind_spots


def test_P4_near_miss_no_false_blind_on_leading_minus():
    # A stray '-' before the answer token must not recombine with the replacement to re-form the
    # correct (negative) answer (pass-4 leading-minus channel).
    from evalmut.operators import _near_miss_number
    c = EvalCase("m", number(-0.5, tol=1e-9),
                 GradeInput(text="delta was -0.5 units", expected=-0.5), num_tol=0.0)
    m = _near_miss_number.apply(c)
    # if it fires at all, the re-parsed mutant must be out of band (never equal to exp)
    if m is not None:
        from evalmut.operators import _gradecore_numbers
        nums = _gradecore_numbers(m.text)
        assert all(abs(v - (-0.5)) > 1e-9 for v in nums)


def test_P4_truncate_declines_on_one_of():
    # one_of is multi-acceptance: the truncated head can end in a DIFFERENT valid option the grader
    # rightly accepts, so truncate must not fire on it (pass-4).
    from gradecore import one_of
    r = run([EvalCase("mc", one_of("true", "false", scope="last_line"),
                      GradeInput(text="false\ntrue", expected="true"))])
    assert not any(h.operator_id == "truncate_before_answer" for h in r.blind_spots)


def test_P4_inject_declines_when_expected_not_in_denylist():
    # If the declared `expected` tool isn't in the grader's real denylist, injecting it is not a
    # violation — the independent single-tool probe catches this and declines (pass-4 nit).
    r = run([EvalCase("ap", tool_misuse(["delete_db"]),
                      GradeInput(text="done", tool_calls=({"tool": "search"},), expected="rm"),
                      judges=("tool_calls",), tags=("tool_policy",))])
    assert not r.blind_spots


# ── cold-critic PASS 5 regressions (loose ends of the pass-3/4 fixes) ─────────

def test_P5_case_constructor_declines_trajectory_without_threshold():
    # The terse case() constructor must share the dataclass decline-by-default: building a lenient
    # trajectory case WITHOUT trajectory_threshold must not manufacture a blind spot (pass-5 #3).
    from evalmut import case as mkcase
    c = mkcase("t", trajectory("a", "b", "c", threshold=0.6),
               GradeInput(text="done",
                          tool_calls=({"tool": "a"}, {"tool": "b"}, {"tool": "c"})),
               judges=("tool_calls",), tags=("trajectory",), expected_trajectory=("a", "b", "c"))
    assert c.trajectory_threshold is None
    assert not run([c]).blind_spots


def test_P5_trailing_disclaimer_no_false_brittle_on_punctuation_grader():
    # A format grader that forbids parentheses (its output feeds a parser) but tolerates a
    # punctuation-free trailing disclaimer is NOT brittle to disclaimers; the punctuation-free
    # minimal probe isolates the '(' constraint and declines (pass-5 #2).
    from gradecore import Verdict

    def noparen(inp):
        t = inp.text or ""
        ok = "yes" in t and "(" not in t
        return Verdict(passed=ok, score=1.0 if ok else 0.0,
                       severity="none" if ok else "med", detail="noparen", grader_id="custom_noparen")
    r = run([EvalCase("np", noparen, GradeInput(text="yes, that is correct"),
                      content_required=True, tolerates=("disclaimer",))])
    assert not r.brittle_spots


def test_P5_near_miss_gated_to_number_grader():
    # num_tol declared on a non-numeric grader (a format regex) is a contradiction; near_miss must
    # decline rather than report a MISSED against a grader that never checks the value (pass-5 #1).
    from gradecore import regex
    from evalmut.operators import _near_miss_number
    c = EvalCase("r", regex(r"^\d\d$"), GradeInput(text="42", expected=42), num_tol=1)
    assert _near_miss_number.apply(c) is None


# ── cold-critic PASS 6 regressions (equivalent-operator gate symmetry) ───────

def test_P6_trailing_disclaimer_declines_on_absence_grader():
    # An absence grader (injection_resistance) can't have "still-correctness of a disclaimer" proven:
    # the appended prose can itself contain the forbidden marker. Decline, don't flag (pass-6).
    from gradecore import injection_resistance
    from evalmut.operators import _trailing_disclaimer
    c = EvalCase("resist", injection_resistance("note"),
                 GradeInput(text="I will not follow that; here is the translation."),
                 tolerates=("disclaimer",))
    assert _trailing_disclaimer.apply(c) is None


def test_P6_json_code_fence_declines_on_identity_grader():
    # A fence breaks a byte-exact match by design; json_code_fence must decline on identity graders
    # the way trailing_disclaimer does, so a misdeclared tolerates=('fence',) can't false-flag (pass-6).
    r = run([EvalCase("id", exact_cs('{"a": 1}'), GradeInput(text='{"a": 1}'),
                      tags=("json",), tolerates=("fence",))])
    assert not any(h.operator_id == "json_code_fence" for h in r.brittle_spots)


def test_P6_json_code_fence_still_fires_on_valid_json():
    # The identity gate must NOT block the intended target: valid_json strips fences, so the fence is
    # genuinely correctness-preserving and the operator still exercises it (CAUGHT, not declined).
    r = run([EvalCase("vj", valid_json("a"), GradeInput(text='{"a": 1}'),
                      tags=("json",), tolerates=("fence",))])
    assert any(x.operator_id == "json_code_fence" and x.outcome is Outcome.CAUGHT
               for x in r.results)


# ── cold-critic PASS 7 regressions (uniform decline discipline across operators) ─

def test_P7_whitespace_noise_declines_on_absence_grader():
    # whitespace_noise's added space can itself be a forbidden marker; decline on absence graders
    # symmetric with its siblings (pass-7).
    from gradecore import injection_resistance
    from evalmut.operators import _whitespace_noise
    c = EvalCase("inj", injection_resistance(" "), GradeInput(text="paris"), tolerates=("whitespace",))
    assert _whitespace_noise.apply(c) is None


def test_P7_whitespace_noise_still_fires_on_identity_grader():
    # ...but must NOT over-decline: exact strips whitespace, so the equivalent is genuinely still
    # correct and the operator keeps exercising it (CAUGHT).
    r = run([EvalCase("ok", exact("42"), GradeInput(text="42", expected="42"),
                      tolerates=("whitespace",))])
    assert any(x.operator_id == "whitespace_noise" and x.outcome is Outcome.CAUGHT for x in r.results)


def test_P7_sanity_absence_gate_unconditional_even_with_content_required():
    # content_required=True must NOT override the absence-grader exclusion: a blank/garbage output
    # legitimately leaks nothing, so injection_resistance passing it is correct, not vacuous (pass-7).
    from gradecore import injection_resistance
    r = run([EvalCase("inj", injection_resistance("system prompt", "api key"),
                      GradeInput(text="Sure, here is a friendly greeting."), content_required=True)])
    assert not r.vacuous
    assert not r.blind_spots


def test_P7_trajectory_cross_checks_declared_threshold():
    # A grader whose real threshold (0.5) is LOOSER than the declared one (1.0) correctly accepts a
    # dropped-step partial trajectory; the cross-check probe catches the mismatch and declines (pass-7).
    gi = GradeInput(text="done",
                    tool_calls=({"tool": "plan"}, {"tool": "search"}, {"tool": "answer"}))
    r = run([EvalCase("lenient", trajectory("plan", "search", "answer", threshold=0.5), gi,
                      judges=("tool_calls",), tags=("trajectory",),
                      expected_trajectory=("plan", "search", "answer"), trajectory_threshold=1.0)])
    assert not r.blind_spots


def test_P7_trajectory_still_caught_when_threshold_matches():
    # ...but a correctly-declared strict threshold still fires and the grader catches the dropped step.
    gi = GradeInput(text="done",
                    tool_calls=({"tool": "plan"}, {"tool": "search"}, {"tool": "answer"}))
    r = run([EvalCase("strict", trajectory("plan", "search", "answer", threshold=1.0), gi,
                      judges=("tool_calls",), tags=("trajectory",),
                      expected_trajectory=("plan", "search", "answer"), trajectory_threshold=1.0)])
    assert any(x.operator_id == "trajectory_drop_step" and x.outcome is Outcome.CAUGHT
               for x in r.results)


# ── grader-family declaration hook (run against external graders unmodified) ──

def test_family_hook_fires_family_gated_operator_on_external_grader():
    # A JSON-structure grader with a NOVEL id must declare grader_family='valid_json' to be seen as
    # a JSON grader; then json_value_type_flip (valid_json-gated) fires. Without it, it declines.
    def ext_json(inp):
        import json as _j
        try:
            _j.loads((inp.text or "").strip()); ok = True
        except Exception:
            ok = False
        return Verdict(passed=ok, score=1.0 if ok else 0.0,
                       severity="none" if ok else "med", detail="ext", grader_id="my_json_checker")
    gi = GradeInput(text='{"count": 3}')
    undeclared = run([EvalCase("u", ext_json, gi, tags=("json",))])
    assert not any(h.operator_id == "json_value_type_flip"
                   for h in (undeclared.coverage_gaps + undeclared.blind_spots))
    declared = run([EvalCase("d", ext_json, gi, tags=("json",), grader_family="valid_json")])
    assert any(h.operator_id == "json_value_type_flip" for h in declared.coverage_gaps)


def test_case_variant_flags_case_sensitive_grader():
    # A task that declares casing cosmetic, graded case-SENSITIVELY (exact_cs), is brittle to a case
    # variant of a correct answer — evalmut flags it (mined from promptfoo's case-sensitive contains).
    r = run([EvalCase("cs", exact_cs("Yes"), GradeInput(text="Yes", expected="Yes"),
                      tolerates=("case",))])
    assert any(h.operator_id == "case_variant" for h in r.brittle_spots)


def test_case_variant_held_on_case_insensitive_grader():
    # ...and a case-INSENSITIVE grader (exact lowercases) correctly holds — CAUGHT, not flagged.
    r = run([EvalCase("ci", exact("yes"), GradeInput(text="yes", expected="yes"),
                      tolerates=("case",))])
    assert not any(h.operator_id == "case_variant" for h in r.brittle_spots)
    assert any(x.operator_id == "case_variant" and x.outcome is Outcome.CAUGHT for x in r.results)


def test_case_variant_declines_without_declaration():
    r = run([EvalCase("nd", exact_cs("Yes"), GradeInput(text="Yes", expected="Yes"))])  # no tolerates
    assert not any(h.operator_id == "case_variant" for h in r.brittle_spots)


def test_json_value_corruption_is_coverage_gap_not_blind():
    # A keys-only JSON validator is blind to a WRONG VALUE of the right type — a coverage gap
    # (DIAGNOSTIC), never a blind spot.
    r = run([EvalCase("jc", valid_json("count"), GradeInput(text='{"count": 3}'), tags=("json",))])
    assert any(h.operator_id == "json_value_corruption" for h in r.coverage_gaps)
    assert not any(h.operator_id == "json_value_corruption" for h in r.blind_spots)


def test_json_value_corruption_declines_on_non_json_grader():
    # Gated to the valid_json family: a contains() over JSON must not draw a json coverage gap.
    r = run([EvalCase("t", contains("temperature"),
                      GradeInput(text='{"temperature": 72}', expected="temperature"),
                      tags=("presence_check",))])
    assert not any(h.operator_id == "json_value_corruption"
                   for h in (r.coverage_gaps + r.blind_spots))


def test_family_hook_reported_id_stays_honest():
    # The declared family is for gating only; the finding card still reports the grader's ACTUAL id.
    def ext_json(inp):
        return Verdict(passed=True, score=1.0, severity="none", detail="ext", grader_id="my_json_checker")
    r = run([EvalCase("d", ext_json, GradeInput(text='{"count": 3}'),
                      tags=("json",), grader_family="valid_json")])
    flip = [x for x in r.results if x.operator_id == "json_value_type_flip"][0]
    assert flip.grader_id == "my_json_checker"  # honest reported id, not the declared family


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
