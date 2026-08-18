"""Adversarial tests for the review protocol's validator.

The scarce input is a reviewer's judgement, and the failure mode is not a malformed file: it is a
well-formed file that agrees with everything and would then be counted as independent
classification. So the load-bearing test here is the rubber-stamp one.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "external" / "corpus_b"
REVIEW = ROOT / "review"
_spec = importlib.util.spec_from_file_location("cbvalidate", REVIEW / "validate_response.py")
V = importlib.util.module_from_spec(_spec)
sys.modules["cbvalidate"] = V
_spec.loader.exec_module(V)

KNOWN = {c["id"] for c in json.loads((ROOT / "MANIFEST.json").read_text())["cards"]}
LONG = ("the check's contract covers whole-document validity, and a recovering parser cannot "
        "establish it, so the shape is real")


def sub(**kw):
    d = {"reviewer": "R", "affiliation": "Uni", "received_at": "2026-09-01", "classifications": []}
    d.update(kw)
    return d


def row(cid="CB-001", label="invalid", rationale=LONG, **kw):
    d = {"card_id": cid, "label": label, "named_semantic": "is-xml whole-document validity",
         "rationale": rationale}
    d.update(kw)
    return d


# ---------------------------------------------------------------- substance, not just shape

def test_a_rubber_stamp_is_refused():
    """Twelve one-word approvals are a signature, not a review."""
    rows = [row(cid=c, label="valid", rationale="looks fine to me, seems right") for c in
            sorted(KNOWN)]
    with pytest.raises(V.ReviewRejected) as e:
        V.validate(sub(classifications=rows), KNOWN)
    assert "rubber stamp" in str(e.value)


def test_genuine_unanimity_with_real_reasoning_is_accepted():
    """The check must not punish a reviewer who honestly finds every card valid. Uniform approval
    is not suspect; uniform approval with no reasoning is."""
    rows = [row(cid=c, label="valid", rationale=LONG + " " + LONG) for c in sorted(KNOWN)]
    assert len(V.validate(sub(classifications=rows), KNOWN)) == len(KNOWN)


def test_a_thin_rationale_is_refused():
    with pytest.raises(V.ReviewRejected) as e:
        V.validate(sub(classifications=[row(rationale="no")]), KNOWN)
    assert "minimum" in str(e.value)


def test_named_semantic_is_required_even_for_valid():
    r = row(label="valid", rationale=LONG)
    r["named_semantic"] = ""
    with pytest.raises(V.ReviewRejected) as e:
        V.validate(sub(classifications=[r]), KNOWN)
    assert "named_semantic is required" in str(e.value)


def test_disputing_the_authors_call_requires_a_reason():
    with pytest.raises(V.ReviewRejected) as e:
        V.validate(sub(classifications=[row(disputes_author_applicability=True)]), KNOWN)
    assert "without saying why" in str(e.value)


# ---------------------------------------------------------------- the four labels are equal

@pytest.mark.parametrize("label", ["valid", "invalid", "unclear", "scope-dependent"])
def test_all_four_labels_pass_with_equal_ease(label):
    """A protocol that makes 'invalid' harder to submit than 'valid' collects agreement."""
    assert V.validate(sub(classifications=[row(label=label)]), KNOWN) == ["CB-001"]


def test_an_unknown_card_id_is_refused():
    with pytest.raises(V.ReviewRejected) as e:
        V.validate(sub(classifications=[row(cid="CB-999")]), KNOWN)
    assert "not a card in the frozen manifest" in str(e.value)


def test_duplicate_cards_from_one_reviewer_are_refused():
    with pytest.raises(V.ReviewRejected):
        V.validate(sub(classifications=[row(), row()]), KNOWN)


def test_every_problem_is_reported_not_just_the_first():
    """Handing a reviewer one error at a time is how a protocol burns its own goodwill."""
    bad = sub(reviewer="", classifications=[row(cid="CB-999", rationale="x")])
    with pytest.raises(V.ReviewRejected) as e:
        V.validate(bad, KNOWN)
    msg = str(e.value)
    assert "missing reviewer" in msg and "not a card" in msg and "minimum" in msg


def test_a_decline_is_a_valid_submission():
    """REFUSED is a recorded outcome, not a failure to process."""
    assert V.validate(sub(declined=True), KNOWN) == []


# ---------------------------------------------------------------- independence is checked

def test_the_known_coauthorship_conflict_is_caught():
    a = sub(reviewer="Alex Groce", affiliation="NAU", coauthors_with=["Rahul Gopinath"])
    b = sub(reviewer="Rahul Gopinath", affiliation="Elsewhere")
    ok, why = V.independent(a, b)
    assert not ok and "co-author" in why


def test_shared_affiliation_is_not_independent():
    ok, why = V.independent(sub(reviewer="A", affiliation="Same U"),
                            sub(reviewer="B", affiliation="Same U"))
    assert not ok and "affiliation" in why


def test_two_unrelated_reviewers_are_independent():
    ok, _ = V.independent(sub(reviewer="A", affiliation="X"), sub(reviewer="B", affiliation="Y"))
    assert ok


# ---------------------------------------------------------------- the protocol says the hard parts

def _prose():
    return " ".join((REVIEW / "PROTOCOL.md").read_text().split())


def test_the_protocol_states_the_rules_that_are_easy_to_drop_later():
    doc = _prose()
    assert "Silence is a recorded state, never an approval" in doc
    assert "The card is not edited to reconcile them" in doc
    assert "No tiebreaker is sought to produce a majority" in doc
    assert "Both rationales are preserved verbatim" in doc
    assert "Gopinath is a co-author" in doc
    assert "Two-per-card is unreachable" in doc


def test_the_stamp_check_needs_enough_rows_to_mean_anything():
    """It fired on a single legitimate 'valid' row in draft. A check that punishes a small honest
    submission is one a reviewer learns to route around."""
    two = [row(cid="CB-001", label="valid"), row(cid="CB-002", label="valid")]
    assert len(V.validate(sub(classifications=two), KNOWN)) == 2
    three = two + [row(cid="CB-003", label="valid")]
    with pytest.raises(V.ReviewRejected) as e:
        V.validate(sub(classifications=three), KNOWN)
    assert "rubber stamp" in str(e.value)
