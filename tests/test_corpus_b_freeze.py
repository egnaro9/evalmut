"""The frozen card set is a claim that nothing changed after execution, so it is checked.

A freeze whose only enforcement is a filename is not a freeze. These tests recompute every card's
digest from its bytes and require the manifest to agree, so editing a card after a run turns the
suite red rather than silently rewriting history.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "external" / "corpus_b"
MANIFEST = ROOT / "MANIFEST.json"
needs_freeze = pytest.mark.skipif(not MANIFEST.exists(), reason="cards not frozen on this machine")


@pytest.fixture
def manifest():
    return json.loads(MANIFEST.read_text())


@needs_freeze
def test_every_card_matches_its_frozen_digest(manifest):
    """The assertion the freeze exists for: a card edited after the fact is caught."""
    for e in manifest["cards"]:
        raw = (ROOT / e["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e["sha256"], (
            f"{e['id']} has changed since it was frozen. A card edited after a run describes the "
            "result instead of predicting it, which is the whole thing the freeze prevents.")
        assert len(raw) == e["bytes"]


@needs_freeze
def test_no_card_is_missing_and_none_is_unlisted(manifest):
    """Adding a card after a run is the same defect as editing one, in the other direction."""
    listed = {e["file"] for e in manifest["cards"]}
    onDisk = {f"cards/{p.name}" for p in (ROOT / "cards").glob("*.json")}
    assert listed == onDisk, f"manifest and directory disagree: {listed ^ onDisk}"


@needs_freeze
def test_the_set_is_externally_sourced(manifest):
    """The Corpus A contamination check, kept as a gate rather than a memory of having looked."""
    assert manifest["authored_by_egnaro9"] == 0
    for e in manifest["cards"]:
        card = json.loads((ROOT / e["file"]).read_text())
        assert card["source"]["authored_by_egnaro9"] is False
        assert card["source"]["url"].startswith("https://github.com/promptfoo/promptfoo/pull/")
        assert len(card["source"]["merge_commit"]) >= 12


@needs_freeze
def test_every_card_carries_all_seven_required_fields(manifest):
    for e in manifest["cards"]:
        c = json.loads((ROOT / e["file"]).read_text())
        for f in ("source", "semantic", "applicability_predicate", "not_applicable_cases",
                  "pair", "counterexample", "risks"):
            assert c.get(f), f"{e['id']} is missing {f}"
        for f in ("clean_input", "defective_transformation", "expected_on_clean",
                  "expected_on_defective"):
            assert c["pair"].get(f), f"{e['id']} pair is missing {f}"
        assert c["risks"]["false_positive"] and c["risks"]["false_negative"]


@needs_freeze
def test_non_applicable_cards_are_kept_and_say_why(manifest):
    """Dropping them would produce a tidier set and a false impression of reach.

    Four externally sourced, merged defects are outside what this tool can validly express: three
    because a verdict-based tester cannot see them at all, and one because reaching it would mean
    mutating an assertion parameter rather than a model output. That is a fact about the tool, and
    the corpus is where it belongs."""
    kept = [e for e in manifest["cards"] if not e["applicable"]]
    assert len(kept) == 4
    for e in kept:
        c = json.loads((ROOT / e["file"]).read_text())
        assert c["applicable_to_evalmut"] is False
        assert len(c["not_applicable_cases"]) >= 2
        assert c["maps_to_existing_operator"].startswith("none")


@needs_freeze
def test_the_manifest_binds_provenance_per_entry_not_only_a_digest(manifest):
    """An auditor should not have to open twelve files to ask "is any of this self-authored"."""
    for e in manifest["cards"]:
        for f in ("source_url", "pr", "merge_commit", "author", "authored_by_egnaro9",
                  "applicable", "verdict_class", "sha256"):
            assert f in e, f"{e['id']} manifest entry is missing {f}"
        assert e["authored_by_egnaro9"] is False
        card = json.loads((ROOT / e["file"]).read_text())
        assert card["source"]["merge_commit"] == e["merge_commit"]
        assert card["source"]["url"] == e["source_url"]
        assert card["applicable_to_evalmut"] == e["applicable"]


@needs_freeze
def test_no_card_claims_applicability_its_own_body_denies(manifest):
    """CB-008 shipped a draft with applicable=True while its maps_to said the shape was outside
    the mutation surface. A flag that disagrees with its own card is how an applicable count grows
    without any new reach."""
    for e in manifest["cards"]:
        c = json.loads((ROOT / e["file"]).read_text())
        if c["maps_to_existing_operator"].startswith("none") and "outside" in \
                c["maps_to_existing_operator"]:
            assert c["applicable_to_evalmut"] is False, (
                f"{e['id']} claims applicability while its own maps_to says otherwise")


@needs_freeze
def test_the_label_never_claims_validation(manifest):
    """A frozen, externally sourced set is still a set of hypotheses."""
    assert "CANDIDATE" in manifest["label"]
    assert "NOT\nindependently reviewed" in manifest["label"] or \
           "NOT independently reviewed" in manifest["label"]
    assert manifest["review"]["independent_classifications_received"] == 0
    assert manifest["review"]["independent_engineers_required"] == 2
    for e in manifest["cards"]:
        c = json.loads((ROOT / e["file"]).read_text())
        assert c["status"].startswith("CANDIDATE")
