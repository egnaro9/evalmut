"""Refuse a review submission that cannot be told apart from a rubber stamp.

WHY A VALIDATOR AT ALL. The scarce thing here is a reviewer's judgement, and the failure mode is
not a malformed file: it is a well-formed file that agrees with everything. A protocol that
accepts twelve one-word "valid" responses has collected a signature, not a review, and would then
be reported as independent classification. So the checks below are about SUBSTANCE as much as
shape, and the substance check is the one that will actually fire.

WHAT THIS DELIBERATELY DOES NOT DO. It never judges whether a label is correct. A reviewer saying
`invalid` about a card the author believes in is the protocol working. The only thing refused is a
submission that carries no reasoning to disagree with.
"""
from __future__ import annotations

import json
import pathlib
import sys

MIN_RATIONALE = 40
STAMP_MEAN = 120
# The stamp heuristic needs enough rows to mean anything. Applied to one or two
# classifications it punishes a small honest submission, and a check that cries wolf
# gets switched off, which is a slower way to have no check.
STAMP_MIN_ROWS = 3
LABELS = {"valid", "invalid", "unclear", "scope-dependent"}


class ReviewRejected(ValueError):
    """The submission cannot be counted as an independent classification."""


def validate(doc: dict, known_ids: set[str]) -> list[str]:
    """Return the list of accepted card ids, or raise with every problem found.

    Every problem, not the first: handing a reviewer one error at a time to fix is how a protocol
    burns the goodwill it depends on."""
    problems: list[str] = []
    for f in ("reviewer", "affiliation", "received_at"):
        if not doc.get(f):
            problems.append(f"missing {f}")

    rows = doc.get("classifications") or []
    if doc.get("declined"):
        if rows:
            problems.append("declined submissions must not carry classifications")
        if problems:
            raise ReviewRejected("; ".join(problems))
        return []

    if not rows:
        problems.append("no classifications and not marked declined")

    seen: set[str] = set()
    for i, c in enumerate(rows):
        cid = c.get("card_id", f"<row {i}>")
        if cid in seen:
            problems.append(f"{cid}: duplicate from the same reviewer")
        seen.add(cid)
        if cid not in known_ids:
            problems.append(f"{cid}: not a card in the frozen manifest")
        if c.get("label") not in LABELS:
            problems.append(f"{cid}: label {c.get('label')!r} is not one of {sorted(LABELS)}")
        if not (c.get("named_semantic") or "").strip():
            problems.append(f"{cid}: named_semantic is required for every label, including valid")
        r = (c.get("rationale") or "").strip()
        if len(r) < MIN_RATIONALE:
            problems.append(f"{cid}: rationale is {len(r)} chars, minimum {MIN_RATIONALE}")
        if c.get("disputes_author_applicability") and not (c.get("dispute_rationale") or "").strip():
            problems.append(f"{cid}: disputes the author's applicability call without saying why")

    # The rubber-stamp check. Uniform approval is not itself suspect; uniform approval with no
    # reasoning is, because it is exactly what a reviewer who did not read produces.
    if len(rows) >= STAMP_MIN_ROWS and all(c.get("label") == "valid" for c in rows):
        lens = [len((c.get("rationale") or "").strip()) for c in rows]
        mean = sum(lens) / len(lens)
        if mean < STAMP_MEAN:
            problems.append(
                f"every card labelled 'valid' with mean rationale {mean:.0f} chars (under "
                f"{STAMP_MEAN}). This is indistinguishable from a rubber stamp and cannot be "
                "counted as independent classification. Genuine unanimity is fine; write the "
                "reasoning and this check clears.")

    if problems:
        raise ReviewRejected("; ".join(problems))
    return sorted(seen)


def independent(a: dict, b: dict) -> tuple[bool, str]:
    """Do two submissions count as independent on a shared card?

    Checked from recorded fields rather than from a memory of having thought about it. The known
    live case is Groce and Gopinath, co-authors on all four mutation papers checked."""
    if a.get("reviewer") == b.get("reviewer"):
        return False, "same reviewer"
    if a.get("affiliation") and a.get("affiliation") == b.get("affiliation"):
        return False, f"shared affiliation: {a['affiliation']}"
    ca, cb = set(a.get("coauthors_with") or []), set(b.get("coauthors_with") or [])
    if b.get("reviewer") in ca or a.get("reviewer") in cb:
        return False, "co-authors"
    if ca & cb:
        return False, f"shared co-authors: {sorted(ca & cb)}"
    return True, "independent"


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    known = {c["id"] for c in json.loads((root / "MANIFEST.json").read_text())["cards"]}
    ok = True
    for p in sorted((pathlib.Path(__file__).resolve().parent / "responses").glob("*.json")):
        try:
            ids = validate(json.loads(p.read_text()), known)
            print(f"ACCEPTED  {p.name}  {len(ids)} classifications")
        except (ReviewRejected, Exception) as e:
            ok = False
            print(f"REJECTED  {p.name}\n          {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
