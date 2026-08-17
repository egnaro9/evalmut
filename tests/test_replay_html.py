"""The replay held to the one thing that could make it dishonest.

An interface that paces work theatrically while implying live computation is lying about where
its numbers came from. This tool would have no standing to make that mistake, so the tests below
check the disclosure and the inertness, not the animation.
"""
from __future__ import annotations

import json
import re

import pytest

from evalmut.replay_html import render_replay_html

RUN = {"score": 0.9, "tally": {"caught": 9, "missed": 1, "na": 5},
       "results": [
           {"case_name": "capital", "operator_id": "garbage_answer", "family": "answer",
            "polarity": "defect", "outcome": "missed", "detail": "grader passed the mutant",
            "mutant_preview": "zxqfp wgbrtl"},
           {"case_name": "capital", "operator_id": "case_variant", "family": "equivalent",
            "polarity": "equivalent", "outcome": "na", "detail": "n/a", "mutant_preview": ""},
       ]}


def test_it_says_on_its_face_that_it_is_a_replay():
    """The load-bearing test. A viewer must not be able to come away believing this page ran
    anything, because it did not."""
    out = render_replay_html(RUN)
    assert "This is a replay, not a live run" in out
    assert "executes no grader" in out or "executes no grader" in out.replace("\n", " ")
    assert "cannot find anything the run did not" in out.replace("\n", " ")


def test_it_admits_the_pacing_is_not_a_measurement():
    """Per-mutation timings are not in the export. Inventing durations would read as data."""
    out = render_replay_html(RUN)
    assert "not a measurement" in out


def test_it_reaches_no_network():
    out = render_replay_html(RUN)
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', out)
    assert "fetch(" not in out and "XMLHttpRequest" not in out
    assert "@import" not in out


def test_every_row_comes_from_the_payload():
    out = render_replay_html(RUN)
    blob = re.search(r'<script id="d" type="application/json">(.*?)</script>', out, re.S).group(1)
    data = json.loads(blob)
    assert len(data["steps"]) == len(RUN["results"])
    assert {s["o"] for s in data["steps"]} == {"garbage_answer", "case_variant"}


def test_a_decline_is_explained_rather_than_shown_as_a_bare_na():
    """The whole reason this page exists: n/a read cold looks like skipped work."""
    out = render_replay_html(RUN)
    assert "refused to guess" in out
    assert "could not prove" in out


def test_it_refuses_a_payload_with_no_rows():
    """Silently rendering an empty replay would imply a run with nothing in it."""
    with pytest.raises(ValueError, match="--json --all"):
        render_replay_html({"score": 1.0, "tally": {}, "results": []})
