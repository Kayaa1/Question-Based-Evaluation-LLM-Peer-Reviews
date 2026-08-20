"""Build JSONL requests for LLM-assisted open coding.

This script does not call the OpenAI API. It converts sampled review records
into a request file that the API runner can read, allowing the prompt,
metadata, and review-text format to be inspected before incurring API costs.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from string import Template
from typing import Any


DEFAULT_SAMPLE_PATH = (
    "outputs/sampling/"
    "nlpeer_review_sample_ARR22-ARREMNLP24v1.1-EMNLP23_n180_seed20260613.csv"
)
DEFAULT_PROMPT_PATH = "prompts/open_coding.md"
DEFAULT_OUTPUT_DIR = "outputs/open_coding/requests"


def read_text(path: Path) -> str:
    with path.open(encoding="utf-8") as f:
        return f.read()


def read_sample_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def make_review_record_id(row: dict[str, str]) -> str:
    """Build a stable ID for joining model output back to the sample CSV."""

    return "::".join(
        [
            row["dataset"],
            row["paper_id"],
            row["version"],
            row["review_index"],
        ]
    )


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate an overlong review by character count to bound request size.

    The current sample's maximum word count is modest, so the default should
    not truncate anything. The parameter makes future expansion to larger
    samples or datasets safer.
    """

    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[TRUNCATED]"


def build_user_input(row: dict[str, str], review_record_id: str, max_review_chars: int) -> str:
    """Convert one sampled-review row into the model's input block."""

    review_text = truncate_text(row["review_text"], max_review_chars)
    score_proxy_field = row.get("score_proxy_field", "unknown")
    score_proxy_raw = row.get("score_proxy_raw", row.get("overall_score_raw", ""))

    template = Template(
        """Review metadata:
- review_record_id: $review_record_id
- dataset: $dataset
- paper_id: $paper_id
- version: $version
- review_index: $review_index
- score_tier_for_sampling_only: $score_tier
- score_proxy_field_for_sampling_only: $score_proxy_field
- score_proxy_raw_for_sampling_only: $score_proxy_raw
- paper_title: $title
- venue_or_cycle: $venue_or_cycle
- report_fields: $report_fields

Human peer review text:
$review_text
"""
    )

    return template.substitute(
        review_record_id=review_record_id,
        dataset=row["dataset"],
        paper_id=row["paper_id"],
        version=row["version"],
        review_index=row["review_index"],
        score_tier=row["score_tier"],
        score_proxy_field=score_proxy_field,
        score_proxy_raw=score_proxy_raw,
        title=row["title"],
        venue_or_cycle=row["venue_or_cycle"],
        report_fields=row["report_fields"],
        review_text=review_text,
    )


def build_request(
    row: dict[str, str],
    prompt_template: str,
    model: str,
    prompt_version: str,
    max_review_chars: int,
) -> dict[str, Any]:
    review_record_id = make_review_record_id(row)

    return {
        "request_id": f"open_coding::{review_record_id}",
        "task": "llm_assisted_open_coding",
        "prompt_version": prompt_version,
        "model": model,
        "source": {
            "review_record_id": review_record_id,
            "dataset": row["dataset"],
            "paper_id": row["paper_id"],
            "version": row["version"],
            "review_index": row["review_index"],
            "score_tier_for_sampling_only": row["score_tier"],
            "source_reviews_path": row["source_reviews_path"],
        },
        "messages": [
            {
                "role": "system",
                "content": prompt_template,
            },
            {
                "role": "user",
                "content": build_user_input(row, review_record_id, max_review_chars),
            },
        ],
        "expected_output": "valid_json_only",
    }


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build JSONL requests for LLM-assisted open coding.")
    parser.add_argument("--sample-path", default=DEFAULT_SAMPLE_PATH, help="Path to the sampling CSV.")
    parser.add_argument("--prompt-path", default=DEFAULT_PROMPT_PATH, help="Path to the open-coding prompt template.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for request JSONL files.")
    parser.add_argument("--model", default="gpt-5.5", help="ID of the model to use for open coding.")
    parser.add_argument(
        "--prompt-version",
        default="open_coding_v0_1",
        help="Prompt version to record in request metadata.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Build only the first N requests; use 0 for all rows.")
    parser.add_argument(
        "--max-review-chars",
        type=int,
        default=20000,
        help="Maximum characters per review_text; use 0 to disable truncation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    sample_path = Path(args.sample_path)
    prompt_path = Path(args.prompt_path)
    output_dir = Path(args.output_dir)

    rows = read_sample_rows(sample_path)
    if args.limit > 0:
        rows = rows[: args.limit]

    prompt_template = read_text(prompt_path)
    requests = [
        build_request(
            row=row,
            prompt_template=prompt_template,
            model=args.model,
            prompt_version=args.prompt_version,
            max_review_chars=args.max_review_chars,
        )
        for row in rows
    ]

    sample_stem = sample_path.stem
    limit_label = f"n{len(requests)}" if args.limit > 0 else "all"
    output_path = output_dir / f"{sample_stem}_{args.prompt_version}_{limit_label}_requests.jsonl"
    write_jsonl(requests, output_path)

    print(
        json.dumps(
            {
                "sample_path": str(sample_path),
                "prompt_path": str(prompt_path),
                "output_path": str(output_path),
                "prompt_version": args.prompt_version,
                "model": args.model,
                "requests": len(requests),
                "limit": args.limit,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
