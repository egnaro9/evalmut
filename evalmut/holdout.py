"""Commitments for a holdout operator set: what can be proved, and what cannot.

TWO PROPERTIES, AND ONLY ONE OF THEM IS AVAILABLE TO A SOLO PROJECT.

A cryptographic commitment normally buys two things:

    BINDING  the committed value cannot be changed after the fact.
    HIDING   the commitment reveals nothing about the value.

A hash published by the same person who revises the suite is BINDING and NOT HIDING. It proves
the holdout was fixed before the suite moved. It cannot prove the author never looked, because
the author already has the plaintext. Any protocol here that implies otherwise would be exactly
the unsupported claim this project exists to make fail, wearing cryptography.

So this module says so in the artifact itself: every commitment carries a `hiding` field naming
who, if anyone, the value is hidden from. A self-held seal records `hiding: "nobody"`.

SALTS ARE NOT OPTIONAL, AND THE REASON IS ARITHMETIC. If a holdout is "k of the 25 operator ids
in this repo", the space of possible sets is small: 300 for k=2, 2,300 for k=3, 53,130 for k=5.
An unsalted digest over a canonical listing can be inverted by enumeration in under a second, so
the commitment would be neither binding-and-hiding nor even weakly private. Every commitment here
mixes a 32-byte random salt, withheld until reveal.

THE INSTANCE THAT ACTUALLY HIDES. A commitment over material that DOES NOT YET EXIST is hiding
against everyone including its author, because there is nothing to peek at. That is a
preregistered SELECTION RULE (a predicate plus a cutoff) rather than a sealed set, and it is the
only construction available to this project today: every externally sourced defect it knows about
is either already implemented or already published in the backlog. `KIND_RULE` exists for that
case and `KIND_SET` for the ordinary sealed-set case, and they are labelled differently on
purpose.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import secrets
import subprocess
from dataclasses import dataclass, field

KIND_SET = "sealed-set"    # the holdout's contents exist now and are withheld
KIND_RULE = "preregistered-rule"  # the contents do not exist yet; a predicate selects them later

COMMITMENT_VERSION = 1

# The digest recipe, recorded IN the commitment rather than only in this file. An auditor who has
# the published JSON and nothing else must be able to recompute the seal; a commitment whose
# verification procedure lives only in the code that produced it is checkable by its author alone.
ALGORITHM = {
    "hash": "sha256",
    "input": "utf8(salt) || 0x00 || canonical_json(payload)",
    "canonical_json": "json.dumps(payload, sort_keys=True, separators=(',',':'), "
                      "ensure_ascii=False) encoded utf-8",
    "salt": "32 random bytes, hex-encoded to 64 characters, withheld until reveal",
}


class HoldoutError(ValueError):
    """A commitment is malformed, was changed after sealing, or leaked its own contents."""


def canonical(payload) -> bytes:
    """One byte-string for a value, so a commitment is over content and never over formatting.

    Sorted keys and no insignificant whitespace: a reformat of the manifest must not look like a
    different holdout, and a different holdout must not be reachable by reformatting."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest(payload, salt: str) -> str:
    if not salt or len(salt) < 32:
        raise HoldoutError(
            "refusing to commit with a short or empty salt. The set of plausible holdouts is "
            "small enough to enumerate, so an unsalted digest can be inverted and the commitment "
            "would protect nothing.")
    return hashlib.sha256(salt.encode("utf-8") + b"\x00" + canonical(payload)).hexdigest()


def new_salt() -> str:
    return secrets.token_hex(32)


@dataclass(frozen=True)
class Commitment:
    """The public half of a seal. Contains no holdout content by construction."""

    version: int
    instance: str            # e.g. "001"
    kind: str                # KIND_SET or KIND_RULE
    sha256: str              # salted digest of the sealed payload
    sealed_at: str           # ISO date, supplied by the caller, never read from the clock here
    sealed_at_commit: str    # the repo commit this seal is anchored to
    hiding: str              # WHO the value is hidden from. "nobody" for a self-held seal.
    reveal_after: str        # the earliest date the salt and payload may be published
    revision_boundary: str   # what counts as a suite revision, in words a reader can check
    rotation: str            # what replaces this holdout once it is revealed
    payload_location: str    # where the plaintext lives, for a set; "n/a, does not exist yet"
    algorithm: dict = field(default_factory=lambda: dict(ALGORITHM))
    public_rule: dict = field(default_factory=dict)  # for KIND_RULE, the predicate IS public

    def to_json(self) -> str:
        d = {k: getattr(self, k) for k in
             ("version", "instance", "kind", "sha256", "sealed_at", "sealed_at_commit", "hiding",
              "reveal_after", "revision_boundary", "rotation", "payload_location", "algorithm",
              "public_rule")}
        return json.dumps(d, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    @staticmethod
    def from_json(text: str) -> "Commitment":
        d = json.loads(text)
        missing = [k for k in ("version", "instance", "kind", "sha256", "sealed_at",
                               "sealed_at_commit", "hiding", "reveal_after", "revision_boundary",
                               "rotation", "payload_location") if k not in d]
        if missing:
            raise HoldoutError(f"commitment is missing {missing}")
        if d["version"] != COMMITMENT_VERSION:
            raise HoldoutError(f"unknown commitment version {d['version']!r}")
        if d["kind"] not in (KIND_SET, KIND_RULE):
            raise HoldoutError(f"unknown holdout kind {d['kind']!r}")
        if "algorithm" not in d:
            raise HoldoutError(
                "commitment does not record how its digest is computed. Verification would depend "
                "on code the auditor may not have, which makes the seal checkable only by its "
                "author.")
        known = {"version", "instance", "kind", "sha256", "sealed_at", "sealed_at_commit",
                 "hiding", "reveal_after", "revision_boundary", "rotation", "payload_location",
                 "algorithm", "public_rule"}
        extra = set(d) - known
        if extra:
            raise HoldoutError(f"commitment carries unrecognised fields {sorted(extra)}")
        return Commitment(**{k: d[k] for k in d})


def seal(payload, *, instance: str, kind: str, sealed_at: str, sealed_at_commit: str,
         hiding: str, reveal_after: str, revision_boundary: str, rotation: str,
         payload_location: str, public_rule: dict | None = None,
         salt: str | None = None, now_utc: str | None = None) -> tuple[Commitment, str]:
    """Produce (public commitment, salt). The salt is the caller's to withhold until reveal.

    A KIND_RULE seal REQUIRES `now_utc` and refuses a cutoff that is not strictly in the future.
    Instance 001 shipped with a cutoff sixteen minutes in the past, which opened a retroactive
    window in which a qualifying report could already have existed. Nothing was filed in it, so
    the set was unaffected, but the hiding claim stopped being guaranteed by construction and
    became an empirical check. That defect was recorded in a note; a note is a promise, and this
    is the gate that keeps it."""
    if kind == KIND_RULE:
        cutoff = (payload or {}).get("cutoff_utc")
        if not cutoff:
            raise HoldoutError(
                "a preregistered rule must state a cutoff_utc. Without one there is no moment "
                "before which the material provably did not exist, which is the only thing that "
                "makes a rule hiding rather than merely binding.")
        if not now_utc:
            raise HoldoutError(
                "sealing a rule requires now_utc so the cutoff can be checked against it. "
                "Refusing to seal a rule whose futurity nobody verified.")
        if cutoff <= now_utc:
            raise HoldoutError(
                f"cutoff_utc {cutoff} is not strictly after the sealing moment {now_utc}. That "
                "opens a retroactive window in which qualifying material may already exist, so "
                "the seal would be binding but not hiding while claiming otherwise. Move the "
                "cutoff past the seal.")
    s = salt or new_salt()
    c = Commitment(version=COMMITMENT_VERSION, instance=instance, kind=kind,
                   sha256=digest(payload, s), sealed_at=sealed_at,
                   sealed_at_commit=sealed_at_commit, hiding=hiding, reveal_after=reveal_after,
                   revision_boundary=revision_boundary, rotation=rotation,
                   payload_location=payload_location, algorithm=dict(ALGORITHM),
                   public_rule=public_rule or {})
    return c, s


def verify(commitment: Commitment, payload, salt: str) -> None:
    """Recompute the seal at reveal time. Raises with the two digests rather than returning False,
    because a silent boolean is how a failed verification becomes a shrug."""
    got = digest(payload, salt)
    if got != commitment.sha256:
        raise HoldoutError(
            f"holdout {commitment.instance} does not match its commitment. Sealed "
            f"{commitment.sha256}, revealed {got}. Either the payload changed after sealing or "
            "the salt is wrong. A holdout that fails this check has no evidential value and must "
            "be discarded rather than re-sealed.")


# ---------------------------------------------------------------- adversarial checks

def scan_for_disclosure(root: pathlib.Path, secrets_: list[str],
                        allow: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """Find any holdout identifier that has leaked into the tree that is about to be published.

    THE FAILURE THIS CATCHES is mundane and fatal: a holdout id pasted into a changelog, a test
    name, a docstring, or a commit-adjacent note. It does not need malice, only autocomplete.
    Returns (path, secret) pairs so the caller can name every leak, not just the first."""
    hits: list[tuple[str, str]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or ".git/" in str(p) or any(a in str(p) for a in allow):
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        for s in secrets_:
            if s and s in text:
                hits.append((str(p.relative_to(root)), s))
    return hits


def revisions_since(repo: pathlib.Path, commit: str, paths: tuple[str, ...]) -> list[str]:
    """Commits touching the suite since the seal. The revision boundary, made countable.

    Ambiguity about WHEN a revision happened is how a holdout result gets argued away after the
    fact, so the boundary is a commit range over named paths rather than a date or a memory."""
    out = subprocess.run(["git", "-C", str(repo), "log", "--format=%H %s",
                          f"{commit}..HEAD", "--", *paths],
                         capture_output=True, text=True, check=True).stdout.strip()
    return [ln for ln in out.splitlines() if ln]


def seal_precedes_revisions(repo: pathlib.Path, commit: str) -> bool:
    """The seal must be an ANCESTOR of HEAD, or the ordering claim is not checkable.

    A commitment anchored to a commit that is not reachable from HEAD proves nothing about what
    came first, which is the entire point of sealing."""
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, "HEAD"],
                          capture_output=True).returncode == 0
