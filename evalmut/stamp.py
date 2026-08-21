"""The publication stamp: which commit produced the artifact you are holding.

ONE DEFINITION, TWO CONSUMERS. emit_vac.py stamps the VAC bundle and the witness run stamps its
own artifact. If each kept its own copy of the rule they would drift, and a drifted stamp is worse
than no stamp: it names a commit with authority it does not have.

THE RULE. The stamp is the last commit that touched CODE_PATHS, not HEAD. A commit that changes
only tests, docs or generated output cannot alter the bytes, so stamping it would assert that it
produced something it had no hand in. This was settled the hard way: a review asked for the stamp
to equal HEAD after a test-only commit, and following that would have made the bundle claim a
test edit regenerated its artifacts.

DIRTY TREES ARE RECORDED, NOT REFUSED, HERE. emit_vac.py refuses outright, because a bundle is a
published claim. The witness run is also a development command that tests invoke as a subprocess,
so refusing would make an ordinary edit break the suite. It records `dirty` instead and leaves the
decision to whoever publishes: the consumer of a stamped artifact is expected to refuse a dirty
one rather than trusting a stamp that cannot identify the working tree it came from.
"""
from __future__ import annotations

import pathlib
import subprocess

# The paths whose contents can change the emitted bytes. Tests, docs and generated output are
# deliberately absent: a change there cannot move an artifact, so it must not move a stamp.
CODE_PATHS = ("evalmut", "demos/dogfood_gradecore.py",
              "external/promptfoo_suite.py",
              "external/promptfoo_assertions.py",
              "pyproject.toml", "emit_vac.py")

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _git(args: list[str], repo: pathlib.Path) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()


def code_commit(repo: pathlib.Path | None = None) -> str:
    """The last commit touching CODE_PATHS. Empty string when git cannot answer."""
    repo = repo or _ROOT
    try:
        return _git(["log", "-1", "--format=%h", "--abbrev=7", "--", *CODE_PATHS], repo)
    except Exception:
        return ""


def is_dirty(repo: pathlib.Path | None = None, output_paths: tuple[str, ...] = ()) -> bool:
    """Is anything outside the declared output paths modified or untracked?

    -uall because porcelain collapses a fully untracked directory to one line, which would let
    code dirt hide inside an output directory and read as clean."""
    repo = repo or _ROOT
    try:
        lines = _git(["status", "--porcelain", "-uall"], repo).splitlines()
    except Exception:
        return True  # cannot tell, so assume the worst rather than certify a tree we cannot see
    return any(not ln[3:].startswith(output_paths) for ln in lines if ln.strip())


def evidence(repo: pathlib.Path | None = None,
             output_paths: tuple[str, ...] = ()) -> dict[str, object]:
    """What a stamped artifact records about the code that produced it."""
    return {"issuer_commit": code_commit(repo),
            "code_paths": list(CODE_PATHS),
            "dirty": is_dirty(repo, output_paths),
            "rule": ("the last commit touching code_paths, not HEAD: a commit that changes only "
                     "tests, docs or generated output cannot alter these bytes")}
