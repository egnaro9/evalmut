"""Compare two clean-process runs on distinct OS and architecture, without picking a winner.

WHY A MODULE AND NOT A DIFF. The temptation in a two-runner protocol is not fraud, it is drift: a
row disagrees, one runner looks obviously right, and the obviously-right one quietly becomes "the
result" while the disagreement stops being mentioned. That is how a cross-platform check turns
into a second chance. So disagreement is a FIRST-CLASS OUTCOME here. There is no code path that
returns one runner's value when the two differ, and a test asserts that by trying.

WHAT IS COMPARED IS DECLARED IN ADVANCE. Comparing everything makes a run fail on timestamps and
paths, and a check that fails on noise gets loosened until it fails on nothing. Comparing whatever
happens to match makes the comparison unfalsifiable. So the fields are named up front and a bundle
that omits one is incomplete rather than partially compared.

PREREQUISITES ARE CHECKED BEFORE ANY COMPARISON. A pair of bundles that agree perfectly proves
nothing if neither carries witness evidence, if they sealed different inputs, or if the negative
control never ran. Agreement between two instruments that were not measuring is still agreement.
"""
from __future__ import annotations

import json
from typing import Any

# Named before the first comparison, not discovered from what happened to match.
COMPARED_FIELDS = ("card_id", "status", "verdict_clean", "verdict_defective", "raw_upstream")

# Fields that legitimately differ between runners and must NOT be compared. Listed explicitly so
# the exemption is a decision on the record rather than an omission nobody noticed.
EXEMPT = ("started_at", "duration_ms", "runner", "os", "arch", "workspace_path", "environment")


class CrossRunRefused(ValueError):
    """The pair cannot be compared, or was compared and disagrees."""


def _prereqs(name: str, b: dict[str, Any]) -> None:
    for f in ("run_id", "sealed", "rows", "negative_control", "environment"):
        if f not in b:
            raise CrossRunRefused(f"{name}: bundle is missing {f!r}, so it is incomplete")
    if not b["rows"]:
        raise CrossRunRefused(f"{name}: bundle carries no rows")
    nc = b["negative_control"]
    if not nc.get("invoked") or nc.get("discriminated") is not False:
        raise CrossRunRefused(
            f"{name}: negative control did not demonstrate liveness "
            f"(invoked={nc.get('invoked')}, discriminated={nc.get('discriminated')}). Two runners "
            "agreeing proves nothing if neither instrument was shown able to fail.")
    for r in b["rows"]:
        w = r.get("witness")
        if not w or not w.get("invoked"):
            raise CrossRunRefused(
                f"{name}: row {r.get('card_id')} has no invocation witness. Agreement between two "
                "runs that may not have called the scorer is still not evidence.")


def _distinct_platforms(a: dict, b: dict) -> None:
    ea, eb = a["environment"], b["environment"]
    if ea.get("os") == eb.get("os") and ea.get("arch") == eb.get("arch"):
        raise CrossRunRefused(
            f"both bundles ran on {ea.get('os')}/{ea.get('arch')}. The requirement is two clean "
            "processes on DISTINCT os and architecture; a second process on the same platform "
            "repeats the same environment's assumptions rather than testing them.")


def compare(a: dict, b: dict, *, name_a: str = "runner_a", name_b: str = "runner_b") -> dict:
    """Return an explicit agreement report. Never returns one runner's value over the other."""
    _prereqs(name_a, a)
    _prereqs(name_b, b)
    _distinct_platforms(a, b)

    if a["run_id"] != b["run_id"]:
        raise CrossRunRefused(
            f"run ids differ ({a['run_id']} vs {b['run_id']}); these are two different studies, "
            "not one study on two runners.")
    if a["sealed"] != b["sealed"]:
        raise CrossRunRefused(
            f"sealed inputs differ: {a['sealed']} vs {b['sealed']}. The runners did not measure "
            "the same declared population and corpus.")

    ra = {r["card_id"]: r for r in a["rows"]}
    rb = {r["card_id"]: r for r in b["rows"]}
    only_a, only_b = sorted(set(ra) - set(rb)), sorted(set(rb) - set(ra))
    if only_a or only_b:
        raise CrossRunRefused(
            f"row sets differ. Only in {name_a}: {only_a}. Only in {name_b}: {only_b}. A partial "
            "overlap cannot be reported as a cross-platform result.")

    agreements, disagreements = [], []
    for cid in sorted(ra):
        diffs = {}
        for f in COMPARED_FIELDS:
            if f == "card_id":
                continue
            if f not in ra[cid] or f not in rb[cid]:
                raise CrossRunRefused(
                    f"{cid}: declared comparison field {f!r} missing from a bundle. The field set "
                    "is fixed in advance, so an absent field is incomplete evidence and not a "
                    "reason to compare less.")
            if ra[cid][f] != rb[cid][f]:
                diffs[f] = {name_a: ra[cid][f], name_b: rb[cid][f]}
        (disagreements if diffs else agreements).append(
            {"card_id": cid, **({"fields": diffs} if diffs else {})})

    return {
        "run_id": a["run_id"],
        "sealed": a["sealed"],
        "platforms": {name_a: a["environment"], name_b: b["environment"]},
        "compared_fields": list(COMPARED_FIELDS),
        "exempt_fields": list(EXEMPT),
        "agree": [x["card_id"] for x in agreements],
        "disagree": disagreements,
        # Stated as a fact about the pair, never resolved. There is deliberately no "winner" key.
        "verdict": "CROSS_RUN_AGREEMENT" if not disagreements else "CROSS_RUN_DISAGREEMENT",
        "note": ("Every compared field matched on both platforms." if not disagreements else
                 f"{len(disagreements)} row(s) disagree across platforms. A disagreement is a "
                 "finding about the measurement, not a menu. Neither runner's value is adopted "
                 "and no aggregate may be published from this pair until it is explained."),
    }


def may_aggregate(report: dict) -> None:
    """Gate. Refuses on any disagreement rather than letting a caller decide it is minor."""
    if report["verdict"] != "CROSS_RUN_AGREEMENT":
        raise CrossRunRefused(
            "cross-run disagreement is unresolved, so no aggregate may be published: "
            + json.dumps(report["disagree"])[:400])
