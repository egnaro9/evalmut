"""The VAC bundle held to evalmut's own standard: a gate must be proven in
both directions. Freshness — the battery and the manifest re-emit
byte-identical to the committed artifacts, twice over. Liveness — a
tampered results artifact changes the re-emitted bundle (so the CI
`git status` gate over docs/ external/ vac/ cannot stay green over a
cooked artifact), and the stamp's two refusals fire on a throwaway repo.
A freshness gate that was never seen red, and a stamp that was never seen
refusing, would be exactly the vacuous checks this tool exists to catch.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import emit_vac  # noqa: E402


@pytest.fixture(scope="module")
def battery():
    return emit_vac.run_battery()


# ── freshness: emit twice → byte-identical, and identical to what is committed

def test_battery_is_byte_stable(battery):
    assert emit_vac.run_battery() == battery


def test_battery_reproduces_the_committed_artifacts(battery):
    for home, data in battery.items():
        assert (ROOT / home).read_bytes() == data, (
            f"{home}: committed bytes are not what the code re-emits — "
            "run `python emit_vac.py` and commit the diff")


def test_committed_bundle_is_closed_and_derived(battery):
    """vac/ holds byte-copies of exactly the five listed artifacts plus a
    manifest that is a pure function of those bytes and the stamped commit
    — a re-authored number, a stale copy, or a smuggled file all fail."""
    names = {pathlib.PurePosixPath(h).name: h for _, h in emit_vac.ARTIFACTS}
    assert sorted(p.name for p in (ROOT / "vac").iterdir()) == sorted(
        [*names, "vac.json"])
    committed = (ROOT / "vac/vac.json").read_text(encoding="utf-8")
    man = json.loads(committed)
    assert sorted(e["path"] for e in man["evidence"]) == sorted(names)
    for e in man["evidence"]:
        data = (ROOT / "vac" / e["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == e["sha256"]
        assert data == battery[names[e["path"]]]
    regen = emit_vac.build_manifest(battery, man["protocol"]["issuer_commit"])
    assert regen == committed


def test_manifest_is_byte_stable(battery):
    assert emit_vac.build_manifest(battery, "abc1234") == \
        emit_vac.build_manifest(battery, "abc1234")


# ── liveness: a tampered artifact cannot survive re-emission ────────────────

def test_tampered_rows_change_the_manifest(battery):
    """Relabel one missed row as caught: the sha256 pin AND the derived
    counts both move (derive() reads only the rows, never the payload's own
    aggregates), so the freshness gate fires on the cooked artifact."""
    key = "docs/dogfood_gradecore.json"
    payload = json.loads(battery[key])
    row = next(r for r in payload["results"] if r["outcome"] == "missed")
    row["outcome"] = "caught"
    tampered = {**battery,
                key: (json.dumps(payload, indent=2) + "\n").encode()}
    honest = json.loads(emit_vac.build_manifest(battery, "abc1234"))
    cooked = json.loads(emit_vac.build_manifest(tampered, "abc1234"))
    assert [e["sha256"] for e in honest["evidence"]] != \
        [e["sha256"] for e in cooked["evidence"]]
    h, c = (m["results"]["checks"][0]["expect"] for m in (honest, cooked))
    assert c["caught"] == h["caught"] + 1
    assert c["missed"] == h["missed"] - 1


# ── the stamp must still be ON this branch, not merely correct when written ─

def test_committed_stamp_is_reachable_from_head():
    """Freshness proves the artifacts match the code. It does NOT prove the commit the
    manifest names is still on this branch, and a history rewrite breaks the second while
    leaving the first perfectly green: every SHA moves, every byte stays. The bundle then
    tells a replayer to check out a commit that is not there.

    Not skipped on a shallow clone. A skip reads green, which is the failure this whole file
    exists to prevent, so the helper raises and the test fails loudly with the fix in the
    message."""
    manifest = json.loads((ROOT / "vac/vac.json").read_text(encoding="utf-8"))
    stamp = manifest["protocol"]["issuer_commit"]
    assert emit_vac.stamp_is_reachable(stamp), (
        f"vac.json names issuer_commit {stamp}, which is not an ancestor of HEAD. "
        "A rebase, squash, or amend rewrote history after the bundle was emitted; "
        "re-run emit_vac.py so the stamp names a commit that exists here.")


def test_reachability_check_fires_on_an_orphaned_stamp(toy_repo):
    """Liveness for the gate above, reproducing the real incident: commit, record the SHA,
    then rewrite history so that SHA is orphaned. The check must go False."""
    orphaned = subprocess.run(["git", "rev-parse", "HEAD"], cwd=toy_repo,
                              capture_output=True, text=True, check=True).stdout.strip()
    assert emit_vac.stamp_is_reachable(orphaned, toy_repo), "sanity: own HEAD is reachable"
    _git(toy_repo, "commit", "-q", "--amend", "-m", "rewritten")
    assert not emit_vac.stamp_is_reachable(orphaned, toy_repo), (
        "the amended-away commit still read as reachable — the gate cannot fire")


def test_reachability_refuses_a_shallow_clone(tmp_path, toy_repo):
    """A shallow clone cannot see its own history. Answering False there would falsely accuse
    a good stamp; answering True would be a check that passed because it could not look. It
    must refuse instead."""
    _git(toy_repo, "commit", "-q", "--allow-empty", "-m", "second")
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{toy_repo}", str(shallow)],
                   check=True, capture_output=True)
    with pytest.raises(RuntimeError, match="shallow"):
        emit_vac.stamp_is_reachable("HEAD", shallow)


# ── the stamp's two refusals, live on a throwaway repo ──────────────────────

def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def toy_repo(tmp_path):
    repo = tmp_path / "r"
    (repo / "evalmut").mkdir(parents=True)
    (repo / "evalmut" / "core.py").write_text("x = 1\n")
    (repo / "docs").mkdir()
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "code")
    return repo


def test_stamp_refuses_a_dirty_tree(toy_repo):
    (toy_repo / "evalmut" / "core.py").write_text("x = 2\n")
    with pytest.raises(RuntimeError, match="refusing to stamp"):
        emit_vac.stamp_code_commit(toy_repo)


def test_stamp_ignores_output_dirt_and_tracks_only_code_commits(toy_repo):
    code = emit_vac.stamp_code_commit(toy_repo)
    # the emitter's own outputs may be dirty (they are what is being emitted)
    (toy_repo / "docs" / "dogfood_gradecore.json").write_text("{}\n")
    assert emit_vac.stamp_code_commit(toy_repo) == code
    # an outputs-only commit must NOT move the stamp: CI re-runs the emitter
    # at the results commit expecting byte-identity, stamp included
    _git(toy_repo, "add", ".")
    _git(toy_repo, "commit", "-qm", "results")
    assert emit_vac.stamp_code_commit(toy_repo) == code
    # a code commit must move it
    (toy_repo / "evalmut" / "core.py").write_text("x = 3\n")
    _git(toy_repo, "add", ".")
    _git(toy_repo, "commit", "-qm", "code2")
    assert emit_vac.stamp_code_commit(toy_repo) != code
