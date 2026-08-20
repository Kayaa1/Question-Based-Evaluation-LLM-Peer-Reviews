"""Build zero-shot review-generation requests for held-out papers.

The model receives only the matching manuscript version and an opaque generation ID.
Human reviews, score tiers, acceptance decisions, the checklist, and the annotation
guideline are never included in the messages; they appear only in the private
selection manifest or subsequent analysis.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE_PATH = (
    "outputs/validation_sampling/"
    "validation_sampling_v0_2_seed20260717_human_pilot_n3.csv"
)
DEFAULT_PROMPT_PATH = "prompts/review_generation.md"
DEFAULT_OUTPUT_DIR = "outputs/review_generation/requests"
DEFAULT_PROMPT_VERSION = "zero_shot_review_generation_v0_6"


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalise_text(value: object) -> str:
    return " ".join(str(value or "").split())


def node_section(node: dict[str, Any], current_section: str) -> str:
    meta = node.get("meta")
    if isinstance(meta, dict) and meta.get("section"):
        return normalise_text(meta["section"])
    return current_section


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def extract_tei_table_text(value: object) -> str:
    """Recover table-cell text from bytes-repr TEI XML in a media node."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("b'", 'b"')):
        try:
            decoded = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return ""
        if not isinstance(decoded, bytes):
            return ""
        raw = decoded.decode("utf-8", errors="replace")
    if "<" not in raw or "table" not in raw:
        return ""

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    if xml_local_name(root.tag) != "table":
        return ""

    rows: list[str] = []
    for row in root.iter():
        if xml_local_name(row.tag) != "row":
            continue
        cells: list[str] = []
        for cell in row:
            if xml_local_name(cell.tag) != "cell":
                continue
            cell_text = normalise_text(" ".join(cell.itertext()))
            cells.append(cell_text)
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def linearise_itg(paper: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Linearize ITG nodes while preserving traceable node, type, and section markers."""

    pieces: list[str] = []
    current_section = ""
    included_nodes = 0
    skipped_media_nodes = 0
    included_media_table_nodes = 0
    empty_nodes = 0

    nodes = paper.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("The nodes field in paper.itg.json is not a list.")

    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            empty_nodes += 1
            continue

        node_type = normalise_text(node.get("ntype", "text")) or "text"
        if node_type == "media":
            content = extract_tei_table_text(node.get("content", ""))
            if not content:
                skipped_media_nodes += 1
                continue
            node_type = "table_content"
            included_media_table_nodes += 1
        else:
            content = normalise_text(node.get("content", ""))
        if not content:
            empty_nodes += 1
            continue

        if node_type == "heading":
            current_section = node_section(node, content) or content
        section = node_section(node, current_section)
        node_id = normalise_text(node.get("ix", "")) or f"node_{node_index:04d}"

        marker = f"[NODE {node_id}] [TYPE {node_type}]"
        if section:
            marker += f" [SECTION {section}]"
        pieces.append(f"{marker}\n{content}")
        included_nodes += 1

    text = "\n\n".join(pieces)
    stats = {
        "total_nodes": len(nodes),
        "included_nodes": included_nodes,
        "skipped_media_nodes": skipped_media_nodes,
        "included_media_table_nodes": included_media_table_nodes,
        "empty_or_invalid_nodes": empty_nodes,
        "paper_text_chars": len(text),
    }
    return text, stats


def build_user_message(
    generation_id: str,
    title: str,
    paper_input_mode: str,
    paper_text: str = "",
) -> str:
    if paper_input_mode == "pdf":
        manuscript_block = "The complete manuscript PDF is attached to this message."
    else:
        manuscript_block = f"BEGIN MANUSCRIPT\n{paper_text}\nEND MANUSCRIPT"
    return (
        "Generate an independent peer review for the manuscript below.\n\n"
        f"generation_id: {generation_id}\n"
        f"manuscript_title: {title}\n\n"
        f"{manuscript_block}"
    )


def validate_manifest_row(row: dict[str, str], paper_itg_path: Path) -> None:
    required = [
        "pair_id",
        "dataset",
        "paper_id",
        "review_version",
        "review_record_id",
        "title",
        "paper_itg_path",
        "paper_pdf_path",
    ]
    missing = [field for field in required if not row.get(field)]
    if missing:
        raise ValueError(f"Selection manifest is missing required field values: {missing}")

    if paper_itg_path.parent.name != row["review_version"]:
        raise ValueError(
            f"{row['pair_id']} version mismatch: review={row['review_version']}, "
            f"paper={paper_itg_path.parent.name}"
        )
    if not resolve_path(row["paper_pdf_path"]).is_file():
        raise FileNotFoundError(
            f"Matching-version PDF not found: {row['paper_pdf_path']}"
        )


def build_request(
    row: dict[str, str],
    prompt_text: str,
    prompt_version: str,
    model: str,
    max_paper_chars: int,
    paper_input_mode: str,
) -> dict[str, Any]:
    generation_id = f"LLM_REVIEW::{row['pair_id']}"
    paper_itg_path = resolve_path(row["paper_itg_path"])
    if not paper_itg_path.is_file():
        raise FileNotFoundError(f"Paper ITG not found: {paper_itg_path}")
    validate_manifest_row(row, paper_itg_path)

    raw_itg = paper_itg_path.read_bytes()
    paper_pdf_path = resolve_path(row["paper_pdf_path"])
    raw_pdf = paper_pdf_path.read_bytes()
    paper_text = ""
    paper_stats: dict[str, int] = {
        "total_nodes": 0,
        "included_nodes": 0,
        "skipped_media_nodes": 0,
        "included_media_table_nodes": 0,
        "empty_or_invalid_nodes": 0,
        "paper_text_chars": 0,
    }
    if paper_input_mode == "itg_text":
        paper = json.loads(raw_itg.decode("utf-8"))
        paper_text, paper_stats = linearise_itg(paper)
        if len(paper_text) < 5_000:
            raise ValueError(
                f"{row['pair_id']} paper text is too short: {len(paper_text)} chars"
            )
        if max_paper_chars > 0 and len(paper_text) > max_paper_chars:
            raise ValueError(
                f"{row['pair_id']} paper text={len(paper_text)} chars exceeds "
                f"--max-paper-chars={max_paper_chars}; aborting to avoid silent truncation."
            )

    user_message = build_user_message(
        generation_id,
        row["title"],
        paper_input_mode=paper_input_mode,
        paper_text=paper_text,
    )
    if row.get("review_text") and row["review_text"] in user_message:
        raise AssertionError("Human review text unexpectedly entered the generation message.")
    forbidden_metadata_labels = ["score_tier", "acceptance_decision", "human_review"]
    leaked_labels = [label for label in forbidden_metadata_labels if label in user_message.lower()]
    if leaked_labels:
        raise AssertionError(
            f"Generation message contains forbidden metadata labels: {leaked_labels}"
        )

    source = {
        "generation_id": generation_id,
        "pair_id": row["pair_id"],
        "dataset": row["dataset"],
        "paper_id": row["paper_id"],
        "paper_version": paper_itg_path.parent.name,
        "human_review_record_id": row["review_record_id"],
        "paper_itg_path": display_path(paper_itg_path),
        "paper_pdf_path": display_path(paper_pdf_path),
        "paper_input_mode": paper_input_mode,
        "paper_input_sha256": (
            sha256_bytes(raw_pdf)
            if paper_input_mode == "pdf"
            else sha256_bytes(paper_text.encode("utf-8"))
        ),
        "paper_input_bytes": len(raw_pdf) if paper_input_mode == "pdf" else len(paper_text.encode("utf-8")),
        "paper_input_truncated": False,
        "paper_itg_sha256": sha256_bytes(raw_itg),
        "paper_pdf_sha256": sha256_bytes(raw_pdf),
        "paper_text_sha256": (
            sha256_bytes(paper_text.encode("utf-8")) if paper_text else None
        ),
        "paper_text_truncated": False,
        **paper_stats,
    }
    return {
        "request_id": f"review_generation::{prompt_version}::{row['pair_id']}",
        "task": "zero_shot_peer_review_generation",
        "prompt_version": prompt_version,
        "model": model,
        "source": source,
        "messages": [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": user_message},
        ],
        "expected_output": "valid_json_only",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build zero-shot peer-review generation requests."
    )
    parser.add_argument("--sample-path", default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--prompt-path", default=DEFAULT_PROMPT_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument(
        "--paper-input-mode",
        choices=["pdf", "itg_text"],
        default="pdf",
        help=(
            "Production generation sends the matching-version PDF by default; "
            "itg_text remains available for fallback and auditing."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Use 0 to build all sample rows."
    )
    parser.add_argument(
        "--max-paper-chars",
        type=int,
        default=120_000,
        help=(
            "Raise an error instead of silently truncating text that exceeds the limit; "
            "use 0 for no limit."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sample_path = resolve_path(args.sample_path)
    prompt_path = resolve_path(args.prompt_path)
    output_dir = resolve_path(args.output_dir)

    rows = read_csv_rows(sample_path)
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise ValueError("Selection manifest has no rows to build.")

    prompt_text = prompt_path.read_text(encoding="utf-8")
    requests = [
        build_request(
            row=row,
            prompt_text=prompt_text,
            prompt_version=args.prompt_version,
            model=args.model,
            max_paper_chars=args.max_paper_chars,
            paper_input_mode=args.paper_input_mode,
        )
        for row in rows
    ]

    sample_stem = sample_path.stem
    output_path = output_dir / (
        f"{sample_stem}_{args.prompt_version}_{args.paper_input_mode}_"
        f"n{len(requests)}_requests.jsonl"
    )
    write_jsonl(requests, output_path)

    input_sizes = [request["source"]["paper_input_bytes"] for request in requests]
    print(
        json.dumps(
            {
                "sample_path": display_path(sample_path),
                "prompt_path": display_path(prompt_path),
                "prompt_version": args.prompt_version,
                "model": args.model,
                "paper_input_mode": args.paper_input_mode,
                "requests": len(requests),
                "output_path": display_path(output_path),
                "paper_input_size_bytes": {
                    "min": min(input_sizes),
                    "mean": round(sum(input_sizes) / len(input_sizes), 2),
                    "max": max(input_sizes),
                },
                "paper_input_truncated_count": sum(
                    bool(request["source"]["paper_input_truncated"]) for request in requests
                ),
                "human_review_or_score_metadata_in_messages": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
