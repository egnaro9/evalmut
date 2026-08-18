"""The row this must reject looks completely healthy.

A card id, a clean verdict, a defective verdict, no errors, and no proof anything upstream ran.
That is indistinguishable from a row the harness answered for itself, and it is the shape this
estate has twice shipped as a passing gate.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from evalmut.witnessed import (WitnessInconsistent, WitnessMissing,  # noqa: E402
                               check_bundle, check_row)

EV = pathlib.Path(__file__).resolve().parents[1] / "external/corpus_b/runs/probes/witness_evidence"
REAL, FAKE = EV / "invoked.json", EV / "never_invoked.json"
GOOD = {
    "card_id": "CB-001",
    "verdicts": {"clean": {"isValid": True}, "defective": {"isValid": True}},
    "witness": {"target": "src/assertions/xml.ts:validateXml", "invoked": True, "calls": 2,
                "raw_upstream": [{"isValid": True}, {"isValid": True}]},
}


def test_a_healthy_looking_row_with_no_witness_is_refused():
    bare = {"card_id": "CB-001", "verdicts": GOOD["verdicts"]}
    with pytest.raises(WitnessMissing) as e:
        check_row(bare)
    assert "cannot be told apart from one the harness produced itself" in str(e.value)


def test_a_witness_that_reports_no_invocation_is_refused():
    r = copy.deepcopy(GOOD)
    r["witness"].update(invoked=False, calls=0, raw_upstream=[])
    with pytest.raises(WitnessMissing) as e:
        check_row(r)
    assert "never invoked" in str(e.value)


def test_calls_and_raw_values_must_agree():
    """Either the count or the capture is wrong, and the row must not be interpreted either way."""
    r = copy.deepcopy(GOOD)
    r["witness"]["raw_upstream"] = [{"isValid": True}]
    with pytest.raises(WitnessInconsistent) as e:
        check_row(r)
    assert "One of" in str(e.value)


def test_a_probe_that_made_fewer_calls_than_declared_is_caught():
    """Reaching less of the scorer than claimed is a different fact from a failing verdict."""
    with pytest.raises(WitnessInconsistent) as e:
        check_row(GOOD, expect_calls=3)
    assert "did not exercise what it said it would" in str(e.value)


def test_raw_upstream_is_required_even_when_the_verdict_is_present():
    r = copy.deepcopy(GOOD)
    del r["witness"]["raw_upstream"]
    with pytest.raises(WitnessInconsistent) as e:
        check_row(r)
    assert "missing" in str(e.value)


def test_a_bundle_is_all_witnessed_or_it_fails():
    """Mixing witnessed and bare rows invites averaging across two kinds of claim."""
    bare = {"card_id": "CB-002", "verdicts": {}}
    with pytest.raises(WitnessMissing) as e:
        check_bundle([GOOD, bare])
    assert "1 of 2 row(s) are not witnessed" in str(e.value)


def test_a_fully_witnessed_bundle_passes():
    assert check_bundle([GOOD, {**GOOD, "card_id": "CB-002"}]) == {"rows": 2, "witnessed": 2}


@pytest.mark.skipif(not REAL.exists(), reason="live witness artifact not on this machine")
def test_the_real_promptfoo_observation_carries_a_usable_witness():
    """Not a fixture. This is the artifact the vitest probe wrote while calling promptfoo's own
    validateXml, so the checker is exercised against the shape it will actually meet."""
    row = {"card_id": "CB-001", **json.loads(REAL.read_text())}
    w = check_row(row, expect_calls=2)
    assert w["target"].endswith("validateXml")
    assert w["invoked"] is True and w["calls"] == 2
    assert len(w["raw_upstream"]) == 2


@pytest.mark.skipif(not FAKE.exists(), reason="live witness artifact not on this machine")
def test_the_recorded_bypass_is_refused():
    """The liveness proof, committed rather than described.

    A vitest probe fabricated a passing verdict without calling promptfoo's validateXml at all.
    The witness recorded zero invocations and this refuses the row. A witness never seen reporting
    absence is indistinguishable from one that cannot."""
    row = {"card_id": "CB-001-FABRICATED", **json.loads(FAKE.read_text())}
    assert row["verdicts"]["clean"]["isValid"] is True, "the fabricated verdict looks healthy"
    with pytest.raises(WitnessMissing) as e:
        check_row(row)
    assert "never invoked" in str(e.value)
