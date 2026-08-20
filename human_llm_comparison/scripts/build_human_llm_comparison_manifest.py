"""Convert 48 human--LLM pairs into 96 local automation manifest records."""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any


DEFAULT_HUMAN_PATH = (
    "outputs/validation_sampling/validation_sampling_v0_2_seed20260717_main_n48.csv"
)
DEFAULT_LLM_PATH = (
    "outputs/review_generation/analysis/"
    "validation_sampling_v0_2_seed20260717_main_n48_"
    "zero_shot_review_generation_v0_6_pdf_n48_requests_results_"
    "gpt-5.4_temp0.0_reviews.csv"
)
DEFAULT_OUTPUT_PATH = (
    "outputs/human_llm_comparison/inputs/human_llm_main_v0_1_seed20260719_n96.csv"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


SECTION_HEADING_MAP = {
    "paper_summary": "Summary",
    "summary_of_strengths": "Strengths",
    "summary_of_weaknesses": "Weaknesses",
    "comments,_suggestions_and_typos": "Comments and suggestions",
    "comments_suggestions_and_typos": "Comments and suggestions",
    "comments_suggestions_and_questions": "Comments and suggestions",
    "ethical_concerns": "Ethical concerns",
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def normalise_section_headings(review_text: str) -> str:
    """Standardise section labels so formatting does not reveal the review source."""

    for original, display in SECTION_HEADING_MAP.items():
        review_text = review_text.replace(f"[{original}]", f"[{display}]")
    if "[Ethical concerns]" not in review_text:
        review_text = review_text.rstrip() + "\n\n[Ethical concerns]\n"
    return review_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build 96 local manifest records for paired comparison."
    )
    parser.add_argument("--human-path", default=DEFAULT_HUMAN_PATH)
    parser.add_argument("--llm-path", default=DEFAULT_LLM_PATH)
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--seed", type=int, default=20260719)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    human_rows = read_csv_rows(resolve_path(args.human_path))
    llm_rows = read_csv_rows(resolve_path(args.llm_path))
    if len(human_rows) != 48 or len(llm_rows) != 48:
        raise ValueError(
            "Expected 48 human and 48 LLM reviews; found "
            f"{len(human_rows)} and {len(llm_rows)}."
        )

    llm_by_pair = {row["pair_id"]: row for row in llm_rows}
    if set(llm_by_pair) != {row["pair_id"] for row in human_rows}:
        raise ValueError("Human and LLM pair_id sets do not match.")

    records: list[dict[str, Any]] = []
    standard_fields = "Summary | Strengths | Weaknesses | Comments and suggestions | Ethical concerns"
    for human in sorted(human_rows, key=lambda row: row["pair_id"]):
        pair_id = human["pair_id"]
        llm = llm_by_pair[pair_id]
        common = {
            "pair_id": pair_id,
            "dataset": human["dataset"],
            "paper_id": human["paper_id"],
            "version": human["review_version"],
            "score_tier": human["score_tier"],
            "score_proxy_field": human["score_proxy_field"],
            "score_proxy_raw": human["score_proxy_raw"],
            "title": human["title"],
            "abstract": human["abstract"],
            "venue_or_cycle": human["venue_or_cycle"],
            "report_fields": standard_fields,
            "source_reviews_path": human["source_reviews_path"],
            "paper_itg_path": human["paper_itg_path"],
            "paper_pdf_path": human["paper_pdf_path"],
        }
        records.extend(
            [
                {
                    **common,
                    "source_type": "human",
                    "source_record_id": human["review_record_id"],
                    "review_index": human["review_index"],
                    "review_text": normalise_section_headings(human["review_text"]),
                    "review_word_count": human["review_word_count"],
                },
                {
                    **common,
                    "source_type": "llm",
                    "source_record_id": llm["generation_id"],
                    "review_index": "llm",
                    "review_text": normalise_section_headings(llm["generated_review_text"]),
                    "review_word_count": llm["generated_review_word_count"],
                },
            ]
        )

    random.Random(args.seed).shuffle(records)
    for number, record in enumerate(records, start=1):
        record["review_record_id"] = f"C{number:03d}"

    output_path = resolve_path(args.output_path)
    write_csv(records, output_path)
    summary = {
        "seed": args.seed,
        "rows": len(records),
        "pairs": len({row["pair_id"] for row in records}),
        "human_reviews": sum(row["source_type"] == "human" for row in records),
        "llm_reviews": sum(row["source_type"] == "llm" for row in records),
        "review_ids_unique": len({row["review_record_id"] for row in records}) == 96,
        "output_path": str(output_path.relative_to(PROJECT_ROOT)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
