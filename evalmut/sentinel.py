"""Proof that the intended scoring path actually ran, instead of an inference that it did.

THE GAP THIS CLOSES. evalmut's claim (a) says a wrapper "imports selected installed deterministic
scorers (import path proven by `inspect.getfile`)". `getfile` proves the right module was loaded.
It does not prove the module's scoring method was ever entered. Between those two facts sits every
way a wrapper can quietly answer for the library it is supposed to be measuring: an adapter that
falls back to its own comparison when the upstream call raises, a metric whose `measure()` returns
a cached attribute set by a previous case, a code path that never reaches the call at all because
a guard above it returned early. In each of those, the import is real, the numbers look plausible,
and the result is a fact about the wrapper rather than about the library. A skeptic reading claim
(a) could hold exactly that, and nothing in the repo refuted it.

A sentinel refutes it per row: patch the upstream method, count entries, capture what it returned,
restore. The recorded count is evidence a reader can check, and a count of zero is a loud failure
rather than a silently plausible score.

WHAT A SENTINEL IS NOT. It proves the method was ENTERED and what it HANDED BACK. It does not
prove the method did anything sensible inside, and it cannot: that is what the mutation operators
are for. Nor does it make a co-adapted fixture independent. It closes one specific hole, the one
between "imported" and "executed", and claiming more from it would be the same overreach it was
built to prevent.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class Witness:
    """What the patched method actually did while the sentinel was installed."""

    target: str
    calls: int = 0
    returns: list[Any] = field(default_factory=list)
    raised: list[str] = field(default_factory=list)

    @property
    def invoked(self) -> bool:
        return self.calls > 0

    def raw_score(self) -> Any:
        """The last value the upstream method handed back, or None if it never ran. Recorded
        alongside evalmut's own verdict so a reader can see the number the LIBRARY produced next
        to the number this tool reports, rather than taking the second on faith."""
        return self.returns[-1] if self.returns else None

    def as_evidence(self) -> dict:
        return {"target": self.target, "invoked": self.invoked, "calls": self.calls,
                "raw_returns": [repr(r)[:200] for r in self.returns],
                "raised": list(self.raised)}


@contextmanager
def sentinel(obj: Any, method: str) -> Iterator[Witness]:
    """Record every entry into `obj.method` for the duration of the block.

    Patches the INSTANCE (or class) attribute and always restores it, including when the body
    raises, so a failing case cannot leave a half-patched library behind for the next one. An
    exception inside the upstream method is recorded and re-raised rather than swallowed: a
    sentinel that ate errors would manufacture the exact silence it exists to detect."""
    original = getattr(obj, method)
    # Whether the attribute lived on the INSTANCE before we touched it, captured now because
    # patching creates one either way and checking afterwards always says yes. Restoring by
    # assignment in the class-attribute case would leave a permanent instance override shadowing
    # the class, which is a leak that outlives the block and only shows up cases later.
    was_own = method in vars(obj)
    w = Witness(target=f"{type(obj).__name__}.{method}")

    def wrapper(*args, **kwargs):
        w.calls += 1
        try:
            out = original(*args, **kwargs)
        except BaseException as e:
            w.raised.append(f"{type(e).__name__}: {e}")
            raise
        w.returns.append(out)
        return out

    setattr(obj, method, wrapper)
    try:
        yield w
    finally:
        if was_own:
            setattr(obj, method, original)
        else:
            delattr(obj, method)


class UpstreamNeverRan(AssertionError):
    """The scoring path this result claims to be about was never entered."""


def require_invoked(w: Witness, context: str = "") -> None:
    """Fail loudly when the upstream path never ran.

    Deliberately an exception, not a warning and not a logged note. A score computed without ever
    entering the library it names is not a weaker result, it is a different claim entirely, and
    letting the run continue would put that claim in the report next to honest ones."""
    if not w.invoked:
        where = f" ({context})" if context else ""
        raise UpstreamNeverRan(
            f"{w.target} was never called{where}: this row's score cannot be a fact about the "
            "upstream scorer. An import proves the module loaded, not that its method ran.")
