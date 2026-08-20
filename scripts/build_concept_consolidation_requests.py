"""Build JSONL requests for LLM-assisted concept consolidation.

The first concept-grouping stage produces batch-local concepts. This script
batches their summaries by candidate dimension so the LLM can merge duplicate
and near-duplicate concepts.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SUMMARY_PATH = (
    "outputs/open_coding/concept_grouping/analysis/"
    "open_coding_v0_1_n180_concept_grouping_v0_1_llm_concept_summary.csv"
)
DEFAULT_PROMPT_PATH = "prompts/concept_consolidation.md"
DEFAULT_OUTPUT_DIR = "outputs/open_coding/concept_grouping/requests"
DEFAULT_PROMPT_VERSION = "concept_consolidation_v0_1"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def truncate(text: Any, max_chars: int) -> str:
    value = str(text or "").replace("\n", " ").strip()
    value = " ".join(value.split())
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def primary_dimension(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Other"
    first = text.split(";")[0].strip()
    if ":" in first:
        first = first.split(":", 1)[0].strip()
    allowed = {
        "Specificity",
        "Independence",
        "Grounding",
        "Constructiveness",
        "Substance",
        "Coverage",
        "Reasoning",
        "Clarity",
        "Ethics",
        "Other",
    }
    return first if first in allowed else "Other"


def make_local_concept_id(index: int) -> str:
    return f"LC{index:04d}"


def format_local_concept(row: pd.Series, text_chars: int) -> str:
    return "\n".join(
        [
            f"- local_concept_id: {row['local_concept_id']}",
            f"  local_concept_label: {row.get('concept_label_llm_suggested', '')}",
            f"  primary_dimension_candidate: {row.get('primary_dimension_candidate', '')}",
            f"  review_n: {row.get('review_n', '')}",
            f"  mention_n: {row.get('mention_n', '')}",
            f"  dataset_counts: {row.get('dataset_counts', '')}",
            f"  score_tier_counts: {row.get('score_tier_counts', '')}",
            f"  local_definition_examples: {truncate(row.get('concept_definitions', ''), text_chars)}",
            f"  candidate_question_examples: {truncate(row.get('candidate_checklist_questions', ''), text_chars)}",
            f"  example_behaviour_labels: {truncate(row.get('example_behaviour_labels', ''), text_chars)}",
            f"  example_evidence_quotes: {truncate(row.get('example_evidence_quotes', ''), text_chars)}",
            f"  known_failure_links: {row.get('known_failure_links', '')}",
        ]
    )


def build_user_input(batch_id: str, dimension: str, batch_df: pd.DataFrame, text_chars: int) -> str:
    local_ids = ", ".join(batch_df["local_concept_id"].tolist())
    concept_block = "\n\n".join(
        format_local_concept(row, text_chars=text_chars) for _, row in batch_df.iterrows()
    )
    return f"""Batch metadata:
- batch_id: {batch_id}
- primary_dimension_for_batching: {dimension}
- local_concepts_in_batch: {len(batch_df)}
- local_concept_ids: {local_ids}

Local concepts to consolidate:
{concept_block}
"""


def build_request(
    batch_id: str,
    dimension: str,
    batch_df: pd.DataFrame,
    prompt_template: str,
    model: str,
    prompt_version: str,
    text_chars: int,
) -> dict[str, Any]:
    return {
        "request_id": f"{prompt_version}::{batch_id}",
        "task": "llm_assisted_concept_consolidation",
        "prompt_version": prompt_version,
        "model": model,
        "source": {
            "batch_id": batch_id,
            "primary_dimension": dimension,
            "local_concept_count": len(batch_df),
            "local_concept_ids": batch_df["local_concept_id"].tolist(),
        },
        "messages": [
            {"role": "system", "content": prompt_template},
            {
                "role": "user",
                "content": build_user_input(
                    batch_id=batch_id,
                    dimension=dimension,
                    batch_df=batch_df,
                    text_chars=text_chars,
                ),
            },
        ],
        "expected_output": "valid_json_only",
    }


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def make_batches(summary: pd.DataFrame, max_concepts_per_batch: int) -> list[tuple[str, str, pd.DataFrame]]:
    dimension_order = [
        "Reasoning",
        "Constructiveness",
        "Substance",
        "Coverage",
        "Specificity",
        "Grounding",
        "Independence",
        "Clarity",
        "Ethics",
        "Other",
    ]
    summary = summary.copy()
    summary["primary_dimension_candidate"] = summary["final_dimension_candidates"].map(primary_dimension)
    summary["dimension_rank"] = summary["primary_dimension_candidate"].map(
        {dimension: idx for idx, dimension in enumerate(dimension_order)}
    ).fillna(len(dimension_order))
    summary = summary.sort_values(
        ["dimension_rank", "review_n", "mention_n", "concept_label_llm_suggested"],
        ascending=[True, False, False, True],
    )

    batches: list[tuple[str, str, pd.DataFrame]] = []
    for dimension, dimension_df in summary.groupby("primary_dimension_candidate", sort=False):
        dimension_df = dimension_df.drop(columns=["dimension_rank"])
        for batch_index, start in enumerate(range(0, len(dimension_df), max_concepts_per_batch), start=1):
            batch_df = dimension_df.iloc[start : start + max_concepts_per_batch].copy()
            batch_id = f"{safe_name(str(dimension))}_concepts_batch{batch_index:02d}"
            batches.append((batch_id, str(dimension), batch_df))
    return batches


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build LLM-assisted concept consolidation requests.")
    parser.add_argument("--summary-path", default=DEFAULT_SUMMARY_PATH, help="LLM local-concept summary CSV.")
    parser.add_argument("--prompt-path", default=DEFAULT_PROMPT_PATH, help="Path to the consolidation prompt.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for request JSONL files.")
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION, help="Prompt-version metadata.")
    parser.add_argument("--model", default="gpt-5.5", help="ID of the model to call.")
    parser.add_argument(
        "--max-concepts-per-batch",
        type=int,
        default=45,
        help="Maximum number of local concepts per request.",
    )
    parser.add_argument("--text-chars", type=int, default=260, help="Maximum characters per long-text field.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary_path = Path(args.summary_path)
    prompt_path = Path(args.prompt_path)
    output_dir = Path(args.output_dir)

    summary = pd.read_csv(summary_path).fillna("")
    summary = summary.reset_index(drop=True)
    summary["local_concept_id"] = [make_local_concept_id(index + 1) for index in range(len(summary))]
    prompt_template = read_text(prompt_path)

    batches = make_batches(summary, max_concepts_per_batch=args.max_concepts_per_batch)
    requests = [
        build_request(
            batch_id=batch_id,
            dimension=dimension,
            batch_df=batch_df,
            prompt_template=prompt_template,
            model=args.model,
            prompt_version=args.prompt_version,
            text_chars=args.text_chars,
        )
        for batch_id, dimension, batch_df in batches
    ]

    output_path = output_dir / f"open_coding_v0_1_n180_{args.prompt_version}_requests.jsonl"
    write_jsonl(requests, output_path)

    local_summary_path = output_dir / f"open_coding_v0_1_n180_{args.prompt_version}_local_concepts_with_ids.csv"
    summary.to_csv(local_summary_path, index=False)

    print(
        json.dumps(
            {
                "summary_path": str(summary_path),
                "prompt_path": str(prompt_path),
                "output_path": str(output_path),
                "local_summary_path": str(local_summary_path),
                "prompt_version": args.prompt_version,
                "model": args.model,
                "local_concepts": len(summary),
                "requests": len(requests),
                "max_concepts_per_batch": args.max_concepts_per_batch,
                "batch_sizes": [len(batch_df) for _, _, batch_df in batches],
                "batches_by_dimension": {
                    dimension: sum(1 for _, batch_dimension, _ in batches if batch_dimension == dimension)
                    for dimension in sorted({dimension for _, dimension, _ in batches})
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
