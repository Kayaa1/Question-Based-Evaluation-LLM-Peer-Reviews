"""Build checklist draft v0.3 from the v0.2 item audit.

v0.3 does not rederive the checklist. It refines the 23 candidate items from
v0.2 based on the project's item-level audit: it rewrites the boundaries of
`COV_3` and `SUB_4`, and splits `REA_4` and `CON_3`.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path

from checklist_builder_core import (
    CHECKLIST_ITEMS as CHECKLIST_ITEMS_V0_2,
    DEFAULT_GLOBAL_SUMMARY,
    ROOT,
    read_global_summary,
)


DEFAULT_CSV_OUTPUT = (
    ROOT
    / "outputs/framework_derivation/checklist.csv"
)
DEFAULT_MD_OUTPUT = ROOT / "outputs/framework_derivation/checklist.md"
DEFAULT_TXT_OUTPUT = ROOT / "outputs/framework_derivation/checklist_questions.txt"


def build_v0_3_items() -> list[dict[str, object]]:
    items = []
    for original in CHECKLIST_ITEMS_V0_2:
        item = copy.deepcopy(original)
        question_id = item["question_id"]

        if question_id == "COV_3":
            item["candidate_question"] = (
                "Does the review consider whether the empirical scope covers relevant tasks, "
                "datasets, evaluation conditions, and generalisation settings?"
            )
            item["source_global_concepts"] = [
                "assesses_empirical_breadth_design_and_operational_coverage",
                "recommends_broader_generalization_or_robustness_evaluation",
                "identifies_limited_scope_or_missing_evaluation_conditions",
            ]
            item["rationale"] = (
                "v0.3 narrows COV_3 to empirical scope and generalisation; "
                "SUB_4 primarily covers baseline adequacy."
            )
            item["change_from_v0_2"] = "rewritten_boundary"
            items.append(item)
            continue

        if question_id == "SUB_4":
            item["candidate_question"] = (
                "Does the review judge whether the relevant baselines, comparisons, metrics, "
                "or empirical evidence are adequate for supporting the paper's contribution?"
            )
            item["source_global_concepts"] = [
                "assesses_baseline_and_comparison_coverage",
                "assesses_baseline_or_comparison_adequacy",
                "assesses_baseline_metric_or_comparison_adequacy",
                "suggests_stronger_baselines_metrics_or_comparisons",
            ]
            item["rationale"] = (
                "v0.3 retains empirical-support adequacy but uses 'relevant' "
                "and 'or' to avoid implying that every component must be covered; "
                "coverage of only one minor component should generally be partial."
            )
            item["change_from_v0_2"] = "rewritten_boundary"
            items.append(item)
            continue

        if question_id == "REA_4":
            items.append(
                {
                    "question_id": "REA_4a",
                    "dimension": "Reasoning",
                    "candidate_question": (
                        "Does the review assess or request ablations, robustness checks, "
                        "or sensitivity tests that would test whether the paper's claims hold?"
                    ),
                    "source_type": "bottom_up",
                    "source_global_concepts": [
                        "assesses_ablation_diagnostic_mechanism_or_robustness_analysis",
                        "requests_ablation_component_or_sensitivity_analysis",
                    ],
                    "rationale": "Split claim robustness, ablation, and sensitivity out of v0.2 REA_4.",
                    "needs_paper_text": "yes",
                    "change_from_v0_2": "split_from_REA_4",
                }
            )
            items.append(
                {
                    "question_id": "REA_4b",
                    "dimension": "Reasoning",
                    "candidate_question": (
                        "Does the review assess or request diagnostic, error, qualitative, "
                        "or mechanistic analyses that would explain why the results occur?"
                    ),
                    "source_type": "bottom_up",
                    "source_global_concepts": [
                        "requests_diagnostic_or_mechanistic_analysis",
                        "assesses_ablation_diagnostic_mechanism_or_robustness_analysis",
                        "requests_qualitative_examples_case_studies_or_error_analysis",
                    ],
                    "rationale": (
                        "Split diagnostic, explanatory, and mechanistic reasoning out of v0.2 REA_4."
                    ),
                    "needs_paper_text": "yes",
                    "change_from_v0_2": "split_from_REA_4",
                }
            )
            continue

        if question_id == "CON_3":
            items.append(
                {
                    "question_id": "CON_3a",
                    "dimension": "Constructiveness",
                    "candidate_question": (
                        "When asking for more empirical support, does the review specify "
                        "concrete additional experiments, baselines, comparisons, or "
                        "robustness checks rather than generic additions?"
                    ),
                    "source_type": "bottom_up",
                    "source_global_concepts": [
                        "suggests_stronger_baselines_metrics_or_comparisons",
                        "requests_ablation_component_or_sensitivity_analysis",
                        "requests_specific_experimental_reporting_or_result_explanation",
                    ],
                    "rationale": (
                        "In response to supervisor feedback, separate empirical-support requests from CON_3."
                    ),
                    "needs_paper_text": "partial",
                    "change_from_v0_2": "split_from_CON_3",
                }
            )
            items.append(
                {
                    "question_id": "CON_3b",
                    "dimension": "Constructiveness",
                    "candidate_question": (
                        "When asking for more explanatory support, does the review specify "
                        "concrete analyses, examples, case studies, or error analyses rather "
                        "than generic additions?"
                    ),
                    "source_type": "bottom_up",
                    "source_global_concepts": [
                        "requests_qualitative_examples_case_studies_or_error_analysis",
                        "requests_diagnostic_or_mechanistic_analysis",
                        "requests_specific_experimental_reporting_or_result_explanation",
                    ],
                    "rationale": (
                        "In response to supervisor feedback, separate explanatory and diagnostic-support "
                        "requests from CON_3."
                    ),
                    "needs_paper_text": "partial",
                    "change_from_v0_2": "split_from_CON_3",
                }
            )
            continue

        item["change_from_v0_2"] = "kept_needs_criteria"
        items.append(item)

    return items


CHECKLIST_ITEMS_V0_3 = build_v0_3_items()


def enrich_items(
    items: list[dict[str, object]], concepts: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    enriched = []
    for item in items:
        source_labels = [str(label) for label in item["source_global_concepts"]]
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
                "answer_scale": "yes/partial/no/not_applicable",
                "source_type": str(item["source_type"]),
                "needs_paper_text": str(item["needs_paper_text"]),
                "source_concept_n": str(len(source_rows)),
                "source_review_n_max": str(max(review_ns) if review_ns else ""),
                "source_mention_n_total": str(sum(mention_ns) if mention_ns else ""),
                "known_failure_links": "; ".join(known_failure_links)
                if known_failure_links
                else "none",
                "rationale": str(item["rationale"]),
                "source_global_concepts": "; ".join(source_labels),
                "missing_source_concepts": "; ".join(missing_labels),
                "change_from_v0_2": str(item["change_from_v0_2"]),
                "status": "candidate_v0_3",
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
        "change_from_v0_2",
        "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_question_txt(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    current_dimension = None
    for row in rows:
        if row["dimension"] != current_dimension:
            if lines:
                lines.append("")
            current_dimension = row["dimension"]
        lines.append(f"{row['dimension']}: {row['question_id']}: {row['candidate_question']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def markdown_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "| ID | Dimension | Candidate question | Change from v0.2 | Source / rationale |",
        "| --- | --- | --- | --- | --- |",
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
                    row["change_from_v0_2"],
                    source,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def count_by(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[key]] = counts.get(row[key], 0) + 1
    return counts


def write_markdown(rows: list[dict[str, str]], path: Path, csv_output: Path) -> None:
    shape = {
        "questions": len(rows),
        "by_dimension": count_by(rows, "dimension"),
        "by_source_type": count_by(rows, "source_type"),
        "by_change_from_v0_2": count_by(rows, "change_from_v0_2"),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    body = f"""# Checklist Draft v0.3

This is a refined **candidate** review-level checklist produced from
`checklist_draft_v0_2` after the item-level audit in
the project's item-level audit.

v0.3 is not a new derivation. It keeps the v0.2 high-frequency concept backbone
and only changes item granularity and boundaries so the checklist is closer to
annotation-ready.

## Source

- Open-coding sample: 180 human reviews from ARR-22, ARR-EMNLP-24-v1.1, and EMNLP23
- Open-coding output: 1379 behaviours
- Concept grouping: 1379 behaviours -> 350 local concepts -> 114 global concepts
- Previous checklist: generated internally by `checklist_builder_core.py`
- Item audit: retained in the private research record, not this public release
- Convenience CSV for this draft:
  `{csv_output.relative_to(ROOT)}`

## What Changed From v0.2

- v0.2 had 23 candidate items.
- v0.3 has 25 candidate items.
- Most items are kept and should receive clearer annotation criteria.
- `COV_3` and `SUB_4` are rewritten to clarify their boundary.
- `REA_4` is split into `REA_4a` and `REA_4b`.
- `CON_3` is split into `CON_3a` and `CON_3b`.
- The planned answer scale is now explicitly `yes / partial / no / not_applicable`.

## Current Shape

```json
{json.dumps(shape, indent=2)}
```

## Design Rules

- Each checklist item is answered at the **review level**, not once per sentence
  or behaviour.
- A good review does not need to satisfy every item; the checklist records what
  the review covers and what it misses.
- `yes / partial / no` is a three-level ordinal judgement. `not_applicable` is
  used when an item is not relevant to the paper/review context.
- One review comment may serve as evidence for multiple items, but the annotator
  must explain what role it plays under each item.
- v0.3 remains a candidate checklist. The next step is an annotation guideline
  with definitions, scoring criteria, and examples.

## Candidate Questions

{markdown_table(rows)}

## Boundary Rules For The Guideline

- `Coverage` asks whether the review notices relevant parts of the paper or
  empirical setup.
- `Substance` asks whether the review evaluates the importance, adequacy, or
  quality of those parts.
- `Reasoning` asks whether the review checks inference, evidence-to-claim logic,
  validity threats, or needed analyses.
- `Grounding` asks whether the review's own claims are supported by manuscript
  evidence or verifiable scholarly context.
- `Constructiveness` asks whether the review's requests are actionable and
  specific enough for authors to respond.
- `Independence` asks whether the review contributes its own assessment rather
  than echoing limitations already stated by the paper.
- `Specificity` asks whether feedback is locatable and precise, regardless of
  whether it is positive, negative, or a suggestion.
- `Clarity` asks whether the review identifies presentation, organisation,
  terminology, notation, or exposition problems in the paper.
- `Ethics` asks whether the review identifies relevant ethical, social, safety,
  privacy, release, or environmental concerns, or marks them as not applicable.

## Main Split Decisions

### REA_4 Split

- `REA_4a` captures robustness / ablation / sensitivity tests that check whether
  claims hold.
- `REA_4b` captures diagnostic / error / qualitative / mechanistic analyses that
  explain why results occur.

### CON_3 Split

- `CON_3a` captures concrete requests for empirical support, such as additional
  experiments, baselines, comparisons, or robustness checks.
- `CON_3b` captures concrete requests for explanatory support, such as analyses,
  examples, case studies, or error analyses.

## Next Step

Turn this v0.3 item list into `annotation_guideline_v0_1` by adding, for each
item:

- a short definition;
- `yes / partial / no / not_applicable` criteria;
- whether paper text is required;
- one positive example and one ambiguous or boundary example where possible.
"""
    path.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build checklist draft v0.3 from the v0.2 item audit."
    )
    parser.add_argument("--global-summary", type=Path, default=DEFAULT_GLOBAL_SUMMARY)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--txt-output", type=Path, default=DEFAULT_TXT_OUTPUT)
    args = parser.parse_args()

    concepts = read_global_summary(args.global_summary)
    rows = enrich_items(CHECKLIST_ITEMS_V0_3, concepts)
    write_csv(rows, args.csv_output)
    write_markdown(rows, args.md_output, args.csv_output)
    write_question_txt(rows, args.txt_output)

    missing = [row for row in rows if row["missing_source_concepts"]]
    print(
        json.dumps(
            {
                "checklist_items": len(rows),
                "csv_output": str(args.csv_output.relative_to(ROOT)),
                "md_output": str(args.md_output.relative_to(ROOT)),
                "txt_output": str(args.txt_output.relative_to(ROOT)),
                "missing_source_rows": len(missing),
                "by_dimension": count_by(rows, "dimension"),
                "by_change_from_v0_2": count_by(rows, "change_from_v0_2"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
