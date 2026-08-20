"""Run the descriptive review-length diagnostic on ensemble pair scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import pearsonr, spearmanr


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAIR_SCORES_PATH = (
    "outputs/human_llm_comparison/ensemble/analysis/"
    "human_llm_ensemble_pair_scores_v0_1.csv"
)
DEFAULT_MANIFEST_PATH = "inputs/comparison/human_llm_pair_manifest.csv"
DEFAULT_OUTPUT_DIR = "outputs/human_llm_comparison/ensemble/analysis"
DEFAULT_OUTPUT_STEM = "human_llm_ensemble_length_diagnostic"


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def rounded(value: float) -> float | None:
    return None if pd.isna(value) else round(float(value), 6)


def group_summary(group: pd.DataFrame, label: str) -> dict[str, Any]:
    differences = group["llm_minus_human"]
    return {
        "group": label,
        "pairs_n": int(len(group)),
        "human_word_count_mean": rounded(group["human_word_count"].mean()),
        "llm_word_count_mean": rounded(group["llm_word_count"].mean()),
        "human_score_mean": rounded(group["human_score"].mean()),
        "llm_score_mean": rounded(group["llm_score"].mean()),
        "mean_score_difference_llm_minus_human": rounded(differences.mean()),
        "llm_higher_pairs": int((differences > 0).sum()),
        "ties": int((differences == 0).sum()),
        "human_higher_pairs": int((differences < 0).sum()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the descriptive length diagnostic for ensemble Overall scores."
    )
    parser.add_argument("--pair-scores-path", default=DEFAULT_PAIR_SCORES_PATH)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-stem", default=DEFAULT_OUTPUT_STEM)
    parser.add_argument("--evaluator-id", default="ensemble")
    parser.add_argument("--expected-pairs", type=int, default=48)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pair_scores_path = resolve_path(args.pair_scores_path)
    manifest_path = resolve_path(args.manifest_path)
    output_dir = resolve_path(args.output_dir)

    pair_scores = pd.read_csv(pair_scores_path)
    manifest = pd.read_csv(manifest_path)

    score_fields = {
        "pair_id",
        "metric",
        "evaluator_id",
        "human_score",
        "llm_score",
        "llm_minus_human",
    }
    manifest_fields = {"pair_id", "source_type", "review_word_count"}
    missing_score_fields = sorted(score_fields - set(pair_scores.columns))
    missing_manifest_fields = sorted(manifest_fields - set(manifest.columns))
    if missing_score_fields:
        raise ValueError(f"Pair-score fields missing: {missing_score_fields}")
    if missing_manifest_fields:
        raise ValueError(f"Manifest fields missing: {missing_manifest_fields}")

    overall = pair_scores[
        pair_scores["metric"].eq("Overall")
        & pair_scores["evaluator_id"].eq(args.evaluator_id)
    ].copy()
    if len(overall) != args.expected_pairs:
        raise ValueError(
            f"Expected {args.expected_pairs} Overall rows for {args.evaluator_id!r}; "
            f"found {len(overall)}"
        )
    if overall["pair_id"].duplicated().any():
        raise ValueError("Overall pair scores contain duplicate pair IDs")

    length_rows = manifest[["pair_id", "source_type", "review_word_count"]].copy()
    if length_rows.duplicated(["pair_id", "source_type"]).any():
        raise ValueError("Manifest contains duplicate pair/source rows")
    unexpected_sources = sorted(set(length_rows["source_type"]) - {"human", "llm"})
    if unexpected_sources:
        raise ValueError(f"Unexpected source types: {unexpected_sources}")
    length_rows["review_word_count"] = pd.to_numeric(
        length_rows["review_word_count"], errors="raise"
    )
    lengths = length_rows.pivot(
        index="pair_id", columns="source_type", values="review_word_count"
    ).reset_index()
    if not {"human", "llm"}.issubset(lengths.columns):
        raise ValueError("Manifest must contain one human and one LLM row per pair")
    lengths = lengths.rename(
        columns={"human": "human_word_count", "llm": "llm_word_count"}
    )

    diagnostic = overall.merge(lengths, on="pair_id", how="left", validate="one_to_one")
    if diagnostic[["human_word_count", "llm_word_count"]].isna().any().any():
        raise ValueError("Word counts are missing for one or more scored pairs")
    diagnostic["word_count_difference_llm_minus_human"] = (
        diagnostic["llm_word_count"] - diagnostic["human_word_count"]
    )

    length_difference = diagnostic["word_count_difference_llm_minus_human"]
    score_difference = diagnostic["llm_minus_human"]
    masks = {
        "all_pairs": pd.Series(True, index=diagnostic.index),
        "llm_longer": length_difference > 0,
        "equal_length": length_difference == 0,
        "human_longer": length_difference < 0,
        "absolute_length_difference_le_50": length_difference.abs() <= 50,
        "absolute_length_difference_le_100": length_difference.abs() <= 100,
    }
    group_rows = [group_summary(diagnostic[mask], label) for label, mask in masks.items()]
    groups = pd.DataFrame(group_rows)

    spearman = spearmanr(length_difference, score_difference)
    pearson = pearsonr(length_difference, score_difference)
    output_dir.mkdir(parents=True, exist_ok=True)
    pair_output = output_dir / f"{args.output_stem}_pairs.csv"
    group_output = output_dir / f"{args.output_stem}_groups.csv"
    summary_output = output_dir / f"{args.output_stem}_summary.json"
    diagnostic.to_csv(pair_output, index=False)
    groups.to_csv(group_output, index=False)

    summary = {
        "analysis": "descriptive review-length diagnostic",
        "evaluator_id": args.evaluator_id,
        "pairs": int(len(diagnostic)),
        "word_count_difference": "LLM minus Human",
        "score_difference": "LLM minus Human",
        "human_word_count_mean": rounded(diagnostic["human_word_count"].mean()),
        "llm_word_count_mean": rounded(diagnostic["llm_word_count"].mean()),
        "mean_word_count_difference_llm_minus_human": rounded(length_difference.mean()),
        "median_word_count_difference_llm_minus_human": rounded(length_difference.median()),
        "llm_longer_pairs": int((length_difference > 0).sum()),
        "equal_length_pairs": int((length_difference == 0).sum()),
        "human_longer_pairs": int((length_difference < 0).sum()),
        "spearman_rho_length_difference_vs_score_difference": rounded(
            spearman.statistic
        ),
        "spearman_p_value": float(spearman.pvalue),
        "pearson_r_length_difference_vs_score_difference": rounded(
            pearson.statistic
        ),
        "pearson_p_value": float(pearson.pvalue),
        "groups": group_rows,
        "interpretation": (
            "descriptive diagnostic only; no word-count adjustment, truncation, "
            "matching, or regeneration"
        ),
        "paths": {
            "pair_scores_input": display_path(pair_scores_path),
            "manifest_input": display_path(manifest_path),
            "pairs": display_path(pair_output),
            "groups": display_path(group_output),
        },
    }
    summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"summary": display_path(summary_output), **summary}, indent=2))


if __name__ == "__main__":
    main()
