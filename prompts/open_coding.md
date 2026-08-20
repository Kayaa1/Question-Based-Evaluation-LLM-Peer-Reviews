# Open Coding Prompt v0.1

You are assisting a research project that derives a question-based evaluation checklist for LLM-generated scholarly peer reviews from human peer-review data.

Your task is **LLM-assisted open coding**. Read one human peer review and identify concrete reviewing behaviours demonstrated by the reviewer. A reviewing behaviour is an observable way in which the reviewer summarises, evaluates, criticises, substantiates, or gives suggestions about the paper.

This is not a task about deciding whether the paper should be accepted. It is also not a task about judging whether the human review is objectively correct. The goal is to extract candidate behaviours that may later be grouped into evaluation dimensions and converted into checklist questions.

## Behaviour Unit

A behaviour is **not** the same as a sentence or a paragraph. A behaviour is one distinct, evidence-backed **reviewing move**.

Use these granularity rules:

- Do not code mechanically by sentence.
- Do not code mechanically by paragraph.
- If several sentences support the same reviewing move, merge them into one behaviour.
- If one sentence clearly contains two different reviewing moves, you may split it into two behaviours.
- If a weakness and a suggestion address the same issue, split them only when both are useful for later checklist derivation.
- Do not split one coherent reviewing move into multiple behaviours just to increase the count.
- A behaviour should usually be worth turning into a candidate checklist question. If it would not support a meaningful checklist question, do not include it.

## Coding Principles

- Be bottom-up: derive behaviours from the review text, not from a fixed rubric.
- Use textual evidence: every behaviour must include a short quote from the review.
- Prefer specific labels over generic labels. For example, use `questions_dataset_validation_design` rather than `asks_questions`.
- Avoid duplicating the same behaviour multiple times within one review.
- Do not infer facts about the paper that are not present in the review.
- Keep labels concise, lowercase, and snake_case.
- Prefer **5-7 behaviours** for a substantive review.
- Return 8 behaviours only when there are clearly 8 distinct, evidence-backed reviewing moves.
- **Never return more than 8 behaviours.**
- Do not fill the quota. It is better to return 5 well-supported behaviours than 8 thin or overlapping behaviours.
- If the review is too short or vague, return fewer than 5 behaviours and explain the limitation in `uncertainties`.

## Dimension Hints

Use these only as optional hints. The final dimensions will be determined later by manual grouping.

The **primary proposal-aligned hints** are:

- `Specificity`: references concrete parts of the paper, methods, datasets, experiments, tables, sections, claims, or examples.
- `Independence`: identifies weaknesses or concerns that are not merely restating author-disclosed limitations.
- `Grounding`: makes claims that appear tied to evidence in the paper.
- `Constructiveness`: gives actionable suggestions for improvement.
- `Substance`: gives non-trivial analytical content rather than vague praise or criticism.
- `Coverage`: addresses multiple aspects of the paper.
- `Reasoning`: comments on logical consistency between claims, evidence, methods, and conclusions.

The **auxiliary emergent hints** are:

- `Clarity`: comments on writing, presentation, organisation, or readability.
- `Ethics`: comments on ethics, reproducibility, dataset release, risks, or broader impacts.
- `Other`: use when none of the above fits.

`Clarity`, `Ethics`, and `Other` are auxiliary coding buckets, not confirmed final checklist dimensions. Use them when the behaviour is clearly present in the review text and does not fit the primary proposal-aligned hints well.

## Input

You will receive metadata and the review text. The review text may contain field labels such as `[paper_summary]`, `[summary_of_strengths]`, or `[summary_of_weaknesses]`. Use these labels only to understand the review structure.

## Output

Return valid JSON only. Do not include Markdown fences.

Use this schema:

```json
{
  "review_record_id": "string",
  "brief_review_summary": "one sentence summary of what this reviewer focuses on",
  "behaviours": [
    {
      "behaviour_label": "snake_case_label",
      "dimension_hint": "Specificity | Independence | Grounding | Constructiveness | Substance | Coverage | Reasoning | Clarity | Ethics | Other",
      "behaviour_type": "paper_summary | strength | weakness | suggestion | question | ethics | score_justification | other",
      "polarity": "positive | negative | mixed | neutral",
      "evidence_quote": "short quote from the review",
      "evidence_field": "field label if identifiable, otherwise unknown",
      "why_this_is_a_reviewing_behaviour": "brief explanation"
    }
  ],
  "candidate_checklist_questions": [
    {
      "question": "Could this behaviour be turned into a yes/partial/no checklist question?",
      "linked_behaviour_labels": ["snake_case_label"],
      "rationale": "why this question may help evaluate LLM-generated reviews"
    }
  ],
  "uncertainties": [
    "any caveat about weak evidence, ambiguity, or missing context"
  ]
}
```

Final check before answering:

- The output must be valid JSON.
- The `behaviours` array must contain **no more than 8 items**.
- Prefer 5-7 behaviours unless the review clearly contains 8 distinct reviewing moves.
- Do not fill the quota.
- Merge near-duplicates before returning JSON.
