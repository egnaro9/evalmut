"""`code_sha256` pinned as a SOURCE fingerprint, and shown failing the way it used to.

This field claims to identify the grader implementation. It used to be `sha256(code.co_code)`,
which identifies compiled bytecode on one interpreter instead, and that cost two things:

  1. The committed witness artifact could not verify anywhere but the machine that produced it.
     Generated on CPython 3.14, checked by a 3.11/3.12 matrix, red on every CI run between
     2026-08-21 and 2026-08-30 and green on none.
  2. It could not tell `must_refuse` from `must_abstain`. Both compile to the same instructions
     over different closure constants, so 88 witness sites carried one hash for two graders.

The pinned table below is the cross-version requirement. Every leg of the matrix runs it and
demands the same values, so an interpreter-dependent representation cannot come back quietly:
it fails on the leg that disagrees. The negative cases are the load-bearing ones, as elsewhere
in this suite. A fingerprint that has only ever been seen agreeing is worth nothing.
"""
from __future__ import annotations

import hashlib
import sys

import pytest
from gradecore import adversarial, graders, grounding, trajectory

from evalmut.invocation_witness import _source_fingerprint, identify

# target identity -> source fingerprint. Identical on every supported interpreter.
PINNED = {
    "gradecore.adversarial.injection_resistance.<locals>.g": "ac113765c057bf8f",
    "gradecore.adversarial.must_abstain.<locals>.g": "469a343dd4a61ad9",
    "gradecore.adversarial.must_comply.<locals>.g": "fd45e4718f34424f",
    "gradecore.adversarial.must_refuse.<locals>.g": "c46b0e147b872343",
    "gradecore.adversarial.tool_misuse.<locals>.g": "b5dca106462374fd",
    "gradecore.adversarial.valid_json.<locals>.g": "6313dc85bac2aad3",
    "gradecore.graders.contains.<locals>.g": "e9bea7d63e2d65a7",
    "gradecore.graders.exact.<locals>.g": "403c64b8f0679236",
    "gradecore.graders.exact_cs.<locals>.g": "d9b7b7586ce9eb00",
    "gradecore.graders.number.<locals>.g": "53fbf6ba95758c6a",
    "gradecore.graders.one_of.<locals>.g": "f9a472633927f3e1",
    "gradecore.graders.regex.<locals>.g": "1e9a5cbf0a64e7c3",
    "gradecore.grounding.grounding.<locals>._grounding": "cc9ba04b869d16fc",
    "gradecore.trajectory.trajectory.<locals>.g": "f7c3e163554c0631",
}


def _every_witnessed_grader():
    """One live instance of each grader the dogfood suite witnesses."""
    return [
        graders.exact("x"), graders.exact_cs("x"), graders.contains("x"),
        graders.regex("x"), graders.one_of("x"), graders.number(1.0),
        adversarial.must_refuse(), adversarial.must_abstain(), adversarial.must_comply("x"),
        adversarial.valid_json("x"), adversarial.injection_resistance("x"),
        adversarial.tool_misuse(["x"]),
        grounding(0.6), trajectory("x"),
    ]


@pytest.mark.parametrize("fn", _every_witnessed_grader(),
                         ids=lambda f: identify(f)["identity"])
def test_the_fingerprint_is_the_pinned_value_on_this_interpreter(fn):
    """The cross-version requirement, enforced once per matrix leg.

    Nothing here reads sys.version: the matrix supplies the versions and this asserts they agree.
    A representation that varies by interpreter fails on whichever leg is not the one that
    produced the table, which is exactly how the bytecode hash should have been caught.
    """
    ident = identify(fn)
    assert ident["identity"] in PINNED, f"unpinned grader {ident['identity']}"
    assert ident["code_sha256"] == PINNED[ident["identity"]], (
        f"{ident['identity']} fingerprints {ident['code_sha256']} on "
        f"Python {sys.version_info.major}.{sys.version_info.minor}, pinned "
        f"{PINNED[ident['identity']]}. If this is red on one matrix leg only, the field has "
        f"gone interpreter-dependent again.")


def test_the_pinned_table_covers_every_witnessed_grader():
    """A table that silently stopped covering a grader would pass while checking less."""
    assert {identify(f)["identity"] for f in _every_witnessed_grader()} == set(PINNED)


def test_the_fingerprint_is_not_the_bytecode_hash():
    """The regression that started this. A revert to co_code must go red here, not on CI."""
    g = graders.exact("x")
    bytecode = hashlib.sha256(g.__code__.co_code).hexdigest()[:16]
    assert identify(g)["code_sha256"] != bytecode


def test_it_separates_two_graders_that_share_one_bytecode_hash():
    """must_refuse and must_abstain compiled identically; 88 witness sites claimed one identity."""
    refuse, abstain = adversarial.must_refuse(), adversarial.must_abstain()
    assert (hashlib.sha256(refuse.__code__.co_code).hexdigest()[:16]
            == hashlib.sha256(abstain.__code__.co_code).hexdigest()[:16]), (
        "the bytecode collision this field was changed to fix no longer reproduces; if gradecore "
        "diverged these two, keep the source fingerprint anyway and rewrite this test")
    assert identify(refuse)["code_sha256"] != identify(abstain)["code_sha256"]


def test_different_source_fingerprints_differently():
    """Mutation check: a fingerprint that cannot change cannot identify anything."""
    assert (_source_fingerprint(graders.exact("x").__code__)
            != _source_fingerprint(graders.contains("x").__code__))


def test_the_same_definition_fingerprints_the_same_from_two_instances():
    """Two closures over different constants are the same DEFINITION and must agree."""
    assert (_source_fingerprint(graders.exact("one").__code__)
            == _source_fingerprint(graders.exact("two").__code__))


def test_line_endings_do_not_change_the_fingerprint(monkeypatch):
    """A checkout with CRLF must fingerprint identically to one with LF."""
    import evalmut.invocation_witness as iw
    src = "def g():\n    return 1\n"
    code = graders.exact("x").__code__
    monkeypatch.setattr(iw.inspect, "getsource", lambda c: src)
    lf = _source_fingerprint(code)
    monkeypatch.setattr(iw.inspect, "getsource", lambda c: src.replace("\n", "\r\n"))
    crlf = _source_fingerprint(code)
    monkeypatch.setattr(iw.inspect, "getsource", lambda c: src.replace("\n", "\r"))
    cr = _source_fingerprint(code)
    assert lf == crlf == cr


def test_unresolvable_source_is_none_and_not_a_shared_constant():
    """None is honest about not knowing. Two unknowns must not thereby claim one identity."""
    ns: dict = {}
    exec(compile("def a(): return 1\ndef b(): return 2", "<no-such-file>", "exec"), ns)
    assert _source_fingerprint(ns["a"].__code__) is None
    assert _source_fingerprint(ns["b"].__code__) is None
    assert identify(ns["a"])["code_sha256"] is None


def test_no_code_object_is_none():
    assert _source_fingerprint(None) is None
