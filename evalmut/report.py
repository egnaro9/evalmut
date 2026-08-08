"""Render a Report as text a person can act on.

The score is one line and the least important. The body is the holes, grouped by how
alarming they are and each carrying the real defect it is the shape of — because
"your grounding check passed a fabricated clause (the SciFact 'vaccines cause autism'
shape)" is a thing to go fix, and "0.82" is not.
"""
from __future__ import annotations

from .outcome import Outcome
from .score import Report, Tally

_BAR = "─" * 72


def _pct(t: Tally) -> str:
    return f"{t.score * 100:.0f}%" if t.applied else "  —"


def render(report: Report, *, verbose: bool = False) -> str:
    out: list[str] = []
    w = out.append
    t = report.total

    w(_BAR)
    w("  evalmut — does your eval actually check anything?")
    w(_BAR)
    w(f"  mutation score   {t.score * 100:5.1f}%   "
      f"({t.caught} caught / {t.applied} applied; {t.na} n/a)")
    holes = len(report.holes)
    if holes == 0:
        w("  holes            none — every applied mutation was handled correctly")
    else:
        parts = []
        if report.vacuous:      parts.append(f"{len(report.vacuous)} vacuous")
        if report.blind_spots:  parts.append(f"{len(report.blind_spots)} blind")
        if report.brittle_spots:parts.append(f"{len(report.brittle_spots)} brittle")
        if report.coverage_gaps:parts.append(f"{len(report.coverage_gaps)} coverage-gap")
        w(f"  holes            {holes}  ({', '.join(parts)})")

    if getattr(report, "baseline_failures", ()):  # loud, never swallowed
        w("")
        w("  ⚠ BASELINE FAILURES — these cases were skipped (grader fails its own reference):")
        for be in report.baseline_failures:
            w(f"      {be}")

    _section(w, "VACUOUS — the grader asserts nothing about the answer and cannot fail",
             report.vacuous, verbose)
    _section(w, "BLIND SPOTS — a real defect shipped green; the check is present and broken",
             report.blind_spots, verbose)
    _section(w, "BRITTLE SPOTS — the check fails a still-correct output (a false-positive)",
             report.brittle_spots, verbose)
    _section(w, "COVERAGE GAPS — no check guards this shape (a missing grader, not a broken one)",
             report.coverage_gaps, verbose)

    if verbose:
        w("")
        w("  per-grader:")
        for gid, gt in sorted(report.by_grader.items()):
            w(f"      {_pct(gt):>4}  {gid:<22} caught {gt.caught} missed {gt.missed} "
              f"flagged {gt.flagged} n/a {gt.na}")

    w(_BAR)
    return "\n".join(out)


def _section(w, title: str, items, verbose: bool) -> None:
    if not items:
        return
    w("")
    w(f"  {title}")
    for h in items:
        arrow = "passed" if h.outcome is Outcome.MISSED else "failed"
        w(f"    • {h.grader_id} / {h.case_name}")
        w(f"        mutation : {h.operator_id} — {h.defect_shape}")
        w(f"        grader   : {arrow} the mutant  ({h.detail})")
        w(f"        mined from: {h.real_origin}")
        if verbose and h.mutant_preview:
            w(f"        mutant   : {h.mutant_preview}")
        if h.grader_error:
            w(f"        note     : grader crashed — {h.grader_error}")


def render_short(report: Report) -> str:
    """One line, for CI: score, hole counts, exit-worthy."""
    t = report.total
    return (f"evalmut {t.score*100:.0f}%  "
            f"vacuous={len(report.vacuous)} blind={len(report.blind_spots)} "
            f"brittle={len(report.brittle_spots)} gap={len(report.coverage_gaps)}")
