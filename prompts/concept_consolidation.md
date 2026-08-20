# Concept Consolidation Prompt v0.1

You are assisting a research project that derives a question-based evaluation checklist for LLM-generated scholarly peer reviews.

You will receive a batch of local concepts produced by a previous LLM-assisted concept grouping step. These local concepts may be duplicates or near-duplicates because they were created in separate batches.

Your task is **cross-batch concept consolidation**: merge semantically similar local concepts into broader global concepts that could later become checklist criteria.

This is still an assistive step. A human researcher will inspect and revise the global concepts before finalising the checklist.

## What To Merge

Merge local concepts when they describe the same recurring reviewing pattern, even if their labels differ.

For example, these should probably merge:

- `questions_metric_validity`
- `critiques_evaluation_metric_choice`
- `checks_whether_results_support_claims`

Possible global concept:

- `assesses_evaluation_validity_or_result_support`

Do not merge concepts only because they share a broad dimension. For example, baseline adequacy and ethical risk should not merge simply because both are criticisms.

## Desired Granularity

Global concepts should be broad enough to recur across reviews and useful enough to become checklist questions.

Avoid concepts that are too narrow:

- `asks_about_table_2_caption`

Avoid concepts that are too broad:

- `criticises_the_paper`
- `review_quality`

## Known LLM Review Failures

Flag a global concept if it is connected to known LLM-generated review failure modes:

- `hallucination_or_unsupported_feedback`
- `limitation_echo`
- `faulty_reasoning`
- `hidden_text_or_prompt_injection_vulnerability`
- `none`

## Output Format

Return valid JSON only. Do not wrap it in markdown.

Use this schema:

```json
{
  "batch_id": "string",
  "batch_summary": "brief description of the main consolidated concepts in this batch",
  "global_concepts": [
    {
      "global_concept_label": "snake_case_label",
      "global_concept_definition": "one short sentence defining the consolidated reviewing pattern",
      "final_dimension": "Specificity | Independence | Grounding | Constructiveness | Substance | Coverage | Reasoning | Clarity | Ethics | Other",
      "known_failure_link": "hallucination_or_unsupported_feedback | limitation_echo | faulty_reasoning | hidden_text_or_prompt_injection_vulnerability | none",
      "keep_decision_suggested": "keep_candidate | merge_or_review | drop_or_merge",
      "candidate_checklist_question": "one concise yes/partial/no checklist question",
      "source_local_concept_ids": ["LC0001"],
      "why_these_local_concepts_belong_together": "brief explanation, 25 words or fewer"
    }
  ],
  "assignments": [
    {
      "local_concept_id": "LC0001",
      "global_concept_label": "snake_case_label",
      "assignment_confidence": "high | medium | low",
      "rationale": "very brief reason, 15 words or fewer"
    }
  ],
  "uncertainties": [
    "any caveat about ambiguous merges or concepts that may need human review"
  ]
}
```

## Constraints

- Every input `local_concept_id` must appear exactly once in `assignments`.
- Every `assignment.global_concept_label` must match one of the labels in `global_concepts`.
- For a batch of local concepts, usually create 5--15 global concepts.
- Prefer `merge_or_review` if a global concept seems real but may need cross-dimension merging later.
- Prefer `drop_or_merge` for concepts that are form artifacts, too generic, or unlikely to become checklist criteria.
