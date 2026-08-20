"""Build JSONL requests for LLM-assisted concept grouping.

This script batches flattened open-coding behaviours by `dimension_hint` and
asks an LLM to propose semantic concept groupings. It only creates requests; it
does not call an API. Run the requests later with
`scripts/run_open_coding.py --request-path ...`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_BEHAVIOURS_PATH = (
    "outputs/open_coding/analysis/open_coding_v0_1_n180_behaviours_flat.csv"
)
DEFAULT_PROMPT_PATH = "prompts/concept_grouping.md"
DEFAULT_OUTPUT_DIR = "outputs/open_coding/concept_grouping/requests"
DEFAULT_PROMPT_VERSION = "concept_grouping_v0_1"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def truncate(text: Any, max_chars: int) -> str:
    value = str(text or "").replace("\n", " ").strip()
    value = " ".join(value.split())
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def make_behaviour_id(row: pd.Series) -> str:
    result_idx = int(row["result_idx"])
    behaviour_idx = int(row["behaviour_idx"])
    return f"B{result_idx:04d}_{behaviour_idx:02d}"


def format_behaviour(row: pd.Series, quote_chars: int, why_chars: int) -> str:
    return "\n".join(
        [
            f"- behaviour_id: {row['behaviour_id']}",
            f"  dataset: {row.get('dataset', '')}",
            f"  score_tier_for_sampling_only: {row.get('score_tier', '')}",
            f"  dimension_hint: {row.get('dimension_hint', '')}",
            f"  behaviour_type: {row.get('behaviour_type', '')}",
            f"  polarity: {row.get('polarity', '')}",
            f"  behaviour_label: {row.get('behaviour_label', '')}",
            f"  evidence_field: {row.get('evidence_field', '')}",
            f"  evidence_quote: {truncate(row.get('evidence_quote', ''), quote_chars)}",
            f"  why_this_is_a_reviewing_behaviour: {truncate(row.get('why_this_is_a_reviewing_behaviour', ''), why_chars)}",
        ]
    )


def build_user_input(
    batch_id: str,
    dimension_hint: str,
    batch_df: pd.DataFrame,
    quote_chars: int,
    why_chars: int,
) -> str:
    behaviour_block = "\n\n".join(
        format_behaviour(row, quote_chars=quote_chars, why_chars=why_chars)
        for _, row in batch_df.iterrows()
    )
    behaviour_ids = ", ".join(batch_df["behaviour_id"].tolist())

    return f"""Batch metadata:
- batch_id: {batch_id}
- provisional_dimension_hint_for_batching: {dimension_hint}
- behaviours_in_batch: {len(batch_df)}
- behaviour_ids: {behaviour_ids}

Behaviours to group:
{behaviour_block}
"""


def build_request(
    batch_id: str,
    dimension_hint: str,
    batch_df: pd.DataFrame,
    prompt_template: str,
    model: str,
    prompt_version: str,
    quote_chars: int,
    why_chars: int,
) -> dict[str, Any]:
    return {
        "request_id": f"{prompt_version}::{batch_id}",
        "task": "llm_assisted_concept_grouping",
        "prompt_version": prompt_version,
        "model": model,
        "source": {
            "batch_id": batch_id,
            "dimension_hint": dimension_hint,
            "behaviour_count": len(batch_df),
            "behaviour_ids": batch_df["behaviour_id"].tolist(),
            "datasets": sorted(batch_df["dataset"].dropna().astype(str).unique().tolist()),
            "score_tiers": sorted(batch_df["score_tier"].dropna().astype(str).unique().tolist()),
        },
        "messages": [
            {"role": "system", "content": prompt_template},
            {
                "role": "user",
                "content": build_user_input(
                    batch_id=batch_id,
                    dimension_hint=dimension_hint,
                    batch_df=batch_df,
                    quote_chars=quote_chars,
                    why_chars=why_chars,
                ),
            },
        ],
        "expected_output": "valid_json_only",
    }


def make_batches(behaviours: pd.DataFrame, max_behaviours_per_batch: int) -> list[tuple[str, str, pd.DataFrame]]:
    batches: list[tuple[str, str, pd.DataFrame]] = []
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

    behaviours = behaviours.copy()
    behaviours["dimension_hint"] = behaviours["dimension_hint"].fillna("Other")
    behaviours["dimension_rank"] = behaviours["dimension_hint"].map(
        {dimension: i for i, dimension in enumerate(dimension_order)}
    ).fillna(len(dimension_order))

    for dimension_hint, dimension_df in (
        behaviours.sort_values(["dimension_rank", "behaviour_type", "result_idx", "behaviour_idx"])
        .groupby("dimension_hint", sort=False)
    ):
        dimension_df = dimension_df.drop(columns=["dimension_rank"])
        for batch_index, start in enumerate(range(0, len(dimension_df), max_behaviours_per_batch), start=1):
            batch_df = dimension_df.iloc[start : start + max_behaviours_per_batch].copy()
            safe_dimension = "".join(ch if ch.isalnum() else "_" for ch in str(dimension_hint)).strip("_")
            batch_id = f"{safe_dimension}_batch{batch_index:02d}"
            batches.append((batch_id, str(dimension_hint), batch_df))
    return batches


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build LLM-assisted concept-grouping requests.")
    parser.add_argument("--behaviours-path", default=DEFAULT_BEHAVIOURS_PATH, help="Flattened-behaviours CSV.")
    parser.add_argument("--prompt-path", default=DEFAULT_PROMPT_PATH, help="Path to the concept-grouping prompt.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for request JSONL files.")
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION, help="Prompt-version metadata.")
    parser.add_argument("--model", default="gpt-5.5", help="ID of the model to call.")
    parser.add_argument(
        "--max-behaviours-per-batch",
        type=int,
        default=50,
        help="Maximum number of behaviours per request.",
    )
    parser.add_argument("--quote-chars", type=int, default=260, help="Maximum characters per evidence_quote.")
    parser.add_argument("--why-chars", type=int, default=220, help="Maximum characters per explanation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    behaviours_path = Path(args.behaviours_path)
    prompt_path = Path(args.prompt_path)
    output_dir = Path(args.output_dir)

    behaviours = pd.read_csv(behaviours_path)
    behaviours["behaviour_id"] = behaviours.apply(make_behaviour_id, axis=1)
    prompt_template = read_text(prompt_path)

    batches = make_batches(behaviours, max_behaviours_per_batch=args.max_behaviours_per_batch)
    requests = [
        build_request(
            batch_id=batch_id,
            dimension_hint=dimension_hint,
            batch_df=batch_df,
            prompt_template=prompt_template,
            model=args.model,
            prompt_version=args.prompt_version,
            quote_chars=args.quote_chars,
            why_chars=args.why_chars,
        )
        for batch_id, dimension_hint, batch_df in batches
    ]

    output_path = output_dir / f"open_coding_v0_1_n180_{args.prompt_version}_requests.jsonl"
    write_jsonl(requests, output_path)

    summary = {
        "behaviours_path": str(behaviours_path),
        "prompt_path": str(prompt_path),
        "output_path": str(output_path),
        "prompt_version": args.prompt_version,
        "model": args.model,
        "behaviours": len(behaviours),
        "requests": len(requests),
        "max_behaviours_per_batch": args.max_behaviours_per_batch,
        "batch_sizes": [len(batch_df) for _, _, batch_df in batches],
        "batches_by_dimension": {
            dimension: sum(1 for _, batch_dimension, _ in batches if batch_dimension == dimension)
            for dimension in sorted({dimension for _, dimension, _ in batches})
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
