"""Require invocation evidence on a cross-language observation, instead of trusting a verdict.

WHY THIS IS SEPARATE FROM sentinel.py. `sentinel()` wraps a Python object and can see the call
happen. The Corpus B path runs promptfoo's TypeScript in a subprocess, where no Python patch can
reach, so the witness is produced on the TS side and this module's job is to REFUSE a row that
arrives without one.

THE ROW THIS EXISTS TO REJECT looks completely healthy: a card id, a clean verdict, a defective
verdict, no errors. What it lacks is any proof the upstream scorer ran at all, which makes it
indistinguishable from a row where the harness answered for itself. This estate has twice shipped
a gate that could not tell "checked and clean" from "never checked", and both times the artifact
looked fine. So the absence of evidence is treated as a refusal, never as a pass.

RAW BESIDE THE VERDICT, ALWAYS. The upstream return is recorded per call rather than inferred from
the wrapper's conclusion. A wrapper that transforms a score can be wrong in a way no verdict
reveals, and the only way to notice is to keep both.
"""
from __future__ import annotations

from typing import Any

from .sentinel import UpstreamNeverRan


class WitnessMissing(UpstreamNeverRan):
    """An observation carries a verdict with no proof its upstream scorer executed."""


class WitnessInconsistent(ValueError):
    """The witness contradicts itself or the observation it accompanies."""


REQUIRED = ("target", "invoked", "calls", "raw_upstream")


def check_row(row: dict[str, Any], *, expect_calls: int | None = None) -> dict:
    """Validate one witnessed observation. Returns the witness, or raises.

    `expect_calls` lets a probe declare how many upstream calls it intends. A run that made fewer
    calls than it declared reached less of the scorer than it claims to have measured, and that is
    a different fact from a failing verdict."""
    w = row.get("witness")
    if not w:
        raise WitnessMissing(
            f"{row.get('card_id', '<row>')}: verdicts present but no witness. A verdict with no "
            "proof the upstream scorer ran cannot be told apart from one the harness produced "
            "itself, so it is refused rather than counted.")

    missing = [f for f in REQUIRED if f not in w]
    if missing:
        raise WitnessInconsistent(f"{row.get('card_id', '<row>')}: witness is missing {missing}")

    if not w["invoked"] or int(w["calls"]) < 1:
        raise WitnessMissing(
            f"{row.get('card_id', '<row>')}: witness reports the upstream scorer "
            f"{w['target']!r} was never invoked (calls={w['calls']}). The observation is not "
            "evidence about that scorer.")

    raw = w["raw_upstream"]
    if not isinstance(raw, list) or len(raw) != int(w["calls"]):
        raise WitnessInconsistent(
            f"{row.get('card_id', '<row>')}: witness claims {w['calls']} call(s) but carries "
            f"{len(raw) if isinstance(raw, list) else 'a non-list'} raw upstream value(s). One of "
            "the two is wrong and the row must not be interpreted.")

    if expect_calls is not None and int(w["calls"]) != expect_calls:
        raise WitnessInconsistent(
            f"{row.get('card_id', '<row>')}: probe declared {expect_calls} upstream call(s), "
            f"witness saw {w['calls']}. The probe did not exercise what it said it would.")
    return w


def check_bundle(rows: list[dict], *, expect_calls: dict[str, int] | None = None) -> dict:
    """Every row or none. A bundle that reports some witnessed rows and some bare ones invites a
    reader to average across two different kinds of claim."""
    problems, witnessed = [], 0
    for r in rows:
        try:
            check_row(r, expect_calls=(expect_calls or {}).get(r.get("card_id")))
            witnessed += 1
        except (WitnessMissing, WitnessInconsistent) as e:
            problems.append(str(e))
    if problems:
        raise WitnessMissing(
            f"{len(problems)} of {len(rows)} row(s) are not witnessed:\n  " + "\n  ".join(problems))
    return {"rows": len(rows), "witnessed": witnessed}
