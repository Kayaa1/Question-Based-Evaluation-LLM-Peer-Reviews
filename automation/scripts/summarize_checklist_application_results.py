"""Summarise LLM output from automated checklist application.

This script supports the non-diagnostic application pipeline by expanding each
review's JSON output into three readable analysis tables:
- item-level answers: yes/partial/no/not_applicable for every checklist item;
- dimension-level profiles: an aggregate profile for each dimension;
- review-level profiles: the main strengths and gaps of each review.

It does not reassess the checklist or revise the guideline. It only converts model
output into CSV files and a summary suitable for subsequent comparisons, spot
checks, and research reporting.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULT_PATH = (
    "outputs/checklist_application/results/"
    "checklist_application_v0_1_n9_requests_results_gpt-5.5_temp0.0.jsonl"
)
DEFAULT_OUTPUT_DIR = "outputs/checklist_application/analysis"


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def add_metadata(records: list[dict[str, Any]], metadata_path: Path) -> None:
    """Add paper metadata omitted from older result JSONL using a local manifest."""

    metadata_rows = read_csv_rows(metadata_path)
    metadata_by_review_id: dict[str, dict[str, str]] = {}
    for row in metadata_rows:
        review_id = row.get("review_record_id", "").strip()
        if not review_id:
            raise ValueError("Metadata CSV contains a blank review_record_id.")
        if review_id in metadata_by_review_id:
            raise ValueError(
                f"Metadata CSV contains duplicate review_record_id: {review_id}"
            )
        metadata_by_review_id[review_id] = row

    missing_review_ids: list[str] = []
    missing_titles: list[str] = []
    for record in records:
        source = record.setdefault("source", {})
        review_id = str(source.get("review_record_id", "")).strip()
        metadata = metadata_by_review_id.get(review_id)
        if metadata is None:
            missing_review_ids.append(review_id or "<blank>")
            continue
        paper_title = (
            metadata.get("paper_title") or metadata.get("title") or ""
        ).strip()
        if not paper_title:
            missing_titles.append(review_id)
            continue
        source["paper_title"] = paper_title

    if missing_review_ids:
        raise ValueError(
            "Metadata CSV is missing result records: "
            + ", ".join(sorted(missing_review_ids))
        )
    if missing_titles:
        raise ValueError(
            "Metadata CSV records are missing paper titles: "
            + ", ".join(sorted(missing_titles))
        )


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_join(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, list):
        return " | ".join(str(value) for value in values)
    return str(values)


def flatten_answers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand review-level JSON into item-level answer rows.

    This is the primary table for calculating answer distributions, comparing ITG
    with RAG, and conducting human spot checks.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        parsed = record.get("parsed_output_json") or {}
        source = record.get("source") or {}
        for answer in parsed.get("checklist_answers", []):
            rows.append(
                {
                    "paper_title": source.get("paper_title", source.get("title", "")),
                    "pair_id": source.get("pair_id", ""),
                    "review_record_id": source.get(
                        "review_record_id", parsed.get("review_record_id", "")
                    ),
                    "source_type": source.get("source_type", ""),
                    "dataset": source.get("dataset", ""),
                    "score_tier": source.get("score_tier_for_sampling_only", ""),
                    "question_id": answer.get("question_id", ""),
                    "dimension": answer.get("dimension", ""),
                    "answer": answer.get("answer", ""),
                    "confidence": answer.get("confidence", ""),
                    "review_evidence_quote": answer.get("review_evidence_quote", ""),
                    "review_evidence_field": answer.get("review_evidence_field", ""),
                    "evidence_note": answer.get("evidence_note", ""),
                    "paper_evidence_quote": answer.get("paper_evidence_quote", ""),
                    "paper_evidence_section": answer.get("paper_evidence_section", ""),
                    "paper_evidence_chunk_id": answer.get("paper_evidence_chunk_id", ""),
                    "paper_evidence_status": answer.get("paper_evidence_status", ""),
                    "paper_evidence_note": answer.get("paper_evidence_note", ""),
                    "rationale": answer.get("rationale", ""),
                    "context_limitation": answer.get("context_limitation", ""),
                    "request_id": record.get("request_id", ""),
                    "checklist_version": source.get("checklist_version", ""),
                    "guideline_version": source.get("guideline_version", ""),
                    "paper_context_mode": source.get("paper_context_mode", ""),
                    "paper_context_truncated": source.get("paper_context_truncated", ""),
                    "paper_context_chars_sent": source.get("paper_context_chars_sent", ""),
                    "paper_context_full_chars": source.get("paper_context_full_chars", ""),
                    "paper_context_selected_chunk_n": source.get(
                        "paper_context_selected_chunk_n", ""
                    ),
                    "paper_context_retrieval_model": source.get(
                        "paper_context_retrieval_model", ""
                    ),
                    "openai_embedding_model": source.get("openai_embedding_model", ""),
                }
            )
    return rows


def flatten_dimension_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract each review's summary profile for every dimension."""
    rows: list[dict[str, Any]] = []
    for record in records:
        parsed = record.get("parsed_output_json") or {}
        source = record.get("source") or {}
        for summary in parsed.get("dimension_summaries", []):
            rows.append(
                {
                    "paper_title": source.get("paper_title", source.get("title", "")),
                    "pair_id": source.get("pair_id", ""),
                    "review_record_id": source.get(
                        "review_record_id", parsed.get("review_record_id", "")
                    ),
                    "source_type": source.get("source_type", ""),
                    "dataset": source.get("dataset", ""),
                    "score_tier": source.get("score_tier_for_sampling_only", ""),
                    "dimension": summary.get("dimension", ""),
                    "yes_n": summary.get("yes_n", ""),
                    "partial_n": summary.get("partial_n", ""),
                    "no_n": summary.get("no_n", ""),
                    "not_applicable_n": summary.get("not_applicable_n", ""),
                    "profile": summary.get("profile", ""),
                    "request_id": record.get("request_id", ""),
                    "paper_context_mode": source.get("paper_context_mode", ""),
                    "paper_context_retrieval_model": source.get(
                        "paper_context_retrieval_model", ""
                    ),
                }
            )
    return rows


def flatten_review_profiles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract each review's overall quality profile.

    This table is intended for a quick reading of the model's overall assessment
    rather than item-by-item inspection.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        parsed = record.get("parsed_output_json") or {}
        source = record.get("source") or {}
        profile = parsed.get("overall_quality_profile") or {}
        rows.append(
            {
                "paper_title": source.get("paper_title", source.get("title", "")),
                "pair_id": source.get("pair_id", ""),
                "review_record_id": source.get(
                    "review_record_id", parsed.get("review_record_id", "")
                ),
                "source_type": source.get("source_type", ""),
                "dataset": source.get("dataset", ""),
                "score_tier": source.get("score_tier_for_sampling_only", ""),
                "main_strengths": safe_join(profile.get("main_strengths")),
                "main_gaps": safe_join(profile.get("main_gaps")),
                "most_informative_items": safe_join(profile.get("most_informative_items")),
                "caution_notes": safe_join(profile.get("caution_notes")),
                "paper_context_used": parsed.get("paper_context_used", ""),
                "request_id": record.get("request_id", ""),
                "paper_context_mode": source.get("paper_context_mode", ""),
                "paper_context_chars_sent": source.get("paper_context_chars_sent", ""),
                "paper_context_full_chars": source.get("paper_context_full_chars", ""),
                "paper_context_selected_chunk_n": source.get(
                    "paper_context_selected_chunk_n", ""
                ),
                "paper_context_retrieval_model": source.get(
                    "paper_context_retrieval_model", ""
                ),
                "openai_embedding_model": source.get("openai_embedding_model", ""),
            }
        )
    return rows


def build_summary(
    records: list[dict[str, Any]],
    answer_rows: list[dict[str, Any]],
    dimension_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a run-level summary of output completeness and answer distributions."""
    answer_counts = Counter(row["answer"] for row in answer_rows)
    confidence_counts = Counter(row["confidence"] for row in answer_rows)
    context_limitation_counts = Counter(
        row["context_limitation"] for row in answer_rows if row.get("context_limitation")
    )
    paper_evidence_status_counts = Counter(
        row["paper_evidence_status"]
        for row in answer_rows
        if row.get("paper_evidence_status")
    )
    paper_context_modes = Counter(row["paper_context_mode"] for row in answer_rows)
    by_dimension: dict[str, Counter[str]] = defaultdict(Counter)
    by_question: dict[str, Counter[str]] = defaultdict(Counter)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    expected_answers = len(records) * len({row["question_id"] for row in answer_rows})

    for row in answer_rows:
        by_dimension[row["dimension"]].update([row["answer"]])
        by_question[row["question_id"]].update([row["answer"]])
        by_source[row.get("source_type", "")].update([row["answer"]])

    return {
        "records": len(records),
        "parsed_records": sum(record.get("parsed_output_json") is not None for record in records),
        "parse_error_count": sum(record.get("parsed_output_json") is None for record in records),
        "answer_rows": len(answer_rows),
        "expected_answer_rows_if_complete": expected_answers,
        "dimension_summary_rows": len(dimension_rows),
        "answer_counts": dict(answer_counts),
        "confidence_counts": dict(confidence_counts),
        "context_limitation_counts": dict(context_limitation_counts),
        "paper_evidence_status_counts": dict(paper_evidence_status_counts),
        "paper_context_mode_counts": dict(paper_context_modes),
        "answer_counts_by_dimension": {
            dimension: dict(counts) for dimension, counts in sorted(by_dimension.items())
        },
        "answer_counts_by_question": {
            question_id: dict(counts) for question_id, counts in sorted(by_question.items())
        },
        "answer_counts_by_source": {
            source_type: dict(counts) for source_type, counts in sorted(by_source.items())
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarise automated checklist-application results."
    )
    parser.add_argument("--result-path", default=DEFAULT_RESULT_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--metadata-path",
        help=(
            "Optional local manifest CSV used to restore paper_title and other "
            "metadata omitted from older result JSONL, matched by review_record_id."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_path = resolve_path(args.result_path)
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = read_jsonl(result_path)
    if args.metadata_path:
        add_metadata(records, resolve_path(args.metadata_path))
    answer_rows = flatten_answers(records)
    dimension_rows = flatten_dimension_summaries(records)
    profile_rows = flatten_review_profiles(records)
    summary = build_summary(records, answer_rows, dimension_rows)

    stem = result_path.stem
    answers_path = output_dir / f"{stem}_answers.csv"
    dimensions_path = output_dir / f"{stem}_dimension_summaries.csv"
    profiles_path = output_dir / f"{stem}_review_profiles.csv"
    summary_path = output_dir / f"{stem}_summary.json"

    write_csv(answer_rows, answers_path)
    write_csv(dimension_rows, dimensions_path)
    write_csv(profile_rows, profiles_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "answers_path": str(answers_path.relative_to(PROJECT_ROOT)),
                "dimension_summaries_path": str(dimensions_path.relative_to(PROJECT_ROOT)),
                "review_profiles_path": str(profiles_path.relative_to(PROJECT_ROOT)),
                "summary_path": str(summary_path.relative_to(PROJECT_ROOT)),
                **summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
