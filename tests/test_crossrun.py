"""Two runners, and no path that picks a winner.

The failure this guards is not fraud, it is drift: a row disagrees, one runner looks obviously
right, and the obviously-right one quietly becomes "the result". The load-bearing test tries to
extract a winner from a disagreeing pair and requires that there is nothing to extract.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from evalmut.crossrun import COMPARED_FIELDS, CrossRunRefused, compare, may_aggregate  # noqa: E402

SEALED = {"corpus": "f1c97f3", "manifest": "c2992838", "inventory": "aa11bb22"}
NC = {"invoked": True, "calls": 2, "discriminated": False}


def row(cid="CB-001", status="VERIFIED", clean=True, defective=False):
    return {"card_id": cid, "status": status, "verdict_clean": clean,
            "verdict_defective": defective, "raw_upstream": [clean, defective],
            "witness": {"invoked": True, "calls": 2}}


def bundle(os_="macOS-26.6", arch="arm64", rows=None, **kw):
    b = {"run_id": "cb-2026-08-18-a", "sealed": dict(SEALED), "negative_control": dict(NC),
         "environment": {"os": os_, "arch": arch, "node": "v24.14.1"},
         "rows": rows or [row(), row("CB-004")]}
    b.update(kw)
    return b


MAC, LINUX = lambda **k: bundle(**k), lambda **k: bundle("ubuntu-24.04", "x86_64", **k)


# ---------------------------------------------------------------- no winner exists

def test_a_disagreement_is_a_verdict_not_a_menu():
    b = LINUX(rows=[row(defective=True), row("CB-004")])
    rep = compare(MAC(), b)
    assert rep["verdict"] == "CROSS_RUN_DISAGREEMENT"
    assert rep["disagree"][0]["card_id"] == "CB-001"
    assert "winner" not in rep and "chosen" not in rep and "result" not in rep
    assert "not a menu" in rep["note"]


def test_no_aggregate_survives_a_disagreement():
    b = LINUX(rows=[row(defective=True), row("CB-004")])
    with pytest.raises(CrossRunRefused) as e:
        may_aggregate(compare(MAC(), b))
    assert "unresolved" in str(e.value)


def test_the_report_carries_both_values_so_neither_is_lost():
    b = LINUX(rows=[row(defective=True), row("CB-004")])
    d = compare(MAC(), b)["disagree"][0]["fields"]["verdict_defective"]
    assert d == {"runner_a": False, "runner_b": True}


# ---------------------------------------------------------------- agreement must mean something

def test_agreement_between_two_uninstrumented_runs_is_refused():
    """Two runs that may never have called the scorer agreeing is still not evidence."""
    bad = MAC(); bad["rows"][0].pop("witness")
    with pytest.raises(CrossRunRefused) as e:
        compare(bad, LINUX())
    assert "still not evidence" in str(e.value)


def test_agreement_without_a_live_negative_control_is_refused():
    bad = MAC(); bad["negative_control"] = {"invoked": True, "discriminated": True}
    with pytest.raises(CrossRunRefused) as e:
        compare(bad, LINUX())
    assert "shown able to fail" in str(e.value)


def test_two_runs_on_the_same_platform_do_not_satisfy_the_requirement():
    with pytest.raises(CrossRunRefused) as e:
        compare(MAC(), MAC())
    assert "DISTINCT os and architecture" in str(e.value)


def test_differing_sealed_inputs_are_refused():
    b = LINUX(); b["sealed"]["manifest"] = "deadbeef"
    with pytest.raises(CrossRunRefused) as e:
        compare(MAC(), b)
    assert "did not measure the same declared population" in str(e.value)


def test_differing_run_ids_are_two_studies_not_one():
    b = LINUX(); b["run_id"] = "cb-2026-08-18-b"
    with pytest.raises(CrossRunRefused) as e:
        compare(MAC(), b)
    assert "two different studies" in str(e.value)


def test_a_partial_row_overlap_is_refused():
    with pytest.raises(CrossRunRefused) as e:
        compare(MAC(), LINUX(rows=[row()]))
    assert "partial overlap" in str(e.value)


# ---------------------------------------------------------------- the field set is fixed

def test_a_missing_declared_field_is_incomplete_not_a_reason_to_compare_less():
    b = LINUX(); b["rows"][0].pop("raw_upstream")
    with pytest.raises(CrossRunRefused) as e:
        compare(MAC(), b)
    assert "not a reason to compare less" in str(e.value)


def test_exempt_fields_do_not_cause_a_disagreement():
    """A check that fails on timestamps gets loosened until it fails on nothing."""
    a, b = MAC(), LINUX()
    a["rows"][0]["duration_ms"] = 12
    b["rows"][0]["duration_ms"] = 9999
    assert compare(a, b)["verdict"] == "CROSS_RUN_AGREEMENT"


def test_a_clean_agreeing_pair_passes_the_gate():
    rep = compare(MAC(), LINUX())
    may_aggregate(rep)
    assert rep["agree"] == ["CB-001", "CB-004"] and rep["disagree"] == []
    assert rep["compared_fields"] == list(COMPARED_FIELDS)
    assert rep["platforms"]["runner_b"]["arch"] == "x86_64"
