"""The scorer population and its denominator, declared before a run rather than chosen after one.

THE AMBIGUITY THIS EXISTS TO REMOVE. In the pilot, several defensible denominators were available
and each could only be picked after the outcomes were visible: all discovered scorers, the ones
the harness could drive, the ones that returned a verdict, the ones whose verdict was
interpretable. Every one of those is arguable. Arguable AFTER the fact is the problem, because the
choice then carries information about the results, and a rate whose denominator was selected that
way is not a measurement of anything.

So the population is a CONTRACT. Every reachable scorer is discovered, given a stable identity,
and assigned exactly one disposition with a named predicate. The whole thing is canonically
serialised and hashed BEFORE execution, and the digest is bound into the run bundle. A denominator
is then not a number someone wrote down; it is the deterministic result of a named query over the
sealed inventory.

FAIL CLOSED, IN BOTH DIRECTIONS. A discovered scorer missing from the inventory stops the build,
because silent omission is exactly how a denominator shrinks to flatter a result. A scorer the
runner meets that the inventory never declared also stops the run, because the population that was
sealed is not the population being measured.

WHAT THIS DELIBERATELY CANNOT DO. It cannot tell whether a disposition is CORRECT. Calling a
scorer `unsupported` when it is merely inconvenient is a judgement, and the enumerated predicate
plus a written rationale is what makes that judgement reviewable by someone else rather than
invisible.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum

INVENTORY_VERSION = 1


class Disposition(str, Enum):
    """Exactly one per scorer. There is no default and no implicit fourth state."""

    INCLUDED = "included"        # in the denominator
    EXCLUDED = "excluded"        # deliberately out of scope for this study
    INFEASIBLE = "infeasible"    # cannot be driven by this harness, for a stated mechanical reason
    UNSUPPORTED = "unsupported"  # out of the tool's remit by design, e.g. non-deterministic


# Enumerated so a disposition cannot be justified by improvisation. "not applicable" on its own is
# the kind of reason that stops a reader asking the next question, which is why it is not here.
PREDICATES = {
    "non_deterministic": "verdict depends on a live provider or other uncontrolled input",
    "no_verdict": "returns no pass/fail verdict, so a mutation cannot change an outcome",
    "message_only": "affects explanation text while the verdict and score are unchanged",
    "performance_only": "affects time or memory, never the verdict",
    "parameter_surface": "the defect lives in the assertion's parameters, not the model output",
    "harness_incompatible": "cannot be invoked by this harness for a stated technical reason",
    "requires_network": "cannot run in the sealed environment without external access",
    "duplicate_of": "same underlying scorer already counted under another identity",
    "out_of_scope_by_design": "outside the study's declared question, stated in the rationale",
}

MIN_RATIONALE = 30


class InventoryError(ValueError):
    """The population, a disposition, or a denominator does not satisfy the contract."""


@dataclass(frozen=True)
class Scorer:
    """A stable identity. Two runs naming the same scorer must produce the same id."""

    suite: str            # e.g. promptfoo/promptfoo
    revision: str         # the pinned commit the population was discovered at
    module_path: str      # import or file path within the suite
    symbol: str           # the function, class or assertion type
    config_digest: str = ""   # hash of the scorer's configuration, when it is configurable
    discovered_by: str = ""   # HOW it was found, so the discovery itself is auditable

    @property
    def id(self) -> str:
        return f"{self.suite}@{self.revision[:12]}:{self.module_path}:{self.symbol}" + (
            f"#{self.config_digest[:8]}" if self.config_digest else "")


@dataclass(frozen=True)
class Row:
    scorer: Scorer
    disposition: Disposition
    predicate: str = ""   # required unless INCLUDED
    rationale: str = ""   # required unless INCLUDED

    def check(self) -> list[str]:
        p: list[str] = []
        if self.disposition is Disposition.INCLUDED:
            if self.predicate or self.rationale:
                # Not an error worth failing a build over, but it signals the row was copied from
                # an excluded one, so it is surfaced rather than silently tolerated.
                p.append(f"{self.scorer.id}: INCLUDED rows should carry no exclusion predicate")
            return p
        if self.predicate not in PREDICATES:
            p.append(f"{self.scorer.id}: predicate {self.predicate!r} is not one of the "
                     f"enumerated predicates {sorted(PREDICATES)}")
        if len((self.rationale or "").strip()) < MIN_RATIONALE:
            p.append(f"{self.scorer.id}: a non-included row needs a rationale of at least "
                     f"{MIN_RATIONALE} characters. 'not applicable' is not a reason.")
        return p


@dataclass(frozen=True)
class Inventory:
    suite: str
    revision: str
    environment: dict
    rows: tuple[Row, ...]
    discovery_method: str = ""
    queries: dict = field(default_factory=dict)  # name -> the disposition set it selects

    def canonical(self) -> bytes:
        payload = {
            "inventory_version": INVENTORY_VERSION,
            "suite": self.suite, "revision": self.revision,
            "environment": self.environment,
            "discovery_method": self.discovery_method,
            "queries": {k: sorted(v) for k, v in self.queries.items()},
            "rows": sorted(
                [{"id": r.scorer.id, "scorer": asdict(r.scorer),
                  "disposition": r.disposition.value,
                  "predicate": r.predicate, "rationale": r.rationale} for r in self.rows],
                key=lambda d: d["id"]),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical()).hexdigest()

    @property
    def ids(self) -> set[str]:
        return {r.scorer.id for r in self.rows}

    def denominator(self, query: str) -> int:
        """A count derived from a NAMED query, never a number typed by a person.

        The query must have been declared in the sealed inventory. Asking for a denominator by
        naming a disposition set at aggregation time is the post-hoc choice this module refuses."""
        if query not in self.queries:
            raise InventoryError(
                f"denominator query {query!r} was not declared in the sealed inventory. Declared "
                f"queries: {sorted(self.queries)}. A denominator chosen after the run is not a "
                "denominator, it is a result.")
        wanted = set(self.queries[query])
        return sum(1 for r in self.rows if r.disposition.value in wanted)


def build(discovered: list[Scorer], dispositions: dict[str, Row], **kw) -> Inventory:
    """Fail closed on a scorer that was found but never dispositioned.

    Silent omission is how a denominator quietly shrinks toward whatever flatters the result, so
    the discovered set is the authority and the inventory must cover all of it."""
    by_id = {s.id: s for s in discovered}
    missing = sorted(set(by_id) - set(dispositions))
    if missing:
        raise InventoryError(
            f"{len(missing)} discovered scorer(s) have no disposition: {missing[:5]}"
            f"{' ...' if len(missing) > 5 else ''}. Every scorer the discovery step found must be "
            "declared, including the ones being left out.")
    extra = sorted(set(dispositions) - set(by_id))
    if extra:
        raise InventoryError(
            f"inventory declares {len(extra)} scorer(s) that discovery never found: {extra[:5]}. "
            "A population cannot contain what was not discovered.")

    rows = tuple(dispositions[i] for i in sorted(by_id))
    problems = [p for r in rows for p in r.check()]
    if problems:
        raise InventoryError("; ".join(problems))
    return Inventory(rows=rows, **kw)


def check_execution(sealed: Inventory, sealed_digest: str, observed: list[Scorer]) -> None:
    """Stop rather than continue when the run meets a population it did not seal."""
    if sealed.digest != sealed_digest:
        raise InventoryError(
            f"inventory digest changed since sealing. Sealed {sealed_digest[:16]}, now "
            f"{sealed.digest[:16]}. Something in the population, a disposition, a predicate or a "
            "declared query moved after the seal.")
    obs = {s.id for s in observed}
    unknown = sorted(obs - sealed.ids)
    if unknown:
        raise InventoryError(
            f"the runner met {len(unknown)} scorer(s) absent from the sealed inventory: "
            f"{unknown[:5]}. The population being measured is not the population that was "
            "declared, so the run is invalid rather than merely incomplete.")


def aggregate(numerator: int, sealed: Inventory, sealed_digest: str, query: str) -> dict:
    """The only sanctioned way to produce a rate. Refuses on any contract mismatch."""
    if sealed.digest != sealed_digest:
        raise InventoryError("cannot aggregate: the inventory digest does not match the seal.")
    d = sealed.denominator(query)
    if d <= 0:
        raise InventoryError(
            f"query {query!r} selects no scorers, so there is no rate to compute. An empty "
            "denominator is not a perfect score.")
    if numerator > d:
        raise InventoryError(
            f"numerator {numerator} exceeds the declared denominator {d} for query {query!r}.")
    return {"numerator": numerator, "denominator": d, "query": query,
            "inventory_digest": sealed_digest, "rate": numerator / d}
