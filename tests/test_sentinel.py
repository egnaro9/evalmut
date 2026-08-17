"""The sentinel held to the standard it exists to enforce: proven in BOTH directions.

A sentinel that reports "invoked" is worth nothing unless it can be shown reporting "not invoked"
on a path that genuinely did not run. That is the whole failure it was built against, so the
negative case is the load-bearing test here, not the positive one.
"""
from __future__ import annotations

import pytest

from evalmut.sentinel import UpstreamNeverRan, require_invoked, sentinel


class FakeMetric:
    """Stands in for an installed library's metric object."""

    def __init__(self, score=0.75):
        self._score = score

    def measure(self, case):
        return self._score

    def explode(self, case):
        raise ValueError("upstream blew up")


class ShortCircuitAdapter:
    """The failure mode in the wild: an adapter that answers for the library it names. The import
    is real, `measure` exists, the number looks fine, and the method is never entered."""

    def __init__(self, metric):
        self.metric = metric

    def score(self, case):
        if case == "cached":
            return 0.75          # same value the metric would have returned
        return self.metric.measure(case)


def test_sentinel_records_a_real_invocation():
    m = FakeMetric(0.75)
    with sentinel(m, "measure") as w:
        assert m.measure("x") == 0.75
    assert w.invoked and w.calls == 1
    assert w.raw_score() == 0.75


def test_sentinel_catches_a_path_that_never_ran():
    """The load-bearing case. The adapter returns the RIGHT number without touching the metric,
    so every downstream check passes and only the sentinel can tell the difference."""
    m = FakeMetric(0.75)
    a = ShortCircuitAdapter(m)
    with sentinel(m, "measure") as w:
        assert a.score("cached") == 0.75      # correct-looking answer
    assert not w.invoked, "the sentinel failed to notice the upstream was bypassed"
    assert w.raw_score() is None
    with pytest.raises(UpstreamNeverRan, match="never called"):
        require_invoked(w, context="cached row")


def test_require_invoked_is_silent_when_the_path_ran():
    m = FakeMetric()
    a = ShortCircuitAdapter(m)
    with sentinel(m, "measure") as w:
        a.score("live")
    require_invoked(w)      # must not raise


def test_sentinel_records_but_reraises_an_upstream_exception():
    """Swallowing the error would manufacture the silence the sentinel exists to detect."""
    m = FakeMetric()
    with pytest.raises(ValueError, match="blew up"):
        with sentinel(m, "explode") as w:
            m.explode("x")
    assert w.calls == 1
    assert w.raised and "ValueError" in w.raised[0]
    assert w.raw_score() is None


def test_sentinel_restores_the_method_even_when_the_body_raises():
    """A half-patched library would leak into the next case and taint it."""
    m = FakeMetric()
    before = FakeMetric.measure
    with pytest.raises(RuntimeError):
        with sentinel(m, "measure"):
            raise RuntimeError("body failed")
    assert "measure" not in vars(m), "an instance override survived the block"
    assert FakeMetric.measure is before
    assert m.measure("x") == 0.75


def test_multiple_calls_are_all_counted():
    m = FakeMetric(0.5)
    with sentinel(m, "measure") as w:
        for _ in range(3):
            m.measure("x")
    assert w.calls == 3
    assert w.returns == [0.5, 0.5, 0.5]


def test_evidence_is_serializable():
    m = FakeMetric(0.25)
    with sentinel(m, "measure") as w:
        m.measure("x")
    ev = w.as_evidence()
    assert ev["invoked"] is True and ev["calls"] == 1
    import json
    json.loads(json.dumps(ev))      # must survive the report layer
