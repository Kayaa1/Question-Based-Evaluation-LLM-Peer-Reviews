"""Check how well a checklist draft covers consolidated global concepts.

This script makes the previously ad hoc high-frequency coverage check
reproducible. It reads 114 global concepts and each checklist question's
`source_global_concepts`, identifies which concepts the checklist explicitly
references, and calculates top-k coverage by `review_n`.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLOBAL_SUMMARY = (
    ROOT
    / "outputs/open_coding/concept_grouping/analysis/"
    / "open_coding_v0_1_n180_concept_consolidation_v0_1_global_summary.csv"
)
DEFAULT_CHECKLIST = (
    ROOT
    / "inputs/framework_derivation/checklist_derivation_mapping.csv"
)
DEFAULT_OUTPUT_PREFIX = (
    ROOT
    / "outputs/framework_derivation/checklist_concept_coverage"
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def int_value(value: str | int | None) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def split_source_concepts(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def make_source_map(
    checklist_rows: list[dict[str, str]],
) -> dict[str, dict[str, set[str]]]:
    source_map: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"question_ids": set(), "dimensions": set()}
    )
    for row in checklist_rows:
        question_id = row["question_id"]
        dimension = row["dimension"]
        for concept in split_source_concepts(row.get("source_global_concepts")):
            source_map[concept]["question_ids"].add(question_id)
            source_map[concept]["dimensions"].add(dimension)
    return source_map


def add_coverage_columns(
    global_rows: list[dict[str, str]],
    source_map: dict[str, dict[str, set[str]]],
) -> list[dict[str, str | int]]:
    sorted_rows = sorted(
        global_rows,
        key=lambda r: (
            -int_value(r.get("review_n")),
            -int_value(r.get("mention_n")),
            r["global_concept_label"],
        ),
    )

    covered_rows: list[dict[str, str | int]] = []
    for rank, row in enumerate(sorted_rows, start=1):
        concept = row["global_concept_label"]
        source = source_map.get(concept)
        explicitly_referenced = source is not None
        covered_rows.append(
            {
                "rank_by_review_n": rank,
                "global_concept_label": concept,
                "explicitly_referenced": int(explicitly_referenced),
                "source_question_ids": "; ".join(sorted(source["question_ids"]))
                if source
                else "",
                "source_dimensions": "; ".join(sorted(source["dimensions"]))
                if source
                else "",
                "review_n": int_value(row.get("review_n")),
                "mention_n": int_value(row.get("mention_n")),
                "local_concept_n": int_value(row.get("local_concept_n")),
                "final_dimensions": row.get("final_dimensions", ""),
                "known_failure_links": row.get("known_failure_links", ""),
                "candidate_checklist_questions": row.get(
                    "candidate_checklist_questions", ""
                ),
                "global_concept_definitions": row.get("global_concept_definitions", ""),
            }
        )
    return covered_rows


def coverage_rate(rows: list[dict[str, str | int]]) -> dict[str, int | float]:
    total = len(rows)
    covered = sum(int(row["explicitly_referenced"]) for row in rows)
    return {
        "covered_n": covered,
        "total_n": total,
        "coverage_rate": covered / total if total else 0.0,
    }


def topk_rows(
    coverage_rows: list[dict[str, str | int]], topks: list[int]
) -> list[dict[str, int | float | str]]:
    rows = []
    total = len(coverage_rows)
    for k in topks:
        actual_k = min(k, total)
        sub = coverage_rows[:actual_k]
        stats = coverage_rate(sub)
        rows.append(
            {
                "criterion": f"top_{k}_by_review_n",
                "covered_n": stats["covered_n"],
                "total_n": stats["total_n"],
                "coverage_rate": stats["coverage_rate"],
            }
        )
    return rows


def threshold_rows(
    coverage_rows: list[dict[str, str | int]], thresholds: list[int]
) -> list[dict[str, int | float | str]]:
    rows = []
    for threshold in thresholds:
        sub = [row for row in coverage_rows if int(row["review_n"]) >= threshold]
        if not sub:
            continue
        stats = coverage_rate(sub)
        rows.append(
            {
                "criterion": f"review_n_ge_{threshold}",
                "covered_n": stats["covered_n"],
                "total_n": stats["total_n"],
                "coverage_rate": stats["coverage_rate"],
            }
        )
    return rows


def summarize(coverage_rows: list[dict[str, str | int]], missing_sources: list[str]):
    included = [row for row in coverage_rows if int(row["explicitly_referenced"]) == 1]
    omitted = [row for row in coverage_rows if int(row["explicitly_referenced"]) == 0]

    def review_ns(rows: list[dict[str, str | int]]) -> list[int]:
        return [int(row["review_n"]) for row in rows]

    included_review_ns = review_ns(included)
    omitted_review_ns = review_ns(omitted)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_global_concepts": len(coverage_rows),
        "explicitly_referenced_global_concepts": len(included),
        "omitted_or_not_explicit_global_concepts": len(omitted),
        "included_mention_n_total": sum(int(row["mention_n"]) for row in included),
        "omitted_mention_n_total": sum(int(row["mention_n"]) for row in omitted),
        "included_review_n_mean": mean(included_review_ns)
        if included_review_ns
        else 0.0,
        "included_review_n_median": median(included_review_ns)
        if included_review_ns
        else 0.0,
        "omitted_review_n_mean": mean(omitted_review_ns)
        if omitted_review_ns
        else 0.0,
        "omitted_review_n_median": median(omitted_review_ns)
        if omitted_review_ns
        else 0.0,
        "missing_source_concepts": missing_sources,
    }


def write_csv(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check source-concept coverage for a checklist draft."
    )
    parser.add_argument("--global-summary", type=Path, default=DEFAULT_GLOBAL_SUMMARY)
    parser.add_argument("--checklist", type=Path, default=DEFAULT_CHECKLIST)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    args = parser.parse_args()

    global_rows = read_csv_rows(args.global_summary)
    checklist_rows = read_csv_rows(args.checklist)
    source_map = make_source_map(checklist_rows)
    global_labels = {row["global_concept_label"] for row in global_rows}
    missing_sources = sorted(set(source_map) - global_labels)

    coverage_rows = add_coverage_columns(global_rows, source_map)
    summary = summarize(coverage_rows, missing_sources)
    summary["topk_coverage"] = topk_rows(
        coverage_rows, topks=[10, 20, 30, 40, 50, 60, 80, 100, 114]
    )
    summary["threshold_coverage"] = threshold_rows(
        coverage_rows, thresholds=[30, 25, 20, 15, 10, 5, 1]
    )

    concepts_path = args.output_prefix.with_name(args.output_prefix.name + "_concepts.csv")
    topk_path = args.output_prefix.with_name(args.output_prefix.name + "_topk.csv")
    threshold_path = args.output_prefix.with_name(
        args.output_prefix.name + "_thresholds.csv"
    )
    summary_path = args.output_prefix.with_name(args.output_prefix.name + "_summary.json")

    write_csv(concepts_path, coverage_rows)
    write_csv(topk_path, summary["topk_coverage"])
    write_csv(threshold_path, summary["threshold_coverage"])
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Wrote:")
    print(f"- {concepts_path}")
    print(f"- {topk_path}")
    print(f"- {threshold_path}")
    print(f"- {summary_path}")
    print(
        "Explicit source coverage: "
        f"{summary['explicitly_referenced_global_concepts']}/"
        f"{summary['total_global_concepts']}"
    )
    for row in summary["topk_coverage"][:3]:
        print(
            f"{row['criterion']}: {row['covered_n']}/"
            f"{row['total_n']} ({row['coverage_rate']:.1%})"
        )


if __name__ == "__main__":
    main()
