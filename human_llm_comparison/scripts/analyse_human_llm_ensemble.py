"""Combine multiple automated evaluators for the paired human--LLM analysis.

The primary ensemble gives each evaluator equal weight at the pair/metric level.
An evaluator contributes to a pair/metric only when both the human and LLM
scores are available, so evaluator-specific ``not_applicable`` decisions are
never converted to zero and never change only one side of a paired contrast.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from scipy.stats import rankdata, wilcoxon


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = "outputs/human_llm_comparison/ensemble/analysis"
DEFAULT_FIGURES_DIR = "outputs/human_llm_comparison/ensemble/figures"
DEFAULT_EVALUATORS_ROOT = "outputs/human_llm_comparison/evaluators"
DEFAULT_BOOTSTRAP_REPS = 10_000
DEFAULT_SEED = 20260729

DEFAULT_EVALUATORS = {
    "gpt-5.5": {
        "answers": (
            "outputs/human_llm_comparison/evaluators/gpt-5.5/analysis/"
            "human_llm_main_v0_1_checklist_application_v0_2_rag_bm25_n96_"
            "requests_results_gpt-5.5_temp0.0_answers.csv"
        ),
        "pair_scores": (
            "outputs/human_llm_comparison/evaluators/gpt-5.5/analysis/"
            "human_llm_main_v0_1_paired_comparison_pair_scores.csv"
        ),
    },
    "deepseek-v4-pro": {
        "answers": (
            "outputs/human_llm_comparison/evaluators/deepseek-v4-pro/analysis/"
            "human_llm_main_v0_1_checklist_application_v0_2_rag_bm25_n96_"
            "requests_results_deepseek-v4-pro_thinking-enabled_effort-max_"
            "temp0.0_answers.csv"
        ),
        "pair_scores": (
            "outputs/human_llm_comparison/evaluators/deepseek-v4-pro/analysis/"
            "human_llm_main_v0_1_paired_comparison_pair_scores.csv"
        ),
    },
    "claude-sonnet-5": {
        "answers": (
            "outputs/human_llm_comparison/evaluators/claude-sonnet-5/analysis/"
            "human_llm_main_v0_1_checklist_application_v0_2_rag_bm25_n96_"
            "requests_results_claude-sonnet-5_effort-high_temp0.0_answers.csv"
        ),
        "pair_scores": (
            "outputs/human_llm_comparison/evaluators/claude-sonnet-5/analysis/"
            "human_llm_main_v0_1_paired_comparison_pair_scores.csv"
        ),
    },
}

MODEL_DISPLAY = {
    "gpt-5.5": "GPT-5.5",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "claude-sonnet-5": "Claude Sonnet 5",
    "ensemble": "Three-model ensemble",
}
MODEL_COLOURS = {
    "gpt-5.5": "#0072B2",
    "deepseek-v4-pro": "#D55E00",
    "claude-sonnet-5": "#009E73",
    "ensemble": "#2F3542",
}
SOURCE_COLOURS = {"human": "#0072B2", "llm": "#D55E00"}
HEATMAP_DISPLAY = {
    "gpt-5.5": "GPT-5.5",
    "deepseek-v4-pro": "DeepSeek",
    "claude-sonnet-5": "Claude",
    "ensemble": "Ensemble",
}
METRIC_ORDER = [
    "Overall",
    "Coverage",
    "Substance",
    "Reasoning",
    "Grounding",
    "Constructiveness",
    "Independence",
    "Specificity",
    "Clarity",
    "Ethics",
]
ITEM_ORDER = [
    "COV_1",
    "COV_2",
    "COV_3",
    "SUB_1",
    "SUB_2",
    "SUB_3",
    "SUB_4",
    "REA_1",
    "REA_2",
    "REA_3",
    "REA_4a",
    "REA_4b",
    "GRO_1",
    "GRO_2",
    "GRO_3",
    "CON_1",
    "CON_2",
    "CON_3a",
    "CON_3b",
    "IND_1",
    "SPE_1",
    "SPE_2",
    "CLA_1",
    "CLA_2",
    "ETH_1",
]
ITEM_SHORT_LABELS = {
    "COV_1": "Main task, contribution, method & claims",
    "COV_2": "Evaluation setup, data & findings",
    "COV_3": "Empirical breadth & generalisation",
    "SUB_1": "Novelty, significance & motivation",
    "SUB_2": "Method design & technical depth",
    "SUB_3": "Datasets, resources & artefacts",
    "SUB_4": "Baselines, metrics & evidence adequacy",
    "REA_1": "Claims follow from evidence",
    "REA_2": "Measurement & statistical choices",
    "REA_3": "Confounds & alternative explanations",
    "REA_4a": "Ablations, robustness & sensitivity",
    "REA_4b": "Diagnostics & mechanistic explanation",
    "GRO_1": "Judgements grounded in paper evidence",
    "GRO_2": "Novelty grounded in prior work",
    "GRO_3": "Avoids unsupported criticism",
    "CON_1": "Actionable, issue-specific suggestions",
    "CON_2": "Concrete reporting details",
    "CON_3a": "Concrete additional empirical evidence",
    "CON_3b": "Concrete explanatory support",
    "IND_1": "Independent weaknesses or risks",
    "SPE_1": "Feedback is specific and locatable",
    "SPE_2": "Revision requests name the issue",
    "CLA_1": "Readability, organisation & presentation",
    "CLA_2": "Definitions, notation & exposition",
    "ETH_1": "Ethical and social concerns",
}
LABELS = ["yes", "partial", "no", "not_applicable"]
SCORE_MAP = {"yes": 1.0, "partial": 0.5, "no": 0.0}
ORDINAL_LABELS = ["no", "partial", "yes"]
ANSWER_KEY_FIELDS = ["review_record_id", "question_id"]
ANSWER_METADATA_FIELDS = [
    "paper_title",
    "pair_id",
    "review_record_id",
    "source_type",
    "dataset",
    "score_tier",
    "question_id",
    "dimension",
]


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError(f"Cannot write an empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def optional_float(value: str | float | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def safe_column_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse an equal-weight panel of automated checklist evaluators."
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figures-dir", default=DEFAULT_FIGURES_DIR)
    parser.add_argument(
        "--evaluators-root",
        default=DEFAULT_EVALUATORS_ROOT,
        help=(
            "Directory containing one <evaluator-id>/analysis folder per evaluator. "
            "Relative paths are resolved from the repository root."
        ),
    )
    parser.add_argument("--bootstrap-reps", type=int, default=DEFAULT_BOOTSTRAP_REPS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def holm_adjust(p_values: list[float]) -> list[float]:
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
    positive = sum(
        rank for rank, value in zip(ranks, nonzero, strict=True) if value > 0
    )
    negative = sum(
        rank for rank, value in zip(ranks, nonzero, strict=True) if value < 0
    )
    return float((positive - negative) / (positive + negative))


def paired_wilcoxon(differences: list[float]) -> tuple[float, float]:
    if not differences or all(value == 0 for value in differences):
        return 0.0, 1.0
    result = wilcoxon(differences, alternative="two-sided", method="auto")
    return float(result.statistic), float(result.pvalue)


def bootstrap_mean_ci(
    values: list[float], reps: int, seed: int
) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    vector = np.asarray(values, dtype=float)
    sampled_means = rng.choice(
        vector, size=(reps, len(vector)), replace=True
    ).mean(axis=1)
    lower, upper = np.quantile(sampled_means, [0.025, 0.975])
    return float(lower), float(upper)


def unweighted_kappa(left: list[str], right: list[str]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / len(left)) * (right_counts[label] / len(right))
        for label in LABELS
    )
    if expected == 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def linear_weighted_kappa(left: list[str], right: list[str]) -> float | None:
    pairs = [
        (a, b)
        for a, b in zip(left, right, strict=True)
        if a in ORDINAL_LABELS and b in ORDINAL_LABELS
    ]
    if not pairs:
        return None
    label_index = {label: index for index, label in enumerate(ORDINAL_LABELS)}
    observed_matrix = np.zeros((3, 3), dtype=float)
    for a, b in pairs:
        observed_matrix[label_index[a], label_index[b]] += 1
    observed_matrix /= len(pairs)
    left_marginal = observed_matrix.sum(axis=1)
    right_marginal = observed_matrix.sum(axis=0)
    expected_matrix = np.outer(left_marginal, right_marginal)
    disagreement_weights = np.fromfunction(
        lambda i, j: np.abs(i - j) / 2.0, (3, 3), dtype=float
    )
    observed_disagreement = float((observed_matrix * disagreement_weights).sum())
    expected_disagreement = float((expected_matrix * disagreement_weights).sum())
    if expected_disagreement == 0:
        return None
    return 1.0 - observed_disagreement / expected_disagreement


def fleiss_kappa(label_groups: list[list[str]]) -> float | None:
    if not label_groups:
        return None
    rater_n = len(label_groups[0])
    if rater_n < 2 or any(len(group) != rater_n for group in label_groups):
        raise ValueError("Fleiss kappa requires a fixed number of raters per item.")
    counts = np.asarray(
        [[group.count(label) for label in LABELS] for group in label_groups],
        dtype=float,
    )
    item_agreement = ((counts**2).sum(axis=1) - rater_n) / (
        rater_n * (rater_n - 1)
    )
    observed = float(item_agreement.mean())
    proportions = counts.sum(axis=0) / (len(label_groups) * rater_n)
    expected = float((proportions**2).sum())
    if expected == 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def load_and_validate_inputs(evaluators_root: str | Path) -> tuple[
    list[str],
    dict[str, dict[tuple[str, str], dict[str, str]]],
    dict[str, dict[tuple[str, str], dict[str, str]]],
]:
    evaluator_ids = list(DEFAULT_EVALUATORS)
    input_root = resolve_path(evaluators_root)
    answers_by_evaluator: dict[
        str, dict[tuple[str, str], dict[str, str]]
    ] = {}
    pair_scores_by_evaluator: dict[
        str, dict[tuple[str, str], dict[str, str]]
    ] = {}

    for evaluator_id, paths in DEFAULT_EVALUATORS.items():
        evaluator_analysis_dir = input_root / evaluator_id / "analysis"
        answers_path = evaluator_analysis_dir / Path(paths["answers"]).name
        pair_scores_path = evaluator_analysis_dir / Path(paths["pair_scores"]).name
        answer_rows = read_csv_rows(answers_path)
        pair_rows = read_csv_rows(pair_scores_path)
        if len(answer_rows) != 2400:
            raise ValueError(
                f"{evaluator_id}: expected 2400 answer rows, found {len(answer_rows)}."
            )
        if len(pair_rows) != 480:
            raise ValueError(
                f"{evaluator_id}: expected 480 pair/metric rows, found {len(pair_rows)}."
            )
        invalid_labels = sorted({row["answer"] for row in answer_rows} - set(LABELS))
        if invalid_labels:
            raise ValueError(f"{evaluator_id}: invalid labels {invalid_labels}.")
        answer_index = {
            tuple(row[field] for field in ANSWER_KEY_FIELDS): row for row in answer_rows
        }
        pair_index = {(row["pair_id"], row["metric"]): row for row in pair_rows}
        if len(answer_index) != len(answer_rows) or len(pair_index) != len(pair_rows):
            raise ValueError(f"{evaluator_id}: duplicate analysis keys detected.")
        answers_by_evaluator[evaluator_id] = answer_index
        pair_scores_by_evaluator[evaluator_id] = pair_index

    reference_answer_keys = set(answers_by_evaluator[evaluator_ids[0]])
    reference_pair_keys = set(pair_scores_by_evaluator[evaluator_ids[0]])
    expected_metrics = set(METRIC_ORDER)
    observed_metrics = {metric for _, metric in reference_pair_keys}
    if observed_metrics != expected_metrics:
        raise ValueError(
            f"Unexpected metric set: expected {expected_metrics}, found {observed_metrics}."
        )

    for evaluator_id in evaluator_ids[1:]:
        if set(answers_by_evaluator[evaluator_id]) != reference_answer_keys:
            raise ValueError(f"{evaluator_id}: answer keys do not align.")
        if set(pair_scores_by_evaluator[evaluator_id]) != reference_pair_keys:
            raise ValueError(f"{evaluator_id}: pair-score keys do not align.")
        for key in reference_answer_keys:
            reference = answers_by_evaluator[evaluator_ids[0]][key]
            current = answers_by_evaluator[evaluator_id][key]
            for field in ANSWER_METADATA_FIELDS:
                if reference[field] != current[field]:
                    raise ValueError(
                        f"Answer metadata mismatch at {key}, field {field}: "
                        f"{reference[field]!r} != {current[field]!r}."
                    )

    return evaluator_ids, answers_by_evaluator, pair_scores_by_evaluator


def build_item_consensus(
    evaluator_ids: list[str],
    answers_by_evaluator: dict[str, dict[tuple[str, str], dict[str, str]]],
) -> list[dict[str, Any]]:
    reference = answers_by_evaluator[evaluator_ids[0]]
    rows: list[dict[str, Any]] = []
    for key in sorted(reference):
        base = reference[key]
        row: dict[str, Any] = {field: base[field] for field in ANSWER_METADATA_FIELDS}
        labels = [answers_by_evaluator[evaluator_id][key]["answer"] for evaluator_id in evaluator_ids]
        scores = [SCORE_MAP[label] for label in labels if label in SCORE_MAP]
        for evaluator_id, label in zip(evaluator_ids, labels, strict=True):
            prefix = safe_column_name(evaluator_id)
            row[f"{prefix}_label"] = label
            row[f"{prefix}_score"] = SCORE_MAP.get(label, "")
        counts = Counter(labels)
        most_common_label, most_common_n = counts.most_common(1)[0]
        row.update(
            {
                "scorable_evaluator_n": len(scores),
                "not_applicable_n": labels.count("not_applicable"),
                "ensemble_mean_item_score": mean(scores) if scores else "",
                "score_range": max(scores) - min(scores) if scores else "",
                "all_three_labels_unanimous": len(set(labels)) == 1,
                "majority_label": most_common_label if most_common_n >= 2 else "no_majority",
            }
        )
        rows.append(row)
    return rows


def build_label_distributions(
    evaluator_ids: list[str],
    answers_by_evaluator: dict[str, dict[tuple[str, str], dict[str, str]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evaluator_id in evaluator_ids:
        answers = list(answers_by_evaluator[evaluator_id].values())
        for source in ["overall", "human", "llm"]:
            subset = answers if source == "overall" else [
                row for row in answers if row["source_type"] == source
            ]
            counts = Counter(row["answer"] for row in subset)
            scorable = [SCORE_MAP[row["answer"]] for row in subset if row["answer"] in SCORE_MAP]
            result: dict[str, Any] = {
                "evaluator_id": evaluator_id,
                "source": source,
                "judgement_n": len(subset),
                "scorable_n": len(scorable),
                "mean_scorable_item_score": mean(scorable) if scorable else "",
            }
            for label in LABELS:
                result[f"{label}_n"] = counts[label]
                result[f"{label}_fraction"] = counts[label] / len(subset)
            rows.append(result)
    return rows


def scope_filter(
    rows: Iterable[dict[str, str]], scope_type: str, scope_value: str
) -> list[dict[str, str]]:
    if scope_type == "overall":
        return list(rows)
    if scope_type == "source":
        return [row for row in rows if row["source_type"] == scope_value]
    if scope_type == "dimension":
        return [row for row in rows if row["dimension"] == scope_value]
    raise ValueError(f"Unknown scope type: {scope_type}")


def agreement_scopes() -> list[tuple[str, str]]:
    return [
        ("overall", "all"),
        ("source", "human"),
        ("source", "llm"),
        *[("dimension", metric) for metric in METRIC_ORDER if metric != "Overall"],
    ]


def build_pairwise_agreement(
    evaluator_ids: list[str],
    answers_by_evaluator: dict[str, dict[tuple[str, str], dict[str, str]]],
) -> list[dict[str, Any]]:
    reference_rows = list(answers_by_evaluator[evaluator_ids[0]].values())
    rows: list[dict[str, Any]] = []
    for left_index, left_id in enumerate(evaluator_ids):
        for right_id in evaluator_ids[left_index + 1 :]:
            for scope_type, scope_value in agreement_scopes():
                subset = scope_filter(reference_rows, scope_type, scope_value)
                keys = [(row["review_record_id"], row["question_id"]) for row in subset]
                left = [answers_by_evaluator[left_id][key]["answer"] for key in keys]
                right = [answers_by_evaluator[right_id][key]["answer"] for key in keys]
                scorable_pairs = [
                    (a, b)
                    for a, b in zip(left, right, strict=True)
                    if a in SCORE_MAP and b in SCORE_MAP
                ]
                left_higher = sum(
                    SCORE_MAP[a] > SCORE_MAP[b] for a, b in scorable_pairs
                )
                right_higher = sum(
                    SCORE_MAP[b] > SCORE_MAP[a] for a, b in scorable_pairs
                )
                exact_n = sum(a == b for a, b in zip(left, right, strict=True))
                scorable_exact_n = sum(a == b for a, b in scorable_pairs)
                score_differences = [
                    SCORE_MAP[a] - SCORE_MAP[b] for a, b in scorable_pairs
                ]
                rows.append(
                    {
                        "scope_type": scope_type,
                        "scope_value": scope_value,
                        "evaluator_a": left_id,
                        "evaluator_b": right_id,
                        "judgement_n": len(left),
                        "exact_agreement_n": exact_n,
                        "exact_agreement_rate": exact_n / len(left),
                        "cohen_kappa_4_labels": unweighted_kappa(left, right),
                        "jointly_scorable_n": len(scorable_pairs),
                        "scorable_exact_n": scorable_exact_n,
                        "scorable_exact_rate": (
                            scorable_exact_n / len(scorable_pairs)
                            if scorable_pairs
                            else ""
                        ),
                        "linear_weighted_kappa_3_labels": linear_weighted_kappa(
                            left, right
                        ),
                        "evaluator_a_higher_n": left_higher,
                        "evaluator_b_higher_n": right_higher,
                        "equal_scorable_n": len(scorable_pairs)
                        - left_higher
                        - right_higher,
                        "mean_score_a_minus_b": (
                            mean(score_differences) if score_differences else ""
                        ),
                    }
                )
    return rows


def build_multirater_agreement(
    evaluator_ids: list[str],
    answers_by_evaluator: dict[str, dict[tuple[str, str], dict[str, str]]],
) -> list[dict[str, Any]]:
    reference_rows = list(answers_by_evaluator[evaluator_ids[0]].values())
    rows: list[dict[str, Any]] = []
    for scope_type, scope_value in agreement_scopes():
        subset = scope_filter(reference_rows, scope_type, scope_value)
        keys = [(row["review_record_id"], row["question_id"]) for row in subset]
        label_groups = [
            [answers_by_evaluator[evaluator_id][key]["answer"] for evaluator_id in evaluator_ids]
            for key in keys
        ]
        unanimous_n = sum(len(set(group)) == 1 for group in label_groups)
        jointly_scorable = [
            group for group in label_groups if all(label in SCORE_MAP for label in group)
        ]
        scorable_unanimous_n = sum(
            len(set(group)) == 1 for group in jointly_scorable
        )
        rows.append(
            {
                "scope_type": scope_type,
                "scope_value": scope_value,
                "judgement_n": len(label_groups),
                "all_three_unanimous_n": unanimous_n,
                "all_three_unanimous_rate": unanimous_n / len(label_groups),
                "fleiss_kappa_4_labels": fleiss_kappa(label_groups),
                "jointly_scorable_n": len(jointly_scorable),
                "jointly_scorable_unanimous_n": scorable_unanimous_n,
                "jointly_scorable_unanimous_rate": (
                    scorable_unanimous_n / len(jointly_scorable)
                    if jointly_scorable
                    else ""
                ),
            }
        )
    return rows


def build_combined_pair_scores(
    evaluator_ids: list[str],
    pair_scores_by_evaluator: dict[str, dict[tuple[str, str], dict[str, str]]],
) -> list[dict[str, Any]]:
    reference = pair_scores_by_evaluator[evaluator_ids[0]]
    rows: list[dict[str, Any]] = []
    for key in sorted(reference, key=lambda item: (item[0], METRIC_ORDER.index(item[1]))):
        for evaluator_id in evaluator_ids:
            source = pair_scores_by_evaluator[evaluator_id][key]
            human = optional_float(source["human_score"])
            llm = optional_float(source["llm_score"])
            rows.append(
                {
                    "pair_id": source["pair_id"],
                    "dataset": source["dataset"],
                    "score_tier_for_sampling_only": source[
                        "score_tier_for_sampling_only"
                    ],
                    "metric": source["metric"],
                    "evaluator_id": evaluator_id,
                    "human_score": "" if human is None else human,
                    "llm_score": "" if llm is None else llm,
                    "llm_minus_human": (
                        "" if human is None or llm is None else llm - human
                    ),
                    "contributing_evaluator_n": (
                        1 if human is not None and llm is not None else 0
                    ),
                    "contributing_evaluators": (
                        evaluator_id if human is not None and llm is not None else ""
                    ),
                }
            )

        valid: list[tuple[str, float, float]] = []
        for evaluator_id in evaluator_ids:
            source = pair_scores_by_evaluator[evaluator_id][key]
            human = optional_float(source["human_score"])
            llm = optional_float(source["llm_score"])
            if human is not None and llm is not None:
                valid.append((evaluator_id, human, llm))
        if not valid:
            raise ValueError(f"No evaluator has a paired score for {key}.")
        human_mean = mean(item[1] for item in valid)
        llm_mean = mean(item[2] for item in valid)
        source = reference[key]
        rows.append(
            {
                "pair_id": source["pair_id"],
                "dataset": source["dataset"],
                "score_tier_for_sampling_only": source[
                    "score_tier_for_sampling_only"
                ],
                "metric": source["metric"],
                "evaluator_id": "ensemble",
                "human_score": human_mean,
                "llm_score": llm_mean,
                "llm_minus_human": llm_mean - human_mean,
                "contributing_evaluator_n": len(valid),
                "contributing_evaluators": "|".join(item[0] for item in valid),
            }
        )
    return rows


def build_test_rows(
    combined_pair_scores: list[dict[str, Any]],
    evaluator_ids: list[str],
    bootstrap_reps: int,
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    all_ids = [*evaluator_ids, "ensemble"]
    for evaluator_index, evaluator_id in enumerate(all_ids):
        evaluator_rows: list[dict[str, Any]] = []
        raw_p_values: list[float] = []
        for metric_index, metric in enumerate(METRIC_ORDER):
            subset = [
                row
                for row in combined_pair_scores
                if row["evaluator_id"] == evaluator_id
                and row["metric"] == metric
                and row["llm_minus_human"] != ""
            ]
            human = [float(row["human_score"]) for row in subset]
            llm = [float(row["llm_score"]) for row in subset]
            differences = [float(row["llm_minus_human"]) for row in subset]
            statistic, p_value = paired_wilcoxon(differences)
            ci_low, ci_high = bootstrap_mean_ci(
                differences,
                reps=bootstrap_reps,
                seed=seed + evaluator_index * 100 + metric_index,
            )
            row = {
                "evaluator_id": evaluator_id,
                "metric": metric,
                "pairs_n": len(subset),
                "human_mean": mean(human),
                "human_median": median(human),
                "llm_mean": mean(llm),
                "llm_median": median(llm),
                "mean_difference_llm_minus_human": mean(differences),
                "mean_difference_bootstrap_ci95_lower": ci_low,
                "mean_difference_bootstrap_ci95_upper": ci_high,
                "median_difference_llm_minus_human": median(differences),
                "llm_higher_pairs": sum(value > 0 for value in differences),
                "ties": sum(value == 0 for value in differences),
                "human_higher_pairs": sum(value < 0 for value in differences),
                "wilcoxon_statistic": statistic,
                "p_value": p_value,
                "rank_biserial_effect": rank_biserial(differences),
                "pairs_with_all_evaluators": sum(
                    int(row["contributing_evaluator_n"]) == len(evaluator_ids)
                    for row in subset
                )
                if evaluator_id == "ensemble"
                else "",
            }
            evaluator_rows.append(row)
            raw_p_values.append(p_value)
        for row, adjusted in zip(
            evaluator_rows, holm_adjust(raw_p_values), strict=True
        ):
            row["p_value_holm_within_evaluator"] = adjusted
        rows.extend(evaluator_rows)
    return rows


def build_leave_one_out_rows(
    evaluator_ids: list[str],
    pair_scores_by_evaluator: dict[str, dict[tuple[str, str], dict[str, str]]],
    bootstrap_reps: int,
    seed: int,
) -> list[dict[str, Any]]:
    reference = pair_scores_by_evaluator[evaluator_ids[0]]
    overall_keys = sorted(key for key in reference if key[1] == "Overall")
    panels = [("none", evaluator_ids)] + [
        (omitted, [item for item in evaluator_ids if item != omitted])
        for omitted in evaluator_ids
    ]
    rows: list[dict[str, Any]] = []
    for panel_index, (omitted, included) in enumerate(panels):
        human: list[float] = []
        llm: list[float] = []
        for key in overall_keys:
            human.append(
                mean(float(pair_scores_by_evaluator[item][key]["human_score"]) for item in included)
            )
            llm.append(
                mean(float(pair_scores_by_evaluator[item][key]["llm_score"]) for item in included)
            )
        differences = [right - left for left, right in zip(human, llm, strict=True)]
        statistic, p_value = paired_wilcoxon(differences)
        bootstrap_seed = (
            seed + len(evaluator_ids) * 100
            if omitted == "none"
            else seed + 1000 + panel_index
        )
        ci_low, ci_high = bootstrap_mean_ci(
            differences, bootstrap_reps, bootstrap_seed
        )
        rows.append(
            {
                "omitted_evaluator": omitted,
                "included_evaluators": "|".join(included),
                "evaluator_n": len(included),
                "pairs_n": len(differences),
                "human_mean": mean(human),
                "llm_mean": mean(llm),
                "mean_difference_llm_minus_human": mean(differences),
                "mean_difference_bootstrap_ci95_lower": ci_low,
                "mean_difference_bootstrap_ci95_upper": ci_high,
                "llm_higher_pairs": sum(value > 0 for value in differences),
                "ties": sum(value == 0 for value in differences),
                "human_higher_pairs": sum(value < 0 for value in differences),
                "wilcoxon_statistic": statistic,
                "p_value": p_value,
                "rank_biserial_effect": rank_biserial(differences),
            }
        )
    return rows


def build_metric_robustness(
    test_rows: list[dict[str, Any]], evaluator_ids: list[str]
) -> list[dict[str, Any]]:
    index = {(row["evaluator_id"], row["metric"]): row for row in test_rows}
    rows: list[dict[str, Any]] = []
    for metric in METRIC_ORDER:
        row: dict[str, Any] = {"metric": metric}
        evaluator_gaps: list[float] = []
        for evaluator_id in [*evaluator_ids, "ensemble"]:
            prefix = safe_column_name(evaluator_id)
            source = index[(evaluator_id, metric)]
            gap = float(source["mean_difference_llm_minus_human"])
            row[f"{prefix}_human_mean"] = source["human_mean"]
            row[f"{prefix}_llm_mean"] = source["llm_mean"]
            row[f"{prefix}_gap"] = gap
            row[f"{prefix}_p_holm"] = source[
                "p_value_holm_within_evaluator"
            ]
            if evaluator_id != "ensemble":
                evaluator_gaps.append(gap)
        row.update(
            {
                "evaluator_gap_min": min(evaluator_gaps),
                "evaluator_gap_max": max(evaluator_gaps),
                "evaluator_gap_range": max(evaluator_gaps) - min(evaluator_gaps),
                "all_evaluators_positive": all(value > 0 for value in evaluator_gaps),
            }
        )
        rows.append(row)
    return rows


def build_item_descriptives(
    evaluator_ids: list[str],
    answers_by_evaluator: dict[str, dict[tuple[str, str], dict[str, str]]],
) -> list[dict[str, Any]]:
    reference = answers_by_evaluator[evaluator_ids[0]]
    rows: list[dict[str, Any]] = []
    for item_id in ITEM_ORDER:
        keys = [key for key, row in reference.items() if row["question_id"] == item_id]
        if not keys:
            raise ValueError(f"Missing item: {item_id}")
        result: dict[str, Any] = {
            "question_id": item_id,
            "dimension": reference[keys[0]]["dimension"],
        }
        gaps: list[float] = []
        for evaluator_id in evaluator_ids:
            prefix = safe_column_name(evaluator_id)
            human = [
                SCORE_MAP[answers_by_evaluator[evaluator_id][key]["answer"]]
                for key in keys
                if reference[key]["source_type"] == "human"
                and answers_by_evaluator[evaluator_id][key]["answer"] in SCORE_MAP
            ]
            llm = [
                SCORE_MAP[answers_by_evaluator[evaluator_id][key]["answer"]]
                for key in keys
                if reference[key]["source_type"] == "llm"
                and answers_by_evaluator[evaluator_id][key]["answer"] in SCORE_MAP
            ]
            human_mean = mean(human)
            llm_mean = mean(llm)
            gap = llm_mean - human_mean
            result[f"{prefix}_human_mean"] = human_mean
            result[f"{prefix}_human_applicable_n"] = len(human)
            result[f"{prefix}_llm_mean"] = llm_mean
            result[f"{prefix}_llm_applicable_n"] = len(llm)
            result[f"{prefix}_gap"] = gap
            gaps.append(gap)
        result.update(
            {
                "ensemble_equal_weight_gap": mean(gaps),
                "evaluator_gap_min": min(gaps),
                "evaluator_gap_max": max(gaps),
                "evaluator_gap_range": max(gaps) - min(gaps),
                "all_evaluators_positive": all(value > 0 for value in gaps),
                "all_evaluators_negative": all(value < 0 for value in gaps),
            }
        )
        rows.append(result)
    return rows


def save_figure(fig: plt.Figure, figures_dir: Path, stem: str) -> list[Path]:
    figures_dir.mkdir(parents=True, exist_ok=True)
    paths = [figures_dir / f"{stem}.png", figures_dir / f"{stem}.pdf"]
    fig.savefig(paths[0], dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(paths[1], bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def plot_item_human_llm_by_evaluator(
    item_rows: list[dict[str, Any]],
    evaluator_ids: list[str],
    figures_dir: Path,
) -> list[Path]:
    """Show absolute human and LLM means for all 25 items in three panels."""

    index = {row["question_id"]: row for row in item_rows}
    missing = [item_id for item_id in ITEM_ORDER if item_id not in index]
    if missing:
        raise ValueError(f"Item descriptives are missing: {missing}")
    y_positions = np.arange(len(ITEM_ORDER))
    fig, axes = plt.subplots(
        1,
        len(evaluator_ids),
        figsize=(17.5, 14.5),
        sharex=True,
        sharey=True,
    )

    dimension_ranges: list[tuple[int, int]] = []
    start = 0
    current = index[ITEM_ORDER[0]]["dimension"]
    for item_index, item_id in enumerate(ITEM_ORDER[1:], start=1):
        dimension = index[item_id]["dimension"]
        if dimension != current:
            dimension_ranges.append((start, item_index - 1))
            start = item_index
            current = dimension
    dimension_ranges.append((start, len(ITEM_ORDER) - 1))

    for axis_index, (ax, evaluator_id) in enumerate(
        zip(axes, evaluator_ids, strict=True)
    ):
        prefix = safe_column_name(evaluator_id)
        for group_index, (group_start, group_end) in enumerate(dimension_ranges):
            if group_index % 2 == 0:
                ax.axhspan(
                    group_start - 0.5,
                    group_end + 0.5,
                    color="#F3F5F7",
                    zorder=0,
                )
            ax.axhline(group_end + 0.5, color="#D8DCE2", linewidth=0.8, zorder=1)

        for y, item_id in zip(y_positions, ITEM_ORDER, strict=True):
            row = index[item_id]
            human = float(row[f"{prefix}_human_mean"])
            llm = float(row[f"{prefix}_llm_mean"])
            ax.plot([human, llm], [y, y], color="#AEB4BC", linewidth=1.8, zorder=2)
            ax.scatter(human, y, s=42, color=SOURCE_COLOURS["human"], zorder=3)
            ax.scatter(llm, y, s=42, color=SOURCE_COLOURS["llm"], zorder=3)

        ax.set_title(MODEL_DISPLAY[evaluator_id], fontweight="bold", pad=12)
        ax.set_xlim(0, 1.02)
        ax.set_xticks(np.linspace(0, 1, 6))
        ax.set_xlabel("Mean checklist score")
        ax.grid(axis="x", color="#E4E7EB", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        if axis_index > 0:
            ax.tick_params(axis="y", labelleft=False)

    item_labels = [
        f"{item_id}  {ITEM_SHORT_LABELS[item_id]}" for item_id in ITEM_ORDER
    ]
    axes[0].set_yticks(y_positions, item_labels)
    axes[0].invert_yaxis()
    axes[0].tick_params(axis="y", labelsize=9)
    legend = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=SOURCE_COLOURS["human"],
            markeredgecolor="none",
            markersize=8,
            label="Human review",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=SOURCE_COLOURS["llm"],
            markeredgecolor="none",
            markersize=8,
            label="LLM review",
        ),
    ]
    fig.suptitle(
        "Human and LLM review scores by checklist item and evaluator",
        x=0.035,
        y=0.987,
        ha="left",
        fontweight="bold",
    )
    fig.text(
        0.035,
        0.963,
        "Each panel uses the same 0–1 scale; not_applicable judgements are excluded.",
        fontsize=9,
        color="#555555",
    )
    fig.legend(handles=legend, frameon=False, loc="upper right", ncol=2)
    fig.subplots_adjust(left=0.34, right=0.98, top=0.92, bottom=0.06, wspace=0.08)
    return save_figure(
        fig, figures_dir, "ensemble_item_human_llm_by_evaluator_v0_1"
    )


def plot_dimension_human_llm_by_evaluator(
    test_rows: list[dict[str, Any]],
    evaluator_ids: list[str],
    figures_dir: Path,
) -> list[Path]:
    """Show human/LLM dimension means for each evaluator and the ensemble."""

    panel_order = [*evaluator_ids, "ensemble"]
    metric_order = [metric for metric in METRIC_ORDER if metric != "Overall"]
    index = {(row["evaluator_id"], row["metric"]): row for row in test_rows}
    y_positions = np.arange(len(metric_order))
    fig, axes_grid = plt.subplots(
        2,
        2,
        figsize=(7.2, 8.0),
        sharex=True,
        sharey=True,
    )
    axes = list(axes_grid.flat)

    for axis_index, (ax, evaluator_id) in enumerate(
        zip(axes, panel_order, strict=True)
    ):
        for y, metric in zip(y_positions, metric_order, strict=True):
            row = index[(evaluator_id, metric)]
            human = float(row["human_mean"])
            llm = float(row["llm_mean"])
            gap = float(row["mean_difference_llm_minus_human"])
            significant = float(row["p_value_holm_within_evaluator"]) < 0.05
            if y % 2 == 0:
                ax.axhspan(y - 0.5, y + 0.5, color="#F3F5F7", zorder=0)
            ax.plot([human, llm], [y, y], color="#AEB4BC", linewidth=2, zorder=2)
            ax.scatter(
                human,
                y,
                s=48,
                marker="o",
                color=SOURCE_COLOURS["human"],
                zorder=3,
            )
            ax.scatter(
                llm,
                y,
                s=48,
                marker="D",
                color=SOURCE_COLOURS["llm"],
                zorder=3,
            )
            ax.text(
                1.025,
                y,
                f"{gap:+.3f}{'*' if significant else ''}",
                ha="left",
                va="center",
                fontsize=8,
                color="#333333",
            )
        ax.set_title(
            MODEL_DISPLAY[evaluator_id], fontweight="bold", fontsize=10, pad=9
        )
        ax.set_xlim(0, 1.18)
        ax.set_xticks(np.linspace(0, 1, 6))
        ax.set_xlabel("Mean score", fontsize=9)
        ax.grid(axis="x", color="#E4E7EB", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="both", labelsize=8)
        ax.tick_params(axis="y", length=0)
        if axis_index % 2 == 0:
            ax.set_yticks(y_positions, metric_order)
            ax.tick_params(axis="y", labelleft=True)
        else:
            ax.tick_params(axis="y", labelleft=False)

    axes[0].invert_yaxis()
    legend = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=SOURCE_COLOURS["human"],
            markeredgecolor="none",
            markersize=8,
            label="Human review",
        ),
        Line2D(
            [0],
            [0],
            marker="D",
            color="none",
            markerfacecolor=SOURCE_COLOURS["llm"],
            markeredgecolor="none",
            markersize=8,
            label="LLM review",
        ),
    ]
    fig.suptitle(
        "Human and LLM review scores by dimension and evaluator",
        x=0.06,
        y=0.99,
        ha="left",
        fontweight="bold",
        fontsize=11,
    )
    fig.text(
        0.06,
        0.958,
        "Right labels are LLM minus human; * Holm-adjusted p < 0.05 within each panel.",
        fontsize=8,
        color="#555555",
    )
    fig.legend(
        handles=legend,
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.005),
        ncol=2,
        fontsize=8.5,
    )
    fig.subplots_adjust(
        left=0.20,
        right=0.96,
        top=0.91,
        bottom=0.11,
        wspace=0.18,
        hspace=0.27,
    )
    return save_figure(
        fig, figures_dir, "ensemble_dimension_human_llm_by_evaluator_v0_1"
    )


def plot_overall_robustness(
    test_rows: list[dict[str, Any]], evaluator_ids: list[str], figures_dir: Path
) -> list[Path]:
    order = [*evaluator_ids, "ensemble"]
    overall = {
        row["evaluator_id"]: row for row in test_rows if row["metric"] == "Overall"
    }
    fig, ax = plt.subplots(figsize=(9.4, 5.3))
    y_positions = np.arange(len(order))
    for y, evaluator_id in zip(y_positions, order, strict=True):
        row = overall[evaluator_id]
        gap = float(row["mean_difference_llm_minus_human"])
        low = float(row["mean_difference_bootstrap_ci95_lower"])
        high = float(row["mean_difference_bootstrap_ci95_upper"])
        ax.errorbar(
            gap,
            y,
            xerr=[[gap - low], [high - gap]],
            fmt="o",
            markersize=8 if evaluator_id != "ensemble" else 10,
            linewidth=2,
            capsize=4,
            color=MODEL_COLOURS[evaluator_id],
            zorder=3,
        )
        ax.text(
            high + 0.012,
            y,
            f"{gap:+.3f}  [{low:.3f}, {high:.3f}]",
            va="center",
            ha="left",
            fontsize=9,
            color="#333333",
        )
    ax.axvline(0, color="#727780", linewidth=1.2, linestyle="--")
    ax.set_yticks(y_positions, [MODEL_DISPLAY[item] for item in order])
    ax.invert_yaxis()
    ax.set_xlim(-0.02, 0.48)
    ax.set_xlabel("Mean paired score difference (LLM minus human)")
    ax.grid(axis="x", color="#E4E7EB", linewidth=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.suptitle(
        "Human–LLM score gap is positive across evaluators",
        x=0.08,
        y=0.98,
        ha="left",
        fontweight="bold",
    )
    fig.text(
        0.08,
        0.915,
        "48 paired papers; points are mean gaps and intervals are pair-bootstrap 95% CIs.",
        fontsize=9,
        color="#555555",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.89])
    return save_figure(fig, figures_dir, "ensemble_overall_robustness_v0_1")


def plot_metric_heatmap(
    metric_rows: list[dict[str, Any]], evaluator_ids: list[str], figures_dir: Path
) -> list[Path]:
    order = [*evaluator_ids, "ensemble"]
    index = {row["metric"]: row for row in metric_rows}
    matrix = np.asarray(
        [
            [float(index[metric][f"{safe_column_name(item)}_gap"]) for item in order]
            for metric in METRIC_ORDER
        ]
    )
    limit = max(abs(float(matrix.min())), abs(float(matrix.max())), 0.1)
    fig, ax = plt.subplots(figsize=(8.4, 7.1))
    image = ax.imshow(
        matrix,
        cmap="RdBu_r",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
        aspect="auto",
    )
    for row_index, metric in enumerate(METRIC_ORDER):
        for column_index, evaluator_id in enumerate(order):
            value = matrix[row_index, column_index]
            text_colour = "white" if abs(value) > 0.62 * limit else "#222222"
            marker = ""
            if evaluator_id == "ensemble":
                p_value = float(
                    index[metric][f"{safe_column_name(evaluator_id)}_p_holm"]
                )
                marker = "*" if p_value < 0.05 else ""
            ax.text(
                column_index,
                row_index,
                f"{value:+.3f}{marker}",
                ha="center",
                va="center",
                fontsize=9,
                color=text_colour,
            )
    ax.set_xticks(np.arange(len(order)), [HEATMAP_DISPLAY[item] for item in order])
    ax.set_yticks(np.arange(len(METRIC_ORDER)), METRIC_ORDER)
    ax.tick_params(axis="both", length=0)
    ax.spines[:].set_visible(False)
    colour_bar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.04)
    colour_bar.set_label("Mean difference (LLM minus human)")
    fig.suptitle(
        "Dimension-level effects are robust to evaluator choice",
        x=0.08,
        y=0.985,
        ha="left",
        fontweight="bold",
    )
    fig.text(
        0.08,
        0.94,
        "Positive values favour LLM reviews; * ensemble Holm-adjusted p < 0.05.",
        fontsize=9,
        color="#555555",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.91])
    return save_figure(fig, figures_dir, "ensemble_metric_robustness_v0_1")


def format_p(value: float) -> str:
    return f"{value:.2e}" if value < 0.001 else f"{value:.3f}"


def build_report(
    evaluator_ids: list[str],
    test_rows: list[dict[str, Any]],
    leave_one_out_rows: list[dict[str, Any]],
    pairwise_agreement_rows: list[dict[str, Any]],
    multirater_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
) -> str:
    tests = {(row["evaluator_id"], row["metric"]): row for row in test_rows}
    ensemble = tests[("ensemble", "Overall")]
    overall_multirater = next(
        row
        for row in multirater_rows
        if row["scope_type"] == "overall" and row["scope_value"] == "all"
    )
    overall_pairwise = [
        row
        for row in pairwise_agreement_rows
        if row["scope_type"] == "overall" and row["scope_value"] == "all"
    ]
    lines = [
        "# Three-evaluator ensemble analysis",
        "",
        "## Primary result",
        "",
        (
            f"The equal-weight three-model panel scored human reviews at "
            f"**{float(ensemble['human_mean']):.3f}** and LLM reviews at "
            f"**{float(ensemble['llm_mean']):.3f}**. The mean paired difference was "
            f"**{float(ensemble['mean_difference_llm_minus_human']):+.3f}** "
            f"(pair-bootstrap 95% CI "
            f"[{float(ensemble['mean_difference_bootstrap_ci95_lower']):.3f}, "
            f"{float(ensemble['mean_difference_bootstrap_ci95_upper']):.3f}]). "
            f"LLM reviews scored higher in {ensemble['llm_higher_pairs']}/"
            f"{ensemble['pairs_n']} pairs; two-sided paired Wilcoxon "
            f"p={format_p(float(ensemble['p_value']))}."
        ),
        "",
        "| Evaluator | Human mean | LLM mean | LLM − human | 95% bootstrap CI | LLM higher |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for evaluator_id in [*evaluator_ids, "ensemble"]:
        row = tests[(evaluator_id, "Overall")]
        lines.append(
            f"| {MODEL_DISPLAY[evaluator_id]} | {float(row['human_mean']):.3f} | "
            f"{float(row['llm_mean']):.3f} | "
            f"{float(row['mean_difference_llm_minus_human']):+.3f} | "
            f"[{float(row['mean_difference_bootstrap_ci95_lower']):.3f}, "
            f"{float(row['mean_difference_bootstrap_ci95_upper']):.3f}] | "
            f"{row['llm_higher_pairs']}/{row['pairs_n']} |"
        )
    lines.extend(
        [
            "",
            "## Leave-one-evaluator-out robustness",
            "",
            "| Omitted evaluator | Included models | LLM − human | 95% bootstrap CI | LLM higher |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in leave_one_out_rows:
        omitted = (
            "None (full panel)"
            if row["omitted_evaluator"] == "none"
            else MODEL_DISPLAY[row["omitted_evaluator"]]
        )
        lines.append(
            f"| {omitted} | {row['evaluator_n']} | "
            f"{float(row['mean_difference_llm_minus_human']):+.3f} | "
            f"[{float(row['mean_difference_bootstrap_ci95_lower']):.3f}, "
            f"{float(row['mean_difference_bootstrap_ci95_upper']):.3f}] | "
            f"{row['llm_higher_pairs']}/{row['pairs_n']} |"
        )
    lines.extend(
        [
            "",
            "## Evaluator agreement",
            "",
            (
                f"Across all 2,400 item judgements, all three evaluators gave the same "
                f"label in **{overall_multirater['all_three_unanimous_n']}/"
                f"{overall_multirater['judgement_n']} "
                f"({100 * float(overall_multirater['all_three_unanimous_rate']):.1f}%)** "
                f"cases. Four-label Fleiss' kappa was "
                f"**{float(overall_multirater['fleiss_kappa_4_labels']):.3f}**."
            ),
            "",
            "| Evaluator pair | Exact agreement | Cohen's κ (4 labels) | Linear weighted κ (scorable) |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in overall_pairwise:
        lines.append(
            f"| {MODEL_DISPLAY[row['evaluator_a']]} vs {MODEL_DISPLAY[row['evaluator_b']]} | "
            f"{100 * float(row['exact_agreement_rate']):.1f}% | "
            f"{float(row['cohen_kappa_4_labels']):.3f} | "
            f"{float(row['linear_weighted_kappa_3_labels']):.3f} |"
        )
    sorted_dimensions = sorted(
        [row for row in metric_rows if row["metric"] != "Overall"],
        key=lambda row: float(row["ensemble_gap"]),
        reverse=True,
    )
    significant_dimensions = [
        row["metric"]
        for row in sorted_dimensions
        if float(row["ensemble_p_holm"]) < 0.05
    ]
    lines.extend(
        [
            "",
            "## Dimension-level interpretation",
            "",
            (
                "The largest ensemble gaps were "
                + ", ".join(
                    f"{row['metric']} {float(row['ensemble_gap']):+.3f}"
                    for row in sorted_dimensions[:3]
                )
                + "."
            ),
            (
                "Holm-corrected ensemble differences were significant for "
                + ", ".join(significant_dimensions)
                + "."
            ),
            "",
            "## Analysis rule",
            "",
            (
                "Each evaluator first retains its original yes=1, partial=0.5, no=0 "
                "scoring with not_applicable excluded. The ensemble then averages "
                "evaluator-specific scores at the pair/metric level. For a dimension, "
                "an evaluator contributes only when both reviews in that pair have a "
                "score. This treats the three named evaluator configurations as a fixed "
                "panel; it does not estimate uncertainty over all possible evaluator models."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    if args.bootstrap_reps < 1000:
        raise ValueError("Use at least 1,000 bootstrap replicates.")
    output_dir = resolve_path(args.output_dir)
    figures_dir = resolve_path(args.figures_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    evaluator_ids, answers_by_evaluator, pair_scores_by_evaluator = (
        load_and_validate_inputs(args.evaluators_root)
    )
    item_consensus = build_item_consensus(evaluator_ids, answers_by_evaluator)
    label_distributions = build_label_distributions(
        evaluator_ids, answers_by_evaluator
    )
    pairwise_agreement = build_pairwise_agreement(
        evaluator_ids, answers_by_evaluator
    )
    multirater_agreement = build_multirater_agreement(
        evaluator_ids, answers_by_evaluator
    )
    combined_pair_scores = build_combined_pair_scores(
        evaluator_ids, pair_scores_by_evaluator
    )
    test_rows = build_test_rows(
        combined_pair_scores,
        evaluator_ids,
        bootstrap_reps=args.bootstrap_reps,
        seed=args.seed,
    )
    leave_one_out_rows = build_leave_one_out_rows(
        evaluator_ids,
        pair_scores_by_evaluator,
        bootstrap_reps=args.bootstrap_reps,
        seed=args.seed,
    )
    metric_robustness = build_metric_robustness(test_rows, evaluator_ids)
    item_descriptives = build_item_descriptives(
        evaluator_ids, answers_by_evaluator
    )

    output_paths = {
        "item_consensus": output_dir / "human_llm_ensemble_item_consensus_v0_1.csv",
        "label_distributions": output_dir
        / "human_llm_ensemble_label_distributions_v0_1.csv",
        "pairwise_agreement": output_dir
        / "human_llm_ensemble_pairwise_agreement_v0_1.csv",
        "multirater_agreement": output_dir
        / "human_llm_ensemble_multirater_agreement_v0_1.csv",
        "pair_scores": output_dir / "human_llm_ensemble_pair_scores_v0_1.csv",
        "tests": output_dir / "human_llm_ensemble_tests_v0_1.csv",
        "leave_one_out": output_dir
        / "human_llm_ensemble_leave_one_out_v0_1.csv",
        "metric_robustness": output_dir
        / "human_llm_ensemble_metric_robustness_v0_1.csv",
        "item_descriptives": output_dir
        / "human_llm_ensemble_item_descriptives_v0_1.csv",
        "report": output_dir / "human_llm_ensemble_report_v0_1.md",
        "summary": output_dir / "human_llm_ensemble_summary_v0_1.json",
    }
    write_csv(item_consensus, output_paths["item_consensus"])
    write_csv(label_distributions, output_paths["label_distributions"])
    write_csv(pairwise_agreement, output_paths["pairwise_agreement"])
    write_csv(multirater_agreement, output_paths["multirater_agreement"])
    write_csv(combined_pair_scores, output_paths["pair_scores"])
    write_csv(test_rows, output_paths["tests"])
    write_csv(leave_one_out_rows, output_paths["leave_one_out"])
    write_csv(metric_robustness, output_paths["metric_robustness"])
    write_csv(item_descriptives, output_paths["item_descriptives"])

    figure_paths = [
        *plot_item_human_llm_by_evaluator(
            item_descriptives, evaluator_ids, figures_dir
        ),
        *plot_dimension_human_llm_by_evaluator(
            test_rows, evaluator_ids, figures_dir
        ),
        *plot_overall_robustness(test_rows, evaluator_ids, figures_dir),
        *plot_metric_heatmap(metric_robustness, evaluator_ids, figures_dir),
    ]
    report = build_report(
        evaluator_ids,
        test_rows,
        leave_one_out_rows,
        pairwise_agreement,
        multirater_agreement,
        metric_robustness,
    )
    output_paths["report"].write_text(report, encoding="utf-8")

    test_index = {(row["evaluator_id"], row["metric"]): row for row in test_rows}
    overall_multirater = next(
        row
        for row in multirater_agreement
        if row["scope_type"] == "overall" and row["scope_value"] == "all"
    )
    summary = {
        "analysis_version": "human_llm_ensemble_v0_1",
        "evaluator_ids": evaluator_ids,
        "evaluator_n": len(evaluator_ids),
        "pairs": 48,
        "item_judgements_per_evaluator": 2400,
        "scoring": "yes=1, partial=0.5, no=0; not_applicable excluded",
        "primary_aggregation": (
            "equal-weight mean of evaluator-specific pair/metric scores; an evaluator "
            "contributes only when both human and LLM scores are available"
        ),
        "inference": (
            "two-sided paired Wilcoxon over paper pairs; Holm correction across Overall "
            "+ 9 dimensions within each evaluator/panel; pair-bootstrap percentile 95% CI "
            "for the mean paired difference"
        ),
        "bootstrap_replicates": args.bootstrap_reps,
        "bootstrap_seed": args.seed,
        "primary_overall_result": test_index[("ensemble", "Overall")],
        "leave_one_out_overall": leave_one_out_rows,
        "overall_multirater_agreement": overall_multirater,
        "paths": {
            key: str(path.relative_to(PROJECT_ROOT))
            for key, path in output_paths.items()
        }
        | {
            "figures": [str(path.relative_to(PROJECT_ROOT)) for path in figure_paths]
        },
    }
    output_paths["summary"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
