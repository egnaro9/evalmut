"""The Corpus B negative control: proof the harness can still expose a scorer that should fail.

Different question from the witness. The witness proves execution; this proves the pipeline is not
laundering a check that cannot fail. A harness can pass the first and fail the second, with every
call recorded and a comfortable number reported.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evalmut.negative_control import (CONTROL_ID, NegativeControlFailure,  # noqa: E402
                                      evaluate, gated_aggregate, require_in_inventory)
from evalmut.witnessed import WitnessMissing  # noqa: E402

_s = importlib.util.spec_from_file_location("inv", ROOT / "evalmut" / "inventory.py")
I = importlib.util.module_from_spec(_s); sys.modules["inv"] = I; _s.loader.exec_module(I)

EVID = ROOT / "external/corpus_b/runs/probes/witness_evidence/negative_control.json"
CTRL_PATH, CTRL_SYM = "test/cbprobe/broken_scorer.ts", "alwaysPasses"


@pytest.fixture
def row():
    return json.loads(EVID.read_text())


def _inv(include_control=True):
    def sc(path, sym):
        return I.Scorer(suite="promptfoo/promptfoo", revision="96929e8758ca", module_path=path,
                        symbol=sym, discovered_by="static scan")
    real = sc("src/assertions/xml.ts", "validateXml")
    ctrl = sc(CTRL_PATH, CTRL_SYM)
    disc = [real] + ([ctrl] if include_control else [])
    rows = {s.id: I.Row(scorer=s, disposition=I.Disposition.INCLUDED) for s in disc}
    return I.build(disc, rows, suite="promptfoo/promptfoo", revision="96929e8758ca",
                   environment={"arch": "arm64"}, discovery_method="static scan",
                   queries={"drivable": ["included"]}), ctrl.id


# ---------------------------------------------------------------- the five required proofs

def test_the_control_is_in_the_sealed_inventory_not_a_side_experiment():
    inv, cid = _inv()
    require_in_inventory(inv, cid)
    inv_without, _ = _inv(include_control=False)
    with pytest.raises(NegativeControlFailure) as e:
        require_in_inventory(inv_without, cid)
    assert "does not cover the run being reported" in str(e.value)


def test_the_control_carries_real_invocation_evidence(row):
    """Held to the same witness bar as any other row, against the artifact vitest actually wrote."""
    got = evaluate(row)
    assert got["invoked"] is True and got["calls"] == 2
    assert len(row["witness"]["raw_upstream"]) == 2
    assert row["witness"]["target"].endswith("alwaysPasses")


def test_the_expected_failure_is_recorded_honestly_not_as_incomplete(row):
    """SURVIVED is the control succeeding and the scorer failing. Collapsing that into INCOMPLETE
    or an infrastructure error would hide the one thing the control exists to show."""
    got = evaluate(row)
    assert got["expected_state"] == "SURVIVED"
    assert got["discriminated"] is False
    assert "INCOMPLETE" not in json.dumps(got)


def test_a_control_that_discriminates_fails_closed(row):
    """If the broken scorer starts telling clean from defective, either it was repaired or the
    pipeline is running something else. Both mean the harness is not measuring what it claims."""
    r = copy.deepcopy(row)
    r["verdicts"]["defective"] = {"isValid": False, "reason": "suspiciously competent"}
    with pytest.raises(NegativeControlFailure) as e:
        evaluate(r)
    assert "DISCRIMINATED" in str(e.value) and "no result may be published" in str(e.value)


def test_aggregation_refuses_without_control_evidence(row):
    inv, cid = _inv()
    with pytest.raises(NegativeControlFailure) as e:
        gated_aggregate(1, inv, inv.digest, "drivable", None, cid)
    assert "not publishable regardless of how it looks" in str(e.value)


def test_aggregation_refuses_when_the_control_was_never_invoked(row):
    inv, cid = _inv()
    r = copy.deepcopy(row)
    r["witness"].update(invoked=False, calls=0, raw_upstream=[])
    with pytest.raises(WitnessMissing):
        gated_aggregate(1, inv, inv.digest, "drivable", r, cid)


def test_aggregation_refuses_when_the_control_unexpectedly_passes(row):
    inv, cid = _inv()
    r = copy.deepcopy(row)
    r["verdicts"]["defective"] = {"isValid": False}
    with pytest.raises(NegativeControlFailure):
        gated_aggregate(1, inv, inv.digest, "drivable", r, cid)


# ---------------------------------------------------------------- and it works when honest

def test_a_sound_run_aggregates_with_the_control_attached(row):
    inv, cid = _inv()
    out = gated_aggregate(1, inv, inv.digest, "drivable", row, cid)
    assert out["denominator"] == 2 and out["rate"] == 0.5
    assert out["negative_control"]["discriminated"] is False
    assert out["inventory_digest"] == inv.digest


def test_an_unlabelled_control_is_refused(row):
    r = copy.deepcopy(row); r.pop("negative_control")
    with pytest.raises(NegativeControlFailure) as e:
        evaluate(r)
    assert "an unchecked control is decoration" in str(e.value)


def test_a_control_missing_one_side_of_the_pair_is_refused(row):
    r = copy.deepcopy(row); r["verdicts"].pop("defective")
    with pytest.raises(NegativeControlFailure) as e:
        evaluate(r)
    assert "cannot show a failure to discriminate" in str(e.value)
