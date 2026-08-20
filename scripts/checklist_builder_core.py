"""Build the current candidate checklist draft from consolidated concepts.

This script condenses 114 LLM-consolidated global concepts into a candidate
review-level checklist. The mapping reflects human research judgement rather
than automated clustering: the LLM concepts provide evidence-backed input, and
the final questions are merged, rewritten, and selected by the researchers.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLOBAL_SUMMARY = (
    ROOT
    / "outputs/open_coding/concept_grouping/analysis/"
    / "open_coding_v0_1_n180_concept_consolidation_v0_1_global_summary.csv"
)
DEFAULT_CSV_OUTPUT = (
    ROOT
    / "outputs/framework_derivation/checklist_draft_v0_2.csv"
)
DEFAULT_MD_OUTPUT = ROOT / "outputs/framework_derivation/checklist_draft_v0_2.md"


CHECKLIST_ITEMS = [
    {
        "question_id": "COV_1",
        "dimension": "Coverage",
        "candidate_question": (
            "Does the review identify the paper's main task, contribution, method, "
            "and central claims accurately enough for the rest of the feedback to be interpretable?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "summarizes_core_contribution_task_method_and_claims",
            "summarizes_core_method_architecture_or_technical_details",
            "summarizes_concrete_contributions_context_or_findings",
        ],
        "rationale": (
            "Retain basic coverage of whether the review understands the paper under evaluation, "
            "without requiring every review to provide a long summary."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "COV_2",
        "dimension": "Coverage",
        "candidate_question": (
            "Does the review cover the paper's evaluation setup, datasets or benchmarks, "
            "and main empirical findings when these are relevant?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "summarizes_evaluation_setup_scope_and_findings",
            "summarizes_dataset_benchmark_or_resource_contribution",
            "summarizes_technical_framework_components_or_pipeline",
        ],
        "rationale": (
            "Combine summaries and coverage of evaluation, data, and resources into one coverage question."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "COV_3",
        "dimension": "Coverage",
        "candidate_question": (
            "Does the review consider whether the empirical scope covers relevant tasks, "
            "datasets, baselines, conditions, and generalisation settings?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "assesses_empirical_breadth_design_and_operational_coverage",
            "recommends_broader_generalization_or_robustness_evaluation",
            "identifies_limited_scope_or_missing_evaluation_conditions",
            "assesses_baseline_and_comparison_coverage",
        ],
        "rationale": "Cover evaluation breadth, generalisation, and missing conditions.",
        "needs_paper_text": "yes",
    },
    {
        "question_id": "SUB_1",
        "dimension": "Substance",
        "candidate_question": (
            "Does the review assess the novelty, significance, motivation, or gap-addressing "
            "value of the work rather than only restating the authors' claims?"
        ),
        "source_type": "hybrid",
        "source_global_concepts": [
            "assesses_contribution_novelty_significance_or_gap",
            "assesses_problem_importance_motivation_or_relevance",
            "assesses_novelty_significance_or_prior_work_positioning",
        ],
        "rationale": (
            "This is the most frequent substantive pattern and also addresses the risk of unsupported "
            "novelty judgements."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "SUB_2",
        "dimension": "Substance",
        "candidate_question": (
            "Does the review substantively assess the method design, component rationale, "
            "technical depth, simplicity, or implementation choices?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "assesses_method_design_motivation_and_component_rationale",
            "assesses_method_design_strength_simplicity_or_depth",
        ],
        "rationale": "Combine concepts related to method design, rationale, and technical depth.",
        "needs_paper_text": "yes",
    },
    {
        "question_id": "SUB_3",
        "dimension": "Substance",
        "candidate_question": (
            "Where relevant, does the review assess the value, validity, or usefulness of "
            "datasets, benchmarks, resources, code, models, or other artifacts?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "assesses_dataset_benchmark_resource_or_artifact_value",
            "assesses_dataset_or_benchmark_design_validity",
        ],
        "rationale": (
            "Retain substantive judgement of papers or contributions involving datasets, benchmarks, "
            "or resources."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "SUB_4",
        "dimension": "Substance",
        "candidate_question": (
            "Does the review judge whether baselines, comparisons, metrics, and empirical "
            "evidence are adequate for supporting the paper's contribution?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "assesses_baseline_or_comparison_adequacy",
            "assesses_baseline_metric_or_comparison_adequacy",
            "suggests_stronger_baselines_metrics_or_comparisons",
        ],
        "rationale": (
            "Baseline and comparison quality is a frequent substantive criterion, so retain it as a "
            "separate question for now."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "REA_1",
        "dimension": "Reasoning",
        "candidate_question": (
            "Does the review check whether major claims follow from the evidence, results, "
            "and internal logic of the paper?"
        ),
        "source_type": "hybrid",
        "source_global_concepts": [
            "checks_claim_support_and_inferential_validity",
            "checks_internal_coherence_between_paper_elements",
        ],
        "rationale": "Address the proposal's faulty-reasoning concern while also covering claim support.",
        "needs_paper_text": "yes",
    },
    {
        "question_id": "REA_2",
        "dimension": "Reasoning",
        "candidate_question": (
            "Does the review evaluate the appropriateness of metrics, measurement choices, "
            "statistical analysis, human evaluation, or construct operationalisation?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "evaluates_metrics_measurement_and_statistical_rigor",
            "evaluates_conceptual_framing_and_construct_validity",
            "assesses_task_construct_framing_or_operationalization",
            "requests_validation_or_interpretation_of_metrics_outputs_or_human_assessment",
        ],
        "rationale": (
            "Combine measurement, statistics, and construct validity into one reasoning question."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "REA_3",
        "dimension": "Reasoning",
        "candidate_question": (
            "Does the review identify confounds, unfair comparisons, alternative explanations, "
            "or threats to causal or comparative interpretation?"
        ),
        "source_type": "hybrid",
        "source_global_concepts": [
            "identifies_confounds_unfair_comparisons_or_alternative_explanations",
        ],
        "rationale": (
            "Retain this pattern because it is strongly related to faulty reasoning, despite not being "
            "among the most frequent."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "REA_4",
        "dimension": "Reasoning",
        "candidate_question": (
            "Does the review assess or request ablations, robustness checks, sensitivity tests, "
            "diagnostic analysis, or mechanistic explanations where they would clarify the claim?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "requests_diagnostic_or_mechanistic_analysis",
            "assesses_ablation_diagnostic_mechanism_or_robustness_analysis",
            "requests_ablation_component_or_sensitivity_analysis",
        ],
        "rationale": "Combine ablation, robustness, diagnostic, and mechanism analysis.",
        "needs_paper_text": "yes",
    },
    {
        "question_id": "GRO_1",
        "dimension": "Grounding",
        "candidate_question": (
            "Are the review's factual claims and evaluative judgements grounded in specific "
            "paper content, reported results, figures, tables, or examples?"
        ),
        "source_type": "hybrid",
        "source_global_concepts": [
            "grounds_positive_empirical_assessments_in_results",
            "grounds_positive_assessment_in_specific_evidence",
            "grounds_critiques_in_specific_manuscript_or_source_evidence",
            "grounds_non_empirical_contribution_in_concrete_elements",
        ],
        "rationale": (
            "This is the central grounding question and the main way to detect hallucinated or "
            "unsupported feedback."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "GRO_2",
        "dimension": "Grounding",
        "candidate_question": (
            "Are novelty, related-work, and positioning judgements grounded in concrete prior "
            "work, baselines, citations, or scholarly context?"
        ),
        "source_type": "hybrid",
        "source_global_concepts": [
            "situates_novelty_or_contribution_in_prior_work",
            "provides_specific_related_work_or_citation_feedback",
            "identifies_missing_related_work_baselines_or_novelty_comparisons",
        ],
        "rationale": "Combine novelty grounding with related-work specificity.",
        "needs_paper_text": "yes",
    },
    {
        "question_id": "GRO_3",
        "dimension": "Grounding",
        "candidate_question": (
            "Does the review avoid unsupported or hallucinated criticisms by tying negative "
            "feedback to evidence in the manuscript or verifiable scholarly context?"
        ),
        "source_type": "top_down",
        "source_global_concepts": [
            "grounds_critiques_in_specific_manuscript_or_source_evidence",
            "checks_claim_support_and_inferential_validity",
        ],
        "rationale": "Directly retain the known LLM failure: hallucination_or_unsupported_feedback.",
        "needs_paper_text": "yes",
    },
    {
        "question_id": "CON_1",
        "dimension": "Constructiveness",
        "candidate_question": (
            "Are the review's suggestions actionable, concrete, and tied to the specific issue "
            "being raised?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "checks_specificity_of_revision_guidance",
            "provides_locatable_editorial_corrections",
            "suggests_actionable_presentation_organization_or_claim_framing",
        ],
        "rationale": (
            "Constructiveness depends not only on whether a suggestion is present, but also on whether "
            "it is actionable."
        ),
        "needs_paper_text": "partial",
    },
    {
        "question_id": "CON_2",
        "dimension": "Constructiveness",
        "candidate_question": (
            "Does the review request concrete missing details needed for reproducibility, "
            "method reporting, setup clarification, or data documentation?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "requests_reproducibility_or_setup_clarification",
            "identifies_or_requests_missing_method_reporting_details",
            "requests_or_critiques_dataset_documentation_specificity",
        ],
        "rationale": (
            "Treat reproducibility, setup, and reporting details as an actionable constructiveness question."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "CON_3",
        "dimension": "Constructiveness",
        "candidate_question": (
            "When asking for more evidence, does the review specify meaningful additional "
            "experiments, analyses, baselines, examples, or error analyses rather than generic additions?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "suggests_stronger_baselines_metrics_or_comparisons",
            "requests_qualitative_examples_case_studies_or_error_analysis",
            "requests_specific_experimental_reporting_or_result_explanation",
        ],
        "rationale": "Avoid generic requests for more experiments and emphasize specific additional evidence.",
        "needs_paper_text": "partial",
    },
    {
        "question_id": "IND_1",
        "dimension": "Independence",
        "candidate_question": (
            "Does the review raise independent weaknesses or risks beyond simply echoing "
            "limitations already stated by the authors?"
        ),
        "source_type": "top_down",
        "source_global_concepts": [
            "identifies_limited_scope_or_missing_evaluation_conditions",
            "considers_analysis_depth_validation_and_interpretation",
            "checks_specificity_of_revision_guidance",
        ],
        "rationale": (
            "Directly retain the known LLM failure limitation_echo, even though its bottom-up frequency "
            "is not among the highest."
        ),
        "needs_paper_text": "yes",
    },
    {
        "question_id": "SPE_1",
        "dimension": "Specificity",
        "candidate_question": (
            "Does the review use specific references to methods, variables, datasets, results, "
            "examples, sections, citations, or claims when making feedback?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "summarizes_core_method_architecture_or_technical_details",
            "summarizes_concrete_contributions_context_or_findings",
            "identifies_missing_related_work_baselines_or_novelty_comparisons",
        ],
        "rationale": (
            "Specificity is a cross-dimensional quality: it means feedback is locatable, not merely long."
        ),
        "needs_paper_text": "partial",
    },
    {
        "question_id": "SPE_2",
        "dimension": "Specificity",
        "candidate_question": (
            "When the review asks for clarification or revision, does it name the missing, "
            "unclear, or problematic information precisely?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "identifies_or_requests_missing_method_reporting_details",
            "requests_specific_experimental_reporting_or_result_explanation",
            "flags_missing_reporting_documentation_or_context_details",
        ],
        "rationale": "Retain precision about missing details as a separate item to support annotation.",
        "needs_paper_text": "partial",
    },
    {
        "question_id": "CLA_1",
        "dimension": "Clarity",
        "candidate_question": (
            "Does the review assess readability, organisation, information flow, or presentation "
            "in a way that would help the authors revise the paper?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "assesses_overall_readability_and_writing_clarity",
            "assesses_structure_organization_and_information_flow",
            "evaluates_figures_tables_layout_and_visual_presentation",
        ],
        "rationale": (
            "Clarity frequently appears as an auxiliary category, so retain it as a candidate dimension "
            "for now."
        ),
        "needs_paper_text": "partial",
    },
    {
        "question_id": "CLA_2",
        "dimension": "Clarity",
        "candidate_question": (
            "Does the review identify unclear definitions, notation, terminology, figures, "
            "tables, or technical exposition where these affect understanding?"
        ),
        "source_type": "bottom_up",
        "source_global_concepts": [
            "assesses_clarity_of_methods_experiments_and_formal_details",
            "checks_definitions_terminology_notation_and_naming",
            "identifies_copyediting_formatting_and_surface_errors",
        ],
        "rationale": (
            "Combine technical clarity with terminology and notation to avoid reducing the item to "
            "copyediting."
        ),
        "needs_paper_text": "partial",
    },
    {
        "question_id": "ETH_1",
        "dimension": "Ethics",
        "candidate_question": (
            "Where relevant, does the review identify ethical, social, safety, fairness, bias, "
            "privacy, data-governance, release, or environmental concerns, or justify why none are apparent?"
        ),
        "source_type": "hybrid",
        "source_global_concepts": [
            "explicitly_addresses_presence_or_absence_of_ethics_concerns",
            "evaluates_artifact_availability_and_responsible_release_governance",
            "identifies_social_harm_bias_or_positionality_risks",
            "considers_computational_efficiency_or_environmental_cost",
        ],
        "rationale": (
            "Ethics is less frequent but remains meaningful for review completeness and responsible release."
        ),
        "needs_paper_text": "yes",
    },
]


def read_global_summary(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return {row["global_concept_label"]: row for row in csv.DictReader(f)}


def enrich_items(items: list[dict[str, object]], concepts: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    enriched = []
    for item in items:
        source_labels = item["source_global_concepts"]
        source_rows = [concepts[label] for label in source_labels if label in concepts]
        missing_labels = [label for label in source_labels if label not in concepts]

        review_ns = [int(row["review_n"]) for row in source_rows]
        mention_ns = [int(row["mention_n"]) for row in source_rows]
        known_failure_links = sorted(
            {
                link.strip()
                for row in source_rows
                for link in row.get("known_failure_links", "").split(";")
                if link.strip() and not link.strip().startswith("none")
            }
        )

        enriched.append(
            {
                "question_id": str(item["question_id"]),
                "dimension": str(item["dimension"]),
                "candidate_question": str(item["candidate_question"]),
                "source_type": str(item["source_type"]),
                "needs_paper_text": str(item["needs_paper_text"]),
                "source_global_concepts": "; ".join(source_labels),
                "source_concept_n": str(len(source_rows)),
                "source_review_n_max": str(max(review_ns) if review_ns else ""),
                "source_mention_n_total": str(sum(mention_ns) if mention_ns else ""),
                "known_failure_links": "; ".join(known_failure_links) if known_failure_links else "none",
                "rationale": str(item["rationale"]),
                "missing_source_concepts": "; ".join(missing_labels),
                "status": "candidate_v0_2",
                "answer_scale": "yes/partial/no",
            }
        )
    return enriched


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "question_id",
        "dimension",
        "candidate_question",
        "answer_scale",
        "source_type",
        "needs_paper_text",
        "source_concept_n",
        "source_review_n_max",
        "source_mention_n_total",
        "known_failure_links",
        "rationale",
        "source_global_concepts",
        "missing_source_concepts",
        "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "| ID | Dimension | Candidate question | Source / rationale |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        source = (
            f"{row['source_type']}; max review_n={row['source_review_n_max']}; "
            f"{row['rationale']}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    row["question_id"],
                    row["dimension"],
                    row["candidate_question"],
                    source,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def write_markdown(rows: list[dict[str, str]], path: Path, csv_output: Path) -> None:
    dimension_counts: dict[str, int] = {}
    source_type_counts: dict[str, int] = {}
    for row in rows:
        dimension_counts[row["dimension"]] = dimension_counts.get(row["dimension"], 0) + 1
        source_type_counts[row["source_type"]] = source_type_counts.get(row["source_type"], 0) + 1

    path.parent.mkdir(parents=True, exist_ok=True)
    body = f"""# Checklist Draft v0.2

This is the current **candidate** review-level checklist produced after the n180
open-coding derivation, LLM-assisted concept grouping, LLM-assisted consolidation,
and human spot-check of the lean concept sample.

It is not the final annotation guideline yet. The goal of v0.2 is only to decide
which questions are worth operationalising. The next version should add
definitions, yes/partial/no criteria, and worked examples.

## Source

- Open-coding prompt: `prompts/open_coding.md`
- Human review sample: 180 reviews from ARR-22, ARR-EMNLP-24-v1.1, and EMNLP23
- Open-coding output: 1379 behaviours
- Concept grouping: 1379 behaviours -> 350 local concepts -> 114 global concepts
- Main concept input:
  `outputs/open_coding/concept_grouping/analysis/open_coding_v0_1_n180_concept_consolidation_v0_1_global_summary.csv`
- Convenience CSV for this draft:
  `{csv_output.relative_to(ROOT)}`

## Design Rules

- Each checklist item is answered at the **review level**, not once per sentence or behaviour.
- The answer scale is planned as `yes / partial / no`.
- A good review does not need to hit every dimension equally; the checklist records what
  the review does well or misses.
- Frequency matters, but it is not the only rule. Known LLM-review failures such as
  hallucinated feedback, limitation echo, and faulty reasoning are retained even when
  they are not the most frequent bottom-up concepts.
- Multiple global concepts can map to one checklist question. This is expected because
  the 114 concepts are still more fine-grained than the final 15-25 checklist target.

## Current Shape

```json
{json.dumps({"questions": len(rows), "by_dimension": dimension_counts, "by_source_type": source_type_counts}, indent=2)}
```

## Current Coverage Caveat

This v0.2 draft should **not** be described as a complete one-to-one mapping of
all 114 global concepts. The current `source_global_concepts` links explicitly
reference 57 of the 114 global concepts. The remaining concepts may be covered
implicitly by broader questions, deferred because they are low-frequency or
less central, or still need manual review.

Before this draft is treated as research-ready, we need a separate global
concept coverage audit. That audit should assign every global concept one of
these statuses:

- `explicit_source`: explicitly listed under a checklist item.
- `covered_by_broader_question`: not listed, but semantically covered by a broader item.
- `deferred`: potentially useful, but not included in v0.2.
- `dropped`: excluded because it is too low-frequency, form-specific, redundant, or outside scope.
- `needs_review`: unclear and requiring manual inspection.

This matters because v0.2 is a candidate checklist synthesis, not a proof that
every global concept has already been accounted for.

## Candidate Questions

{markdown_table(rows)}

## Merged Or Deferred Patterns

- Pure paper-summary behaviours are kept only insofar as they show the reviewer understood
  the object of evaluation. We should not require a long summary if a venue form separates
  summary from critique.
- Surface copyediting is merged into Clarity. It should not become a standalone quality
  dimension unless later annotation shows it is important.
- Audience or venue fit is deferred because it was low frequency and less central to the
  current proposal.
- Ethics is retained as one conditional item. Later guideline writing should specify when
  `not applicable` is allowed versus when a paper should receive an ethics judgement.

## Known Overlap From Paper-Aware Pilot

### English

The paper-aware pilot showed that some checklist items overlap in practice. This
does not necessarily mean the questions are wrong, but the annotation guideline
must define their boundaries clearly.

One concrete example comes from the ARR-EMNLP-24-v1.1 / mid pilot review. The
reviewer asked for or discussed non-CoT baselines, larger-model analysis,
instance-level analysis, and dataset/evaluation consistency. The same feedback
can support several checklist items:

- `COV_3`: the review comments on empirical scope, such as datasets, settings,
  baselines, and generalisation conditions.
- `SUB_4`: the review judges whether baselines, comparisons, metrics, and
  empirical evidence are sufficient to support the contribution.
- `REA_4`: the review asks for ablations, robustness checks, diagnostic analysis,
  or other tests that clarify whether the claim holds.
- `CON_3`: the review gives concrete, actionable requests for additional
  experiments, analyses, baselines, or examples.

For example, a request for a non-CoT baseline is simultaneously a baseline
adequacy issue (`SUB_4`) and a concrete additional experiment (`CON_3`). If it
also changes the evaluation scope or tests whether the claim generalises, it may
also support `COV_3` or `REA_4`. Therefore, the guideline should allow one
review comment to serve as evidence for multiple items, but annotators must state
what kind of judgement it supports under each item.

### Additional Explanation

The paper-aware pilot showed that some checklist items overlap in practice.
This does not necessarily mean that the questions are wrong; it means that the
annotation guideline must define their boundaries clearly.

One concrete example comes from the ARR-EMNLP-24-v1.1 / mid pilot review. The
reviewer discussed or requested several related forms of feedback:

- a non-CoT baseline;
- larger-model analysis;
- instance-level analysis;
- dataset and evaluation consistency.

This feedback can support multiple checklist items:

- `COV_3`: whether the review discusses empirical scope, such as datasets,
  settings, baselines, and generalisation conditions.
- `SUB_4`: whether the review judges baselines, comparisons, metrics, and
  empirical evidence to be sufficient to support the contribution.
- `REA_4`: whether the review requests ablations, robustness checks, diagnostic
  analysis, or other analyses that can test whether a claim holds.
- `CON_3`: whether the review provides concrete, actionable requests for
  additional experiments, analyses, baselines, or examples.

For example, requesting a non-CoT baseline can be understood simultaneously as:

- a baseline-adequacy issue, supporting `SUB_4`;
- a concrete additional experiment, supporting `CON_3`;
- an expansion of the evaluation setup, potentially supporting `COV_3`;
- a test of whether the claim generalises, potentially supporting `REA_4`.

The next guideline should therefore allow one review comment to serve as
evidence for multiple items, but the annotator must explain the specific type
of judgement that the evidence supports under each item.

## Next Step

First, create a global concept coverage audit showing where each of the 114
global concepts went. Then turn the audited candidate checklist into
`annotation_guideline_v0_1`: for each item, write a short definition,
yes/partial/no criteria, and one or two worked examples from the spot-check
sample. Finally, pilot the guideline on 5-10 reviews before the formal IAA set.
"""
    path.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build candidate checklist draft v0.2 from consolidated concepts."
    )
    parser.add_argument("--global-summary", type=Path, default=DEFAULT_GLOBAL_SUMMARY)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    concepts = read_global_summary(args.global_summary)
    rows = enrich_items(CHECKLIST_ITEMS, concepts)
    write_csv(rows, args.csv_output)
    write_markdown(rows, args.md_output, args.csv_output)

    missing = [row for row in rows if row["missing_source_concepts"]]
    print(
        json.dumps(
            {
                "checklist_items": len(rows),
                "csv_output": str(args.csv_output.relative_to(ROOT)),
                "md_output": str(args.md_output.relative_to(ROOT)),
                "missing_source_rows": len(missing),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
