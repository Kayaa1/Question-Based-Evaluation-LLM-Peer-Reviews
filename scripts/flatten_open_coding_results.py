"""Flatten formal open-coding JSONL results into the two analysis CSVs.

The original experiment performed this deterministic transformation in the
open-coding walkthrough notebook.  This standalone release utility preserves
that transformation without publishing the exploratory notebook.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT_PATH = (
    "outputs/open_coding/results/"
    "nlpeer_review_sample_ARR22-ARREMNLP24v1.1-EMNLP23_n180_seed20260613_"
    "open_coding_v0_1_all_requests_results_gpt-5.5_temp0.0.jsonl"
)
DEFAULT_BEHAVIOURS_OUTPUT = (
    "outputs/open_coding/analysis/open_coding_v0_1_n180_behaviours_flat.csv"
)
DEFAULT_QUESTIONS_OUTPUT = (
    "outputs/open_coding/analysis/"
    "open_coding_v0_1_n180_candidate_questions_flat.csv"
)

BEHAVIOUR_FIELDS = [
    "request_id",
    "review_record_id",
    "result_idx",
    "behaviour_idx",
    "dataset",
    "score_tier",
    "behaviour_label",
    "dimension_hint",
    "behaviour_type",
    "polarity",
    "evidence_quote",
    "evidence_field",
    "why_this_is_a_reviewing_behaviour",
    "label_norm",
]

QUESTION_FIELDS = [
    "request_id",
    "review_record_id",
    "result_idx",
    "question_idx",
    "dataset",
    "score_tier",
    "question",
    "linked_behaviour_labels",
    "linked_labels_text",
    "rationale",
]


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number} is not a JSON object")
            rows.append(value)
    return rows


def normalise_label(value: object) -> str:
    label = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", label).strip("_")


def flatten_behaviours(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for result_idx, row in enumerate(rows, start=1):
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        parsed = (
            row.get("parsed_output_json")
            if isinstance(row.get("parsed_output_json"), dict)
            else {}
        )
        behaviours = parsed.get("behaviours", [])
        if not isinstance(behaviours, list):
            raise ValueError(f"Result {result_idx} has a non-list behaviours field")
        for behaviour_idx, behaviour in enumerate(behaviours, start=1):
            if not isinstance(behaviour, dict):
                raise ValueError(
                    f"Result {result_idx}, behaviour {behaviour_idx} is not an object"
                )
            flattened.append(
                {
                    "request_id": row.get("request_id"),
                    "review_record_id": parsed.get("review_record_id"),
                    "result_idx": result_idx,
                    "behaviour_idx": behaviour_idx,
                    "dataset": source.get("dataset"),
                    "score_tier": source.get("score_tier_for_sampling_only"),
                    "behaviour_label": behaviour.get("behaviour_label"),
                    "dimension_hint": behaviour.get("dimension_hint"),
                    "behaviour_type": behaviour.get("behaviour_type"),
                    "polarity": behaviour.get("polarity"),
                    "evidence_quote": behaviour.get("evidence_quote"),
                    "evidence_field": behaviour.get("evidence_field"),
                    "why_this_is_a_reviewing_behaviour": behaviour.get(
                        "why_this_is_a_reviewing_behaviour"
                    ),
                    "label_norm": normalise_label(behaviour.get("behaviour_label")),
                }
            )
    return flattened


def flatten_candidate_questions(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for result_idx, row in enumerate(rows, start=1):
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        parsed = (
            row.get("parsed_output_json")
            if isinstance(row.get("parsed_output_json"), dict)
            else {}
        )
        questions = parsed.get("candidate_checklist_questions", [])
        if not isinstance(questions, list):
            raise ValueError(
                f"Result {result_idx} has a non-list candidate_checklist_questions field"
            )
        for question_idx, question in enumerate(questions, start=1):
            if not isinstance(question, dict):
                raise ValueError(
                    f"Result {result_idx}, question {question_idx} is not an object"
                )
            linked_labels = question.get("linked_behaviour_labels") or []
            if isinstance(linked_labels, str):
                linked_labels = [linked_labels]
            if not isinstance(linked_labels, list):
                raise ValueError(
                    f"Result {result_idx}, question {question_idx} has invalid labels"
                )
            linked_labels = [str(label) for label in linked_labels]
            flattened.append(
                {
                    "request_id": row.get("request_id"),
                    "review_record_id": parsed.get("review_record_id"),
                    "result_idx": result_idx,
                    "question_idx": question_idx,
                    "dataset": source.get("dataset"),
                    "score_tier": source.get("score_tier_for_sampling_only"),
                    "question": question.get("question"),
                    "linked_behaviour_labels": "|".join(linked_labels),
                    "linked_labels_text": ", ".join(linked_labels),
                    "rationale": question.get("rationale"),
                }
            )
    return flattened


def write_csv(rows: list[dict[str, Any]], fields: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flatten formal open-coding JSONL results into analysis CSVs."
    )
    parser.add_argument("--result-path", default=DEFAULT_RESULT_PATH)
    parser.add_argument("--behaviours-output", default=DEFAULT_BEHAVIOURS_OUTPUT)
    parser.add_argument("--questions-output", default=DEFAULT_QUESTIONS_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_path = resolve_path(args.result_path)
    behaviours_path = resolve_path(args.behaviours_output)
    questions_path = resolve_path(args.questions_output)

    rows = read_jsonl(result_path)
    behaviours = flatten_behaviours(rows)
    questions = flatten_candidate_questions(rows)
    write_csv(behaviours, BEHAVIOUR_FIELDS, behaviours_path)
    write_csv(questions, QUESTION_FIELDS, questions_path)

    print(
        json.dumps(
            {
                "result_records": len(rows),
                "behaviour_rows": len(behaviours),
                "candidate_question_rows": len(questions),
                "behaviours_output": str(behaviours_path),
                "questions_output": str(questions_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
