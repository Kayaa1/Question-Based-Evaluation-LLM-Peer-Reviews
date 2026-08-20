# Checklist Application Prompt v0.2

You are applying a pre-validation checklist for evaluating peer reviews.
Use the provided annotation guideline to score one review against all checklist
items, using paper context when required.

Important context:
- This is an automated checklist application run, not a guideline pilot.
- Judge the whole review at the review level. Do not answer once per sentence.
- Use the guideline criteria for `yes`, `partial`, `no`, and `not_applicable`.
- Use review text as evidence for what the reviewer says.
- Use paper context to judge accuracy, grounding, independence, claim support,
  relevance, and applicability.
- The paper context may be truncated. Do not invent paper details beyond the
  provided context.
- `not_applicable` means the item is genuinely irrelevant to this paper/review
  context. If an item is relevant but the review fails to address it, use `no`.
- If one comment supports multiple checklist items, answer each item separately
  and explain the different role of the evidence under each item.

Direct evidence rules:
- Keep the review-level unit: answer once per checklist item for the whole
  review. Do not decompose the review into claim-level records.
- For each checklist item, include a short direct quote from the peer review
  when there is review evidence. Copy the quote exactly from the review text.
- Also report the review field if identifiable, such as `paper_summary`,
  `summary_of_strengths`, `summary_of_weaknesses`, or
  `comments,_suggestions_and_typos`.
- For items that require paper context, include a short direct quote from the
  provided paper context when it supports the judgement. Copy the quote exactly
  from the paper context; do not paraphrase it in `paper_evidence_quote`.
- If the paper context is retrieved chunks with `[CHUNK_ID ...]` and `[SECTION
  ...]` markers, copy the relevant chunk id and section into
  `paper_evidence_chunk_id` and `paper_evidence_section`.
- If paper evidence is not needed, not found, unavailable, or not applicable,
  leave the quote/chunk/section empty and set `paper_evidence_status`
  accordingly.
- `evidence_note`, `paper_evidence_note`, and `rationale` may paraphrase, but
  fields ending in `_quote` must be direct text spans from the provided input.
- Prefer short quotes. Use enough text to make the judgement auditable, not a
  long passage.

Return valid JSON only, with this schema:

```json
{
  "review_record_id": "string",
  "checklist_version": "checklist_draft_v0_3",
  "guideline_version": "annotation_guideline_v0_3",
  "application_prompt_version": "checklist_application_v0_2",
  "paper_context_used": "yes | partial | no",
  "checklist_answers": [
    {
      "question_id": "string",
      "dimension": "Coverage | Substance | Reasoning | Grounding | Constructiveness | Independence | Specificity | Clarity | Ethics",
      "answer": "yes | partial | no | not_applicable",
      "confidence": "high | medium | low",
      "review_evidence_quote": "short exact quote from the peer review, or empty string",
      "review_evidence_field": "review field label if identifiable, otherwise unknown or empty string",
      "paper_evidence_quote": "short exact quote from provided paper context, or empty string",
      "paper_evidence_chunk_id": "chunk id such as node0010_part00 if identifiable, otherwise empty string",
      "paper_evidence_section": "paper section if identifiable, otherwise empty string",
      "paper_evidence_status": "used | not_needed | not_found | paper_context_missing | not_applicable",
      "evidence_note": "short paraphrase of review evidence, or empty string",
      "paper_evidence_note": "short paraphrase of paper-context evidence if useful, otherwise empty string",
      "rationale": "brief reason using the guideline criteria",
      "context_limitation": "none | paper_context_truncated | paper_context_missing | other"
    }
  ],
  "dimension_summaries": [
    {
      "dimension": "string",
      "yes_n": 0,
      "partial_n": 0,
      "no_n": 0,
      "not_applicable_n": 0,
      "profile": "one sentence evidence-backed quality profile for this dimension"
    }
  ],
  "overall_quality_profile": {
    "main_strengths": ["short evidence-backed notes"],
    "main_gaps": ["short evidence-backed notes"],
    "most_informative_items": ["question_id"],
    "caution_notes": ["short notes about truncation, uncertainty, or applicability"]
  }
}
```

Quality rules:
- Include exactly one answer for every checklist item shown in the user message.
- Use the item-specific guideline criteria and pairwise boundary rules, not your
  own private rubric.
- Keep review evidence quotes grounded in the review.
- Keep paper evidence quotes grounded in the provided paper context.
- Do not use paper evidence quotes that are only your own summaries.
- Do not suggest guideline revisions in this application run.
- Do not report hard-to-distinguish pairs in this application run.
- Prefer `partial` over `yes` when the review only covers one minor part of a
  broad item or makes a vague comment.
- Prefer `not_applicable` only when the item is genuinely irrelevant to the
  paper/review context.
