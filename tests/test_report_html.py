"""The renderer held to its own claim: it READS a run, it does not recompute one.

The docstring in report_html.py says every number on the page comes from the payload and that if
the page and the terminal disagree, the page is wrong. That is a claim, and an untested claim is
the thing this repo exists to be suspicious of. So the load-bearing test here hands the renderer a
payload whose stated numbers CONTRADICT its own rows, and requires the page to show the stated
ones. A renderer that quietly "fixed" the inconsistency would be deriving verdicts, which is
exactly what it promises not to do.
"""
from __future__ import annotations

import re

from evalmut.report_html import render_html

CLEAN = {"score": 1.0, "tally": {"caught": 4, "missed": 0, "flagged": 0, "error": 0, "na": 2},
         "holes": {"vacuous": [], "blind": [], "error": [], "brittle": [], "coverage_gap": []},
         "results": []}

HOLE = {
    "case_name": "capital", "grader_id": "contains", "operator_id": "spurious_cue_token_insert",
    "family": "presence-proxy", "polarity": "defect", "op_type": "kill", "outcome": "missed",
    "real_origin": "arXiv:1907.07355 : BERT reached 77% off the unigram 'not'",
    "defect_shape": "the grepped keyword carried by text that does none of the work",
    "detail": "grader passed the mutant", "mutant_preview": "zxqfp capital 8H@ac3%o",
}
HOLED = {"score": 0.9, "tally": {"caught": 9, "missed": 1, "flagged": 0, "error": 0, "na": 5},
         "holes": {"vacuous": [], "blind": [HOLE], "error": [], "brittle": [],
                   "coverage_gap": []},
         "results": [HOLE]}


def test_it_shows_the_payloads_numbers_even_when_they_contradict_the_rows():
    """The load-bearing test. The payload claims 99 caught and 0 missed while carrying a missed
    row. A renderer that recomputed would print the truth; this one must print the CLAIM, because
    its whole contract is that the run is the authority and the page is a view of it."""
    lying = {**HOLED, "score": 0.42, "tally": {"caught": 99, "missed": 0, "flagged": 0,
                                               "error": 0, "na": 7}}
    out = render_html(lying)
    assert "99" in out, "the renderer replaced the payload's caught count with its own"
    assert "42.0%" in out, "the renderer replaced the payload's score with its own"
    # and it still renders the hole that the tally denies
    assert "spurious_cue_token_insert" in out


def test_a_clean_run_says_so_without_inventing_a_grade():
    out = render_html(CLEAN)
    assert "No holes found" in out
    assert "blind spot" not in out.lower().split("footer")[0].split("no holes found")[0]


def test_a_hole_carries_its_operator_case_shape_and_provenance():
    out = render_html(HOLED)
    for probe in ("spurious_cue_token_insert", "capital", "contains",
                  "does none of the work", "arXiv:1907.07355", "zxqfp capital"):
        assert probe in out, f"missing {probe!r} from the hole card"


def test_buckets_are_not_distinguished_by_colour_alone():
    """A reader who cannot see the accent must still be able to tell a broken check from a
    missing one, since those lead to opposite actions."""
    out = render_html(HOLED)
    assert "Blind spot" in out
    assert "present and BROKEN" in out
    assert "Fix the check." in out


def test_declined_is_explained_rather_than_left_as_a_bare_number():
    """A large n/a beside a small denominator reads as skipping. It is the opposite: a decline is
    a refusal to guess a polarity."""
    out = render_html(HOLED)
    assert "declined" in out
    assert "not skipped" in out


def test_user_content_is_escaped():
    """Case names and mutant previews are suite-author text and, for an external suite, not
    necessarily friendly. A page that executed them would be a new hole shipped by the tool that
    finds holes."""
    nasty = {**HOLE, "case_name": '<script>alert(1)</script>',
             "mutant_preview": '"><img src=x onerror=alert(1)>'}
    out = render_html({**HOLED, "holes": {**HOLED["holes"], "blind": [nasty]},
                       "results": [nasty]})
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out
    assert "onerror=alert(1)>" not in out


def test_the_page_is_self_contained():
    """No CDN, no font fetch, no script tag: it has to open from a file path on a machine with no
    network, the same standard the VAC bundle is held to."""
    out = render_html(HOLED)
    assert "<script" not in out.lower()
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', out)
    assert "@import" not in out


def test_all_three_theme_states_are_defined():
    """Bare :root, the prefers-color-scheme default, and an explicit data-theme choice. A colour
    defined only inside a media block leaves the un-stamped state rendering one theme's text on
    the other theme's ground."""
    out = render_html(CLEAN)
    assert ":root{" in out
    assert "prefers-color-scheme:dark" in out
    assert "[data-theme=dark]" in out
    assert "--bg:" in out.split("prefers-color-scheme")[0], "bare :root must define the palette"
