"""The weekly grader-drift tripwire.

evalmut is deterministic, so the emitter's whole job is to say nothing until
something underneath it moves. Each test below pins a way it could fail at
exactly that: firing when nothing changed, staying silent when something did,
or reporting a broken run as a finding about someone else's code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notes"))
import emit_findings as emit  # noqa: E402


TARGET = {"key": "promptfoo", "suite": "external/promptfoo_suite.py",
          "label": "promptfoo's deterministic assertions"}


def _result(holes, score=0.53):
    return {"score": score, "holes": holes}


def _h(case, grader, op):
    return {"case_name": case, "grader_id": grader, "operator_id": op}


# ── silence when nothing moved ────────────────────────────────────────────

def test_an_identical_run_produces_no_finding():
    r = _result({"blind": [_h("a", "pf_contains", "negate")]})
    assert emit.compare(TARGET, r, r) is None


def test_reordered_holes_are_still_no_finding():
    """Order is not identity. A run that reports the same holes in a different
    order has not drifted, and saying it has would fire every week forever."""
    a = _result({"blind": [_h("a", "g1", "o1"), _h("b", "g2", "o2")]})
    b = _result({"blind": [_h("b", "g2", "o2"), _h("a", "g1", "o1")]})
    assert emit.compare(TARGET, a, b) is None


# ── speech when it did ────────────────────────────────────────────────────

def test_a_newly_opened_hole_is_a_finding():
    was = _result({"blind": [_h("a", "g1", "o1")]})
    now = _result({"blind": [_h("a", "g1", "o1"), _h("b", "g2", "o2")]})
    f = emit.compare(TARGET, was, now)
    assert f and "new hole" in f["headline"]
    assert any("g2" in row["how"] for row in f["evidence"])


def test_a_closed_hole_is_also_a_finding():
    """A grader that got STRICTER is news too. An emitter that only reports
    bad news is an advocacy tool, not an instrument."""
    was = _result({"blind": [_h("a", "g1", "o1"), _h("b", "g2", "o2")]})
    now = _result({"blind": [_h("a", "g1", "o1")]})
    f = emit.compare(TARGET, was, now)
    assert f and "closed" in f["headline"]


def test_the_same_count_with_different_holes_is_a_finding():
    """Two runs can both say 'six holes' with a different six. A count-only
    comparison would call that unchanged, which is the whole reason holes are
    compared by identity."""
    was = _result({"blind": [_h("a", "g1", "o1")]})
    now = _result({"blind": [_h("z", "g9", "o9")]})
    f = emit.compare(TARGET, was, now)
    assert f is not None, "same count, different holes, must still be a finding"


# ── the category that keeps the receiving pipeline honest ─────────────────

def test_a_drift_finding_is_filed_as_harness_never_as_models():
    """A hole in a grader is a fact about the checking layer. model-drift's
    parser refuses any other value, and it refuses rather than repairs."""
    f = emit.compare(TARGET, _result({"blind": []}),
                     _result({"blind": [_h("a", "g1", "o1")]}))
    assert f["about"] == "harness"


def test_every_finding_carries_evidence():
    f = emit.compare(TARGET, _result({"blind": []}),
                     _result({"blind": [_h("a", "g1", "o1")]}))
    assert len(f["evidence"]) >= 3
    assert all(r.get("claim") and r.get("how") for r in f["evidence"])


# ── identity, so one drift is reported once ───────────────────────────────

def test_the_run_key_is_the_hole_set_not_the_date():
    """A standing condition re-derives forever. Keyed on the calendar it would
    be re-reported forever, which is the bug that logged one model-drift
    regression 19 times."""
    now = _result({"blind": [_h("a", "g1", "o1")]})
    a = emit.compare(TARGET, _result({"blind": []}), now)
    b = emit.compare(TARGET, _result({"blind": [_h("z", "g9", "o9")]}), now)
    assert a["run_key"] == b["run_key"], \
        "same resulting hole set must produce the same key regardless of what it came from"


def test_a_different_hole_set_gets_a_different_key():
    base = _result({"blind": []})
    a = emit.compare(TARGET, base, _result({"blind": [_h("a", "g1", "o1")]}))
    b = emit.compare(TARGET, base, _result({"blind": [_h("b", "g2", "o2")]}))
    assert a["run_key"] != b["run_key"]


# ── a broken run is not a finding about the target ────────────────────────

def test_a_run_that_produced_no_json_raises_rather_than_reporting():
    """evalmut exits 1 when it finds serious holes, which is a RESULT. Only a
    run with no parseable JSON is an error, and that is a finding about us
    rather than about promptfoo."""
    with pytest.raises(RuntimeError, match="produced no result"):
        emit.run_suite("external/does_not_exist.py")


def test_a_nonzero_exit_with_valid_json_is_treated_as_a_result(monkeypatch):
    import subprocess

    class Proc:
        returncode = 1
        stdout = json.dumps({"score": 0.5, "holes": {"blind": []}})
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Proc())
    assert emit.run_suite("external/whatever.py")["score"] == 0.5


# ── the committed artifacts ───────────────────────────────────────────────

def test_the_committed_findings_file_matches_the_shared_schema():
    p = Path("notes/findings.json")
    if not p.exists():
        pytest.skip("no findings emitted yet")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["schema"] == emit.SCHEMA
    assert d["source"] == "evalmut"
    assert isinstance(d["findings"], list)


def test_every_configured_target_has_a_suite_file():
    """A target whose suite vanished would be reported as a problem rather
    than silently dropped, but it should not vanish in the first place."""
    missing = [t["key"] for t in emit.TARGETS if not Path(t["suite"]).exists()]
    assert not missing, f"configured targets with no suite file: {missing}"
