"""The negative control for the Corpus B path: a scorer that is SUPPOSED to fail.

WHY THIS IS NOT THE WITNESS. The witness proves a scorer EXECUTED. It says nothing about whether
the harness could still tell a broken scorer from a working one. Those are different questions and
a harness can pass the first while failing the second: every call recorded, every raw value
captured, and a comfortable result reported for a check that cannot fail. That is worse than no
harness, because it launders the defect it was bought to find. evalmut's own suite learned this
when every fixture was a grader believed correct, so the suite could only ever demonstrate the
absence of false positives.

WHAT THE CONTROL ASSERTS. A deliberately broken scorer, declared in the sealed inventory like any
other, run through the same witnessed path, must come back as NOT discriminating clean from
defective. Its expected outcome is SURVIVED, and SURVIVED here is success for the control and
failure for the scorer. Those are the same fact stated from two directions, which is exactly why
the four-state vocabulary refuses to collapse them into pass and fail.

THE THREE WAYS THIS FAILS CLOSED, all of which mean the same thing: the harness is not measuring
what it claims. The control is missing from the evidence. The control was never invoked. The
control DISCRIMINATED, meaning either someone repaired it or the pipeline is not running the
scorer it thinks it is. In every case aggregation is refused rather than annotated.
"""
from __future__ import annotations

from typing import Any

from .witnessed import check_row

CONTROL_ID = "NEG-CONTROL-1"


class NegativeControlFailure(AssertionError):
    """The control is absent, uninvoked, or behaved unlike a broken scorer."""


def evaluate(row: dict[str, Any]) -> dict:
    """Judge the control row. Returns its evidence, or raises with what went wrong."""
    if not row.get("negative_control"):
        raise NegativeControlFailure(
            f"{row.get('card_id', '<row>')} is not flagged as the negative control. A control that "
            "is not labelled cannot be checked for, and an unchecked control is decoration.")

    w = check_row(row)  # the control is held to the same invocation evidence as any other row

    v = row.get("verdicts") or {}
    if "clean" not in v or "defective" not in v:
        raise NegativeControlFailure(
            f"{row['card_id']}: the control needs BOTH a clean and a defective observation. One "
            "of them alone cannot show a failure to discriminate.")

    discriminated = v["clean"] != v["defective"]
    if discriminated:
        raise NegativeControlFailure(
            f"{row['card_id']}: the deliberately broken scorer DISCRIMINATED between the clean and "
            f"defective inputs (clean={v['clean']!r}, defective={v['defective']!r}). Either it was "
            "repaired, or the pipeline is not running the scorer it believes it is. Either way the "
            "harness is not measuring what it claims and no result may be published from this run.")

    return {"control_id": row["card_id"], "invoked": True, "calls": w["calls"],
            "discriminated": False, "expected_state": "SURVIVED",
            "meaning": "the broken scorer failed to separate clean from defective, which is the "
                       "control working and the scorer failing. Both readings are the same fact."}


def require_in_inventory(inventory, control_scorer_id: str) -> None:
    """The control must be a declared member of the population, not a side experiment.

    A control run outside the sealed inventory proves the harness can catch something, but not
    that it would have caught it on the run being reported."""
    if control_scorer_id not in inventory.ids:
        raise NegativeControlFailure(
            f"the negative control {control_scorer_id!r} is not in the sealed inventory. A control "
            "outside the declared population does not cover the run being reported.")


def gated_aggregate(numerator: int, inventory, sealed_digest: str, query: str,
                    control_row: dict | None, control_scorer_id: str) -> dict:
    """The only sanctioned path to a published number. Wraps the inventory's own aggregation.

    Deliberately a wrapper rather than an edit to inventory.aggregate: the inventory contract is
    about the POPULATION, this is about whether the instrument can fail, and fusing them would
    make each harder to reason about and to test."""
    from .inventory import aggregate  # local import keeps the two contracts independently usable

    require_in_inventory(inventory, control_scorer_id)
    if control_row is None:
        raise NegativeControlFailure(
            "no negative-control evidence accompanies this run. Without it there is nothing "
            "showing the harness can expose a scorer that should fail, so the number is not "
            "publishable regardless of how it looks.")
    control = evaluate(control_row)
    out = aggregate(numerator, inventory, sealed_digest, query)
    out["negative_control"] = control
    return out
