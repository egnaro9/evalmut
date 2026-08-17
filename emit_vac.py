"""Emit evalmut's own results as a CLOSED VAC bundle (vac-protocol SPEC
v0.1, profile evalmut-run-v1): `vac/` = `vac.json` plus byte-copies of
exactly the five artifacts the manifest lists, nothing else.

One run (re)writes both the canonical committed artifacts and the bundle:

    docs/dogfood_gradecore.txt        evalmut run demos/dogfood_gradecore.py
    docs/dogfood_gradecore.json       …same, --json --all (the raw rows)
    external/promptfoo_findings.txt   evalmut run external/promptfoo_suite.py
    external/promptfoo_findings.json  …same, --json --all
    docs/operators.json               evalmut operators --json

Each artifact is the exact stdout bytes of the command line a stranger
would run — captured from a real subprocess, never an in-process
shortcut — so the replay recipe's byte-compare is like against like.
Everything in the manifest is DERIVED, never authored: the stamp from git
history (with the fleet's dirty-tree refusal), the declared numbers
recomputed from the per-mutation rows exactly as vac-protocol's verifier
recomputes them, the sha256s from the just-written bytes. No clock
anywhere, so re-emission is byte-identical and a `git status` gate over
docs/ external/ vac/ is a freshness+liveness gate for the whole bundle:
a tampered artifact or a re-authored number cannot survive a re-run.

`python emit_vac.py` — exits nonzero only on a real failure. The
`evalmut run` calls inside it exit 1 BY DESIGN (the found holes fail
evalmut's own CI gate; the finding is the result) and are treated as
success here.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ISSUER = "egnaro9/evalmut"

# The battery: CLI argv -> the artifact's canonical committed home. The
# bundle copies each under its basename, so basenames must stay unique.
ARTIFACTS = (
    (("run", "demos/dogfood_gradecore.py"), "docs/dogfood_gradecore.txt"),
    (("run", "demos/dogfood_gradecore.py", "--json", "--all"),
     "docs/dogfood_gradecore.json"),
    (("run", "external/promptfoo_suite.py"), "external/promptfoo_findings.txt"),
    (("run", "external/promptfoo_suite.py", "--json", "--all"),
     "external/promptfoo_findings.json"),
    (("operators", "--json"), "docs/operators.json"),
    # The pinned fixture corpus for each suite in the battery. Emitted the same way as every
    # other artifact (real subprocess, exact stdout bytes) so the freshness gate covers the
    # INPUTS as well as the results: previously a fixture could be reworded after a
    # disappointing run and every check stayed green, because only the operators were pinned.
    (("manifest", "demos/dogfood_gradecore.py"), "docs/dogfood_fixtures.json"),
    (("manifest", "external/promptfoo_suite.py"), "external/promptfoo_fixtures.json"),
)

# Inputs whose bytes ARE the protocol: hashed into protocol.hashes so the
# claim is pinned to these exact suites, not "the suites, roughly".
SUITE_INPUTS = {
    "dogfood_suite_sha256": "demos/dogfood_gradecore.py",
    "promptfoo_suite_sha256": "external/promptfoo_suite.py",
    "promptfoo_assertions_sha256": "external/promptfoo_assertions.py",
}

# Every path whose bytes can change the emitted artifacts. tests/ and prose
# are deliberately excluded: a commit that cannot move the results must not
# move the stamp (the fleet discipline — results land in a follow-up commit
# touching only outputs, and CI re-runs the emitter there expecting
# byte-identity, stamp included).
CODE_PATHS = ("evalmut", "demos/dogfood_gradecore.py",
              "external/promptfoo_suite.py",
              "external/promptfoo_assertions.py",
              "pyproject.toml", "emit_vac.py")

# The only paths allowed to be dirty when stamping: the emitter's own
# outputs. Anything else dirty means the stamped commit would not contain
# the code that produced these bytes.
OUTPUT_PATHS = tuple(home for _, home in ARTIFACTS) + ("vac/",)

# Hole classes in report rank order: class -> (outcome, op_type or None).
# Mirrors evalmut/score.py and vac-protocol's evalmut-run-v1 recomputation.
HOLE_CLASSES = (("vacuous", "missed", "sanity"),
                ("blind", "missed", "kill"),
                ("error", "error", None),
                ("brittle", "flagged", None),
                ("coverage_gap", "missed", "diagnostic"))


def stamp_is_reachable(commit: str, repo: pathlib.Path = ROOT) -> bool:
    """Is the stamped commit an ancestor of HEAD in this repo?

    The freshness gate proves the artifacts are what the code re-emits. It says nothing about
    whether the commit the manifest NAMES still exists on this branch, and those are different
    facts: rebasing, squashing, or amending rewrites every SHA while leaving each artifact byte
    for byte identical. The bundle then points a replayer at `git checkout <sha>` for a commit
    that is not there, and every other check stays green. Found the hard way, by hand, after a
    `git rebase --signoff` orphaned a stamp that freshness had just certified.

    Raises on a shallow clone rather than answering. A shallow repo cannot see its own history,
    so it would report unreachable for a perfectly good stamp; returning False there would be a
    false accusation and returning True would be a gate that passed because it could not look."""
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=repo,
        capture_output=True, text=True, check=True).stdout.strip()
    if shallow == "true":
        raise RuntimeError(
            "cannot check stamp reachability in a shallow clone: history is truncated, so a "
            "reachable stamp would read as missing. Check out with fetch-depth: 0.")
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=repo, capture_output=True).returncode == 0


def stamp_code_commit(repo: pathlib.Path = ROOT) -> str:
    """The publication stamp, with the fleet's two refusals: dirty tree,
    no code commit."""
    # -uall: porcelain collapses a fully-untracked directory to one `?? dir/`
    # line, which would defeat the exact-path allowlist below in both
    # directions (output dirt misread as code dirt, or code dirt hidden
    # inside an output directory). List every file individually.
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "-uall"], cwd=repo,
        capture_output=True, text=True, check=True).stdout.splitlines()
    outside = [ln for ln in dirty if not ln[3:].startswith(OUTPUT_PATHS)]
    if outside:
        raise RuntimeError(
            "refusing to stamp a dirty tree — the stamped commit must "
            "contain the exact code that produced these artifacts. "
            "Commit first:\n" + "\n".join(outside))
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%h", "--abbrev=7", "--", *CODE_PATHS],
        cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    if not commit:
        raise RuntimeError("git log returned no code commit; cannot stamp")
    return commit


def run_battery(python: str = sys.executable) -> dict[str, bytes]:
    """{canonical repo-relative path: exact CLI stdout bytes}. UTF-8 is
    forced in the children so a non-UTF-8 locale cannot degrade the report
    glyphs (cli.py backslashreplace) and silently change bytes."""
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    out: dict[str, bytes] = {}
    for argv, home in ARTIFACTS:
        proc = subprocess.run([python, "-m", "evalmut.cli", *argv],
                              cwd=ROOT, env=env, capture_output=True)
        # `evalmut run` exits 1 BY DESIGN when it finds serious holes — the
        # finding is the result. Anything else is a real failure.
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                f"evalmut {' '.join(argv)} exited {proc.returncode}:\n"
                + proc.stderr.decode(errors="replace"))
        if not proc.stdout:
            raise RuntimeError(f"evalmut {' '.join(argv)} produced no output")
        out[home] = proc.stdout
    return out


def derive(payload: bytes) -> dict:
    """Every declared number recomputed from the payload's per-mutation
    rows — the same recomputation vac-protocol's evalmut-run-v1 check
    performs, and nothing read from the payload's own aggregates, so the
    manifest can never declare what the verifier would not re-earn."""
    rows = json.loads(payload)["results"]
    d = {k: sum(1 for r in rows if r["outcome"] == k)
         for k in ("caught", "missed", "flagged", "error", "na")}
    d["applied"] = d["caught"] + d["missed"] + d["flagged"]
    d["results"] = len(rows)
    d["score_3"] = round(
        1.0 if d["applied"] == 0 else d["caught"] / d["applied"], 3)
    for cls, outcome, op_type in HOLE_CLASSES:
        if cls != "error":  # the error hole count IS the error tally
            d[cls] = sum(1 for r in rows if r["outcome"] == outcome
                         and (op_type is None or r["op_type"] == op_type))
    d["operators_exercised"] = len({r["operator_id"] for r in rows})
    return d


def _holes(d: dict) -> dict:
    return {cls: d[cls] for cls, _, _ in HOLE_CLASSES if d[cls]}


def build_manifest(artifacts: dict[str, bytes], commit: str) -> str:
    """The vac.json text — a pure function of the artifact bytes and the
    stamped commit (plus the committed suite inputs those bytes came from)."""
    import importlib.metadata

    import evalmut  # the checkout's own package (script dir on sys.path)

    gradecore_v = importlib.metadata.version("gradecore")
    dog = derive(artifacts["docs/dogfood_gradecore.json"])
    pf = derive(artifacts["external/promptfoo_findings.json"])
    ops = json.loads(artifacts["docs/operators.json"])
    manifest = {
        "vac_version": "0.1",
        "claim": {
            "capability": (
                "eval-suite mutation testing over a mined operator "
                f"battery: gradecore's own grader-family suite scores "
                f"{dog['caught']}/{dog['applied']} with "
                f"{dog['blind'] + dog['coverage_gap'] + dog['vacuous'] + dog['brittle'] + dog['error']} "
                f"holes, and the committed ports of promptfoo's documented "
                f"deterministic assertions score {pf['caught']}/"
                f"{pf['applied']} with "
                f"{pf['blind'] + pf['coverage_gap'] + pf['vacuous'] + pf['brittle'] + pf['error']} "
                "holes — every number recomputable from committed "
                "per-mutation rows"),
            "scope": (
                "exactly the two committed suites at the stamped commit — "
                "demos/dogfood_gradecore.py (gradecore "
                f"{gradecore_v}'s grader families, their documented "
                "scoping the ground truth) and external/promptfoo_suite.py "
                "(committed ports of promptfoo's documented deterministic "
                "assertions) — mutated by the operator battery pinned in "
                "operators.json and graded by each suite's own graders; "
                "deterministic throughout: no LLM judge, no sampling, no "
                "network, no clock"),
            "limitations": [
                "injected defects are author-chosen: every operator is "
                "mined from a real, documented failure (real_origin in "
                "operators.json) but the selection is still the issuer's — "
                "a score over this battery bounds nothing about defect "
                "classes outside it; certified-defect ground truth is "
                "reference-fleet's job, not this bundle's",
                "the promptfoo findings grade committed PORTS of "
                "promptfoo's documented deterministic assertion semantics "
                "(external/promptfoo_assertions.py), not promptfoo's "
                "shipped codebase, and say nothing about its LLM-judged "
                "assertion types",
                f"the dogfood findings are claims about gradecore "
                f"{gradecore_v}'s documented grader scopings; a later "
                "gradecore that widens a grader dissolves them — replay "
                f"must install gradecore=={gradecore_v}",
                "operators that cannot establish a mutant's polarity for a "
                "case return n/a and leave the score's denominator "
                f"({dog['na']} and {pf['na']} of the rows here); the score "
                "is over applied mutations only",
                "the paper's process narrative (false-positive convergence "
                "across review passes) is not covered by this bundle: no "
                "committed artifact recomputes it",
                "byte-identity of the two rendered .txt reports requires "
                "UTF-8 output (the emitter forces PYTHONUTF8=1 in its "
                "subprocesses); the .json artifacts are ensure_ascii and "
                "locale-immune",
            ],
        },
        "subject": {
            "kind": "suite-archetype",
            "id": "demos/dogfood_gradecore.py + external/promptfoo_suite.py "
                  "under the evalmut mined-operator battery",
            "version": {"evalmut": evalmut.__version__,
                        "gradecore": gradecore_v,
                        "suites_commit": commit},
        },
        "protocol": {
            "issuer": ISSUER,
            "issuer_commit": commit,
            "task": "mined-operator mutation battery over the two "
                    "committed suites",
            "hashes": {
                name: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
                for name, rel in SUITE_INPUTS.items()},
            "grading": (
                "deterministic: each operator mutates one graded field of "
                "a case with a polarity it must itself establish against "
                "the case's own reference (else n/a), the suite's grader "
                "is re-run on the mutant, and the outcome is classified "
                "caught/missed/flagged/error/na; score = caught/applied; "
                "no sampling, no LLM judge, no clock"),
            "control_policy": (
                "baseline-green enforced per case (a grader failing or "
                "crashing on its own reference output is excluded and "
                "reported by name, never silently scored); EQUIVALENT "
                "mutations are graded beside DEFECT mutations, so a "
                "grader that fails everything reads brittle, not "
                "vigilant; SANITY probes (blank/garbage) expose graders "
                "that cannot fail; a grader that crashes on a defect is "
                "surfaced beside the blind spots, never scored as a "
                "catch"),
        },
        "evidence": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(
                (pathlib.PurePosixPath(home).name, data)
                for home, data in artifacts.items())
        ],
        "results": {
            "summary": {
                "dogfood_gradecore": {
                    "score_3": dog["score_3"], "caught": dog["caught"],
                    "applied": dog["applied"], "na": dog["na"],
                    "holes": _holes(dog)},
                "promptfoo_ports": {
                    "score_3": pf["score_3"], "caught": pf["caught"],
                    "applied": pf["applied"], "na": pf["na"],
                    "holes": _holes(pf)},
                "operators": len(ops),
            },
            "checks": [
                # `render` binds the human-readable .txt to the payload it
                # was rendered from. Both .txt files were pinned by evidence
                # and read by no check, so the bundle carried two artifacts
                # showing headline numbers nothing verified.
                {"profile": "evalmut-run-v1",
                 "artifact": "dogfood_gradecore.json",
                 "catalog": "operators.json",
                 "render": "dogfood_gradecore.txt",
                 "expect": {**dog, "operators": len(ops)}},
                {"profile": "evalmut-run-v1",
                 "artifact": "promptfoo_findings.json",
                 "catalog": "operators.json",
                 "render": "promptfoo_findings.txt",
                 "expect": {**pf, "operators": len(ops)}},
            ],
        },
        "replay": {
            "issuer_commit": commit,
            "commands": [
                f"git clone https://github.com/{ISSUER} issuer",
                f"git -C issuer checkout {commit}",
                f"python -m pip install gradecore=={gradecore_v} ./issuer",
                "( cd issuer && python emit_vac.py )",
                "for f in dogfood_gradecore.txt dogfood_gradecore.json "
                "operators.json promptfoo_findings.txt "
                "promptfoo_findings.json vac.json; "
                "do cmp issuer/vac/$f $f || exit 1; done",
            ],
            "expected": (
                "every command exits 0 and every cmp stays silent: the "
                "emitter re-runs the whole battery at the stamped commit "
                "and re-emits all five artifacts plus vac.json "
                "byte-identical to this bundle (commands run from the "
                "bundle directory). Inside the emitter each `evalmut run` "
                "exits 1 BY DESIGN — the found holes fail evalmut's own "
                "CI gate; the finding is the result — and the emitter "
                "treats exit 0 and 1 both as success. The emitter forces "
                "UTF-8 output in its subprocesses, so locale cannot "
                "perturb the rendered report glyphs."),
        },
    }
    return json.dumps(manifest, indent=1) + "\n"


def emit() -> None:
    commit = stamp_code_commit()
    artifacts = run_battery()
    bundle = ROOT / "vac"
    bundle.mkdir(exist_ok=True)
    # the bundle is CLOSED: refuse to publish around an unexpected rider
    names = {pathlib.PurePosixPath(h).name for h in artifacts} | {"vac.json"}
    for stale in bundle.iterdir():
        if stale.name not in names:
            raise RuntimeError(f"unexpected file in the closed bundle: {stale}")
    for home, data in artifacts.items():
        (ROOT / home).write_bytes(data)
        (bundle / pathlib.PurePosixPath(home).name).write_bytes(data)
    (bundle / "vac.json").write_text(build_manifest(artifacts, commit),
                                     encoding="utf-8")
    print(f"stamped {commit}; wrote {len(artifacts)} artifacts "
          f"+ their byte-copies + vac/vac.json")


if __name__ == "__main__":
    emit()
