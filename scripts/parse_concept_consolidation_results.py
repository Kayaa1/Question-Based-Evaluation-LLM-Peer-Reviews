"""Parse LLM-assisted concept-consolidation results."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_RESULTS_PATH = (
    "outputs/open_coding/concept_grouping/results/"
    "open_coding_v0_1_n180_concept_consolidation_v0_1_requests_results_gpt-5.5_temp0.0.jsonl"
)
DEFAULT_LOCAL_SUMMARY_PATH = (
    "outputs/open_coding/concept_grouping/requests/"
    "open_coding_v0_1_n180_concept_consolidation_v0_1_local_concepts_with_ids.csv"
)
DEFAULT_ASSIGNMENTS_PATH = (
    "outputs/open_coding/concept_grouping/analysis/"
    "open_coding_v0_1_n180_concept_grouping_v0_1_llm_assignments.csv"
)
DEFAULT_OUTPUT_DIR = "outputs/open_coding/concept_grouping/analysis"
DEFAULT_PREFIX = "open_coding_v0_1_n180_concept_consolidation_v0_1"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def count_string(values: pd.Series, top_n: int = 10) -> str:
    counts = Counter(str(value) for value in values.dropna() if str(value).strip())
    return "; ".join(f"{key}: {value}" for key, value in counts.most_common(top_n))


def first_nonempty(values: pd.Series, n: int = 3, max_chars: int = 240) -> str:
    examples: list[str] = []
    seen: set[str] = set()
    for value in values.dropna():
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if len(text) > max_chars:
            text = text[: max_chars - 3].rstrip() + "..."
        examples.append(text)
        if len(examples) >= n:
            break
    return " || ".join(examples)


def extract_results(rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    global_rows: list[dict[str, Any]] = []
    assignment_rows: list[dict[str, Any]] = []
    uncertainty_rows: list[dict[str, Any]] = []
    validation: dict[str, Any] = {
        "result_rows": len(rows),
        "parsed_rows": 0,
        "parse_error_rows": 0,
        "missing_local_concept_ids": {},
        "extra_local_concept_ids": {},
        "duplicate_local_concept_ids": {},
        "unknown_global_concept_assignments": {},
    }

    for row in rows:
        source = row.get("source", {})
        batch_id = source.get("batch_id", "")
        expected_ids = set(source.get("local_concept_ids", []))
        parsed = row.get("parsed_output_json") or {}
        if not parsed:
            validation["parse_error_rows"] += 1
            continue
        validation["parsed_rows"] += 1

        global_concepts = parsed.get("global_concepts", [])
        global_labels = {concept.get("global_concept_label") for concept in global_concepts}
        for concept in global_concepts:
            global_rows.append(
                {
                    "batch_id": batch_id,
                    "primary_dimension_batch": source.get("primary_dimension", ""),
                    "global_concept_label": concept.get("global_concept_label", ""),
                    "global_concept_definition": concept.get("global_concept_definition", ""),
                    "final_dimension": concept.get("final_dimension", ""),
                    "known_failure_link": concept.get("known_failure_link", ""),
                    "keep_decision_suggested": concept.get("keep_decision_suggested", ""),
                    "candidate_checklist_question": concept.get("candidate_checklist_question", ""),
                    "source_local_concept_ids": "|".join(concept.get("source_local_concept_ids", []) or []),
                    "why_these_local_concepts_belong_together": concept.get(
                        "why_these_local_concepts_belong_together", ""
                    ),
                }
            )

        assigned_ids: list[str] = []
        for assignment in parsed.get("assignments", []):
            local_concept_id = assignment.get("local_concept_id", "")
            global_label = assignment.get("global_concept_label", "")
            assigned_ids.append(local_concept_id)
            assignment_rows.append(
                {
                    "batch_id": batch_id,
                    "primary_dimension_batch": source.get("primary_dimension", ""),
                    "local_concept_id": local_concept_id,
                    "global_concept_label": global_label,
                    "assignment_confidence": assignment.get("assignment_confidence", ""),
                    "assignment_rationale": assignment.get("rationale", ""),
                }
            )
            if global_label not in global_labels:
                validation["unknown_global_concept_assignments"].setdefault(batch_id, []).append(global_label)

        assigned_set = set(assigned_ids)
        missing = sorted(expected_ids - assigned_set)
        extra = sorted(assigned_set - expected_ids)
        duplicates = sorted([item for item, count in Counter(assigned_ids).items() if count > 1])
        if missing:
            validation["missing_local_concept_ids"][batch_id] = missing
        if extra:
            validation["extra_local_concept_ids"][batch_id] = extra
        if duplicates:
            validation["duplicate_local_concept_ids"][batch_id] = duplicates

        for idx, uncertainty in enumerate(parsed.get("uncertainties", []), start=1):
            uncertainty_rows.append(
                {
                    "batch_id": batch_id,
                    "uncertainty_idx": idx,
                    "uncertainty": str(uncertainty),
                }
            )

    return (
        pd.DataFrame(global_rows),
        pd.DataFrame(assignment_rows),
        pd.DataFrame(uncertainty_rows),
        validation,
    )


def build_global_summary(local_to_global: pd.DataFrame, behaviour_assignments: pd.DataFrame) -> pd.DataFrame:
    behaviour_global = behaviour_assignments.merge(
        local_to_global[["concept_label_llm_suggested", "global_concept_label"]],
        on="concept_label_llm_suggested",
        how="left",
    )
    summary = (
        behaviour_global.groupby("global_concept_label", dropna=False)
        .agg(
            mention_n=("global_concept_label", "size"),
            review_n=("review_record_id", "nunique"),
            local_concept_n=("concept_label_llm_suggested", "nunique"),
            dataset_counts=("dataset", count_string),
            score_tier_counts=("score_tier", count_string),
            dimension_hint_counts=("dimension_hint", count_string),
            behaviour_type_counts=("behaviour_type", count_string),
            example_local_concepts=("concept_label_llm_suggested", first_nonempty),
            example_behaviour_labels=("behaviour_label", first_nonempty),
            example_evidence_quotes=("evidence_quote", first_nonempty),
        )
        .reset_index()
        .sort_values(["review_n", "mention_n"], ascending=False)
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse LLM concept-consolidation results.")
    parser.add_argument("--results-path", default=DEFAULT_RESULTS_PATH, help="Consolidation-result JSONL.")
    parser.add_argument(
        "--local-summary-path",
        default=DEFAULT_LOCAL_SUMMARY_PATH,
        help="Local-summary CSV containing local_concept_id.",
    )
    parser.add_argument(
        "--assignments-path",
        default=DEFAULT_ASSIGNMENTS_PATH,
        help="Behaviour-assignments CSV from the first stage.",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Output filename prefix.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_path = Path(args.results_path)
    local_summary_path = Path(args.local_summary_path)
    assignments_path = Path(args.assignments_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(results_path)
    local_summary = pd.read_csv(local_summary_path).fillna("")
    behaviour_assignments = pd.read_csv(assignments_path).fillna("")
    global_concepts, local_assignments, uncertainties, validation = extract_results(rows)

    local_to_global = local_assignments.merge(local_summary, on="local_concept_id", how="left")
    global_summary = build_global_summary(local_to_global, behaviour_assignments)
    global_meta = (
        global_concepts.groupby("global_concept_label", dropna=False)
        .agg(
            global_concept_definitions=("global_concept_definition", first_nonempty),
            final_dimensions=("final_dimension", count_string),
            known_failure_links=("known_failure_link", count_string),
            keep_decisions_suggested=("keep_decision_suggested", count_string),
            candidate_checklist_questions=("candidate_checklist_question", first_nonempty),
        )
        .reset_index()
    )
    global_summary = global_summary.merge(global_meta, on="global_concept_label", how="left")

    concepts_path = output_dir / f"{args.prefix}_global_concepts.csv"
    local_assignments_path = output_dir / f"{args.prefix}_local_assignments.csv"
    local_to_global_path = output_dir / f"{args.prefix}_local_to_global.csv"
    global_summary_path = output_dir / f"{args.prefix}_global_summary.csv"
    uncertainties_path = output_dir / f"{args.prefix}_uncertainties.csv"
    validation_path = output_dir / f"{args.prefix}_validation.json"
    manual_path = output_dir / f"{args.prefix}_manual_workspace.csv"

    global_concepts.to_csv(concepts_path, index=False)
    local_assignments.to_csv(local_assignments_path, index=False)
    local_to_global.to_csv(local_to_global_path, index=False)
    global_summary.to_csv(global_summary_path, index=False)
    uncertainties.to_csv(uncertainties_path, index=False)

    manual = global_summary.copy()
    manual["global_concept_label_final"] = manual["global_concept_label"]
    manual["final_dimension_final"] = manual.get("final_dimensions", "")
    manual["keep_decision_final"] = manual.get("keep_decisions_suggested", "")
    manual["manual_check_note"] = ""
    if not manual_path.exists():
        manual.to_csv(manual_path, index=False)

    validation.update(
        {
            "global_concepts": len(global_concepts),
            "local_assignments": len(local_assignments),
            "local_to_global_rows": len(local_to_global),
            "unmatched_local_concepts": int(local_to_global["concept_label_llm_suggested"].isna().sum())
            if not local_to_global.empty
            else 0,
            "global_summary_rows": len(global_summary),
        }
    )
    validation_path.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "results_path": str(results_path),
                "concepts_path": str(concepts_path),
                "local_to_global_path": str(local_to_global_path),
                "global_summary_path": str(global_summary_path),
                "validation_path": str(validation_path),
                "manual_path": str(manual_path),
                **validation,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
