# Concept Grouping Prompt v0.1

You are assisting a research project that derives a question-based evaluation checklist for LLM-generated scholarly peer reviews.

You will receive a batch of open-coded reviewing behaviours. Each behaviour was extracted from one human peer review and includes a short label, a provisional dimension hint, behaviour type, polarity, evidence quote, and a short explanation.

Your task is **LLM-assisted concept grouping**: group semantically similar behaviours into broader reviewing concepts that could later become checklist criteria.

This is an assistive step, not final coding. A human researcher will inspect and revise your grouping. Your job is to produce a useful, evidence-aware grouping proposal.

## Important Principles

- Do **not** treat the existing `behaviour_label` as final.
- Do **not** create one concept per behaviour.
- Merge behaviours that express the same reviewing pattern even if their wording differs.
- Keep concepts broad enough to recur across reviews, but not so broad that they become meaningless.
- Use the evidence quote and explanation when deciding whether behaviours belong together.
- If two behaviours share words but mean different things, keep them separate.
- If two behaviours use different words but serve the same reviewing function, group them together.
- Assign every input behaviour to exactly one concept.
- Concepts are suggestions only; do not present them as validated final dimensions.
- Be concise. This is a data-processing step, not an essay.

## Concept Granularity

Good concept labels should describe a recurring reviewing behaviour, for example:

- `assesses_baseline_or_comparison_adequacy`
- `requests_ablation_or_component_analysis`
- `checks_claim_support_or_overstatement`
- `uses_specific_paper_references`
- `raises_independent_limitations`

Avoid labels that are too narrow:

- `asks_about_line_338_current_culture`
- `criticizes_table_4_only`

Avoid labels that are too broad:

- `review_quality`
- `criticism`
- `strength`

## Candidate Dimensions

Use these candidate dimensions when helpful, but you may move a concept to a different dimension if the evidence supports it:

- `Specificity`
- `Independence`
- `Grounding`
- `Constructiveness`
- `Substance`
- `Coverage`
- `Reasoning`
- `Clarity`
- `Ethics`
- `Other`

`Clarity`, `Ethics`, and `Other` are auxiliary buckets unless the evidence shows they should become final dimensions.

## Known LLM Review Failures

Flag a concept if it is connected to known LLM-generated review failure modes:

- `hallucination_or_unsupported_feedback`
- `limitation_echo`
- `faulty_reasoning`
- `hidden_text_or_prompt_injection_vulnerability`
- `none`

Do not force a failure link. Use `none` if no clear connection exists.

## Output Format

Return valid JSON only. Do not wrap it in markdown.

Use this schema:

```json
{
  "batch_id": "string",
  "batch_summary": "brief description of the main concept families in this batch",
  "concepts": [
    {
      "concept_label": "snake_case_label",
      "concept_definition": "one short sentence defining the recurring reviewing pattern",
      "final_dimension_candidate": "Specificity | Independence | Grounding | Constructiveness | Substance | Coverage | Reasoning | Clarity | Ethics | Other",
      "known_failure_link": "hallucination_or_unsupported_feedback | limitation_echo | faulty_reasoning | hidden_text_or_prompt_injection_vulnerability | none",
      "keep_decision_suggested": "keep_candidate | merge_or_review | drop_or_merge",
      "candidate_checklist_question": "one concise yes/partial/no checklist question",
      "representative_behaviour_ids": ["B0001_01"],
      "why_these_behaviours_belong_together": "brief explanation, 25 words or fewer"
    }
  ],
  "assignments": [
    {
      "behaviour_id": "B0001_01",
      "concept_label": "snake_case_label",
      "assignment_confidence": "high | medium | low",
      "rationale": "very brief reason, 15 words or fewer"
    }
  ],
  "uncertainties": [
    "any caveat about ambiguous behaviours, broad concepts, or possible merges"
  ]
}
```

## Constraints

- Every input `behaviour_id` must appear exactly once in `assignments`.
- Every `assignment.concept_label` must match one of the labels in `concepts`.
- Each concept should normally have at least 2 behaviours unless the concept is rare but clearly important.
- For a batch of about 25 behaviours, usually create 4--10 concepts.
- Use `drop_or_merge` for concepts that are too form-dependent, too generic, or unlikely to become checklist criteria.
- Use `merge_or_review` when the concept seems real but may need to be merged with a neighbouring concept in a later cross-batch step.
- Use `keep_candidate` only when the concept looks potentially useful for the final checklist.
