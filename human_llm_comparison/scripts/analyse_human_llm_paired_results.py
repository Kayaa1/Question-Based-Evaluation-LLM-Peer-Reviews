"""Compare 48 human--LLM pairs overall and by checklist dimension."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from scipy.stats import rankdata, wilcoxon


DEFAULT_ANSWERS_PATH = (
    "outputs/human_llm_comparison/analysis/"
    "human_llm_main_v0_1_checklist_application_v0_2_rag_bm25_n96_"
    "requests_results_gpt-5.5_temp0.0_answers.csv"
)
DEFAULT_INPUT_PATH = (
    "outputs/human_llm_comparison/inputs/human_llm_main_v0_1_seed20260719_n96.csv"
)
DEFAULT_OUTPUT_DIR = "outputs/human_llm_comparison/analysis"
DEFAULT_OUTPUT_STEM = "human_llm_main_v0_1_paired_comparison"
SCORE_MAP = {"yes": 1.0, "partial": 0.5, "no": 0.0}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def display_path(path: Path) -> str:
    """Use a repository-relative path when possible, otherwise keep it absolute."""

    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def holm_adjust(p_values: list[float]) -> list[float]:
    """Apply Holm correction across the overall and dimension-level tests."""

    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [0.0] * len(p_values)
    running_max = 0.0
    total = len(p_values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (total - rank) * p_values[index])
        running_max = max(running_max, candidate)
        adjusted[index] = running_max
    return adjusted


def rank_biserial(differences: list[float]) -> float:
    nonzero = [value for value in differences if value != 0]
    if not nonzero:
        return 0.0
    ranks = rankdata([abs(value) for value in nonzero])
    positive = sum(rank for rank, value in zip(ranks, nonzero, strict=True) if value > 0)
    negative = sum(rank for rank, value in zip(ranks, nonzero, strict=True) if value < 0)
    return float((positive - negative) / (positive + negative))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse paired human--LLM checklist profiles."
    )
    parser.add_argument("--answers-path", default=DEFAULT_ANSWERS_PATH)
    parser.add_argument("--input-path", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-stem", default=DEFAULT_OUTPUT_STEM)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    answer_rows = read_csv_rows(resolve_path(args.answers_path))
    input_rows = read_csv_rows(resolve_path(args.input_path))
    if len(answer_rows) != 2400 or len(input_rows) != 96:
        raise ValueError(
            f"Expected 2,400 answers and 96 inputs; found "
            f"{len(answer_rows)} and {len(input_rows)}."
        )

    input_by_id = {row["review_record_id"]: row for row in input_rows}
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    answer_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    dimensions = sorted({row["dimension"] for row in answer_rows})
    for row in answer_rows:
        review_id = row["review_record_id"]
        source = input_by_id[review_id]["source_type"]
        pair_id = input_by_id[review_id]["pair_id"]
        answer_counts[(source, row["dimension"])].update([row["answer"]])
        if row["answer"] in SCORE_MAP:
            score = SCORE_MAP[row["answer"]]
            grouped[(pair_id, source, "Overall")].append(score)
            grouped[(pair_id, source, row["dimension"])].append(score)

    pair_ids = sorted({row["pair_id"] for row in input_rows})
    metrics = ["Overall", *dimensions]
    paired_rows: list[dict[str, Any]] = []
    for pair_id in pair_ids:
        pair_inputs = [row for row in input_rows if row["pair_id"] == pair_id]
        if {row["source_type"] for row in pair_inputs} != {"human", "llm"}:
            raise ValueError(f"Incomplete pair: {pair_id}")
        metadata = pair_inputs[0]
        for metric in metrics:
            human_values = grouped[(pair_id, "human", metric)]
            llm_values = grouped[(pair_id, "llm", metric)]
            human_score = mean(human_values) if human_values else None
            llm_score = mean(llm_values) if llm_values else None
            paired_rows.append(
                {
                    "pair_id": pair_id,
                    "dataset": metadata["dataset"],
                    "score_tier_for_sampling_only": metadata["score_tier"],
                    "metric": metric,
                    "human_score": human_score,
                    "llm_score": llm_score,
                    "llm_minus_human": (
                        llm_score - human_score
                        if human_score is not None and llm_score is not None
                        else ""
                    ),
                    "human_applicable_items": len(human_values),
                    "llm_applicable_items": len(llm_values),
                }
            )

    test_rows: list[dict[str, Any]] = []
    raw_p_values: list[float] = []
    for metric in metrics:
        rows = [row for row in paired_rows if row["metric"] == metric and row["llm_minus_human"] != ""]
        human = [float(row["human_score"]) for row in rows]
        llm = [float(row["llm_score"]) for row in rows]
        differences = [right - left for left, right in zip(human, llm, strict=True)]
        result = wilcoxon(llm, human, alternative="two-sided", method="auto")
        raw_p_values.append(float(result.pvalue))
        test_rows.append(
            {
                "metric": metric,
                "pairs_n": len(rows),
                "human_mean": mean(human),
                "human_median": median(human),
                "llm_mean": mean(llm),
                "llm_median": median(llm),
                "mean_difference_llm_minus_human": mean(differences),
                "median_difference_llm_minus_human": median(differences),
                "llm_higher_pairs": sum(value > 0 for value in differences),
                "ties": sum(value == 0 for value in differences),
                "human_higher_pairs": sum(value < 0 for value in differences),
                "wilcoxon_statistic": float(result.statistic),
                "p_value": float(result.pvalue),
                "rank_biserial_effect": rank_biserial(differences),
            }
        )

    for row, adjusted in zip(test_rows, holm_adjust(raw_p_values), strict=True):
        row["p_value_holm"] = adjusted

    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paired_path = output_dir / f"{args.output_stem}_pair_scores.csv"
    tests_path = output_dir / f"{args.output_stem}_wilcoxon.csv"
    summary_path = output_dir / f"{args.output_stem}_summary.json"
    write_csv(paired_rows, paired_path)
    write_csv(test_rows, tests_path)
    summary = {
        "scoring": "yes=1, partial=0.5, no=0; not_applicable excluded",
        "word_count_adjustment": "none",
        "pairs": len(pair_ids),
        "metrics": len(metrics),
        "multiple_testing": "Holm correction across Overall + 9 dimensions",
        "answer_counts_by_source_and_dimension": {
            f"{source}::{dimension}": dict(counts)
            for (source, dimension), counts in sorted(answer_counts.items())
        },
        "tests": test_rows,
        "paths": {
            "pair_scores": display_path(paired_path),
            "wilcoxon": display_path(tests_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
