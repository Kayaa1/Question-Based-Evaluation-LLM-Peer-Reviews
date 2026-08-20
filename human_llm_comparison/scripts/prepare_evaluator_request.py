"""Create a per-evaluator request JSONL from the frozen human--LLM request.

This script copies an existing source-blind request JSONL and changes only the
top-level ``model`` metadata field. It intentionally does not rebuild prompts,
guidelines, review text, or paper context, so different evaluator models can be
run on identical inputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_REQUEST_PATH = (
    "outputs/human_llm_comparison/evaluators/gpt-5.5/requests/"
    "human_llm_main_v0_1_checklist_application_v0_2_rag_bm25_n96_requests.jsonl"
)
DEFAULT_OUTPUT_ROOT = "outputs/human_llm_comparison/evaluators"


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a source-blind request JSONL for one evaluator model."
    )
    parser.add_argument("--evaluator-id", required=True, help="Folder name under evaluators/.")
    parser.add_argument(
        "--model",
        required=True,
        help="Model metadata to write into the copied request JSONL.",
    )
    parser.add_argument(
        "--source-request-path",
        default=DEFAULT_SOURCE_REQUEST_PATH,
        help="Frozen source request JSONL to copy.",
    )
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help="Root folder containing per-evaluator subfolders.",
    )
    parser.add_argument(
        "--output-filename",
        default="",
        help="Optional output filename. Defaults to the source request filename.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing evaluator request file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = resolve_path(args.source_request_path)
    output_root = resolve_path(args.output_root)
    output_filename = args.output_filename or source_path.name
    output_path = output_root / args.evaluator_id / "requests" / output_filename

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output request already exists: {display_path(output_path)}. "
            "Use --overwrite to replace it."
        )

    records = read_jsonl(source_path)
    for record in records:
        record["model"] = args.model
    write_jsonl(records, output_path)

    print(
        json.dumps(
            {
                "source_request_path": display_path(source_path),
                "output_request_path": display_path(output_path),
                "evaluator_id": args.evaluator_id,
                "model": args.model,
                "records": len(records),
                "changed_field": "model",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
