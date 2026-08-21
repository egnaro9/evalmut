"""The stamp names the code that produced the bytes, not whatever HEAD happens to be.

THE RULE THIS PINS. A commit that changes only tests, docs or generated output cannot alter an
emitted artifact, so it must not move that artifact's stamp. A review once asked for the stamp to
equal HEAD after a test-only commit; following that would have made the bundle assert a test edit
regenerated its artifacts, which is the provenance error the stamp exists to prevent.

ONE DEFINITION. emit_vac.py and the witness run both stamp. Two copies of the rule would drift,
and a drifted stamp is worse than no stamp: it names a commit with authority it does not have.
"""
import pathlib
import subprocess
import sys

import pytest

from evalmut import stamp

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_code_paths_exclude_tests_docs_and_generated_output():
    for excluded in ("tests", "docs", "vac", "README.md"):
        assert excluded not in stamp.CODE_PATHS, (
            f"{excluded!r} is in CODE_PATHS, so a change there would move the stamp even though "
            f"it cannot change an emitted byte")
    assert "evalmut" in stamp.CODE_PATHS
    assert "emit_vac.py" in stamp.CODE_PATHS


def test_emit_vac_and_the_witness_share_one_definition():
    """Not merely equal: the SAME object, so they cannot drift apart."""
    sys.path.insert(0, str(ROOT))
    import emit_vac
    assert emit_vac.CODE_PATHS is stamp.CODE_PATHS, (
        "emit_vac keeps its own CODE_PATHS; two copies of the stamp rule will drift")


def test_the_stamp_is_the_last_code_commit_not_head():
    got = stamp.code_commit()
    expected = subprocess.run(
        ["git", "log", "-1", "--format=%h", "--abbrev=7", "--", *stamp.CODE_PATHS],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert got == expected
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()
    # They MAY be equal. The point is that the stamp is not DEFINED as HEAD.
    assert got == expected, f"stamp {got} is not the last code commit {expected}"
    if got != head:
        touched = subprocess.run(["git", "show", "--name-only", "--format=", head], cwd=ROOT,
                                 capture_output=True, text=True, check=True).stdout.split()
        assert not any(f.startswith(stamp.CODE_PATHS) for f in touched), (
            f"HEAD {head} touched a code path but the stamp is {got}")


def test_a_dirty_tree_is_recorded_rather_than_hidden():
    """The witness run records `dirty` instead of refusing, because tests invoke it as a
    subprocess and refusing would make an ordinary edit break the suite. Recording it is only
    safe because a consumer is expected to refuse a dirty stamp before publishing a claim."""
    ev = stamp.evidence(output_paths=("docs/", "external/", "vac/"))
    assert set(ev) == {"issuer_commit", "code_paths", "dirty", "rule"}
    assert isinstance(ev["dirty"], bool)
    assert ev["issuer_commit"] == stamp.code_commit()


def test_an_unreadable_repo_reports_dirty_rather_than_clean(tmp_path):
    """A tree we cannot inspect must never certify as clean. Absence of evidence is not evidence
    of cleanliness, which is the failure mode this project keeps finding."""
    assert stamp.is_dirty(tmp_path) is True, (
        "a non-repository reported clean; an unreadable tree must fail closed")
    assert stamp.code_commit(tmp_path) == "", "a non-repository must not invent a commit"
