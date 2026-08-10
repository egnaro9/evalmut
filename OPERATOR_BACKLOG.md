# Operator backlog — candidate defect classes, gated on provenance

This is **not a build target.** evalmut ships 18 operators because each one names a *real,
documented* failure it reproduces ("mined, not authored" — see the README). The list below
is the opposite of code-not-yet-written: it is **defect shapes we have seen referenced but
have not yet sourced a real instance for.** An item leaves this file and becomes an operator
**only** the day we can point at a documented case of it — a user report, a promptfoo issue,
a model post-mortem, a line in a real grader — and cite that case in `real_origin`.

Kept this way the backlog *serves* the discipline: it captures the idea without diluting the
catalog with authored mutations that only test what we already imagined a check might miss —
which is exactly the blind spot evalmut exists to find. **Do not** implement one of these to
"reach a number." Promote one when its real defect walks in the door.

## How a backlog item becomes an operator

1. **Find the real defect.** A concrete, documented instance where a grader let this shape
   pass (DEFECT) or wrongly flagged it (EQUIVALENT/brittle). Screenshot, issue link, commit,
   transcript — something citable.
2. **Establish polarity structurally.** The operator must be able to prove, for the case in
   hand, that the mutant is provably-wrong (DEFECT) or provably-still-correct (EQUIVALENT),
   from the case's own ground truth — never a guess. Where it can't, it DECLINES (N/A).
3. **Cite it** in `real_origin`, add the operator, and add a regression test. The
   `test_every_operator_names_a_real_origin` gate enforces the citation.

## Candidates

Polarity: **D** = defect (a wrong output a sound grader must reject) · **E** = equivalent (a
still-correct output a sound grader must still pass; catches brittle checks).

### numeric  *(extends `near_miss_number`)*
| candidate | shape | pol | needs (real instance to mine) |
|---|---|---|---|
| `unit_mismatch` | correct magnitude, wrong/again unit: `42` vs `42%` vs `$42` vs `42 ms` | D | a grader that string-compares a number and ignores or mis-handles the unit |
| `sign_flip` | the answer negated: `-42` for `42` | D | a numeric grader whose tolerance band spans zero and accepts the wrong sign |
| `thousands_separator` | `1,000` / `1 000` / `1.000` vs `1000` (locale formatting) | E | a strict numeric/exact grader that rejects a correctly-formatted number |
| `rounding_boundary` | a correctly-rounded value the grader rejects as off | E | a `num_tol` grader that false-fails a value inside the real tolerance |

### exact / string  *(extends `case_variant`, `whitespace_noise`)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `unicode_normalize` | NFC vs NFD (`café`), same text different bytes | E | an `exact` grader that `==`-compares without NFC-normalizing |
| `smart_quotes` | typographic `’ “ ”` vs ASCII `' " "` around a correct answer | E | a grader that fails a curly-quote variant of the right answer |
| `homoglyph_swap` | a look-alike char (Cyrillic `а` in `data`) — looks right, is wrong | D | a grader/eval where a homoglyph slipped a wrong answer past a human/check |

### presence / contains / regex  *(extends `keyword_present_but_negated`, `garbage_answer`)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `needle_in_larger_word` | `contains("cat")` passes `"category"` — substring, not the token | D | a `contains` gate that a longer word satisfied |
| `answer_echoed_from_prompt` | keyword present because the reply echoed the question, not answered it | D | a proof/keyword gate fooled by a prompt echo (sibling of the transcript-grep origin) |
| `regex_overbroad` | `.+` / `\d+` / `\S+` matches garbage — the pattern asserts nothing | D | a real regex grader whose pattern is vacuous |

### json  *(extends `json_value_corruption`, `json_value_type_flip`)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `json_deep_value_flip` | a *nested* required field corrupted (current op is top-level) | D | a nested-schema grader that only checks top-level presence |
| `json_null_vs_missing` | required field present but `null` (grader treats null as satisfied) | D | a presence-only grader that counts `null` as a value |
| `json_extra_field` | an unexpected field added where the schema forbids extras | D | a grader that ignores `additionalProperties: false` |
| `json_array_order` | required-order array reordered (or unordered array reordered) | D/E | a grader that does/doesn't care about order, mismatched to the task |

### safety  *(extends `comply_with_harm`, `over_refuse_benign`)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `refuse_then_comply` | refusal marker in line 1, the harm delivered in the body below | D | **high value, already referenced** in the README ("refuses in its first line then delivers the harm"); needs one citable transcript |
| `non_marker_refusal` | a genuine refusal phrased without the marker string | E | a marker-based `must_refuse`/`must_comply` grader that false-flags a real refusal |

### grounding  *(extends `drop_supporting_context`)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `fabricated_citation` | answer cites a source id/quote absent from the contexts | D | a grounding grader that scores content overlap but never validates the citation |
| `correct_but_unsupported` | answer factually right yet not derivable from the retrieved contexts | D | a grounding/faithfulness grader that rewards correctness over support |

### trajectory / agent  *(extends `trajectory_drop_step`, `inject_denylisted_tool`)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `trajectory_reorder` | the right tools, wrong order, where order matters | D | an order-sensitive task graded by set/LCS coverage that a reorder survives |
| `tool_wrong_args` | correct tool name, wrong/malformed arguments | D | a trajectory grader that checks tool *names* but not their arguments |

### abstention  *(extends `fabricate_over_abstain`)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `over_abstain_answerable` | refuses/hedges on a fair, answerable question (the abstention twin of over-refusal) | E | an abstention grader that penalizes a correct answer as if it were a fabrication |

### multi-turn / context  *(new family — no operator yet; needs a multi-turn case shape first)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `contradict_earlier_turn` | final answer contradicts a commitment made earlier in the conversation | D | a grader that judges only the last turn; **also needs** an EvalCase that carries multi-turn history |
| `ignore_later_instruction` | obeys the first instruction, ignores a corrected one issued later | D | same — a multi-turn-aware case shape must exist before this can establish polarity |

### meta  *(hardest; evalmut is deterministic-first)*
| candidate | shape | pol | needs |
|---|---|---|---|
| `grader_nondeterminism` | same input, different verdict across runs (a flaky / LLM-judge grader) | — | a real flaky grader; and a design decision on how a deterministic tool reports a non-deterministic one (probably a separate "flaky" outcome, not a mutation) |

## Notes

- The `multi-turn` and `meta` rows are **blocked on structure**, not just provenance: the
  first needs an EvalCase that can hold conversation history; the second needs a way to
  report non-determinism that doesn't pretend to be a mutation. Design those before mining.
- Several rows may already be *partially* covered by an existing operator on a specific case
  — check before promoting, and prefer sharpening the existing operator to adding a near-twin.
- If a candidate can't establish polarity from ground truth (only a human could judge it),
  it does **not** belong in evalmut at all — it belongs in a rubric/LLM-judge tool, which is
  the thing evalmut is deliberately not.
