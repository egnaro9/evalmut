"""Adversarial tests for the scorer inventory contract.

The point is not that a count comes out. It is that the six ways a denominator gets quietly chosen
after the fact all fail closed: a scorer silently dropped, an exclusion with no reason, a
denominator that was never declared, a post-seal edit, inclusion changed in response to a result,
and a runner meeting a population nobody sealed.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    "evalmut_inventory", pathlib.Path(__file__).resolve().parents[1] / "evalmut" / "inventory.py")
I = importlib.util.module_from_spec(_spec)
sys.modules["evalmut_inventory"] = I
_spec.loader.exec_module(I)

SUITE, REV = "promptfoo/promptfoo", "c08cfc454d38"
WHY = "calls a live moderation provider, so a verdict flip cannot be attributed to the mutation"


def sc(sym, **kw):
    return I.Scorer(suite=SUITE, revision=REV, module_path="src/assertions/x.ts", symbol=sym,
                    discovered_by="static scan of src/assertions/*.ts exports", **kw)


def inc(s):
    return I.Row(scorer=s, disposition=I.Disposition.INCLUDED)


def exc(s, pred="non_deterministic", why=WHY):
    return I.Row(scorer=s, disposition=I.Disposition.UNSUPPORTED, predicate=pred, rationale=why)


def make(rows_by_id, discovered, **kw):
    return I.build(discovered, rows_by_id, suite=SUITE, revision=REV,
                   environment={"node": "v24.14.1", "arch": "arm64"},
                   discovery_method="exports of src/assertions/*.ts at the pinned revision",
                   queries={"all_discovered": ["included", "excluded", "infeasible",
                                               "unsupported"],
                            "drivable": ["included"]}, **kw)


@pytest.fixture
def sealed():
    a, b, c = sc("is-xml"), sc("is-sql"), sc("moderation")
    disc = [a, b, c]
    rows = {a.id: inc(a), b.id: inc(b), c.id: exc(c)}
    inv = make(rows, disc)
    return inv, inv.digest, disc


# ---------------------------------------------------------------- the six failure modes

def test_silent_drop_fails_closed():
    """A discovered scorer absent from the inventory is how a denominator shrinks unnoticed."""
    a, b = sc("is-xml"), sc("is-sql")
    with pytest.raises(I.InventoryError) as e:
        make({a.id: inc(a)}, [a, b])
    assert "no disposition" in str(e.value)


def test_unjustified_exclusion_fails():
    a = sc("is-xml")
    bad = I.Row(scorer=a, disposition=I.Disposition.EXCLUDED, predicate="", rationale="")
    with pytest.raises(I.InventoryError) as e:
        make({a.id: bad}, [a])
    assert "not one of the enumerated predicates" in str(e.value)


def test_not_applicable_alone_is_not_a_reason():
    a = sc("is-xml")
    thin = I.Row(scorer=a, disposition=I.Disposition.EXCLUDED,
                 predicate="out_of_scope_by_design", rationale="not applicable")
    with pytest.raises(I.InventoryError) as e:
        make({a.id: thin}, [a])
    assert "is not a reason" in str(e.value)


def test_undeclared_denominator_is_refused(sealed):
    inv, dig, _ = sealed
    with pytest.raises(I.InventoryError) as e:
        inv.denominator("everything_that_returned_a_verdict")
    assert "not declared in the sealed inventory" in str(e.value)
    assert "it is a result" in str(e.value)


def test_inventory_drift_breaks_the_binding(sealed):
    """Change a disposition after sealing and the digest no longer matches."""
    inv, dig, disc = sealed
    a, b, c = disc
    drifted = make({a.id: inc(a), b.id: inc(b), c.id: inc(c)}, disc)
    assert drifted.digest != dig
    with pytest.raises(I.InventoryError) as e:
        I.check_execution(drifted, dig, disc)
    assert "digest changed since sealing" in str(e.value)


def test_result_driven_filtering_is_caught_by_the_seal(sealed):
    """Moving a scorer out of the denominator after seeing its result changes the digest, which is
    the whole reason the seal precedes execution."""
    inv, dig, disc = sealed
    a, b, c = disc
    after_seeing_results = make(
        {a.id: inc(a), b.id: exc(b, "harness_incompatible",
                                 "it produced an inconvenient verdict in the pilot run"),
         c.id: exc(c)}, disc)
    with pytest.raises(I.InventoryError):
        I.check_execution(after_seeing_results, dig, disc)
    assert after_seeing_results.denominator("drivable") == 1 != inv.denominator("drivable")


def test_execution_mismatch_stops_the_run(sealed):
    inv, dig, disc = sealed
    with pytest.raises(I.InventoryError) as e:
        I.check_execution(inv, dig, disc + [sc("is-json")])
    assert "absent from the sealed inventory" in str(e.value)
    assert "invalid rather than merely incomplete" in str(e.value)


# ---------------------------------------------------------------- the contract works when honest

def test_a_clean_inventory_seals_and_verifies(sealed):
    inv, dig, disc = sealed
    I.check_execution(inv, dig, disc)
    assert inv.denominator("all_discovered") == 3
    assert inv.denominator("drivable") == 2


def test_aggregation_requires_a_declared_query(sealed):
    inv, dig, _ = sealed
    got = I.aggregate(1, inv, dig, "drivable")
    assert got == {"numerator": 1, "denominator": 2, "query": "drivable",
                   "inventory_digest": dig, "rate": 0.5}
    with pytest.raises(I.InventoryError):
        I.aggregate(1, inv, dig, "some_query_invented_at_write_up_time")


def test_an_empty_denominator_is_not_a_perfect_score(sealed):
    inv, dig, disc = sealed
    a, b, c = disc
    none_drivable = make({a.id: exc(a), b.id: exc(b), c.id: exc(c)}, disc)
    with pytest.raises(I.InventoryError) as e:
        I.aggregate(0, none_drivable, none_drivable.digest, "drivable")
    assert "not a perfect score" in str(e.value)


def test_a_numerator_cannot_exceed_its_declared_denominator(sealed):
    inv, dig, _ = sealed
    with pytest.raises(I.InventoryError):
        I.aggregate(3, inv, dig, "drivable")


def test_the_digest_is_stable_across_row_order(sealed):
    """Canonicalisation, so a reordered inventory is the same inventory and does not read as
    tampering. Without this the drift check would cry wolf and get switched off."""
    inv, dig, disc = sealed
    a, b, c = disc
    same = make({c.id: exc(c), a.id: inc(a), b.id: inc(b)}, [c, a, b])
    assert same.digest == dig


def test_every_scorer_identity_records_how_it_was_discovered(sealed):
    """Discovery is itself a claim about completeness, so it is auditable rather than assumed."""
    inv, _, _ = sealed
    assert inv.discovery_method
    for r in inv.rows:
        assert r.scorer.discovered_by
