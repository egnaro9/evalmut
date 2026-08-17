"""Adversarial tests for the holdout protocol itself.

The protocol is a claim about what cannot happen, so it is tested by trying to make those things
happen: leak the holdout, change it after sealing, and blur when a revision landed. A protocol
whose failure modes are only described in prose is a protocol nobody has checked.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Loaded directly rather than through the package: sealing must not depend on the runtime deps of
# a suite it is supposed to outlive, and a protocol you cannot verify without installing gradecore
# is a protocol an outside auditor cannot verify at all.
_spec = importlib.util.spec_from_file_location("evalmut_holdout", ROOT / "evalmut" / "holdout.py")
H = importlib.util.module_from_spec(_spec)
sys.modules["evalmut_holdout"] = H
_spec.loader.exec_module(H)

COMMITMENT = ROOT / "holdout" / "commitment-001.json"
SALT_FILE = pathlib.Path.home() / ".evalmut-holdout" / "salt-001.txt"
has_salt = pytest.mark.skipif(not SALT_FILE.exists(),
                              reason="salt is held outside the repo and not on this machine")


@pytest.fixture
def commitment():
    return H.Commitment.from_json(COMMITMENT.read_text())


# ---------------------------------------------------------------- the seal binds

@has_salt
def test_the_sealed_rule_still_verifies(commitment):
    salt = SALT_FILE.read_text().strip()
    H.verify(commitment, commitment.public_rule, salt)


@has_salt
def test_a_post_hoc_change_to_the_payload_is_caught(commitment):
    """The property the seal exists for. Loosening the predicate after seeing the reveal is the
    move this must make impossible to do quietly."""
    salt = SALT_FILE.read_text().strip()
    tampered = json.loads(json.dumps(commitment.public_rule))
    tampered["predicate"].append("or an LLM-judge defect, if that would help")
    with pytest.raises(H.HoldoutError) as e:
        H.verify(commitment, tampered, salt)
    assert "does not match its commitment" in str(e.value)
    assert "discarded rather than re-sealed" in str(e.value)


@has_salt
def test_moving_the_cutoff_later_is_caught(commitment):
    """Sliding the cutoff forward would let already-known reports into a 'future' holdout."""
    salt = SALT_FILE.read_text().strip()
    tampered = json.loads(json.dumps(commitment.public_rule))
    tampered["cutoff_utc"] = "2026-09-30T00:00:00Z"
    with pytest.raises(H.HoldoutError):
        H.verify(commitment, tampered, salt)


@has_salt
def test_reformatting_the_payload_does_not_change_the_seal(commitment):
    """Canonicalisation, from the other side: a key reorder is the same holdout, and must verify.

    Without this the protocol would produce false violations, and a check that cries wolf gets
    switched off, which is a slower way to have no check."""
    salt = SALT_FILE.read_text().strip()
    reordered = dict(reversed(list(commitment.public_rule.items())))
    H.verify(commitment, reordered, salt)


def test_a_wrong_salt_does_not_verify(commitment):
    with pytest.raises(H.HoldoutError):
        H.verify(commitment, commitment.public_rule, "f" * 64)


def test_an_unsalted_commitment_is_refused():
    """The arithmetic in the protocol doc, enforced. A short salt over a small candidate space is
    invertible by enumeration, so the digest would protect nothing."""
    for bad in ("", "short", "a" * 31):
        with pytest.raises(H.HoldoutError) as e:
            H.digest({"x": 1}, bad)
        assert "enumerate" in str(e.value)


# ---------------------------------------------------------------- the seal does not leak

def test_the_commitment_file_carries_no_secret():
    """A commitment that contains its own payload's secret half is not a commitment.

    Checked by SHAPE, not by the word "salt": the file legitimately describes the salt in its
    algorithm block, and a word-match would either fail on that description or, worse, be relaxed
    until it stopped looking for the thing that matters. A 64-hex token is what would actually
    leak, and the digest is the only one allowed to appear."""
    text = COMMITMENT.read_text()
    d = json.loads(text)
    tokens = set(re.findall(r"\b[0-9a-f]{64}\b", text))
    assert tokens <= {d["sha256"]}, f"a 64-hex secret-shaped token leaked: {tokens - {d['sha256']}}"
    assert set(d) <= {"version", "instance", "kind", "sha256", "sealed_at", "sealed_at_commit",
                      "hiding", "reveal_after", "revision_boundary", "rotation",
                      "payload_location", "algorithm", "public_rule"}


@has_salt
def test_the_salt_has_not_leaked_into_the_repository():
    """The likeliest real failure, and it needs no malice: a paste into a note or a test name."""
    salt = SALT_FILE.read_text().strip()
    hits = H.scan_for_disclosure(ROOT, [salt])
    assert hits == [], f"the salt appears in {hits}"


def test_the_salt_is_stored_outside_the_repository():
    """A secret inside the tree is one `git add -A` from publication."""
    c = H.Commitment.from_json(COMMITMENT.read_text())
    if c.kind == H.KIND_SET:
        assert ROOT not in pathlib.Path(c.payload_location).resolve().parents
    assert not (ROOT / "holdout" / "salt-001.txt").exists()


def test_disclosure_scanner_actually_finds_a_planted_secret(tmp_path):
    """Prove the scanner can fire before trusting it to say a tree is clean.

    A scanner that has never been seen catching anything is indistinguishable from one that
    cannot, which this estate has now paid for twice."""
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "scratch.md").write_text("reminder: holdout is deadbeefcafe\n")
    (tmp_path / "clean.txt").write_text("nothing here\n")
    hits = H.scan_for_disclosure(tmp_path, ["deadbeefcafe"])
    assert hits == [("notes/scratch.md", "deadbeefcafe")]


# ---------------------------------------------------------------- the timing is not ambiguous

def test_the_seal_commit_is_an_ancestor_of_head(commitment):
    """A commitment anchored to an unreachable commit proves nothing about what came first, which
    is the entire point of sealing."""
    assert H.seal_precedes_revisions(ROOT, commitment.sealed_at_commit), (
        "the seal commit is not reachable from HEAD, so the ordering claim is unverifiable")


def test_an_unreachable_anchor_is_reported_as_such():
    """The negative case, so the ancestor check is known to discriminate rather than always
    returning True."""
    assert not H.seal_precedes_revisions(ROOT, "0" * 40)


def test_revisions_since_the_seal_are_countable(commitment):
    """The revision boundary must be a list, not a recollection. This asserts the mechanism
    answers, not that the answer is any particular number: the count legitimately grows."""
    revs = H.revisions_since(ROOT, commitment.sealed_at_commit,
                             ("evalmut/operators.py", "evalmut/operator.py", "evalmut/case.py",
                              "demos/", "external/"))
    assert isinstance(revs, list)


def test_the_boundary_paths_in_the_doc_match_the_ones_a_check_would_use():
    """Prose and mechanism drift apart silently. Every path the protocol names must exist, or the
    boundary is partly fictional."""
    doc = _prose()
    for p in ("evalmut/operators.py", "evalmut/operator.py", "evalmut/case.py", "demos/",
              "external/"):
        assert p in doc, f"{p} is used as a boundary but is not named in the protocol"
        assert (ROOT / p).exists(), f"{p} is named as a boundary but does not exist"


# ---------------------------------------------------------------- the claims stay honest

def test_a_self_held_seal_never_claims_to_be_hiding(commitment):
    """The distinction the whole document turns on. A seal held by the party revising the suite is
    binding and not hiding, and the artifact has to say which it is."""
    assert commitment.hiding, "every commitment must name who the value is hidden from"
    if commitment.kind == H.KIND_SET:
        assert commitment.hiding == "nobody", (
            "a sealed set held by the author is not hidden from the author, and recording "
            "otherwise would be the unsupported claim this project exists to refuse")


def _prose() -> str:
    """The protocol with its line wrapping removed.

    Asserting on raw text made a sentence's meaning depend on where it happened to wrap, which is
    how a true statement fails a check and gets "fixed" by weakening the check."""
    return " ".join((ROOT / "HOLDOUT_PROTOCOL.md").read_text().split())


def test_the_protocol_states_that_failed_transfer_is_not_proof_of_cheating():
    doc = _prose()
    assert "not proof of cheating" in doc
    assert "may be overfit" in doc


def test_the_protocol_forbids_score_language():
    doc = _prose()
    assert "transfer diagnostic" in doc
    assert "not a certification" in doc


def test_the_rule_instance_fixes_its_count_and_ordering_in_advance(commitment):
    """Discretion at reveal is how a holdout becomes a selection of convenient results."""
    if commitment.kind != H.KIND_RULE:
        pytest.skip("not a rule instance")
    r = commitment.public_rule
    assert "No discretion is exercised at reveal" in r["selection"]
    assert "cutoff_utc" in r and r["cutoff_utc"].endswith("Z")
    assert "if_fewer_than_5_at_reveal" in r, (
        "a rule with no stated behaviour for an underpowered reveal invites extending the window "
        "until the number looks better")


# ---------------------------------------------------------------- an outsider can recompute it

def test_the_commitment_records_how_to_recompute_its_own_digest(commitment):
    """The seal must be checkable by someone who has the JSON and nothing else."""
    a = commitment.algorithm
    assert a["hash"] == "sha256"
    assert "salt" in a["input"] and "canonical_json" in a["input"]
    assert "sort_keys=True" in a["canonical_json"]
    assert "64 characters" in a["salt"]


@has_salt
def test_an_outsider_reimplementation_reproduces_the_seal(commitment):
    """Recompute the digest from the PUBLISHED recipe, without calling holdout.digest().

    This is the auditor's path. Verifying with the same function that sealed proves only that the
    function agrees with itself, which is the failure shape this repository keeps finding."""
    import hashlib as _h
    import json as _j
    salt = SALT_FILE.read_text().strip()
    canon = _j.dumps(commitment.public_rule, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    got = _h.sha256(salt.encode("utf-8") + b"\x00" + canon).hexdigest()
    assert got == commitment.sha256


def test_a_commitment_without_its_recipe_is_refused(commitment):
    d = json.loads(COMMITMENT.read_text())
    d.pop("algorithm")
    with pytest.raises(H.HoldoutError) as e:
        H.Commitment.from_json(json.dumps(d))
    assert "how its digest is computed" in str(e.value)


def test_an_unrecognised_field_is_refused(commitment):
    """A commitment is append-only; a stray field is either a protocol change or a smuggled note."""
    d = json.loads(COMMITMENT.read_text())
    d["note_to_self"] = "the answer is 4"
    with pytest.raises(H.HoldoutError) as e:
        H.Commitment.from_json(json.dumps(d))
    assert "unrecognised fields" in str(e.value)


# ---------------------------------------------------------------- the 001 defect cannot recur

_RULE = {"cutoff_utc": "2026-12-01T00:00:00Z", "predicate": ["x"]}
_ARGS = dict(instance="test", kind=None, sealed_at="2026-08-17", sealed_at_commit="abc123",
             hiding="everyone", reveal_after="2027-01-01", revision_boundary="paths",
             rotation="next", payload_location="n/a")


def test_a_rule_with_a_past_cutoff_is_refused():
    """Instance 001's defect, turned into a gate.

    Its cutoff sat sixteen minutes before the seal, which opened a retroactive window and reduced
    the hiding claim from a property of construction to an empirical check. Nothing was filed in
    the window, but the next instance must not inherit the shape."""
    with pytest.raises(H.HoldoutError) as e:
        H.seal({"cutoff_utc": "2026-08-17T23:00:00Z"}, **{**_ARGS, "kind": H.KIND_RULE},
               now_utc="2026-08-17T23:16:23Z")
    assert "not strictly after the sealing moment" in str(e.value)


def test_a_rule_sealed_without_a_checked_now_is_refused():
    with pytest.raises(H.HoldoutError) as e:
        H.seal(_RULE, **{**_ARGS, "kind": H.KIND_RULE})
    assert "nobody verified" in str(e.value)


def test_a_rule_with_no_cutoff_is_refused():
    with pytest.raises(H.HoldoutError) as e:
        H.seal({"predicate": ["x"]}, **{**_ARGS, "kind": H.KIND_RULE},
               now_utc="2026-08-17T23:16:23Z")
    assert "must state a cutoff_utc" in str(e.value)


def test_a_future_cutoff_seals_normally():
    c, salt = H.seal(_RULE, **{**_ARGS, "kind": H.KIND_RULE}, now_utc="2026-08-17T23:16:23Z")
    H.verify(c, _RULE, salt)


def test_notes_record_the_discarded_draft_and_the_cutoff_defect():
    """The audit trail is part of the artifact, not a courtesy.

    Each assertion is one statement a reader needs in order to size the limitation themselves
    rather than take the summary's word for it."""
    notes = " ".join((ROOT / "holdout" / "NOTES-001.md").read_text().split())
    assert "bdc664ef" in notes and "7ff8b5ed" in notes
    assert "no eligible candidate selected" in notes
    assert "16-minute retroactive window" in notes
    assert "not guaranteed by construction" in notes
    assert "empirical observation, not a retroactive construction guarantee" in notes
    assert "byte-identical to its state at `70d9d57`" in notes
    assert "There is no third digest" in notes
    assert "requires a checked `now_utc`" in notes
    assert "strictly later than that instant" in notes
