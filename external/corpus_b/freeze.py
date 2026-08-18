"""Freeze the Corpus B candidate cards, before anything is executed against them.

WHY THE CARDS ARE FROZEN FIRST. A card written after a run is a description of the result. The
whole value of an external corpus is that the expected behaviour was fixed while it was still
possible to be wrong about it, so this script writes the cards and their hashes and stops. It
never runs an operator, never scores anything, and imports nothing from evalmut.

WHAT A CARD IS NOT. A frozen card is a well-sourced hypothesis. It is not a validated operator,
and the count of cards here is not evidence of detection power. Independent classification by two
engineers is the standing bar, and it currently stands at zero, so every artifact this script
emits is labelled a CANDIDATE.

THE FIELD THAT MATTERS MOST IS `applicability`. FOUR of the twelve incidents are real, externally
sourced, merged eval-suite defects that evalmut cannot validly express:

    CB-010  changed only a failure MESSAGE; the verdict and score were already correct, so every
            mutation scores identically before and after the fix
    CB-011  regex backtracking. No verdict changes at all, only elapsed time
    CB-012  the same negation defect as CB-004 but in `moderation`, which calls a live provider,
            so drift would be indistinguishable from the hole
    CB-008  sound predicate, wrong SURFACE: reaching it means mutating an assertion PARAMETER, and
            evalmut mutates model OUTPUTS only

CB-008 was initially marked applicable while its own `maps_to` field said the shape was outside
the mutation surface. That contradiction is the exact move this file exists to prevent: relabeling
parameter mutation as output mutation raises the applicable count and measures nothing. The flag
was wrong and the prose was right.

Dropping these four would produce a tidier set and a false impression that every external defect
is in range. They are kept, with `applicable: false` and the reason, because the shape of what a
tool cannot see is part of an honest account of what it can. Two thirds of this externally sourced
sample is reachable, not all of it.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
CARDS = ROOT / "cards"
REPO = "promptfoo/promptfoo"

# verdict classes, used to keep "the tool did not catch it" separate from "the tool cannot see it"
WRONG_VERDICT = "wrong-verdict"      # a correct output scored wrong, or an incorrect one scored right
VACUOUS = "vacuous-check"            # the check passes things it cannot have judged
GRADING_ERROR = "grading-error"      # the check raised instead of returning a verdict
MESSAGE_ONLY = "message-only"        # verdict and score correct; only the explanation was wrong
PERFORMANCE = "performance"          # no verdict changes at all


def card(**kw):
    return kw


DECK = [
    card(
        id="CB-001",
        pr=9782, merge="96929e8758ca", author="i-anubhav-anand",
        title="is-xml accepted non-well-formed XML",
        semantic="`is-xml` is documented as validating the ENTIRE output as XML. It delegated to "
                 "fast-xml-parser, which is a lenient data extractor rather than a validating "
                 "parser, so well-formedness was never actually asserted.",
        verdict_class=WRONG_VERDICT,
        applicable=True,
        applicability="Any assertion whose contract is 'this output is valid <format>' but whose "
                      "implementation delegates to a lenient or recovering parser. The predicate "
                      "is: the checker's parser accepts input the format's own grammar rejects.",
        not_applicable=[
            "assertions that only extract a field and never claim whole-document validity",
            "formats with no well-formedness notion distinct from parseability",
        ],
        clean="<root><a>1</a></root>",
        defective="<root><a>1</b></root>   (mismatched closing tag)",
        expected_clean="PASS. The document is well formed.",
        expected_defective="FAIL. Mismatched tags are not well-formed XML.",
        counterexample="A document with an unusual but LEGAL construct, such as a CDATA section or "
                       "a namespace prefix, must still PASS. An operator that flags those is "
                       "measuring the checker's strictness, not its correctness.",
        fp_risk="Treating a legal-but-exotic document as defective produces a false hole and would "
                "push a maintainer to loosen a check that was right.",
        fn_risk="A parser lenient in a way the operator does not exercise (for example duplicate "
                "roots but not unquoted attributes) leaves the defect undetected and the check "
                "looks sound.",
        maps_to="malformed_structure (already implemented, cites this PR)",
    ),
    card(
        id="CB-002",
        pr=9784, merge="c08cfc454d38", author="i-anubhav-anand",
        title="is-sql false-rejected SELECT DISTINCT",
        semantic="`is-sql` layered a two-column missing-comma heuristic on top of node-sql-parser. "
                 "The heuristic counted a leading SELECT modifier as the first column, so valid "
                 "statements beginning with DISTINCT were rejected.",
        verdict_class=WRONG_VERDICT,
        applicable=True,
        applicability="Any assertion that adds a hand-written heuristic on top of a real parser to "
                      "catch a suspected user error. The predicate is: a syntactically valid input "
                      "is rejected by the heuristic rather than by the grammar.",
        not_applicable=[
            "checks with no heuristic layer, where acceptance is exactly the parser's",
            "cases where the heuristic is the documented contract rather than a guard",
        ],
        clean="SELECT name FROM users",
        defective="SELECT DISTINCT name FROM users   (valid; the heuristic read DISTINCT as a column)",
        expected_clean="PASS.",
        expected_defective="PASS. This is the point: the DEFECT is in the checker, and a sound "
                           "check must pass both.",
        counterexample="`SELECT a b FROM t` is genuinely ambiguous and a check may reject it. An "
                       "operator that demands it pass would be asserting a semantic promptfoo "
                       "never made.",
        fp_risk="Flagging a check for rejecting truly malformed SQL, which is its job.",
        fn_risk="Testing only DISTINCT leaves ALL, TOP and other leading modifiers unexercised, so "
                "the same class of defect survives.",
        maps_to="parser_accepted_variant (already implemented, cites this PR)",
    ),
    card(
        id="CB-003",
        pr=9739, merge="386c0129bf50", author="i-anubhav-anand",
        title="ROUGE scored case-sensitively while its sibling metrics did not",
        semantic="`handleRougeScore` passed empty options to js-rouge, taking the library default "
                 "caseSensitive: true, while bleu, gleu and meteor all lowercase first. A single "
                 "capitalisation changed the score.",
        verdict_class=WRONG_VERDICT,
        applicable=True,
        applicability="Any text-overlap metric in a family whose members disagree about "
                      "normalisation. The predicate is: two metrics documented as comparable "
                      "disagree on an input that differs only by an incidental property.",
        not_applicable=[
            "metrics whose contract is explicitly case-sensitive",
            "tasks where capitalisation carries meaning, such as proper-noun extraction",
        ],
        clean="the cat sat on the mat",
        defective="The Cat Sat On The Mat   (identical content, different case)",
        expected_clean="Score at the reference level.",
        expected_defective="The same score. A case variant of a correct answer is still correct "
                           "under this metric's contract.",
        counterexample="For a task whose ground truth is 'US' versus 'us', case IS the answer, and "
                       "an operator that lowercases would manufacture a false equivalence.",
        fp_risk="Applying this where case is semantic turns a correct rejection into a reported "
                "hole.",
        fn_risk="Only testing ASCII case misses Unicode case folding, where the same defect hides.",
        maps_to="case_variant (implemented, but currently cites gradecore rather than this)",
    ),
    card(
        id="CB-004",
        pr=9722, merge="560ea2d236e7", author="i-anubhav-anand",
        title="not-levenshtein ignored the inverse flag, so negation was a no-op",
        semantic="`handleLevenshtein` never read the `inverse` flag that the framework derives "
                 "from the `not-` prefix, and there is no generic post-handler inversion, so "
                 "`not-levenshtein` behaved identically to `levenshtein`.",
        verdict_class=WRONG_VERDICT,
        applicable=True,
        applicability="Any framework offering a negation prefix implemented per handler rather "
                      "than centrally. The predicate is: an assertion and its negation return the "
                      "same verdict on the same input.",
        not_applicable=[
            "frameworks that invert centrally after the handler returns",
            "assertions with no negated form",
        ],
        clean="assert levenshtein(output, ref) <= threshold  -> PASS on a near-identical output",
        defective="assert NOT-levenshtein on that same near-identical output",
        expected_clean="PASS.",
        expected_defective="FAIL. The negation must invert the verdict.",
        counterexample="A handler that legitimately has no meaningful negation, where the "
                       "framework refuses the `not-` form outright, is correct and must not be "
                       "flagged.",
        fp_risk="Reporting a hole where the framework deliberately rejects negation.",
        fn_risk="Testing one handler proves nothing about the other handlers with the same shape. "
                "PR 9738 is the identical defect in `moderation`, found separately.",
        maps_to="none. A negation-parity operator does not exist in evalmut.",
    ),
    card(
        id="CB-005",
        pr=10089, merge="49c0f6d77496", author="he-yufeng",
        title="out-of-range percentile made trace-span-duration silently pass",
        semantic="`trace-span-duration` never validated its `percentile`. A value of 150 indexed "
                 "past the end of the sorted durations, `calculatePercentile` returned undefined, "
                 "and `undefined > max` is false, so the assertion PASSED and reported "
                 "'(undefinedms) is within...'.",
        verdict_class=VACUOUS,
        applicable=True,
        applicability="Any threshold check whose comparison operand can become undefined or NaN, "
                      "where the language's comparison semantics turn 'no value' into 'not over "
                      "the limit'. The predicate is: an unconfigurable-looking parameter takes a "
                      "value that makes the check unable to fail.",
        not_applicable=[
            "checks that validate their parameters before comparing",
            "languages where comparison against a null value raises rather than returning false",
        ],
        clean="percentile: 95 over a normal duration distribution",
        defective="percentile: 150   (out of range)",
        expected_clean="Verdict determined by the real p95 duration.",
        expected_defective="FAIL or ERROR, naming the bad parameter. Silently passing is the "
                           "defect.",
        counterexample="percentile: 100 is legitimately the maximum and must not be treated as out "
                       "of range.",
        fp_risk="Flagging boundary values (0, 100) that the check is right to accept.",
        fn_risk="An operator that only tries 150 misses negative percentiles and non-numeric "
                "values, which reach the same undefined state by another route.",
        maps_to="none. evalmut has a `vacuous` hole KIND but no parameter-range operator.",
    ),
    card(
        id="CB-006",
        pr=10142, merge="2812d7622b2e", author="Gujiassh",
        title="conversation-relevance defaulted its threshold to 0, so everything passed",
        semantic="An omitted threshold was treated as 0. The metric's score is a proportion in "
                 "[0,1], so an entirely irrelevant conversation scoring 0 still passed. Fixed to "
                 "default 0.5, with nullish coalescing so an explicit 0 stays valid.",
        verdict_class=VACUOUS,
        applicable=True,
        applicability="Any scored assertion whose default threshold sits at or below the minimum "
                      "of its own score range. The predicate is: with default configuration, no "
                      "input can fail.",
        not_applicable=[
            "assertions whose threshold has no default and must be supplied",
            "cases where an explicit 0 is deliberately configured, which remains valid",
        ],
        clean="a relevant conversation, default threshold",
        defective="a wholly irrelevant conversation, default threshold",
        expected_clean="PASS.",
        expected_defective="FAIL. A default that cannot fail is not a check.",
        counterexample="An explicitly configured `threshold: 0` is a legitimate user choice and "
                       "must still be honoured, which is why the fix used nullish coalescing "
                       "rather than truthiness.",
        fp_risk="Treating a deliberate explicit 0 as the defect would report a hole in correct "
                "configuration.",
        fn_risk="A default just ABOVE the floor, say 0.01, is nearly as vacuous and would not be "
                "caught by a test that only asks 'can anything fail'.",
        maps_to="none. Closest is the `vacuous` hole kind, which is a classification and not an "
                "operator.",
    ),
    card(
        id="CB-007",
        pr=9850, merge="cc8c0c65f137", author="he-yufeng",
        title="tokenless GLEU inputs errored, and whitespace-only pairs scored a perfect match",
        semantic="An empty model output is a valid evaluation result, but GLEU treated it as "
                 "invalid input and raised, converting a score-based failure into a grading "
                 "error. Separately, whitespace-only and period-only pairs normalised to empty "
                 "token lists and received an accidental perfect match.",
        verdict_class=VACUOUS,
        applicable=True,
        applicability="Any overlap metric that tokenises before comparing. The predicate is: two "
                      "inputs that normalise to the empty token list are scored as identical, or "
                      "an empty output raises instead of scoring.",
        not_applicable=[
            "metrics that compare raw strings without tokenisation",
            "suites where an empty output is filtered upstream and never reaches the metric",
        ],
        clean="candidate 'the cat sat', reference 'the cat sat'",
        defective="candidate '   ', reference '...'   (both normalise to no tokens)",
        expected_clean="Perfect score, correctly.",
        expected_defective="Score 0. Two empty token lists are not a match; they are an absence of "
                           "evidence.",
        counterexample="A genuinely empty reference paired with a genuinely empty candidate may be "
                       "a legitimate degenerate case in some suites, and the card does not claim "
                       "otherwise for those.",
        fp_risk="Suites that legitimately define empty-equals-empty as a pass would be reported as "
                "holed.",
        fn_risk="Testing only whitespace misses punctuation-only and zero-width-character inputs "
                "that reach the same state.",
        maps_to="blank_output exists but cites gradecore and targets a different contract.",
    ),
    card(
        id="CB-008",
        pr=10012, merge="06d8105dcaa2", author="WatchTree-19",
        title="contains and icontains rejected the numeric value 0",
        semantic="`handleContains` guarded its value with `invariant(value, ...)`, a truthiness "
                 "check, so the numeric 0 was rejected with 'must have a string or number value' "
                 "even though the following line and `String(value)` show numbers are intended.",
        verdict_class=GRADING_ERROR,
        applicable=False,
        applicability="Correct in SHAPE, unreachable by this tool's MUTATION SURFACE. The defect "
                      "predicate is sound (a legal parameter value is rejected because it is "
                      "falsy rather than the wrong type), but reaching it requires mutating the "
                      "assertion's PARAMETER, and evalmut mutates model OUTPUTS only.",
        not_applicable=[
            "evalmut mutates outputs, never assertion parameters, so no operator it can run "
            "reaches this defect. Marking it applicable would relabel parameter mutation as "
            "output mutation purely to raise the applicable count.",
            "it becomes reachable only with a separate parameter-mutation mechanism, which is a "
            "different instrument with its own validity questions and does not exist here.",
            "parameters whose accepted type has no falsy members are out of scope regardless",
        ],
        clean="contains value 42 against an output containing '42'",
        defective="contains value 0 against an output containing '0'",
        expected_clean="PASS.",
        expected_defective="PASS. 0 is a legal numeric value and the check should find it.",
        counterexample="An genuinely absent value (undefined) SHOULD be rejected, so an operator "
                       "must distinguish falsy-but-present from missing.",
        fp_risk="Demanding that undefined be accepted would break a correct guard.",
        fn_risk="Only testing 0 misses the empty string and false, which fail identically.",
        maps_to="none. evalmut mutates OUTPUTS, not assertion PARAMETERS, so this shape is outside "
                "its current mutation surface even though the defect is in range conceptually.",
    ),
    card(
        id="CB-009",
        pr=10076, merge="ffd892292644", author="he-yufeng",
        title="a tool_calls entry with no function object crashed instead of failing",
        semantic="`is-valid-openai-tools-call` is meant to reject anything that is not a valid "
                 "tools response with pass:false and a reason. It read `toolsOutput[0].function."
                 "name` directly, so an entry without a `function` object threw TypeError, an "
                 "uncaught crash rather than an assertion failure.",
        verdict_class=GRADING_ERROR,
        applicable=True,
        applicability="Any structural validator that indexes into nested output before confirming "
                      "the shape exists. The predicate is: malformed input produces an exception "
                      "rather than the FAIL the validator promises.",
        not_applicable=[
            "validators that parse into a schema before field access",
            "runtimes where the harness converts exceptions into failures anyway, which changes "
            "the observable outcome",
        ],
        clean='[{"function": {"name": "f", "arguments": "{}"}}]',
        defective='[{"id": "call_1"}]   (a tool_calls entry with no function object)',
        expected_clean="PASS.",
        expected_defective="FAIL with a reason. Not a crash.",
        counterexample="Input that is not an array at all may legitimately raise before the "
                       "assertion's own contract applies, depending on where the harness draws "
                       "the boundary.",
        fp_risk="Counting a deliberate upstream exception as this defect.",
        fn_risk="A harness that wraps handlers in try/catch converts the crash into a fail, hiding "
                "the defect from any black-box probe.",
        maps_to="evalmut records an `error` OUTCOME, which is the right bucket, but has no "
                "operator that deletes a required nested object.",
    ),
    # ---- kept deliberately, and NOT applicable. See the module docstring. ----
    card(
        id="CB-010",
        pr=9824, merge="d1d8de31470b", author="he-yufeng",
        title="inverse JSON assertions reported the opposite assertion's failure message",
        semantic="Schema-less `not-is-json` and `not-contains-json` already returned the correct "
                 "verdict and score. Only the failure REASON was wrong, describing the positive "
                 "assertion ('Expected output to be valid JSON') on a negated one.",
        verdict_class=MESSAGE_ONLY,
        applicable=False,
        applicability="None for evalmut as it stands.",
        not_applicable=[
            "evalmut classifies by VERDICT. This defect never changed a verdict or a score, so "
            "every mutation would be scored identically before and after the fix and the tool "
            "would report no hole while a real, merged defect sat in front of it.",
            "detecting it needs an explanation-quality oracle, which is a rubric or judge "
            "problem and is deliberately outside this tool.",
        ],
        clean="not-is-json against non-JSON output: PASS with a correct reason",
        defective="not-is-json against JSON output: FAIL with the reason 'Expected output to be "
                  "valid JSON', which describes the un-negated assertion",
        expected_clean="PASS.",
        expected_defective="FAIL, with a reason that describes the NEGATED assertion.",
        counterexample="Any verdict-only comparison passes both before and after the fix, which is "
                       "precisely why this card is marked non-applicable rather than pending.",
        fp_risk="n/a, no operator is proposed.",
        fn_risk="The honest statement of the limit: an eval suite can be wrong in ways a "
                "verdict-based mutation tester structurally cannot see. This card exists to keep "
                "that visible in the corpus rather than in a footnote.",
        maps_to="none, and none should be added.",
    ),
    card(
        id="CB-011",
        pr=10373, merge="57243cf84bd9", author="jameshiester-oai",
        title="regex backtracking in GLEU normalisation and SQL fence parsing",
        semantic="Trailing-period normalisation and Markdown-fence parsing used patterns that "
                 "backtrack catastrophically on long punctuation or whitespace runs. Replaced "
                 "with a linear scan and a deterministic fence parser.",
        verdict_class=PERFORMANCE,
        applicable=False,
        applicability="None for evalmut as it stands.",
        not_applicable=[
            "no verdict changes. Before and after the fix the same inputs produce the same "
            "results, only slower, so a verdict-based tester sees nothing.",
            "detecting it needs a time or complexity budget per check, which evalmut does not "
            "declare and could not adjudicate deterministically across machines.",
        ],
        clean="a normal candidate string",
        defective="a candidate with a long run of punctuation or whitespace",
        expected_clean="Scored promptly.",
        expected_defective="Scored promptly. The defect is elapsed time, not the answer.",
        counterexample="A slow check on a slow machine is not a defect, which is why this needs a "
                       "declared budget rather than a stopwatch.",
        fp_risk="n/a, no operator is proposed.",
        fn_risk="A real availability defect in an eval suite is invisible to this tool. Worth "
                "stating plainly: a green evalmut run says nothing about whether a suite can be "
                "wedged by its own inputs.",
        maps_to="none.",
    ),
    card(
        id="CB-012",
        pr=9738, merge="c56c7121749a", author="i-anubhav-anand",
        title="not-moderation ignored the inverse flag, making the negation a complete no-op",
        semantic="`handleModeration` returned the matcher's pass and score verbatim without "
                 "reading `inverse`, so `not-moderation` behaved identically to `moderation`. "
                 "Structurally the same defect as CB-004, in a different handler.",
        verdict_class=WRONG_VERDICT,
        applicable=False,
        applicability="Correct in SHAPE, out of scope in EXECUTION.",
        not_applicable=[
            "the moderation assertion calls a live moderation API, so the check is not "
            "deterministic. evalmut's entire remit is deterministic scorers, and a run against "
            "this would confound a real hole with provider variance.",
            "it could become applicable against a recorded or stubbed moderation backend, which "
            "is a different experiment with its own validity questions.",
        ],
        clean="moderation on flagged content: FAIL",
        defective="not-moderation on that same flagged content",
        expected_clean="FAIL.",
        expected_defective="PASS. The negation must invert.",
        counterexample="Provider drift alone can flip a moderation verdict between runs, which "
                       "would be indistinguishable from the defect under a black-box probe.",
        fp_risk="Provider variance reported as a suite hole.",
        fn_risk="Kept in the corpus because dropping it would overstate how much of the negation "
                "defect class is reachable deterministically. CB-004 is reachable; this one is "
                "not.",
        maps_to="none. Same missing negation-parity operator as CB-004.",
    ),
]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build() -> dict:
    CARDS.mkdir(parents=True, exist_ok=True)
    entries = []
    for c in DECK:
        body = {
            "id": c["id"],
            "status": "CANDIDATE, not independently reviewed",
            "title": c["title"],
            "source": {
                "url": f"https://github.com/{REPO}/pull/{c['pr']}",
                "repo": REPO,
                "pr": c["pr"],
                "merge_commit": c["merge"],
                "author": c["author"],
                "authored_by_egnaro9": c["author"] == "egnaro9",
            },
            "semantic": c["semantic"],
            "verdict_class": c["verdict_class"],
            "applicable_to_evalmut": c["applicable"],
            "applicability_predicate": c["applicability"],
            "not_applicable_cases": c["not_applicable"],
            "pair": {
                "clean_input": c["clean"],
                "defective_transformation": c["defective"],
                "expected_on_clean": c["expected_clean"],
                "expected_on_defective": c["expected_defective"],
            },
            "counterexample": c["counterexample"],
            "risks": {"false_positive": c["fp_risk"], "false_negative": c["fn_risk"]},
            "maps_to_existing_operator": c["maps_to"],
        }
        raw = (json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        (CARDS / f"{c['id']}.json").write_bytes(raw)
        # Every binding a reader needs lives HERE as well as inside the card. The card hash
        # already commits to its own provenance transitively, but an auditor should not have to
        # open twelve files to answer "is any of this self-authored".
        entries.append({"id": c["id"], "file": f"cards/{c['id']}.json",
                        "sha256": sha256_bytes(raw), "bytes": len(raw),
                        "source_url": f"https://github.com/{REPO}/pull/{c['pr']}",
                        "pr": c["pr"], "merge_commit": c["merge"], "author": c["author"],
                        "authored_by_egnaro9": c["author"] == "egnaro9",
                        "applicable": c["applicable"], "verdict_class": c["verdict_class"]})

    applicable = [e for e in entries if e["applicable"]]
    manifest = {
        "manifest_version": 1,
        "label": "Corpus B CANDIDATE set. Externally sourced, frozen before execution, NOT "
                 "independently reviewed. Independent classification stands at zero.",
        "source_repo": REPO,
        "authored_by_egnaro9": sum(1 for e in entries if e["author"] == "egnaro9"),
        "card_count": len(entries),
        "applicable_count": len(applicable),
        "non_applicable_count": len(entries) - len(applicable),
        "distinct_authors": sorted({e["author"] for e in entries}),
        "cards": sorted(entries, key=lambda e: e["id"]),
        "review": {
            "independent_engineers_required": 2,
            "independent_classifications_received": 0,
            "publish_disagreements": True,
        },
    }
    raw = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    (ROOT / "MANIFEST.json").write_bytes(raw)
    return {"manifest_sha256": sha256_bytes(raw), "cards": len(entries),
            "applicable": len(applicable)}


if __name__ == "__main__":
    r = build()
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()[:12]
    print(f"froze {r['cards']} cards ({r['applicable']} applicable)")
    print(f"manifest sha256 {r['manifest_sha256']}")
    print(f"built at HEAD   {head}  (the freeze commit is the one that ADDS these files)")
