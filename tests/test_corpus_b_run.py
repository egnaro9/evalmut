"""The run bundle is a set of claims about what was observed, so it is bound like one.

The bundle's value is that it cannot drift from the frozen cards it reports on. These tests bind
it to the freeze commit, the manifest digest, and each card's hash, and they keep CB-003's
falsification immutable: a prospectively frozen prediction that turned out wrong is the most
informative row in the file and the easiest one to quietly tidy.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "external" / "corpus_b"
RUN = ROOT / "runs" / "run-001.json"
MANIFEST = ROOT / "MANIFEST.json"
needs_run = pytest.mark.skipif(not RUN.exists(), reason="run bundle not present")


@pytest.fixture
def run():
    return json.loads(RUN.read_text())


@needs_run
def test_the_run_is_bound_to_the_freeze_it_reports_on(run):
    m = json.loads(MANIFEST.read_text())
    assert run["freeze_commit"] == "f1c97f3"
    assert run["manifest_sha256"] == \
        "c29928383f0c086b2716ea9a19c92cff4fa94f368081385290b5c174acf596fc"
    by_id = {e["id"]: e for e in m["cards"]}
    for r in run["results"]:
        assert r["card_sha256"] == by_id[r["card_id"]]["sha256"], (
            f"{r['card_id']} reports a hash that is not the frozen one")
        assert r["source_url"] == by_id[r["card_id"]]["source_url"]


@needs_run
def test_every_applicable_card_is_accounted_for(run):
    m = json.loads(MANIFEST.read_text())
    applicable = {e["id"] for e in m["cards"] if e["applicable"]}
    assert set(run["executed_card_ids"]) == applicable
    assert set(run["excluded_card_ids"]) == {e["id"] for e in m["cards"] if not e["applicable"]}
    for cid, why in run["excluded_card_ids"].items():
        assert len(why) > 30, f"{cid} is excluded without a usable predicate"


@needs_run
def test_states_use_the_four_state_vocabulary_and_do_not_collapse(run):
    """INCOMPLETE must stay separate from a negative finding. Two cards did not execute for named
    harness and structural reasons, and folding those into failures would report a capability
    conclusion nobody measured."""
    allowed = {"VERIFIED", "SURVIVED", "INCOMPLETE", "INVALIDATED"}
    for r in run["results"]:
        assert r["status"] in allowed
        assert len(r["status_reason"]) > 40
    counts = run["state_counts"]
    assert set(counts) == allowed
    assert counts["INCOMPLETE"] == 2
    for r in run["results"]:
        if r["status"] == "INCOMPLETE":
            assert r["raw_pre_fix"] is None or "_error" in str(r["raw_pre_fix"]) or \
                r["not_probed_reason"], f"{r['card_id']} claims INCOMPLETE with no named cause"


@needs_run
def test_every_verified_row_carries_a_post_fix_control(run):
    """A probe returning the same thing on both sides measured nothing. Three did exactly that in
    draft, and two of those were harness bugs that would have shipped as silent nulls."""
    for r in run["results"]:
        if r["status"] != "VERIFIED":
            continue
        pre, post = r["raw_pre_fix"], r["raw_post_fix"]
        assert pre and post, f"{r['card_id']} is VERIFIED without both sides recorded"
        assert pre.get("defective") != post.get("defective"), (
            f"{r['card_id']} is VERIFIED but its defective case is identical pre and post fix, "
            "so the probe did not discriminate")


@needs_run
def test_the_cb003_falsification_is_recorded_and_not_reconciled(run):
    """The freeze exists so a wrong prediction stays visible. This is that row."""
    row = next(r for r in run["results"] if r["card_id"] == "CB-003")
    assert "card_prediction_falsified" in row
    assert "expected_on_clean" in row["card_prediction_falsified"]
    assert "0.83" in row["card_prediction_falsified"]
    card = json.loads((ROOT / "cards" / "CB-003.json").read_text())
    assert "score at the reference level" in card["pair"]["expected_on_clean"].lower(), (
        "CB-003's original frozen prediction must not be edited. A revised card gets a new id "
        "that references this one.")


@needs_run
def test_the_bundle_never_claims_detection_power(run):
    """No evalmut operator ran in this pass, and the label must not imply one did."""
    assert "candidate run" in run["label"].lower()
    assert "does NOT establish that evalmut detects" in run["what_this_run_establishes"]
    assert run["review"]["independent_classifications_received"] == 0
    # Scanned over the ASSERTIVE fields only. A first draft scanned the whole document and fired
    # on the bundle's own disclaimer, which says the word "ranking" precisely to rule one out. A
    # check that cannot tell a claim from its denial would be relaxed until it stopped looking.
    assertive = json.dumps({
        "label": run["label"],
        "results": [{k: v for k, v in r.items() if k != "status_reason"} for r in run["results"]],
        "state_counts": run["state_counts"],
    }).lower()
    for banned in ("detection rate", "mutation score", "ranking", "leaderboard", "percentile rank"):
        assert banned not in assertive, f"the bundle asserts score language: {banned!r}"
    # and the disclaimer must still be present rather than merely absent of banned words
    joined = " ".join(run["what_this_run_does_not_establish"]).lower()
    assert "no percentage" in joined and "detection power" in joined
